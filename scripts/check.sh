#!/bin/sh
set -eu

UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}"
export UV_CACHE_DIR

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Development quality gate requires '$1' on PATH." >&2
    exit 1
  fi
}

require_command biome
require_command tsc

biome ci app.js bootstrap.js preferences.js settings.js
tsc --project jsconfig.json
uv sync --all-groups --locked
uv run --offline ruff format --check src tests .agent/skills/create-viewer-book/scripts
uv run --offline ruff check src tests .agent/skills/create-viewer-book/scripts
uv run --offline pyright
uv run --offline pytest
uv run --offline book-viewer-validate --books-dir books
