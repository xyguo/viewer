"""Tests for the local standalone executable installer."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

BUILD_SCRIPT = Path(__file__).parents[1] / "scripts" / "build-binary.sh"
INSTALL_SCRIPT = Path(__file__).parents[1] / "scripts" / "install-local.sh"


def _fake_executable(path: Path) -> None:
    path.write_text("#!/bin/sh\necho viewer\n", encoding="utf-8")
    path.chmod(0o755)


def _run_installer(
    tmp_path: Path,
    *arguments: str,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    user_home = tmp_path / "home"
    user_home.mkdir()
    environment = {
        **os.environ,
        "PATH": "/usr/bin:/bin",
        "VIEWER_INSTALL_HOME": str(user_home),
        "VIEWER_INSTALL_SHELL": "/bin/zsh",
    }
    result = subprocess.run(
        [str(INSTALL_SCRIPT), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    return result, user_home


def _installed_paths(user_home: Path) -> tuple[Path, Path]:
    if platform.system() == "Darwin":
        app_root = user_home / "Library" / "Application Support" / "Parallel Book Viewer"
        return app_root / "bin" / "book-viewer", app_root / "config.toml"
    return (
        user_home / ".local" / "share" / "parallel-book-viewer" / "bin" / "book-viewer",
        user_home / ".config" / "parallel-book-viewer" / "config.toml",
    )


def _run_fake_build(
    tmp_path: Path,
    response: str,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    project_root = tmp_path / "project"
    scripts_root = project_root / "scripts"
    scripts_root.mkdir(parents=True)
    (project_root / "books").mkdir()
    shutil.copy2(BUILD_SCRIPT, scripts_root / "build-binary.sh")
    shutil.copy2(INSTALL_SCRIPT, scripts_root / "install-local.sh")

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        """#!/bin/sh
case " $* " in
    *" pyinstaller "*)
        mkdir -p dist
        printf '#!/bin/sh\\necho viewer\\n' > dist/book-viewer
        chmod +x dist/book-viewer
        ;;
esac
""",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)

    user_home = tmp_path / "home"
    user_home.mkdir()
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "VIEWER_INSTALL_HOME": str(user_home),
        "VIEWER_INSTALL_SHELL": "/bin/zsh",
    }
    result = subprocess.run(
        [str(scripts_root / "build-binary.sh")],
        input=response,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    return result, user_home


def test_installer_copies_binary_saves_config_and_sets_up_path(tmp_path: Path) -> None:
    binary = tmp_path / "build" / "book-viewer"
    binary.parent.mkdir()
    _fake_executable(binary)
    books_root = tmp_path / "my books"
    books_root.mkdir()

    result, user_home = _run_installer(
        tmp_path,
        "--binary",
        str(binary),
        "--books-root",
        str(books_root),
        "--yes",
    )

    installed_binary, config_path = _installed_paths(user_home)
    link_path = user_home / ".local" / "bin" / "book-viewer"
    assert result.returncode == 0, result.stderr
    assert installed_binary.read_text(encoding="utf-8") == binary.read_text(encoding="utf-8")
    assert os.access(installed_binary, os.X_OK)
    assert config_path.read_text(encoding="utf-8") == f'books_root = "{books_root}"\n'
    assert link_path.resolve() == installed_binary
    assert str(link_path.parent) in (user_home / ".zprofile").read_text(encoding="utf-8")


def test_installer_can_skip_shell_integration(tmp_path: Path) -> None:
    binary = tmp_path / "book-viewer"
    _fake_executable(binary)
    books_root = tmp_path / "books"
    books_root.mkdir()

    result, user_home = _run_installer(
        tmp_path,
        "--binary",
        str(binary),
        "--books-root",
        str(books_root),
        "--no-link",
    )

    assert result.returncode == 0, result.stderr
    assert not (user_home / ".local" / "bin" / "book-viewer").exists()
    assert not (user_home / ".zprofile").exists()
    assert "Skipped command symlink" in result.stdout


def test_build_script_offers_and_runs_installer(tmp_path: Path) -> None:
    result, user_home = _run_fake_build(tmp_path, "y\nn\n")
    installed_binary, _config_path = _installed_paths(user_home)

    assert result.returncode == 0, result.stderr
    assert "Install the viewer for the current user now?" in result.stdout
    assert installed_binary.is_file()
    assert "Saved book library" in result.stdout


def test_build_script_allows_declining_installation(tmp_path: Path) -> None:
    result, user_home = _run_fake_build(tmp_path, "n\n")
    installed_binary, _config_path = _installed_paths(user_home)

    assert result.returncode == 0, result.stderr
    assert "Installation skipped" in result.stdout
    assert not installed_binary.exists()
