"""Tests for command-line build behavior."""

from __future__ import annotations

from pathlib import Path

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
