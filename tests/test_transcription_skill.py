"""Tests for the reusable PDF transcription script in the project skill."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from pydantic import JsonValue

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / ".agent" / "skills" / "create-viewer-book" / "scripts" / "transcribe_pdf.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("project_skill_transcribe_pdf", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = load_script()
PARSE_PAGES = cast(Callable[[str, int], list[int]], SCRIPT.parse_page_selection)
MAKE_PROMPT = cast(Callable[..., str], SCRIPT.make_prompt)
LOAD_EXTRA_BODY = cast(Callable[[Path | None], dict[str, JsonValue]], SCRIPT.load_extra_body)
STRIP_FENCE = cast(Callable[[str], str], SCRIPT.strip_markdown_fence)


def test_page_selection_supports_ranges_and_deduplicates() -> None:
    assert PARSE_PAGES("1-3, 3, 7, 9-10", 10) == [1, 2, 3, 7, 9, 10]
    assert PARSE_PAGES("all", 3) == [1, 2, 3]


@pytest.mark.parametrize("expression", ["", "0", "3-2", "1,8", "one"])
def test_page_selection_rejects_invalid_input(expression: str) -> None:
    with pytest.raises(ValueError):
        PARSE_PAGES(expression, 7)


def test_prompt_replacement_preserves_latex_braces() -> None:
    prompt = MAKE_PROMPT(
        "{{SOURCE_LANGUAGE}} {{PAGE_NUMBER}}/{{PAGE_COUNT}} {{TEXT_LAYER}} $x_{i}$",
        source_language="Japanese",
        physical_page=2,
        total_pages=9,
        text_layer="first {literal} second",
        text_layer_limit=7,
    )

    assert prompt == "Japanese 2/9 first { $x_{i}$"


def test_extra_body_accepts_provider_extensions(tmp_path: Path) -> None:
    path = tmp_path / "extra.json"
    path.write_text(
        json.dumps({"chat_template_kwargs": {"enable_thinking": False}}),
        encoding="utf-8",
    )

    assert LOAD_EXTRA_BODY(path) == {"chat_template_kwargs": {"enable_thinking": False}}


def test_extra_body_cannot_replace_standard_fields(tmp_path: Path) -> None:
    path = tmp_path / "extra.json"
    path.write_text(json.dumps({"model": "replacement"}), encoding="utf-8")

    with pytest.raises(ValueError, match="cannot override: model"):
        LOAD_EXTRA_BODY(path)


def test_extra_body_must_be_an_object(tmp_path: Path) -> None:
    path = tmp_path / "extra.json"
    path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    with pytest.raises(ValueError, match="must contain a JSON object"):
        LOAD_EXTRA_BODY(path)


def test_outer_markdown_fence_is_removed() -> None:
    assert STRIP_FENCE("```markdown\n# Heading\n```\n") == "# Heading"
    assert STRIP_FENCE("# Heading\n") == "# Heading"
