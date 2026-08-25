"""Command-line entry points for the reusable book viewer."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .builder import build_book
from .credentials import CredentialStoreError, KeyringCredentialStore
from .library import build_book_catalog, build_catalog, validate_library, write_manifest_schema
from .settings import load_server_settings


def create_build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build static data for a segmented book.")
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to a strict per-book JSON manifest",
    )
    parser.add_argument(
        "--default-book",
        help="Optional catalog default; otherwise the first built slug is used",
    )
    return parser


def run_build(argv: Sequence[str] | None = None) -> int:
    args = create_build_parser().parse_args(argv)
    manifest_path: Path = args.manifest
    result = build_book(manifest_path)
    book_catalog_result = build_book_catalog(manifest_path)
    catalog_result = build_catalog(
        manifest_path.resolve().parent.parent,
        default_book=args.default_book,
    )
    book_label = "book" if catalog_result.book_count == 1 else "books"
    segment_label = "aligned segments" if result.has_offline_translation else "segments"
    print(
        f"Built {result.output_path} with {result.segment_count} {segment_label} "
        f"across {result.chapter_count} chapters."
    )
    print(f"Built {book_catalog_result.output_path} with a portable one-book catalog.")
    print(
        f"Built {catalog_result.output_path} with "
        f"{catalog_result.book_count} available {book_label}."
    )
    return 0


def create_validate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate local external books against the current viewer metadata contract."
    )
    parser.add_argument("--books-dir", type=Path, default=Path("books"))
    return parser


def run_validate(argv: Sequence[str] | None = None) -> int:
    args = create_validate_parser().parse_args(argv)
    books_dir: Path = args.books_dir
    books = validate_library(books_dir)
    print(f"Validated {len(books)} external book manifests against the latest schema.")
    return 0


def create_schema_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write the current book manifest JSON Schema.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("schemas/book.schema.json"),
    )
    return parser


def run_schema(argv: Sequence[str] | None = None) -> int:
    args = create_schema_parser().parse_args(argv)
    output_path: Path = args.output
    resolved_output = write_manifest_schema(output_path)
    print(f"Wrote {resolved_output}.")
    return 0


def create_serve_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local parallel book viewer.")
    parser.add_argument(
        "--books-root",
        type=Path,
        help="Book library; temporarily overrides viewer.books_root in config.toml",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open the viewer in the default browser",
    )
    parser.add_argument(
        "--forget-api-key",
        action="store_true",
        help="Remove the live-translation API key from the OS keyring and exit",
    )
    return parser


def run_serve(argv: Sequence[str] | None = None) -> int:
    parser = create_serve_parser()
    args = parser.parse_args(argv)
    if args.forget_api_key:
        try:
            KeyringCredentialStore().delete_api_key()
        except CredentialStoreError as error:
            parser.error(str(error))
        print("Removed the live-translation API key from the operating-system keyring.")
        return 0
    try:
        settings = load_server_settings(
            books_root=args.books_root,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    from .server import run_server

    return run_server(settings, open_browser=not args.no_open)


def build_main() -> None:
    raise SystemExit(run_build())


def validate_main() -> None:
    raise SystemExit(run_validate())


def schema_main() -> None:
    raise SystemExit(run_schema())


def serve_main() -> None:
    raise SystemExit(run_serve())
