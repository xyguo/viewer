"""Tests for the reusable segment translation script in the project skill."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast

import pytest
from pydantic import BaseModel, JsonValue

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    ROOT / ".agent" / "skills" / "create-viewer-book" / "scripts" / ("translate_segments.py")
)


class SegmentLike(Protocol):
    segment_id: str
    text: str


class ProtectedTextLike(Protocol):
    text: str
    values: dict[str, str]


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("project_skill_translate_segments", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = load_script()
CONFIG_MODEL = cast(type[BaseModel], SCRIPT.TranslationConfig)
EXTRACT = cast(Callable[[str], list[SegmentLike]], SCRIPT.extract_segments)
MAKE_BATCHES = cast(
    Callable[[list[SegmentLike], int], list[list[SegmentLike]]], SCRIPT.make_batches
)
PARSE_OUTPUT = cast(Callable[[str, int], list[str]], SCRIPT.parse_numbered_output)
PROTECT = cast(Callable[[str, int], ProtectedTextLike], SCRIPT.protect)
RESTORE = cast(Callable[[str, ProtectedTextLike], str], SCRIPT.restore)
VALIDATE = cast(Callable[[str, str], None], SCRIPT.validate_translation)
RENDER_PROMPT = cast(Callable[..., str], SCRIPT.render_system_prompt)
LOAD_EXTRA_BODY = cast(Callable[[Path | None], dict[str, JsonValue]], SCRIPT.load_extra_body)
LOAD_STRING_MAP = cast(Callable[[Path | None, str], dict[str, str]], SCRIPT.load_string_map)
SAVE_LEDGER = cast(Callable[..., None], SCRIPT.save_ledger)
LOAD_LEDGER = cast(Callable[..., dict[str, str]], SCRIPT.load_ledger)
WRITE_TARGET = cast(Callable[..., None], SCRIPT.write_target)
RUN = cast(Callable[[BaseModel], int], SCRIPT.run)


def config(tmp_path: Path) -> BaseModel:
    return CONFIG_MODEL.model_validate(
        {
            "source": tmp_path / "source.md",
            "target": tmp_path / "target.md",
            "ledger": tmp_path / "translations.json",
            "endpoint": "http://localhost:8080/v1/chat/completions",
            "model": "translator",
            "source_language": "Japanese",
            "target_language": "French",
        }
    )


def test_extract_segments_preserves_order_and_rejects_duplicates() -> None:
    source = (
        '<span class="segment" data-seg="A-1">First.</span>\n'
        '<span class="segment" data-seg="A-2">Second.</span>'
    )

    assert [segment.segment_id for segment in EXTRACT(source)] == ["A-1", "A-2"]
    with pytest.raises(ValueError, match="duplicate"):
        EXTRACT(source + '\n<span class="segment" data-seg="A-1">Again.</span>')


def test_batches_keep_complete_segments() -> None:
    segments = EXTRACT(
        '<span class="segment" data-seg="A-1">1234567890</span>\n'
        '<span class="segment" data-seg="A-2">abcdefghij</span>'
    )

    batches = MAKE_BATCHES(segments, 25)

    assert [[segment.segment_id for segment in batch] for batch in batches] == [
        ["A-1"],
        ["A-2"],
    ]


def test_protected_notation_round_trips_exactly() -> None:
    source = "See $E=mc^2$, [12], and https://example.test."
    protected = PROTECT(source, 1)

    restored = RESTORE(protected.text, protected)

    assert restored == source


def test_numbered_output_removes_protocol_markers() -> None:
    output = "  \n[1] First translation\n[2] Second translation\n[3] ⟦END-BATCH⟧\n"

    assert PARSE_OUTPUT(output, 2) == ["First translation", "Second translation"]

    with pytest.raises(ValueError, match="batch sentinel"):
        PARSE_OUTPUT("[1] First\n[2] Second\n[3] extra", 2)


def test_injected_batch_label_is_rejected() -> None:
    with pytest.raises(ValueError, match="injected batch label"):
        VALIDATE("Source sentence.", "[2] Target sentence.")

    VALIDATE("[42] Source citation.", "[42] Target citation.")


def test_prompt_substitutes_languages_and_glossary() -> None:
    prompt = RENDER_PROMPT(
        "{{SOURCE_LANGUAGE}} to {{TARGET_LANGUAGE}}\n{{GLOSSARY}}",
        source_language="Japanese",
        target_language="French",
        glossary={"定理": "théorème"},
    )

    assert prompt == "Japanese to French\n- 定理: théorème"


def test_extra_body_cannot_replace_standard_fields(tmp_path: Path) -> None:
    path = tmp_path / "extra.json"
    path.write_text(json.dumps({"model": "replacement"}), encoding="utf-8")

    with pytest.raises(ValueError, match="cannot override: model"):
        LOAD_EXTRA_BODY(path)


def test_string_maps_require_nonempty_values(tmp_path: Path) -> None:
    path = tmp_path / "glossary.json"
    path.write_text(json.dumps({"term": ""}), encoding="utf-8")

    with pytest.raises(ValueError, match="must be nonempty"):
        LOAD_STRING_MAP(path, "--glossary-file")


def test_ledger_round_trip_and_fingerprint_guard(tmp_path: Path) -> None:
    run_config = config(tmp_path)
    ledger_path = tmp_path / "translations.json"
    translations = {"A-1": "Traduction."}

    SAVE_LEDGER(
        ledger_path,
        config=run_config,
        digest="source-digest",
        fingerprint="request-fingerprint",
        translations=translations,
    )

    assert (
        LOAD_LEDGER(
            ledger_path,
            digest="source-digest",
            fingerprint="request-fingerprint",
        )
        == translations
    )
    with pytest.raises(ValueError, match="different translation configuration"):
        LOAD_LEDGER(
            ledger_path,
            digest="source-digest",
            fingerprint="changed",
        )


def test_target_preserves_segment_contract_and_translates_latex_text(tmp_path: Path) -> None:
    source = (
        '# <span class="segment" data-seg="A-1">Kapitel</span>\n\n'
        '<span class="segment" data-seg="A-2">Text $x$.</span>\n\n'
        "$$x=1 \\tag{1} \\quad \\text{mit}$$\n"
    )
    target_path = tmp_path / "target.md"

    WRITE_TARGET(
        source=source,
        target_path=target_path,
        translations={"A-1": "Chapter", "A-2": "Text $x$."},
        latex_text_map={"mit": "with"},
    )

    target = target_path.read_text(encoding="utf-8")
    assert [segment.segment_id for segment in EXTRACT(target)] == ["A-1", "A-2"]
    assert "\\tag{1}" in target
    assert "\\text{with}" in target


def test_complete_overrides_run_without_calling_a_provider(tmp_path: Path) -> None:
    source_path = tmp_path / "source.md"
    target_path = tmp_path / "target.md"
    ledger_path = tmp_path / "translations.json"
    overrides_path = tmp_path / "overrides.json"
    source_path.write_text(
        '<span class="segment" data-seg="A-1">原文。</span>\n',
        encoding="utf-8",
    )
    overrides_path.write_text(
        json.dumps({"A-1": "Traduction."}),
        encoding="utf-8",
    )
    run_config = CONFIG_MODEL.model_validate(
        {
            "source": source_path,
            "target": target_path,
            "ledger": ledger_path,
            "endpoint": "http://localhost:8080/v1/chat/completions",
            "model": "translator",
            "source_language": "Japanese",
            "target_language": "French",
            "override_json": overrides_path,
        }
    )

    assert RUN(run_config) == 0
    assert "Traduction." in target_path.read_text(encoding="utf-8")
    assert ledger_path.is_file()
