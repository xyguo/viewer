"""Tests for external book discovery, validation, catalog generation, and schema drift."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from book_viewer.library import (
    build_book_catalog,
    build_catalog,
    create_catalog,
    load_local_book,
    manifest_schema_text,
    validate_library,
)
from book_viewer.models import BOOK_SCHEMA_VERSION


def write_external_book(
    books_dir: Path,
    slug: str,
    *,
    built: bool = True,
    manifest_slug: str | None = None,
) -> Path:
    book_dir = books_dir / slug
    book_dir.mkdir(parents=True)
    (book_dir / "source.md").write_text("Source.", encoding="utf-8")
    (book_dir / "target.md").write_text("Target.", encoding="utf-8")
    manifest_path = book_dir / "book.json"
    manifest_path.write_text(
        json.dumps(
            {
                "$schema": "../../schemas/book.schema.json",
                "schema_version": 2,
                "slug": manifest_slug or slug,
                "title": f"Title {slug}",
                "reader_title": f"Reader {slug}",
                "description": "Description.",
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
        ),
        encoding="utf-8",
    )
    if built:
        (book_dir / "document-data.js").write_text("window.DATA = {};\n", encoding="utf-8")
    return manifest_path


def test_validate_library_discovers_external_books(tmp_path: Path) -> None:
    books_dir = tmp_path / "books"
    first = write_external_book(books_dir, "first-book")
    second = write_external_book(books_dir, "second-book")

    books = validate_library(books_dir)
    assert [book.manifest_path for book in books] == [first.resolve(), second.resolve()]
    assert [book.manifest.slug for book in books] == ["first-book", "second-book"]
    assert validate_library(tmp_path / "missing") == []


def test_local_book_requires_matching_directory_and_markdown(tmp_path: Path) -> None:
    books_dir = tmp_path / "books"
    mismatched = write_external_book(
        books_dir,
        "directory-name",
        manifest_slug="different-name",
    )
    with pytest.raises(ValueError, match="must match directory"):
        load_local_book(mismatched)

    missing_source = write_external_book(books_dir, "missing-source")
    (missing_source.parent / "source.md").unlink()
    with pytest.raises(FileNotFoundError, match="source Markdown"):
        load_local_book(missing_source)


def test_build_catalog_includes_only_built_books(tmp_path: Path) -> None:
    books_dir = tmp_path / "books"
    write_external_book(books_dir, "available-book")
    write_external_book(books_dir, "second-book")
    write_external_book(books_dir, "unbuilt-book", built=False)

    result = build_catalog(books_dir, default_book="available-book")
    output = result.output_path.read_text(encoding="utf-8")
    raw_catalog = output.removeprefix("window.BOOK_VIEWER_CATALOG = ").removesuffix(";\n")
    catalog = json.loads(raw_catalog)
    assert result.book_count == 2
    assert catalog == {
        "schemaVersion": 2,
        "defaultBook": "available-book",
        "books": {
            "available-book": {
                "title": "Title available-book",
                "description": "Description.",
                "sourceLabel": "日本語",
                "targetLabel": "English",
                "dataFile": "books/available-book/document-data.js",
            },
            "second-book": {
                "title": "Title second-book",
                "description": "Description.",
                "sourceLabel": "日本語",
                "targetLabel": "English",
                "dataFile": "books/second-book/document-data.js",
            },
        },
    }

    with pytest.raises(ValueError, match="has not been built"):
        build_catalog(books_dir, default_book="unbuilt-book")


def test_create_catalog_does_not_require_or_write_catalog_file(tmp_path: Path) -> None:
    books_dir = tmp_path / "books"
    write_external_book(books_dir, "available-book")

    catalog = create_catalog(books_dir)

    assert catalog is not None
    assert catalog.default_book == "available-book"
    assert list(catalog.books) == ["available-book"]
    assert not (books_dir / "catalog.js").exists()


def test_build_book_catalog_contains_only_selected_book(tmp_path: Path) -> None:
    books_dir = tmp_path / "books"
    selected = write_external_book(books_dir, "selected-book")
    write_external_book(books_dir, "private-book")

    result = build_book_catalog(selected)
    output = result.output_path.read_text(encoding="utf-8")
    raw_catalog = output.removeprefix("window.BOOK_VIEWER_CATALOG = ").removesuffix(";\n")
    catalog = json.loads(raw_catalog)

    assert result.output_path == selected.parent / "catalog.js"
    assert result.book_count == 1
    assert catalog["defaultBook"] == "selected-book"
    assert list(catalog["books"]) == ["selected-book"]


def test_build_book_catalog_requires_built_data(tmp_path: Path) -> None:
    manifest = write_external_book(tmp_path / "books", "unbuilt-book", built=False)
    with pytest.raises(ValueError, match="has not been built"):
        build_book_catalog(manifest)


def test_build_catalog_requires_a_built_book(tmp_path: Path) -> None:
    books_dir = tmp_path / "books"
    write_external_book(books_dir, "unbuilt-book", built=False)
    with pytest.raises(ValueError, match="No built external books"):
        build_catalog(books_dir)


def test_tracked_book_schema_matches_current_model() -> None:
    viewer_root = Path(__file__).resolve().parents[1]
    schema_path = viewer_root / "schemas" / "book.schema.json"
    assert schema_path.read_text(encoding="utf-8") == manifest_schema_text()
    bootstrap = (viewer_root / "bootstrap.js").read_text(encoding="utf-8")
    assert f"SUPPORTED_BOOK_SCHEMA_VERSION = {BOOK_SCHEMA_VERSION};" in bootstrap
