"""Tests for the tracked project skill and its viewer contract examples."""

from __future__ import annotations

import json
import re
from pathlib import Path

from book_viewer.models import BOOK_SCHEMA_VERSION, BookManifest

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / ".agent" / "skills" / "create-viewer-book"
REFERENCE_LINK_PATTERN = re.compile(r"\]\((references/[^)]+)\)")
JSON_BLOCK_PATTERN = re.compile(r"```json\n(\{.*?\})\n```", re.DOTALL)


def test_project_skill_references_resolve() -> None:
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    references = REFERENCE_LINK_PATTERN.findall(skill_text)

    assert references
    assert all((SKILL_ROOT / reference).is_file() for reference in references)


def test_skill_manifest_example_matches_current_model() -> None:
    contract = (SKILL_ROOT / "references" / "book-contract.md").read_text(encoding="utf-8")
    example = JSON_BLOCK_PATTERN.search(contract)

    assert example is not None
    manifest = BookManifest.model_validate(json.loads(example.group(1)))
    assert manifest.schema_version == BOOK_SCHEMA_VERSION
