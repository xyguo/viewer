"""Tests for the local standalone executable installer."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tomllib
from pathlib import Path

BUILD_SCRIPT = Path(__file__).parents[1] / "scripts" / "build-binary.sh"
INSTALL_SCRIPT = Path(__file__).parents[1] / "scripts" / "install-local.sh"
UNINSTALL_SCRIPT = Path(__file__).parents[1] / "scripts" / "uninstall-local.sh"


def _fake_executable(path: Path) -> None:
    path.write_text("#!/bin/sh\necho viewer\n", encoding="utf-8")
    path.chmod(0o755)


def _test_environment(user_home: Path, path: str) -> dict[str, str]:
    return {
        **os.environ,
        "PATH": path,
        "VIEWER_INSTALL_HOME": str(user_home),
        "VIEWER_INSTALL_SHELL": "/bin/zsh",
        "XDG_CONFIG_HOME": str(user_home / ".config"),
        "XDG_DATA_HOME": str(user_home / ".local" / "share"),
    }


def _run_installer(
    tmp_path: Path,
    *arguments: str,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    user_home = tmp_path / "home"
    user_home.mkdir(exist_ok=True)
    environment = _test_environment(user_home, "/usr/bin:/bin")
    result = subprocess.run(
        [str(INSTALL_SCRIPT), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    return result, user_home


def _application_paths(user_home: Path) -> tuple[Path, Path]:
    if platform.system() == "Darwin":
        app_root = user_home / "Library" / "Application Support" / "Parallel Book Viewer"
        config_path = app_root / "config.toml"
    else:
        app_root = user_home / ".local" / "share" / "parallel-book-viewer"
        config_path = user_home / ".config" / "parallel-book-viewer" / "config.toml"
    return config_path, app_root / "reader-data.sqlite3"


def _installed_binary(user_home: Path) -> Path:
    return user_home / ".local" / "bin" / "book-viewer"


def _run_uninstaller(
    tmp_path: Path,
    *arguments: str,
    response: str = "",
) -> tuple[subprocess.CompletedProcess[str], Path]:
    user_home = tmp_path / "home"
    environment = _test_environment(user_home, "/usr/bin:/bin")
    result = subprocess.run(
        [str(UNINSTALL_SCRIPT), *arguments],
        input=response,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    return result, user_home


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
    environment = _test_environment(user_home, f"{fake_bin}:/usr/bin:/bin")
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

    installed_binary = _installed_binary(user_home)
    config_path, _reader_data_path = _application_paths(user_home)
    assert result.returncode == 0, result.stderr
    assert installed_binary.read_text(encoding="utf-8") == binary.read_text(encoding="utf-8")
    assert os.access(installed_binary, os.X_OK)
    assert not installed_binary.is_symlink()
    assert config_path.read_text(encoding="utf-8") == (
        f'schema_version = 1\n\n[viewer]\nbooks_root = "{books_root}"\n'
    )
    profile = (user_home / ".zprofile").read_text(encoding="utf-8")
    assert "# >>> Parallel Book Viewer >>>" in profile
    assert str(installed_binary.parent) in profile
    assert f"Remembered selected book library: {books_root}" in result.stdout


def test_reinstall_updates_books_root_without_overwriting_other_settings(tmp_path: Path) -> None:
    binary = tmp_path / "book-viewer"
    _fake_executable(binary)
    first_books_root = tmp_path / "first-books"
    second_books_root = tmp_path / "second-books"
    first_books_root.mkdir()
    second_books_root.mkdir()
    first_result, user_home = _run_installer(
        tmp_path,
        "--binary",
        str(binary),
        "--books-root",
        str(first_books_root),
        "--no-path",
    )
    assert first_result.returncode == 0, first_result.stderr
    config_path, _reader_data_path = _application_paths(user_home)
    with config_path.open("a", encoding="utf-8") as config_file:
        config_file.write(
            '\n[translation]\nmodel = "preserved-model"\n'
            'chat_completions_url = "http://localhost:8080/v1/chat/completions"\n'
        )

    second_result, _user_home = _run_installer(
        tmp_path,
        "--binary",
        str(binary),
        "--books-root",
        str(second_books_root),
        "--no-path",
    )

    assert second_result.returncode == 0, second_result.stderr
    with config_path.open("rb") as config_file:
        config = tomllib.load(config_file)
    assert config["viewer"]["books_root"] == str(second_books_root)
    assert config["translation"]["model"] == "preserved-model"


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
        "--no-path",
    )

    assert result.returncode == 0, result.stderr
    assert _installed_binary(user_home).is_file()
    assert not (user_home / ".zprofile").exists()
    assert "Skipped PATH setup" in result.stdout


def test_build_script_offers_and_runs_installer(tmp_path: Path) -> None:
    result, user_home = _run_fake_build(tmp_path, "y\nn\n")
    installed_binary = _installed_binary(user_home)

    assert result.returncode == 0, result.stderr
    assert "Install the viewer for the current user now?" in result.stdout
    assert installed_binary.is_file()
    assert "Remembered selected book library" in result.stdout


def test_build_script_allows_declining_installation(tmp_path: Path) -> None:
    result, user_home = _run_fake_build(tmp_path, "n\n")
    installed_binary = _installed_binary(user_home)

    assert result.returncode == 0, result.stderr
    assert "Installation skipped" in result.stdout
    assert not installed_binary.exists()


def test_uninstaller_preserves_reader_data_and_books_by_default(tmp_path: Path) -> None:
    binary = tmp_path / "book-viewer"
    _fake_executable(binary)
    books_root = tmp_path / "books"
    books_root.mkdir()
    (books_root / "keep.txt").write_text("user book", encoding="utf-8")
    install_result, user_home = _run_installer(
        tmp_path,
        "--binary",
        str(binary),
        "--books-root",
        str(books_root),
        "--yes",
    )
    assert install_result.returncode == 0, install_result.stderr
    config_path, reader_data_path = _application_paths(user_home)
    reader_data_path.parent.mkdir(parents=True, exist_ok=True)
    reader_data_path.write_text("reading state", encoding="utf-8")

    result, _user_home = _run_uninstaller(tmp_path, response="y\nn\n")

    assert result.returncode == 0, result.stderr
    assert not _installed_binary(user_home).exists()
    assert not config_path.exists()
    assert reader_data_path.read_text(encoding="utf-8") == "reading state"
    assert (books_root / "keep.txt").is_file()
    assert "# >>> Parallel Book Viewer >>>" not in (user_home / ".zprofile").read_text(
        encoding="utf-8"
    )
    assert "Preserved saved reader data" in result.stdout
    assert "Removed the stored live-translation API key" in result.stdout
    assert "book library was not removed" in result.stdout


def test_uninstaller_can_purge_reader_data_noninteractively(tmp_path: Path) -> None:
    user_home = tmp_path / "home"
    user_home.mkdir()
    installed_binary = _installed_binary(user_home)
    installed_binary.parent.mkdir(parents=True)
    _fake_executable(installed_binary)
    _config_path, reader_data_path = _application_paths(user_home)
    reader_data_path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(f"{reader_data_path}{suffix}").write_text("data", encoding="utf-8")

    result, _user_home = _run_uninstaller(tmp_path, "--yes", "--purge-data")

    assert result.returncode == 0, result.stderr
    assert not installed_binary.exists()
    for suffix in ("", "-wal", "-shm", "-journal"):
        assert not Path(f"{reader_data_path}{suffix}").exists()
    assert "Deleted saved reader data" in result.stdout
