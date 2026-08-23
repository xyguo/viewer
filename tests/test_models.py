"""Tests for strict book and browser data contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import ValidationError

from book_viewer.models import (
    BookDocumentPayload,
    BookManifest,
    MathJaxManifest,
    TranslationRequest,
)


def valid_manifest_data() -> dict[str, object]:
    return {
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
        schema_version=1,
        title="Example Book",
        reader_title="Example Reader",
        description="A test book.",
        source_language="Japanese",
        source_label="日本語",
        source_html_lang="ja",
        target_language="English",
        target_label="English",
        target_html_lang="en",
        source_html='<span class="segment" data-seg="s1">源</span>',
        target_html='<span class="segment" data-seg="s1">Target</span>',
        segment_count=1,
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
    with pytest.raises(ValidationError, match="Input should be 1"):
        BookManifest.model_validate({**valid_manifest_data(), "schema_version": 2})

    invalid = valid_manifest_data()
    source = dict(cast(dict[str, object], invalid["source"]))
    source["markdown"] = "../outside.md"
    invalid["source"] = source
    with pytest.raises(ValidationError, match="within the book directory"):
        BookManifest.model_validate(invalid)


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
