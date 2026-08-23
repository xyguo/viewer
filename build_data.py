#!/usr/bin/env python3
"""Build the self-contained browser data file from the paired Markdown files."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_JP = BASE_DIR.parent / "proof-of-pcp-jp.md"
DEFAULT_EN = BASE_DIR.parent / "proof-of-pcp-en.md"
DEFAULT_OUTPUT = BASE_DIR / "document-data.js"
ID_RE = re.compile(r'\bid="([^"]+)"')
HREF_RE = re.compile(r'href="#([^"]+)"')
TAG_RE = re.compile(r"\\tag\{([^{}]+)\}")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


class SegmentHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if "segment" not in classes:
            return
        segment_id = (attributes.get("data-seg") or "").strip()
        if not segment_id:
            raise ValueError("A rendered .segment element has a missing or empty data-seg value.")
        self.ids.append(segment_id)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jp", type=Path, default=DEFAULT_JP, help="Japanese Markdown path")
    parser.add_argument("--en", type=Path, default=DEFAULT_EN, help="English Markdown path")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Generated JavaScript path")
    return parser.parse_args()


def rendered_segment_ids(html: str) -> list[str]:
    parser = SegmentHTMLParser()
    parser.feed(html)
    parser.close()
    return parser.ids


def validate_rendered_segments(jp_html: str, en_html: str) -> list[str]:
    jp_ids = rendered_segment_ids(jp_html)
    en_ids = rendered_segment_ids(en_html)
    if not jp_ids:
        raise ValueError("No rendered .segment[data-seg] elements were found in the Japanese document.")
    if len(jp_ids) != len(set(jp_ids)):
        raise ValueError("Duplicate rendered sentence segment IDs were found in the Japanese document.")
    if len(en_ids) != len(set(en_ids)):
        raise ValueError("Duplicate rendered sentence segment IDs were found in the English document.")
    if jp_ids != en_ids:
        limit = min(len(jp_ids), len(en_ids))
        mismatch = next((index for index in range(limit) if jp_ids[index] != en_ids[index]), limit)
        jp_value = jp_ids[mismatch] if mismatch < len(jp_ids) else "(missing)"
        en_value = en_ids[mismatch] if mismatch < len(en_ids) else "(missing)"
        raise ValueError(
            f"Sentence alignment differs at index {mismatch}: Japanese={jp_value}, English={en_value}. "
            f"Counts: Japanese={len(jp_ids)}, English={len(en_ids)}."
        )
    return jp_ids


def validate_markdown_contract(jp_markdown: str, en_markdown: str, document_dir: Path) -> None:
    jp_tags = TAG_RE.findall(jp_markdown)
    en_tags = TAG_RE.findall(en_markdown)
    if jp_tags != en_tags:
        raise ValueError(f"Equation tags differ between editions: Japanese={jp_tags}, English={en_tags}.")
    if len(jp_tags) != len(set(jp_tags)):
        raise ValueError("Duplicate equation tags were found in the paired documents.")

    jp_images = IMAGE_RE.findall(jp_markdown)
    en_images = IMAGE_RE.findall(en_markdown)
    if jp_images != en_images:
        raise ValueError("Figure paths or ordering differ between the Japanese and English documents.")
    for image_path in jp_images:
        if "://" in image_path:
            continue
        resolved = (document_dir / image_path).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Referenced figure does not exist: {resolved}")


def render_markdown(markdown: str) -> str:
    pandoc = shutil.which("pandoc")
    if not pandoc:
        raise RuntimeError("Pandoc is required to rebuild document-data.js. The generated viewer itself has no build dependency.")
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
    html = ID_RE.sub(lambda match: f'id="{prefix}-{match.group(1)}"', html)
    html = HREF_RE.sub(lambda match: f'href="#{prefix}-{match.group(1)}"', html)
    return html


def normalize_asset_paths(html: str) -> str:
    return html.replace('src="viewer/assets/', 'src="assets/')


def build(jp_path: Path, en_path: Path, output_path: Path) -> int:
    jp_markdown = jp_path.read_text(encoding="utf-8")
    en_markdown = en_path.read_text(encoding="utf-8")
    validate_markdown_contract(jp_markdown, en_markdown, jp_path.parent)
    jp_rendered = render_markdown(jp_markdown)
    en_rendered = render_markdown(en_markdown)
    ids = validate_rendered_segments(jp_rendered, en_rendered)

    jp_html = normalize_asset_paths(prefix_html_ids(jp_rendered, "jp"))
    en_html = normalize_asset_paths(prefix_html_ids(en_rendered, "en"))
    payload = {
        "title": "Proof of the PCP Theorem",
        "sourceHtml": jp_html,
        "targetHtml": en_html,
        "segmentCount": len(ids),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
    javascript = "window.PCP_DOCUMENT = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    output_path.write_text(javascript, encoding="utf-8")
    return len(ids)


def main() -> None:
    args = parse_args()
    count = build(args.jp.resolve(), args.en.resolve(), args.output.resolve())
    print(f"Built {args.output} with {count} aligned segments.")


if __name__ == "__main__":
    main()
