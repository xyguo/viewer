#!/bin/sh
set -eu

UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}"
export UV_CACHE_DIR

uv sync --all-groups --locked
uv run --offline ruff format --check src tests .agent/skills/create-viewer-book/scripts
uv run --offline ruff check src tests .agent/skills/create-viewer-book/scripts
uv run --offline pyright
uv run --offline pytest
uv run --offline book-viewer-validate --books-dir books
