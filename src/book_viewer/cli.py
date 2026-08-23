"""Command-line entry points for the reusable book viewer."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .builder import build_book


def create_build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build static data for a translated book.")
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to a strict per-book JSON manifest",
    )
    return parser


def run_build(argv: Sequence[str] | None = None) -> int:
    args = create_build_parser().parse_args(argv)
    manifest_path: Path = args.manifest
    result = build_book(manifest_path)
    print(f"Built {result.output_path} with {result.segment_count} aligned segments.")
    return 0


def build_main() -> None:
    raise SystemExit(run_build())


def serve_main() -> None:
    from .server import run_server

    raise SystemExit(run_server())
