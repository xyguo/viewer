"""Tests for the checksum-verified thin MathJax installer."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from book_viewer.mathjax import (
    ENTRYPOINT_MEMBER,
    EXTENSION_MEMBER_PREFIX,
    FONT_MEMBER_PREFIX,
    LICENSE_MEMBER,
    discover_required_packages,
    install_mathjax_archive,
)


def make_archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return buffer.getvalue()


def minimal_archive() -> bytes:
    return make_archive(
        {
            ENTRYPOINT_MEMBER: b"mathjax",
            LICENSE_MEMBER: b"Apache-2.0",
            f"{FONT_MEMBER_PREFIX}MathJax_Main-Regular.woff": b"font",
            f"{EXTENSION_MEMBER_PREFIX}ams.js": b"preloaded",
            f"{EXTENSION_MEMBER_PREFIX}mathtools.js": b"extension",
            "package/unneeded.txt": b"omit",
        }
    )


def manifest_data(slug: str, packages: list[str]) -> dict[str, object]:
    return {
        "schema_version": 2,
        "slug": slug,
        "title": "Book",
        "reader_title": "Reader",
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
        "mathjax": {"packages": packages, "macros": {}},
    }


def test_installer_extracts_only_required_runtime_files(tmp_path: Path) -> None:
    archive = minimal_archive()
    destination = tmp_path / "vendor" / "mathjax"
    destination.mkdir(parents=True)
    (destination / "old-runtime.js").write_text("stale", encoding="utf-8")
    result = install_mathjax_archive(
        archive,
        destination,
        ["ams", "MathTools"],
        expected_sha512=hashlib.sha512(archive).hexdigest(),
    )

    assert result.destination == destination
    assert result.packages == ("ams", "MathTools")
    assert result.file_count == 5
    assert (destination / "es5" / "tex-chtml.js").read_bytes() == b"mathjax"
    assert (destination / "es5/input/tex/extensions/mathtools.js").is_file()
    assert not (destination / "es5/input/tex/extensions/ams.js").exists()
    assert (destination / "es5/output/chtml/fonts/woff-v2/MathJax_Main-Regular.woff").is_file()
    assert (destination / "LICENSE").is_file()
    assert not (destination / "old-runtime.js").exists()
    assert not (destination / "unneeded.txt").exists()
    metadata = json.loads((destination / "INSTALLATION.json").read_text(encoding="utf-8"))
    assert metadata["version"] == "3.2.2"
    assert metadata["packages"] == ["ams", "MathTools"]


def test_installer_rejects_bad_checksum_and_missing_extension(tmp_path: Path) -> None:
    archive = minimal_archive()
    with pytest.raises(ValueError, match="checksum"):
        install_mathjax_archive(archive, tmp_path / "bad", [], expected_sha512="0" * 128)
    with pytest.raises(ValueError, match="no TeX package"):
        install_mathjax_archive(
            archive,
            tmp_path / "missing",
            ["physics"],
            expected_sha512=hashlib.sha512(archive).hexdigest(),
        )


def test_package_discovery_combines_manifests_and_explicit_packages(tmp_path: Path) -> None:
    books_dir = tmp_path / "books"
    book_dir = books_dir / "example-book"
    book_dir.mkdir(parents=True)
    (book_dir / "book.json").write_text(
        json.dumps(manifest_data("example-book", ["ams", "mathtools"])),
        encoding="utf-8",
    )

    assert discover_required_packages(books_dir, ["physics"]) == (
        "ams",
        "mathtools",
        "physics",
    )
    with pytest.raises(ValueError, match="Invalid MathJax package"):
        discover_required_packages(books_dir, ["../unsafe"])
