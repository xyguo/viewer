"""Tests for command-line build behavior."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest import CaptureFixture, MonkeyPatch

from book_viewer import cli
from book_viewer.models import BuildResult


def test_run_build_uses_selected_manifest(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    manifest_path = tmp_path / "book.json"
    output_path = tmp_path / "document-data.js"
    captured: list[Path] = []

    def fake_build(path: Path) -> BuildResult:
        captured.append(path)
        return BuildResult(output_path=output_path, segment_count=7)

    monkeypatch.setattr(cli, "build_book", fake_build)
    assert cli.run_build(["--manifest", str(manifest_path)]) == 0
    assert captured == [manifest_path]
    assert "7 aligned segments" in capsys.readouterr().out


def test_serve_main_exits_with_server_status(monkeypatch: MonkeyPatch) -> None:
    from book_viewer import server

    def fake_run_server() -> int:
        return 3

    monkeypatch.setattr(server, "run_server", fake_run_server)
    with pytest.raises(SystemExit) as exit_info:
        cli.serve_main()
    assert exit_info.value.code == 3
