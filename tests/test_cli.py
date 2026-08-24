"""Tests for command-line build behavior."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest import CaptureFixture, MonkeyPatch

from book_viewer import cli
from book_viewer.library import LocalBook
from book_viewer.models import BuildResult, CatalogBuildResult


def test_run_build_uses_selected_manifest(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    manifest_path = tmp_path / "books" / "example-book" / "book.json"
    output_path = tmp_path / "document-data.js"
    catalog_path = tmp_path / "books" / "catalog.js"
    captured: list[Path] = []
    catalog_calls: list[tuple[Path, str | None]] = []
    book_catalog_calls: list[Path] = []

    def fake_build(path: Path) -> BuildResult:
        captured.append(path)
        return BuildResult(output_path=output_path, segment_count=7, chapter_count=2)

    def fake_catalog(books_dir: Path, *, default_book: str | None) -> CatalogBuildResult:
        catalog_calls.append((books_dir, default_book))
        return CatalogBuildResult(output_path=catalog_path, book_count=1)

    def fake_book_catalog(path: Path) -> CatalogBuildResult:
        book_catalog_calls.append(path)
        return CatalogBuildResult(output_path=manifest_path.parent / "catalog.js", book_count=1)

    monkeypatch.setattr(cli, "build_book", fake_build)
    monkeypatch.setattr(cli, "build_book_catalog", fake_book_catalog)
    monkeypatch.setattr(cli, "build_catalog", fake_catalog)
    assert cli.run_build(["--manifest", str(manifest_path), "--default-book", "example-book"]) == 0
    assert captured == [manifest_path]
    assert book_catalog_calls == [manifest_path]
    assert catalog_calls == [(manifest_path.parent.parent, "example-book")]
    output = capsys.readouterr().out
    assert "7 aligned segments" in output
    assert "across 2 chapters" in output
    assert "portable one-book catalog" in output
    assert "1 available book." in output


def test_build_command_requires_manifest() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.run_build([])
    assert exit_info.value.code == 2


def test_serve_main_exits_with_server_status(monkeypatch: MonkeyPatch) -> None:
    from book_viewer import server

    def fake_run_server() -> int:
        return 3

    monkeypatch.setattr(server, "run_server", fake_run_server)
    with pytest.raises(SystemExit) as exit_info:
        cli.serve_main()
    assert exit_info.value.code == 3


def test_validate_and_schema_commands(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    books_dir = tmp_path / "books"

    def fake_validate(_path: Path) -> list[LocalBook]:
        return []

    def fake_schema(path: Path) -> Path:
        return path.resolve()

    monkeypatch.setattr(cli, "validate_library", fake_validate)
    assert cli.run_validate(["--books-dir", str(books_dir)]) == 0
    assert "Validated 0 external book" in capsys.readouterr().out

    schema_path = tmp_path / "schema.json"
    monkeypatch.setattr(cli, "write_manifest_schema", fake_schema)
    assert cli.run_schema(["--output", str(schema_path)]) == 0
    assert str(schema_path) in capsys.readouterr().out
