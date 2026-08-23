"""Unit tests for manifest-driven static document generation."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from book_viewer import builder


def segment_html(segment_id: str, text: str, *, heading_id: str = "chapter") -> str:
    return (
        f'<h1 id="{heading_id}"><span class="segment" '
        f'data-seg="{segment_id}">{text}</span></h1>'
        f'<a href="#{heading_id}">Back</a>'
        '<img src="source-assets/figure.png">'
    )


def write_test_book(tmp_path: Path) -> Path:
    source_path = tmp_path / "source.md"
    target_path = tmp_path / "target.md"
    source_path.write_text('<span data-seg="s1">源。</span>', encoding="utf-8")
    target_path.write_text('<span data-seg="s1">Target.</span>', encoding="utf-8")
    manifest_path = tmp_path / "book.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": "example-book",
                "title": "Example Book",
                "reader_title": "Example Reader",
                "description": "A test book.",
                "source": {
                    "language": "Japanese",
                    "label": "日本語",
                    "html_lang": "ja",
                    "markdown": "source.md",
                    "html_id_prefix": "source",
                },
                "target": {
                    "language": "English",
                    "label": "English",
                    "html_lang": "en",
                    "markdown": "target.md",
                    "html_id_prefix": "target",
                },
                "asset_rewrites": {"source-assets/": "books/example-book/assets/"},
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_build_book_generates_validated_browser_data(tmp_path: Path) -> None:
    manifest_path = write_test_book(tmp_path)

    def renderer(markdown: str) -> str:
        text = "源" if "源" in markdown else "Target"
        return segment_html("s1", text)

    timestamp = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
    result = builder.build_book(manifest_path, renderer=renderer, generated_at=timestamp)

    assert result.segment_count == 1
    output = result.output_path.read_text(encoding="utf-8")
    assert output.startswith("window.BOOK_VIEWER_DOCUMENT = ")
    raw_payload = output.removeprefix("window.BOOK_VIEWER_DOCUMENT = ").removesuffix(";\n")
    payload = json.loads(raw_payload)
    assert payload["slug"] == "example-book"
    assert payload["schemaVersion"] == 1
    assert payload["generatedAt"] == "2026-08-23T12:00:00Z"
    assert 'id="source-chapter"' in payload["sourceHtml"]
    assert 'href="#target-chapter"' in payload["targetHtml"]
    assert 'src="books/example-book/assets/figure.png"' in payload["sourceHtml"]


def test_build_book_rejects_naive_timestamp(tmp_path: Path) -> None:
    manifest_path = write_test_book(tmp_path)

    def renderer(markdown: str) -> str:
        return segment_html("s1", markdown)

    with pytest.raises(ValueError, match="timezone"):
        builder.build_book(
            manifest_path,
            renderer=renderer,
            generated_at=datetime(2026, 8, 23),  # noqa: DTZ001 -- deliberately naive
        )


def test_rendered_segments_reject_duplicates_and_mismatches() -> None:
    duplicate = segment_html("s1", "One") + segment_html("s1", "Again")
    with pytest.raises(ValueError, match="Duplicate"):
        builder.validate_rendered_segments(duplicate, duplicate)

    with pytest.raises(ValueError, match="alignment differs"):
        builder.validate_rendered_segments(segment_html("s1", "One"), segment_html("s2", "Two"))

    with pytest.raises(ValueError, match="No rendered"):
        builder.validate_rendered_segments("<p>none</p>", "<p>none</p>")


def test_segment_parser_rejects_missing_identifier() -> None:
    with pytest.raises(ValueError, match="missing data-seg"):
        builder.rendered_segment_ids('<span class="segment">Missing</span>')


def test_markdown_contract_checks_equations_and_figures(tmp_path: Path) -> None:
    image = tmp_path / "figure.png"
    image.write_bytes(b"test")
    valid = "Text. $$x = 1 \\tag{1}$$\n![Figure](figure.png)"
    builder.validate_markdown_contract(valid, valid, tmp_path, tmp_path)

    with pytest.raises(ValueError, match="Equation tags differ"):
        builder.validate_markdown_contract(valid, valid.replace("{1}", "{2}"), tmp_path, tmp_path)
    with pytest.raises(ValueError, match="Duplicate equation"):
        duplicated = valid + " $$y = 2 \\tag{1}$$"
        builder.validate_markdown_contract(duplicated, duplicated, tmp_path, tmp_path)
    with pytest.raises(ValueError, match="Figure paths"):
        builder.validate_markdown_contract(
            valid, valid.replace("figure.png", "https://x.test/f.png"), tmp_path, tmp_path
        )
    with pytest.raises(FileNotFoundError, match="does not exist"):
        builder.validate_markdown_contract(
            valid.replace("figure.png", "missing.png"),
            valid.replace("figure.png", "missing.png"),
            tmp_path,
            tmp_path,
        )


def test_render_markdown_requires_pandoc(monkeypatch: MonkeyPatch) -> None:
    def missing_executable(_name: str) -> None:
        return None

    monkeypatch.setattr(builder.shutil, "which", missing_executable)
    with pytest.raises(RuntimeError, match="Pandoc is required"):
        builder.render_markdown("Text")


def test_render_markdown_reports_pandoc_failure(monkeypatch: MonkeyPatch) -> None:
    def pandoc_executable(_name: str) -> str:
        return "/usr/bin/pandoc"

    monkeypatch.setattr(builder.shutil, "which", pandoc_executable)

    def failed_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["pandoc"], returncode=1, stdout="", stderr="bad input")

    monkeypatch.setattr(builder.subprocess, "run", failed_run)
    with pytest.raises(RuntimeError, match="bad input"):
        builder.render_markdown("Text")
