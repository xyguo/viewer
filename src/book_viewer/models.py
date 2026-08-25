"""Strict data contracts shared by the builder, server, and browser payload."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BOOK_SCHEMA_VERSION = 2
BOOK_SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class StrictModel(BaseModel):
    """Base model that rejects coercion and unknown configuration keys."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )


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

    @field_validator("markdown")
    @classmethod
    def require_book_local_markdown(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("markdown must stay within the book directory")
        if path.suffix.lower() not in {".md", ".markdown"}:
            raise ValueError("markdown must reference a Markdown file")
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

    schema_uri: str | None = Field(default=None, alias="$schema")
    schema_version: Literal[2]
    slug: str = Field(pattern=BOOK_SLUG_PATTERN)
    title: str = Field(min_length=1, max_length=300)
    reader_title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    source: EditionManifest
    target: EditionManifest | None = None
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

    def target_path(self, manifest_path: Path) -> Path | None:
        if self.target is None:
            return None
        return (manifest_path.parent / self.target.markdown).resolve()

    def output_path(self, manifest_path: Path) -> Path:
        return (manifest_path.parent / self.data_file).resolve()


class BrowserModel(StrictModel):
    """Strict camel-case contract serialized for the browser."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )


class ReadingState(BrowserModel):
    """Latest resumable reading activity for one book."""

    book_slug: str = Field(pattern=BOOK_SLUG_PATTERN)
    chapter_id: str | None = Field(default=None, min_length=1, max_length=500)
    segment_id: str | None = Field(default=None, min_length=1, max_length=500)
    progress_percent: int = Field(default=0, ge=0, le=100)
    source_scroll_top: float | None = Field(default=None, ge=0)
    target_scroll_top: float | None = Field(default=None, ge=0)
    last_opened_at: int = Field(default=0, ge=0)
    updated_at: int = Field(ge=0)

    @field_validator("chapter_id", "segment_id")
    @classmethod
    def reject_untrimmed_location_ids(cls, value: str | None) -> str | None:
        if value is not None and value != value.strip():
            raise ValueError("location IDs must not have surrounding whitespace")
        return value


class ReadingStateUpdate(BrowserModel):
    """Validated partial reading-state update sent by the browser."""

    book_slug: str = Field(pattern=BOOK_SLUG_PATTERN)
    chapter_id: str | None = Field(default=None, min_length=1, max_length=500)
    segment_id: str | None = Field(default=None, min_length=1, max_length=500)
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    source_scroll_top: float | None = Field(default=None, ge=0)
    target_scroll_top: float | None = Field(default=None, ge=0)
    last_opened_at: int | None = Field(default=None, ge=0)
    updated_at: int = Field(ge=0)

    @field_validator("chapter_id", "segment_id")
    @classmethod
    def reject_untrimmed_location_ids(cls, value: str | None) -> str | None:
        if value is not None and value != value.strip():
            raise ValueError("location IDs must not have surrounding whitespace")
        return value

    @model_validator(mode="after")
    def require_state_change(self) -> Self:
        changed_fields = self.model_fields_set - {"book_slug", "updated_at"}
        if not changed_fields or all(getattr(self, field) is None for field in changed_fields):
            raise ValueError("a reading-state update must contain at least one value")
        return self


class ReadingStateCollection(BrowserModel):
    """All reading states stored for the local reader."""

    states: list[ReadingState]


class BookChapter(BrowserModel):
    """Metadata for one independently loadable source or bilingual chapter."""

    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    source_title: str = Field(min_length=1, max_length=300)
    target_title: str | None = Field(default=None, min_length=1, max_length=300)
    source_data_file: str = Field(min_length=1)
    target_data_file: str | None = Field(default=None, min_length=1)
    segment_ids: list[str] = Field(min_length=1)

    @field_validator("segment_ids")
    @classmethod
    def require_unique_segment_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("chapter segment IDs must be unique")
        if any(not value or value != value.strip() for value in values):
            raise ValueError("chapter segment IDs must be non-empty and trimmed")
        return values

    @model_validator(mode="after")
    def require_complete_target_metadata(self) -> Self:
        if (self.target_title is None) != (self.target_data_file is None):
            raise ValueError(
                "target title and data file must either both be present or both be absent"
            )
        return self


class TocEntry(BrowserModel):
    """One full-book table-of-contents link."""

    segment_id: str = Field(min_length=1)
    chapter_id: str = Field(min_length=1)
    level: int = Field(ge=1, le=3)
    title: str = Field(min_length=1, max_length=500)


class BookDocumentPayload(BrowserModel):
    """Metadata serialized separately from lazily loaded chapter HTML."""

    schema_version: Literal[2]
    slug: str
    title: str
    reader_title: str
    description: str
    source_language: str
    source_label: str
    source_html_lang: str
    has_offline_translation: bool = True
    target_language: str | None = None
    target_label: str | None = None
    target_html_lang: str | None = None
    segment_count: int = Field(ge=1)
    initial_chapter_id: str
    chapters: list[BookChapter] = Field(min_length=1)
    toc: list[TocEntry] = Field(min_length=1)
    generated_at: datetime
    mathjax: MathJaxManifest

    @model_validator(mode="after")
    def validate_chapter_index(self) -> BookDocumentPayload:
        target_metadata = (self.target_language, self.target_label, self.target_html_lang)
        if self.has_offline_translation:
            if any(value is None for value in target_metadata):
                raise ValueError("offline translations require complete target metadata")
            if any(chapter.target_data_file is None for chapter in self.chapters):
                raise ValueError("offline translations require target data for every chapter")
        elif any(value is not None for value in target_metadata) or any(
            chapter.target_data_file is not None for chapter in self.chapters
        ):
            raise ValueError("source-only books must not declare offline target metadata")

        chapter_ids = [chapter.id for chapter in self.chapters]
        if len(chapter_ids) != len(set(chapter_ids)):
            raise ValueError("chapter IDs must be unique")
        if self.initial_chapter_id not in chapter_ids:
            raise ValueError("initial_chapter_id must reference a chapter")

        segment_ids = [
            segment_id for chapter in self.chapters for segment_id in chapter.segment_ids
        ]
        if len(segment_ids) != self.segment_count:
            raise ValueError("segment_count must equal the chapter segment total")
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("segment IDs must be unique across chapters")

        segment_chapters = {
            segment_id: chapter.id
            for chapter in self.chapters
            for segment_id in chapter.segment_ids
        }
        if any(segment_chapters.get(entry.segment_id) != entry.chapter_id for entry in self.toc):
            raise ValueError("TOC entries must reference matching chapter segments")
        return self


class BookChunkPayload(BrowserModel):
    """One language edition of one independently loadable chapter."""

    schema_version: Literal[2]
    slug: str
    chapter_id: str
    language: Literal["source", "target"]
    html: str = Field(min_length=1)


class BuildResult(StrictModel):
    """Summary returned by a successful book build."""

    output_path: Path
    segment_count: int = Field(ge=1)
    chapter_count: int = Field(ge=1)
    has_offline_translation: bool = True


class CatalogEntry(BrowserModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, min_length=1, max_length=500)
    source_label: str | None = Field(default=None, min_length=1, max_length=80)
    target_label: str | None = Field(default=None, min_length=1, max_length=80)
    data_file: str = Field(min_length=1)


class BookCatalog(BrowserModel):
    schema_version: Literal[2]
    default_book: str = Field(pattern=BOOK_SLUG_PATTERN)
    books: dict[str, CatalogEntry] = Field(min_length=1)


class CatalogBuildResult(StrictModel):
    output_path: Path
    book_count: int = Field(ge=1)


MAX_SENTENCE_CHARS = 4_000
MAX_CONTEXT_ITEMS = 4
MAX_LANGUAGE_CHARS = 80
LiveTargetLanguage = Literal[
    "Chinese",
    "English",
    "French",
    "Japanese",
    "Spanish",
    "German",
    "Portuguese",
    "Italian",
]
SUPPORTED_LIVE_TARGET_LANGUAGES: tuple[LiveTargetLanguage, ...] = (
    "Chinese",
    "English",
    "French",
    "Japanese",
    "Spanish",
    "German",
    "Portuguese",
    "Italian",
)


def _normalized_text(value: str) -> str:
    return " ".join(value.split()).strip()


class TranslationRequest(StrictModel):
    """Validated browser request for translating one selected sentence."""

    sentence: str = Field(min_length=1, max_length=MAX_SENTENCE_CHARS)
    before: list[str] = Field(default_factory=list, max_length=MAX_CONTEXT_ITEMS)
    after: list[str] = Field(default_factory=list, max_length=MAX_CONTEXT_ITEMS)
    source_language: str = Field(min_length=1, max_length=MAX_LANGUAGE_CHARS)
    target_language: LiveTargetLanguage

    @field_validator("sentence", "source_language")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = _normalized_text(value)
        if not normalized:
            raise ValueError("must not be empty or whitespace")
        return normalized

    @field_validator("before", "after")
    @classmethod
    def normalize_context(cls, values: list[str]) -> list[str]:
        normalized = [_normalized_text(value) for value in values]
        if any(not value for value in normalized):
            raise ValueError("context items must not be empty or whitespace")
        if any(len(value) > MAX_SENTENCE_CHARS for value in normalized):
            raise ValueError(f"context items must contain at most {MAX_SENTENCE_CHARS} characters")
        return normalized


class TranslationResponse(StrictModel):
    translation: str = Field(min_length=1)


class ErrorResponse(StrictModel):
    error: str = Field(min_length=1)


class ChatMessage(StrictModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatCompletionRequest(StrictModel):
    model: str = Field(min_length=1)
    messages: list[ChatMessage] = Field(min_length=2)
    temperature: float = Field(default=0.0, ge=0, le=2)
    max_tokens: int = Field(default=900, ge=1)
    stream: Literal[False] = False


class UpstreamModel(BaseModel):
    """Strict known fields while allowing provider-specific response metadata."""

    model_config = ConfigDict(extra="ignore", strict=True)


class ChatCompletionChoice(UpstreamModel):
    message: ChatMessage


class ChatCompletionResponse(UpstreamModel):
    choices: list[ChatCompletionChoice] = Field(min_length=1)


class UpstreamErrorDetail(UpstreamModel):
    message: str = Field(min_length=1)


class UpstreamErrorResponse(UpstreamModel):
    error: UpstreamErrorDetail
