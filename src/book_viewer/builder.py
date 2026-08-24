"""Render a paired book manifest into validated static browser data."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Literal

from .models import (
    BOOK_SCHEMA_VERSION,
    BookChapter,
    BookChunkPayload,
    BookDocumentPayload,
    BookManifest,
    BuildResult,
    TocEntry,
)
from .syntax_highlighting import highlight_code_blocks

ID_RE = re.compile(r'\bid="([^"]+)"')
HREF_RE = re.compile(r'href="#([^"]+)"')
TAG_RE = re.compile(r"\\tag\{([^{}]+)\}")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
CHAPTER_START_RE = re.compile(r"(?=<h1\b)", re.IGNORECASE)
DOCUMENT_VARIABLE = "window.BOOK_VIEWER_DOCUMENT"
CHUNKS_VARIABLE = "window.BOOK_VIEWER_CHUNKS"

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


@dataclass(frozen=True, slots=True)
class ParsedHeading:
    level: int
    segment_id: str
    title: str


class HeadingHTMLParser(HTMLParser):
    """Collect visible heading labels and their sentence segment identifiers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headings: list[ParsedHeading] = []
        self._tag: str | None = None
        self._level: int | None = None
        self._segment_id: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h1", "h2", "h3"} and self._tag is None:
            self._tag = tag
            self._level = int(tag[1])
            self._segment_id = None
            self._text = []
            return
        if self._tag is None or self._segment_id is not None:
            return
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if "segment" in classes:
            self._segment_id = (attributes.get("data-seg") or "").strip() or None

    def handle_data(self, data: str) -> None:
        if self._tag is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != self._tag:
            return
        title = " ".join("".join(self._text).split())
        if self._level is not None and self._segment_id and title:
            self.headings.append(
                ParsedHeading(
                    level=self._level,
                    segment_id=self._segment_id,
                    title=title,
                )
            )
        self._tag = None
        self._level = None
        self._segment_id = None
        self._text = []


def load_manifest(manifest_path: Path) -> BookManifest:
    """Load a strict book manifest from JSON."""

    return BookManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def rendered_segment_ids(html: str) -> list[str]:
    parser = SegmentHTMLParser()
    parser.feed(html)
    parser.close()
    return parser.ids


def rendered_headings(html: str) -> list[ParsedHeading]:
    parser = HeadingHTMLParser()
    parser.feed(html)
    parser.close()
    return parser.headings


def split_rendered_chapters(html: str) -> list[str]:
    """Split rendered HTML at top-level chapter headings."""

    starts = [match.start() for match in CHAPTER_START_RE.finditer(html)]
    if not starts:
        return [html.strip()]

    preamble = html[: starts[0]].strip()
    boundaries = [*starts, len(html)]
    chapters = [
        html[boundaries[index] : boundaries[index + 1]].strip() for index in range(len(starts))
    ]
    if preamble:
        chapters[0] = f"{preamble}\n{chapters[0]}"
    return [chapter for chapter in chapters if chapter]


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
    return highlight_code_blocks(process.stdout.strip())


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


def chunk_key(slug: str, chapter_id: str, language: str) -> str:
    return f"{slug}:{chapter_id}:{language}"


def serialize_chunk(payload: BookChunkPayload) -> str:
    data = payload.model_dump(mode="json", by_alias=True)
    key = chunk_key(payload.slug, payload.chapter_id, payload.language)
    serialized_key = json.dumps(key, ensure_ascii=False)
    serialized_data = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return (
        f"{CHUNKS_VARIABLE} = {CHUNKS_VARIABLE} || {{}};"
        f"{CHUNKS_VARIABLE}[{serialized_key}] = {serialized_data};\n"
    )


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

    source_chapters = split_rendered_chapters(source_html)
    target_chapters = split_rendered_chapters(target_html)
    if len(source_chapters) != len(target_chapters):
        raise ValueError(
            "Chapter boundaries differ between editions: "
            f"source={len(source_chapters)}, target={len(target_chapters)}."
        )

    timestamp = generated_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("generated_at must include timezone information")

    chunk_dir = output_path.parent / f"{output_path.stem}-chunks"
    relative_chunk_dir = chunk_dir.relative_to(resolved_manifest_path.parent)
    browser_chunk_dir = PurePosixPath("books", manifest.slug, *relative_chunk_dir.parts)
    chapters: list[BookChapter] = []
    segment_to_chapter: dict[str, str] = {}
    chunk_outputs: dict[str, str] = {}

    for index, (source_chapter, target_chapter) in enumerate(
        zip(source_chapters, target_chapters, strict=True),
        start=1,
    ):
        chapter_segment_ids = validate_rendered_segments(source_chapter, target_chapter)
        chapter_id = chapter_segment_ids[0]
        source_headings = rendered_headings(source_chapter)
        target_headings = rendered_headings(target_chapter)
        source_title = source_headings[0].title if source_headings else chapter_id
        target_title = target_headings[0].title if target_headings else chapter_id
        source_name = f"{index:03d}-source.js"
        target_name = f"{index:03d}-target.js"

        chunk_specs: tuple[
            tuple[Literal["source", "target"], str, str],
            tuple[Literal["source", "target"], str, str],
        ] = (
            ("source", source_name, source_chapter),
            ("target", target_name, target_chapter),
        )
        for language, name, chapter_html in chunk_specs:
            chunk_payload = BookChunkPayload(
                schema_version=BOOK_SCHEMA_VERSION,
                slug=manifest.slug,
                chapter_id=chapter_id,
                language=language,
                html=chapter_html,
            )
            chunk_outputs[name] = serialize_chunk(chunk_payload)

        for segment_id in chapter_segment_ids:
            segment_to_chapter[segment_id] = chapter_id
        chapters.append(
            BookChapter(
                id=chapter_id,
                source_title=source_title,
                target_title=target_title,
                source_data_file=(browser_chunk_dir / source_name).as_posix(),
                target_data_file=(browser_chunk_dir / target_name).as_posix(),
                segment_ids=chapter_segment_ids,
            )
        )

    toc = [
        TocEntry(
            segment_id=heading.segment_id,
            chapter_id=segment_to_chapter[heading.segment_id],
            level=heading.level,
            title=heading.title,
        )
        for heading in rendered_headings(source_html)
    ]

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
        segment_count=len(segment_ids),
        initial_chapter_id=chapters[0].id,
        chapters=chapters,
        toc=toc,
        generated_at=timestamp,
        mathjax=manifest.mathjax,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    for name, content in chunk_outputs.items():
        (chunk_dir / name).write_text(content, encoding="utf-8")
    for stale_path in chunk_dir.glob("*.js"):
        if stale_path.name not in chunk_outputs:
            stale_path.unlink()
    output_path.write_text(serialize_document(payload), encoding="utf-8")
    return BuildResult(
        output_path=output_path,
        segment_count=len(segment_ids),
        chapter_count=len(chapters),
    )
