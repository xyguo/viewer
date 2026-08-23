"""Tests for strict book and browser data contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import ValidationError

from book_viewer.models import (
    SUPPORTED_LIVE_TARGET_LANGUAGES,
    BookChapter,
    BookChunkPayload,
    BookDocumentPayload,
    BookManifest,
    LiveTargetLanguage,
    MathJaxManifest,
    TocEntry,
    TranslationRequest,
)


def valid_manifest_data() -> dict[str, object]:
    return {
        "schema_version": 2,
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
    }


def test_manifest_rejects_unknown_fields_and_type_coercion() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BookManifest.model_validate({**valid_manifest_data(), "unknown": True})

    invalid = valid_manifest_data()
    invalid["title"] = 42
    with pytest.raises(ValidationError, match="valid string"):
        BookManifest.model_validate(invalid)


@pytest.mark.parametrize("data_file", ["../outside.js", "/tmp/data.js", "data.json"])
def test_manifest_requires_safe_javascript_output(data_file: str) -> None:
    with pytest.raises(ValidationError, match="data_file"):
        BookManifest.model_validate({**valid_manifest_data(), "data_file": data_file})


def test_mathjax_manifest_rejects_duplicate_packages_and_invalid_macros() -> None:
    with pytest.raises(ValidationError, match="unique"):
        MathJaxManifest(packages=["ams", "ams"])
    with pytest.raises(ValidationError, match="ASCII letters"):
        MathJaxManifest(macros={"bad-name": "x"})


def test_document_payload_uses_camel_case_and_strict_counts() -> None:
    payload = BookDocumentPayload(
        slug="example-book",
        schema_version=2,
        title="Example Book",
        reader_title="Example Reader",
        description="A test book.",
        source_language="Japanese",
        source_label="日本語",
        source_html_lang="ja",
        target_language="English",
        target_label="English",
        target_html_lang="en",
        segment_count=1,
        initial_chapter_id="s1",
        chapters=[
            BookChapter(
                id="s1",
                source_title="源",
                target_title="Target",
                source_data_file="books/example-book/document-data-chunks/001-source.js",
                target_data_file="books/example-book/document-data-chunks/001-target.js",
                segment_ids=["s1"],
            )
        ],
        toc=[TocEntry(segment_id="s1", chapter_id="s1", level=1, title="源")],
        generated_at=datetime(2026, 1, 2, tzinfo=UTC),
        mathjax=MathJaxManifest(),
    )
    dumped = payload.model_dump(mode="json", by_alias=True)
    assert dumped["readerTitle"] == "Example Reader"
    assert dumped["segmentCount"] == 1

    invalid = {**dumped, "segmentCount": "1"}
    with pytest.raises(ValidationError, match="valid integer"):
        BookDocumentPayload.model_validate(invalid)


def test_manifest_rejects_incompatible_schema_and_external_markdown_paths() -> None:
    with pytest.raises(ValidationError, match="Input should be 2"):
        BookManifest.model_validate({**valid_manifest_data(), "schema_version": 1})

    invalid = valid_manifest_data()
    source = dict(cast(dict[str, object], invalid["source"]))
    source["markdown"] = "../outside.md"
    invalid["source"] = source
    with pytest.raises(ValidationError, match="within the book directory"):
        BookManifest.model_validate(invalid)


def test_document_payload_rejects_inconsistent_chapters_and_chunk_types() -> None:
    chapter = BookChapter(
        id="chapter-1",
        source_title="Source",
        target_title="Target",
        source_data_file="source.js",
        target_data_file="target.js",
        segment_ids=["s1"],
    )
    common: dict[str, object] = {
        "schema_version": 2,
        "slug": "example-book",
        "title": "Example Book",
        "reader_title": "Example Reader",
        "description": "A test book.",
        "source_language": "Japanese",
        "source_label": "日本語",
        "source_html_lang": "ja",
        "target_language": "English",
        "target_label": "English",
        "target_html_lang": "en",
        "segment_count": 1,
        "initial_chapter_id": "chapter-1",
        "chapters": [chapter],
        "toc": [
            TocEntry(
                segment_id="s1",
                chapter_id="wrong-chapter",
                level=1,
                title="Source",
            )
        ],
        "generated_at": datetime(2026, 1, 2, tzinfo=UTC),
        "mathjax": MathJaxManifest(),
    }
    with pytest.raises(ValidationError, match="TOC entries"):
        BookDocumentPayload.model_validate(common)

    chunk = BookChunkPayload(
        schema_version=2,
        slug="example-book",
        chapter_id="chapter-1",
        language="source",
        html='<p><span class="segment" data-seg="s1">Source.</span></p>',
    )
    assert chunk.model_dump(by_alias=True)["chapterId"] == "chapter-1"


def test_translation_request_normalizes_text_and_rejects_loose_input() -> None:
    request = TranslationRequest(
        sentence="  A   sentence. ",
        before=[" Previous.  "],
        after=[],
        source_language=" Japanese ",
        target_language="English",
    )
    assert request.sentence == "A sentence."
    assert request.before == ["Previous."]
    assert request.source_language == "Japanese"

    with pytest.raises(ValidationError, match="Extra inputs"):
        TranslationRequest.model_validate(
            {
                **request.model_dump(),
                "unexpected": True,
            }
        )
    with pytest.raises(ValidationError, match="valid list"):
        TranslationRequest.model_validate({**request.model_dump(), "before": "Previous."})
    with pytest.raises(ValidationError, match="at most 4 items"):
        TranslationRequest.model_validate({**request.model_dump(), "after": ["x"] * 5})
    with pytest.raises(ValidationError, match="must not be empty"):
        TranslationRequest.model_validate({**request.model_dump(), "sentence": "   "})


@pytest.mark.parametrize("target_language", SUPPORTED_LIVE_TARGET_LANGUAGES)
def test_translation_request_accepts_supported_live_target_languages(
    target_language: LiveTargetLanguage,
) -> None:
    request = TranslationRequest(
        sentence="Translate me.",
        source_language="English",
        target_language=target_language,
    )
    assert request.target_language == target_language


def test_translation_request_rejects_unsupported_live_target_language() -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        TranslationRequest.model_validate(
            {
                "sentence": "Translate me.",
                "source_language": "English",
                "target_language": "Klingon",
            }
        )
