"""Render a paired book manifest into validated static browser data."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

from .models import BOOK_SCHEMA_VERSION, BookDocumentPayload, BookManifest, BuildResult

ID_RE = re.compile(r'\bid="([^"]+)"')
HREF_RE = re.compile(r'href="#([^"]+)"')
TAG_RE = re.compile(r"\\tag\{([^{}]+)\}")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
DOCUMENT_VARIABLE = "window.BOOK_VIEWER_DOCUMENT"

MarkdownRenderer = Callable[[str], str]


class SegmentHTMLParser(HTMLParser):
    """Collect sentence segment identifiers from rendered HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del tag
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if "segment" not in classes:
            return
        segment_id = (attributes.get("data-seg") or "").strip()
        if not segment_id:
            raise ValueError("A rendered .segment element has a missing data-seg value.")
        self.ids.append(segment_id)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def load_manifest(manifest_path: Path) -> BookManifest:
    """Load a strict book manifest from JSON."""

    return BookManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def rendered_segment_ids(html: str) -> list[str]:
    parser = SegmentHTMLParser()
    parser.feed(html)
    parser.close()
    return parser.ids


def validate_rendered_segments(source_html: str, target_html: str) -> list[str]:
    source_ids = rendered_segment_ids(source_html)
    target_ids = rendered_segment_ids(target_html)
    if not source_ids:
        raise ValueError(
            "No rendered .segment[data-seg] elements were found in the source document."
        )
    if len(source_ids) != len(set(source_ids)):
        raise ValueError(
            "Duplicate rendered sentence segment IDs were found in the source document."
        )
    if len(target_ids) != len(set(target_ids)):
        raise ValueError(
            "Duplicate rendered sentence segment IDs were found in the target document."
        )
    if source_ids != target_ids:
        limit = min(len(source_ids), len(target_ids))
        mismatch = next(
            (index for index in range(limit) if source_ids[index] != target_ids[index]),
            limit,
        )
        source_value = source_ids[mismatch] if mismatch < len(source_ids) else "(missing)"
        target_value = target_ids[mismatch] if mismatch < len(target_ids) else "(missing)"
        raise ValueError(
            f"Sentence alignment differs at index {mismatch}: "
            f"source={source_value}, target={target_value}. "
            f"Counts: source={len(source_ids)}, target={len(target_ids)}."
        )
    return source_ids


def _validate_local_images(
    markdown: str,
    document_dir: Path,
    *,
    static_root: Path | None,
    asset_rewrites: dict[str, str],
) -> list[str]:
    image_paths = IMAGE_RE.findall(markdown)
    for image_path in image_paths:
        if "://" in image_path:
            continue
        resolved = (document_dir / image_path).resolve()
        if resolved.is_file():
            continue
        if static_root is not None:
            for source_prefix, target_prefix in asset_rewrites.items():
                if image_path.startswith(source_prefix):
                    relative_target = target_prefix + image_path.removeprefix(source_prefix)
                    if (static_root / relative_target).resolve().is_file():
                        break
            else:
                raise FileNotFoundError(f"Referenced figure does not exist: {resolved}")
            continue
        raise FileNotFoundError(f"Referenced figure does not exist: {resolved}")
    return image_paths


def validate_markdown_contract(
    source_markdown: str,
    target_markdown: str,
    source_dir: Path,
    target_dir: Path,
    *,
    static_root: Path | None = None,
    asset_rewrites: dict[str, str] | None = None,
) -> None:
    """Validate structural invariants that must match across both editions."""

    source_tags = TAG_RE.findall(source_markdown)
    target_tags = TAG_RE.findall(target_markdown)
    if source_tags != target_tags:
        raise ValueError(
            f"Equation tags differ between editions: source={source_tags}, target={target_tags}."
        )
    if len(source_tags) != len(set(source_tags)):
        raise ValueError("Duplicate equation tags were found in the paired documents.")

    rewrites = asset_rewrites or {}
    source_images = _validate_local_images(
        source_markdown,
        source_dir,
        static_root=static_root,
        asset_rewrites=rewrites,
    )
    target_images = _validate_local_images(
        target_markdown,
        target_dir,
        static_root=static_root,
        asset_rewrites=rewrites,
    )
    if source_images != target_images:
        raise ValueError("Figure paths or ordering differ between the source and target documents.")


def render_markdown(markdown: str) -> str:
    """Render the controlled Markdown dialect with Pandoc."""

    pandoc = shutil.which("pandoc")
    if pandoc is None:
        raise RuntimeError(
            "Pandoc is required to rebuild book data. The generated viewer has no build dependency."
        )
    process = subprocess.run(
        [
            pandoc,
            "--from=gfm+tex_math_dollars+raw_html",
            "--to=html5",
            "--wrap=none",
            "--mathjax",
        ],
        input=markdown,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode:
        raise RuntimeError(f"Pandoc failed: {process.stderr.strip()}")
    return process.stdout.strip()


def prefix_html_ids(html: str, prefix: str) -> str:
    """Prevent duplicate heading IDs when both editions share one page."""

    prefixed = ID_RE.sub(lambda match: f'id="{prefix}-{match.group(1)}"', html)
    return HREF_RE.sub(lambda match: f'href="#{prefix}-{match.group(1)}"', prefixed)


def rewrite_asset_paths(html: str, rewrites: dict[str, str]) -> str:
    """Map book-source asset prefixes to their static viewer locations."""

    rewritten = html
    for source, target in rewrites.items():
        rewritten = rewritten.replace(f'src="{source}', f'src="{target}')
    return rewritten


def serialize_document(payload: BookDocumentPayload) -> str:
    """Serialize a validated document payload as a static browser script."""

    data = payload.model_dump(mode="json", by_alias=True)
    return f"{DOCUMENT_VARIABLE} = {json.dumps(data, ensure_ascii=False, separators=(',', ':'))};\n"


def build_book(
    manifest_path: Path,
    *,
    renderer: MarkdownRenderer = render_markdown,
    generated_at: datetime | None = None,
) -> BuildResult:
    """Build one book from its manifest and sentence-aligned Markdown editions."""

    resolved_manifest_path = manifest_path.resolve()
    manifest = load_manifest(resolved_manifest_path)
    source_path = manifest.source_path(resolved_manifest_path)
    target_path = manifest.target_path(resolved_manifest_path)
    output_path = manifest.output_path(resolved_manifest_path)
    books_dir = resolved_manifest_path.parent.parent
    static_root = books_dir.parent if books_dir.name == "books" else resolved_manifest_path.parent

    source_markdown = source_path.read_text(encoding="utf-8")
    target_markdown = target_path.read_text(encoding="utf-8")
    validate_markdown_contract(
        source_markdown,
        target_markdown,
        source_path.parent,
        target_path.parent,
        static_root=static_root,
        asset_rewrites=manifest.asset_rewrites,
    )

    source_rendered = renderer(source_markdown)
    target_rendered = renderer(target_markdown)
    segment_ids = validate_rendered_segments(source_rendered, target_rendered)
    source_html = rewrite_asset_paths(
        prefix_html_ids(source_rendered, manifest.source.html_id_prefix),
        manifest.asset_rewrites,
    )
    target_html = rewrite_asset_paths(
        prefix_html_ids(target_rendered, manifest.target.html_id_prefix),
        manifest.asset_rewrites,
    )

    timestamp = generated_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("generated_at must include timezone information")
    payload = BookDocumentPayload(
        schema_version=BOOK_SCHEMA_VERSION,
        slug=manifest.slug,
        title=manifest.title,
        reader_title=manifest.reader_title,
        description=manifest.description,
        source_language=manifest.source.language,
        source_label=manifest.source.label,
        source_html_lang=manifest.source.html_lang,
        target_language=manifest.target.language,
        target_label=manifest.target.label,
        target_html_lang=manifest.target.html_lang,
        source_html=source_html,
        target_html=target_html,
        segment_count=len(segment_ids),
        generated_at=timestamp,
        mathjax=manifest.mathjax,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialize_document(payload), encoding="utf-8")
    return BuildResult(output_path=output_path, segment_count=len(segment_ids))
