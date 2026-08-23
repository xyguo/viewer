"""Strict data contracts shared by the builder, server, and browser payload."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class StrictModel(BaseModel):
    """Base model that rejects coercion and unknown configuration keys."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class EditionManifest(StrictModel):
    """Book-specific metadata for one language edition."""

    language: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=80)
    html_lang: str = Field(pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
    markdown: str = Field(min_length=1)
    html_id_prefix: str = Field(pattern=r"^[a-z][a-z0-9-]*$")

    @field_validator("language", "label", "html_lang", "markdown", "html_id_prefix")
    @classmethod
    def reject_surrounding_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("must not have surrounding whitespace")
        return value


class MathJaxManifest(StrictModel):
    """Optional per-book MathJax extensions and macros."""

    packages: list[str] = Field(default_factory=list)
    macros: dict[str, str] = Field(default_factory=dict)

    @field_validator("packages")
    @classmethod
    def validate_packages(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("MathJax packages must be unique")
        if any(not value or value != value.strip() for value in values):
            raise ValueError("MathJax package names must be non-empty and trimmed")
        return values

    @field_validator("macros")
    @classmethod
    def validate_macros(cls, values: dict[str, str]) -> dict[str, str]:
        macro_name = re.compile(r"^[A-Za-z]+$")
        if any(not macro_name.fullmatch(name) for name in values):
            raise ValueError("MathJax macro names must contain only ASCII letters")
        if any(not replacement for replacement in values.values()):
            raise ValueError("MathJax macro replacements must not be empty")
        return values


class BookManifest(StrictModel):
    """Book-specific inputs and reader presentation metadata."""

    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=300)
    reader_title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    source: EditionManifest
    target: EditionManifest
    data_file: str = Field(default="document-data.js", min_length=1)
    asset_rewrites: dict[str, str] = Field(default_factory=dict)
    mathjax: MathJaxManifest = Field(default_factory=MathJaxManifest)

    @field_validator("slug", "title", "reader_title", "description", "data_file")
    @classmethod
    def reject_surrounding_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("must not have surrounding whitespace")
        return value

    @field_validator("data_file")
    @classmethod
    def require_local_data_filename(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("data_file must stay within the book directory")
        if path.suffix != ".js":
            raise ValueError("data_file must be a JavaScript file")
        return value

    @field_validator("asset_rewrites")
    @classmethod
    def validate_asset_rewrites(cls, values: dict[str, str]) -> dict[str, str]:
        if any(not source or not target for source, target in values.items()):
            raise ValueError("asset rewrite prefixes must not be empty")
        return values

    def source_path(self, manifest_path: Path) -> Path:
        return (manifest_path.parent / self.source.markdown).resolve()

    def target_path(self, manifest_path: Path) -> Path:
        return (manifest_path.parent / self.target.markdown).resolve()

    def output_path(self, manifest_path: Path) -> Path:
        return (manifest_path.parent / self.data_file).resolve()


class BookDocumentPayload(StrictModel):
    """Validated data serialized for the generic browser application."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )

    slug: str
    title: str
    reader_title: str
    description: str
    source_language: str
    source_label: str
    source_html_lang: str
    target_language: str
    target_label: str
    target_html_lang: str
    source_html: str
    target_html: str
    segment_count: int = Field(ge=1)
    generated_at: datetime
    mathjax: MathJaxManifest


class BuildResult(StrictModel):
    """Summary returned by a successful book build."""

    output_path: Path
    segment_count: int = Field(ge=1)
