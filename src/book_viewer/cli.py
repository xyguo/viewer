"""Command-line entry points for the reusable book viewer."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .builder import build_book
from .library import build_catalog, validate_library, write_manifest_schema


def create_build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build static data for a translated book.")
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
    catalog_result = build_catalog(
        manifest_path.resolve().parent.parent,
        default_book=args.default_book,
    )
    book_label = "book" if catalog_result.book_count == 1 else "books"
    print(f"Built {result.output_path} with {result.segment_count} aligned segments.")
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


def build_main() -> None:
    raise SystemExit(run_build())


def validate_main() -> None:
    raise SystemExit(run_validate())


def schema_main() -> None:
    raise SystemExit(run_schema())


def serve_main() -> None:
    from .server import run_server

    raise SystemExit(run_server())
