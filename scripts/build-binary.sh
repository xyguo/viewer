#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
UV_CACHE_DIR="${UV_CACHE_DIR:-$PROJECT_ROOT/.uv-cache}"
export UV_CACHE_DIR

cd "$PROJECT_ROOT"
uv sync --all-groups --locked
uv run --offline pyinstaller --clean --noconfirm book-viewer.spec

echo "Built $PROJECT_ROOT/dist/book-viewer"
