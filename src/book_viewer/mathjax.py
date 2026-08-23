"""Install the minimal browser-side MathJax runtime used by local books."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import json
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import TracebackType
from typing import Protocol, Self, cast

from .library import discover_manifest_paths
from .models import BookManifest

MATHJAX_VERSION = "3.2.2"
MATHJAX_ARCHIVE_URL = f"https://registry.npmjs.org/mathjax/-/mathjax-{MATHJAX_VERSION}.tgz"
MATHJAX_ARCHIVE_SHA512 = (
    "06df9249553c7811b6ef30a155ec0e89c62ced7b1db78d2a9b8f94a47c97ee4d3"
    "f3bd36588f73ec7bee4d7f144b0fb2328f64626fb5164cd6f3be81e5b43a11b"
)
DOWNLOAD_TIMEOUT_SECONDS = 120.0
PACKAGE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
ENTRYPOINT_MEMBER = "package/es5/tex-chtml.js"
LICENSE_MEMBER = "package/LICENSE"
FONT_MEMBER_PREFIX = "package/es5/output/chtml/fonts/woff-v2/"
EXTENSION_MEMBER_PREFIX = "package/es5/input/tex/extensions/"
PRELOADED_TEX_PACKAGES = frozenset(
    {"ams", "autoload", "configmacros", "newcommand", "noundefined", "require"}
)


class ArchiveResponse(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def read(self) -> bytes: ...


class ArchiveOpener(Protocol):
    def __call__(
        self,
        request: urllib.request.Request,
        *,
        timeout: float,
    ) -> ArchiveResponse: ...


@dataclass(frozen=True, slots=True)
class MathJaxInstallResult:
    destination: Path
    packages: tuple[str, ...]
    file_count: int
    size_bytes: int


def discover_required_packages(
    books_dir: Path,
    extra_packages: Sequence[str] = (),
) -> tuple[str, ...]:
    """Collect valid TeX extension names from manifests and explicit additions."""

    packages = set(extra_packages)
    for manifest_path in discover_manifest_paths(books_dir.resolve()):
        manifest = BookManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        packages.update(manifest.mathjax.packages)
    invalid = sorted(package for package in packages if not PACKAGE_NAME_RE.fullmatch(package))
    if invalid:
        raise ValueError(f"Invalid MathJax package names: {invalid}.")
    return tuple(sorted(packages, key=str.casefold))


def download_mathjax_archive(
    *,
    opener: ArchiveOpener | None = None,
) -> bytes:
    """Download the pinned upstream archive without requiring Node.js."""

    request = urllib.request.Request(
        MATHJAX_ARCHIVE_URL,
        headers={"User-Agent": "parallel-book-viewer-mathjax-installer"},
    )
    resolved_opener = opener or cast(ArchiveOpener, urllib.request.urlopen)
    try:
        with resolved_opener(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            return response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError("Could not download the pinned MathJax archive.") from error


def install_mathjax_archive(
    archive_bytes: bytes,
    destination: Path,
    packages: Sequence[str],
    *,
    expected_sha512: str = MATHJAX_ARCHIVE_SHA512,
) -> MathJaxInstallResult:
    """Verify and extract only the files needed by the viewer."""

    actual_sha512 = hashlib.sha512(archive_bytes).hexdigest()
    if not hmac.compare_digest(actual_sha512, expected_sha512):
        raise ValueError("The downloaded MathJax archive failed checksum verification.")

    resolved_destination = destination.resolve()
    if resolved_destination == resolved_destination.parent:
        raise ValueError("MathJax destination must not be a filesystem root.")
    resolved_destination.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        selected_members = _select_archive_members(archive, packages)
        with tempfile.TemporaryDirectory(
            prefix=".mathjax-install-",
            dir=resolved_destination.parent,
        ) as temporary_directory:
            staging_root = Path(temporary_directory) / "mathjax"
            staging_root.mkdir()
            for member in selected_members:
                _write_member(archive, member, staging_root)

            metadata = {
                "version": MATHJAX_VERSION,
                "packages": list(packages),
                "archive_sha512": actual_sha512,
            }
            (staging_root / "INSTALLATION.json").write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            if resolved_destination.exists():
                if not resolved_destination.is_dir():
                    raise ValueError("MathJax destination exists and is not a directory.")
                previous_root = Path(temporary_directory) / "previous"
                resolved_destination.replace(previous_root)
                try:
                    staging_root.replace(resolved_destination)
                except BaseException:
                    previous_root.replace(resolved_destination)
                    raise
            else:
                staging_root.replace(resolved_destination)

    installed_files = [path for path in resolved_destination.rglob("*") if path.is_file()]
    return MathJaxInstallResult(
        destination=resolved_destination,
        packages=tuple(packages),
        file_count=len(installed_files),
        size_bytes=sum(path.stat().st_size for path in installed_files),
    )


def _select_archive_members(
    archive: tarfile.TarFile,
    packages: Sequence[str],
) -> list[tarfile.TarInfo]:
    file_members = {member.name: member for member in archive.getmembers() if member.isfile()}
    required_names = {ENTRYPOINT_MEMBER, LICENSE_MEMBER}
    required_names.update(name for name in file_members if name.startswith(FONT_MEMBER_PREFIX))
    if ENTRYPOINT_MEMBER not in file_members or LICENSE_MEMBER not in file_members:
        raise ValueError("The MathJax archive is missing its entry point or license.")
    if not any(name.startswith(FONT_MEMBER_PREFIX) for name in required_names):
        raise ValueError("The MathJax archive contains no CommonHTML webfonts.")

    extension_members = {
        PurePosixPath(name).stem.casefold(): name
        for name in file_members
        if name.startswith(EXTENSION_MEMBER_PREFIX) and name.endswith(".js")
    }
    for package in packages:
        if not PACKAGE_NAME_RE.fullmatch(package):
            raise ValueError(f"Invalid MathJax package name: {package}.")
        if package.casefold() in PRELOADED_TEX_PACKAGES:
            continue
        extension_name = extension_members.get(package.casefold())
        if extension_name is None:
            raise ValueError(f"MathJax {MATHJAX_VERSION} has no TeX package '{package}'.")
        required_names.add(extension_name)
    return [file_members[name] for name in sorted(required_names)]


def _write_member(archive: tarfile.TarFile, member: tarfile.TarInfo, root: Path) -> None:
    member_path = PurePosixPath(member.name)
    if not member_path.parts or member_path.parts[0] != "package":
        raise ValueError(f"Unexpected MathJax archive path: {member.name}.")
    relative_path = Path(*member_path.parts[1:])
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    source = archive.extractfile(member)
    if source is None:
        raise ValueError(f"Could not read MathJax archive member: {member.name}.")
    with source, target.open("wb") as output:
        shutil.copyfileobj(source, output)


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install a checksum-verified thin MathJax runtime for offline reading."
    )
    parser.add_argument("--books-dir", type=Path, default=Path("books"))
    parser.add_argument("--destination", type=Path, default=Path("vendor/mathjax"))
    parser.add_argument(
        "--package",
        action="append",
        default=[],
        help="Additional MathJax TeX package to install; may be repeated",
    )
    args = parser.parse_args(argv)
    books_dir: Path = args.books_dir
    destination: Path = args.destination
    extra_packages: list[str] = args.package
    packages = discover_required_packages(books_dir, extra_packages)
    result = install_mathjax_archive(download_mathjax_archive(), destination, packages)
    size_mebibytes = result.size_bytes / (1024 * 1024)
    print(
        f"Installed MathJax {MATHJAX_VERSION} to {result.destination} "
        f"({result.file_count} files, {size_mebibytes:.2f} MiB)."
    )
    return 0


def main() -> None:
    raise SystemExit(run())
