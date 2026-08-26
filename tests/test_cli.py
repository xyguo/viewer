"""Tests for command-line build behavior."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest
from pytest import CaptureFixture, MonkeyPatch

from book_viewer import cli
from book_viewer.library import LocalBook
from book_viewer.models import BuildResult, CatalogBuildResult
from book_viewer.settings import ServerSettings


@pytest.mark.parametrize(
    ("has_offline_translation", "segment_label"),
    [(True, "7 aligned segments"), (False, "7 segments")],
)
def test_run_build_uses_selected_manifest(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    *,
    has_offline_translation: bool,
    segment_label: str,
) -> None:
    manifest_path = tmp_path / "books" / "example-book" / "book.json"
    output_path = tmp_path / "document-data.js"
    catalog_path = tmp_path / "books" / "catalog.js"
    captured: list[Path] = []
    catalog_calls: list[tuple[Path, str | None]] = []
    book_catalog_calls: list[Path] = []

    def fake_build(path: Path) -> BuildResult:
        captured.append(path)
        return BuildResult(
            output_path=output_path,
            segment_count=7,
            chapter_count=2,
            has_offline_translation=has_offline_translation,
        )

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
    assert segment_label in output
    assert "across 2 chapters" in output
    assert "portable one-book catalog" in output
    assert "1 available book." in output


def test_build_command_requires_manifest() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.run_build([])
    assert exit_info.value.code == 2


def test_uv_serve_entrypoint_opens_browser_by_default(monkeypatch: MonkeyPatch) -> None:
    from book_viewer import server

    def fake_run_server(_settings: object, *, open_browser: bool) -> int:
        assert open_browser is True
        return 3

    def fake_load_server_settings(*, books_root: Path | None = None) -> ServerSettings:
        assert books_root is None
        return ServerSettings()

    monkeypatch.setattr(cli, "load_server_settings", fake_load_server_settings)
    monkeypatch.setattr(server, "run_server", fake_run_server)
    monkeypatch.setattr("sys.argv", ["book-viewer-serve"])
    with pytest.raises(SystemExit) as exit_info:
        cli.serve_main()
    assert exit_info.value.code == 3


def test_standalone_entrypoint_uses_the_same_serve_cli(monkeypatch: MonkeyPatch) -> None:
    calls = 0

    def fake_serve_main() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(cli, "serve_main", fake_serve_main)
    runpy.run_module("book_viewer", run_name="__main__")

    assert calls == 1


def test_run_serve_passes_command_line_options(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    from book_viewer import server

    books_root = tmp_path / "library"

    def fake_run_server(settings: ServerSettings, *, open_browser: bool) -> int:
        assert settings.books_root == books_root
        assert open_browser is False
        return 0

    def fake_load_server_settings(*, books_root: Path | None = None) -> ServerSettings:
        assert books_root is not None
        return ServerSettings(books_root=books_root)

    monkeypatch.setattr(cli, "load_server_settings", fake_load_server_settings)
    monkeypatch.setattr(server, "run_server", fake_run_server)
    assert cli.run_serve(["--books-root", str(books_root), "--no-open"]) == 0


def test_run_serve_has_no_public_config_path_option(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.run_serve(["--config", str(tmp_path / "missing.toml")])
    assert exit_info.value.code == 2


def test_run_serve_can_remove_the_keyring_secret_and_exit(monkeypatch: MonkeyPatch) -> None:
    deleted = False

    class FakeCredentials:
        def delete_api_key(self) -> None:
            nonlocal deleted
            deleted = True

    monkeypatch.setattr(cli, "KeyringCredentialStore", FakeCredentials)

    assert cli.run_serve(["--forget-api-key"]) == 0
    assert deleted is True


def test_run_serve_can_save_the_installer_books_root(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.toml"
    books_root = tmp_path / "books"
    updates: list[dict[str, str | None]] = []

    class FakeSettingsStore:
        def __init__(self, path: Path) -> None:
            assert path == config_path

        def update(self, values: dict[str, str | None]) -> None:
            updates.append(values)

    monkeypatch.setattr(cli, "default_config_path", lambda: config_path)
    monkeypatch.setattr(cli, "ConfigSettingsStore", FakeSettingsStore)

    assert cli.run_serve(["--installer-books-root", str(books_root)]) == 0
    assert updates == [{"viewer.books_root": str(books_root.resolve())}]


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
