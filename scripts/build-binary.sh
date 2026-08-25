#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
UV_CACHE_DIR="${UV_CACHE_DIR:-$PROJECT_ROOT/.uv-cache}"
export UV_CACHE_DIR

cd "$PROJECT_ROOT"
uv sync --all-groups --locked
uv run --offline pyinstaller --clean --noconfirm book-viewer.spec

echo "Built $PROJECT_ROOT/dist/book-viewer"
printf 'Install the viewer for the current user now? [y/N] '
if read -r answer; then
    case "$answer" in
        y | Y | yes | YES | Yes)
            "$PROJECT_ROOT/scripts/install-local.sh" \
                --binary "$PROJECT_ROOT/dist/book-viewer" \
                --books-root "$PROJECT_ROOT/books"
            ;;
        *) echo "Installation skipped. Run scripts/install-local.sh later if desired." ;;
    esac
else
    echo "Installation skipped. Run scripts/install-local.sh later if desired."
fi
