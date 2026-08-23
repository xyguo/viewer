"""Manage external book directories and their generated browser catalog."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .models import (
    BOOK_SCHEMA_VERSION,
    BookCatalog,
    BookManifest,
    CatalogBuildResult,
    CatalogEntry,
)

CATALOG_VARIABLE = "window.BOOK_VIEWER_CATALOG"


@dataclass(frozen=True, slots=True)
class LocalBook:
    manifest_path: Path
    manifest: BookManifest


def discover_manifest_paths(books_dir: Path) -> list[Path]:
    """Find external book manifests in deterministic slug order."""

    if not books_dir.is_dir():
        return []
    return sorted(
        path
        for path in books_dir.glob("*/book.json")
        if path.parent.name and not path.parent.name.startswith(".")
    )


def load_local_book(manifest_path: Path) -> LocalBook:
    """Validate one manifest and the local source files it declares."""

    resolved_path = manifest_path.resolve()
    manifest = BookManifest.model_validate_json(resolved_path.read_text(encoding="utf-8"))
    if resolved_path.parent.name != manifest.slug:
        raise ValueError(
            f"Book slug '{manifest.slug}' must match directory '{resolved_path.parent.name}'."
        )
    for edition_name, markdown_path in (
        ("source", manifest.source_path(resolved_path)),
        ("target", manifest.target_path(resolved_path)),
    ):
        if not markdown_path.is_file():
            raise FileNotFoundError(
                f"The {edition_name} Markdown file does not exist: {markdown_path}"
            )
    return LocalBook(manifest_path=resolved_path, manifest=manifest)


def validate_library(books_dir: Path) -> list[LocalBook]:
    """Validate every external book against the latest manifest model."""

    return [load_local_book(path) for path in discover_manifest_paths(books_dir.resolve())]


def serialize_catalog(catalog: BookCatalog) -> str:
    data = catalog.model_dump(mode="json", by_alias=True)
    return f"{CATALOG_VARIABLE} = {json.dumps(data, ensure_ascii=False, separators=(',', ':'))};\n"


def build_catalog(
    books_dir: Path,
    *,
    default_book: str | None = None,
) -> CatalogBuildResult:
    """Generate the runtime catalog from locally available, built books."""

    resolved_books_dir = books_dir.resolve()
    local_books = validate_library(resolved_books_dir)
    entries: dict[str, CatalogEntry] = {}
    for local_book in local_books:
        manifest = local_book.manifest
        if not manifest.output_path(local_book.manifest_path).is_file():
            continue
        browser_path = PurePosixPath("books", manifest.slug, manifest.data_file).as_posix()
        entries[manifest.slug] = CatalogEntry(title=manifest.title, data_file=browser_path)

    if not entries:
        raise ValueError("No built external books were found for the browser catalog.")
    selected_default = default_book or next(iter(entries))
    if selected_default not in entries:
        raise ValueError(f"Default book '{selected_default}' has not been built.")

    catalog = BookCatalog(
        schema_version=BOOK_SCHEMA_VERSION,
        default_book=selected_default,
        books=entries,
    )
    output_path = resolved_books_dir / "catalog.js"
    output_path.write_text(serialize_catalog(catalog), encoding="utf-8")
    return CatalogBuildResult(output_path=output_path, book_count=len(entries))


def manifest_schema_text() -> str:
    """Return the canonical JSON Schema for the latest book manifest."""

    schema = BookManifest.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_manifest_schema(output_path: Path) -> Path:
    resolved_output = output_path.resolve()
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(manifest_schema_text(), encoding="utf-8")
    return resolved_output
