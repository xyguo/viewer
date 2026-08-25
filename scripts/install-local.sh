#!/bin/sh
set -eu

usage() {
    cat <<'EOF'
Usage: scripts/install-local.sh [options]

Install the built viewer in a stable per-user location and save the book library path.

Options:
  --binary PATH      Executable to install (default: dist/book-viewer)
  --books-root PATH  Book library to save (default: books)
  --yes              Answer yes to PATH setup prompts
  --no-link          Do not create a command symlink or edit shell PATH setup
  -h, --help         Show this help
EOF
}

fail() {
    echo "Error: $*" >&2
    exit 1
}

absolute_existing_path() {
    path=$1
    directory=$(CDPATH= cd -- "$(dirname -- "$path")" && pwd)
    printf '%s/%s\n' "$directory" "$(basename -- "$path")"
}

confirm() {
    prompt=$1
    if [ "$ASSUME_YES" -eq 1 ]; then
        return 0
    fi
    printf '%s [y/N] ' "$prompt"
    read -r answer || return 1
    case "$answer" in
        y | Y | yes | YES | Yes) return 0 ;;
        *) return 1 ;;
    esac
}

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BINARY_PATH="$PROJECT_ROOT/dist/book-viewer"
BOOKS_ROOT="$PROJECT_ROOT/books"
ASSUME_YES=0
CREATE_LINK=1

while [ "$#" -gt 0 ]; do
    case "$1" in
        --binary)
            [ "$#" -ge 2 ] || fail "--binary requires a path"
            BINARY_PATH=$2
            shift 2
            ;;
        --books-root)
            [ "$#" -ge 2 ] || fail "--books-root requires a path"
            BOOKS_ROOT=$2
            shift 2
            ;;
        --yes)
            ASSUME_YES=1
            shift
            ;;
        --no-link)
            CREATE_LINK=0
            shift
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *) fail "unknown option: $1" ;;
    esac
done

[ -f "$BINARY_PATH" ] || fail "viewer executable not found: $BINARY_PATH"
[ -x "$BINARY_PATH" ] || fail "viewer executable is not executable: $BINARY_PATH"
[ -d "$BOOKS_ROOT" ] || fail "book library does not exist: $BOOKS_ROOT"

BINARY_PATH=$(absolute_existing_path "$BINARY_PATH")
BOOKS_ROOT=$(absolute_existing_path "$BOOKS_ROOT")

case "$BOOKS_ROOT" in
    *'"'* | *'\'* | *'
'*) fail "book library path cannot contain quotes, backslashes, or line breaks" ;;
esac

USER_HOME=${VIEWER_INSTALL_HOME:-${HOME:?HOME is not set}}
case "$(uname -s)" in
    Darwin)
        APP_ROOT="$USER_HOME/Library/Application Support/Parallel Book Viewer"
        CONFIG_ROOT=$APP_ROOT
        ;;
    *)
        DATA_HOME=${XDG_DATA_HOME:-$USER_HOME/.local/share}
        CONFIG_HOME=${XDG_CONFIG_HOME:-$USER_HOME/.config}
        APP_ROOT="$DATA_HOME/parallel-book-viewer"
        CONFIG_ROOT="$CONFIG_HOME/parallel-book-viewer"
        ;;
esac

INSTALL_DIRECTORY="$APP_ROOT/bin"
INSTALLED_BINARY="$INSTALL_DIRECTORY/book-viewer"
CONFIG_PATH="$CONFIG_ROOT/config.toml"

mkdir -p "$INSTALL_DIRECTORY" "$CONFIG_ROOT"
install -m 755 "$BINARY_PATH" "$INSTALLED_BINARY"

CONFIG_TEMP="$CONFIG_PATH.tmp.$$"
trap 'rm -f "$CONFIG_TEMP"' EXIT HUP INT TERM
umask 077
printf 'books_root = "%s"\n' "$BOOKS_ROOT" > "$CONFIG_TEMP"
mv "$CONFIG_TEMP" "$CONFIG_PATH"
trap - EXIT HUP INT TERM

echo "Installed viewer: $INSTALLED_BINARY"
echo "Saved book library: $BOOKS_ROOT"
echo "Saved configuration: $CONFIG_PATH"

if [ "$CREATE_LINK" -eq 0 ]; then
    echo "Skipped command symlink and PATH setup."
    exit 0
fi

LINK_DIRECTORY=${VIEWER_LINK_DIR:-$USER_HOME/.local/bin}
LINK_PATH="$LINK_DIRECTORY/book-viewer"
if confirm "Create $LINK_PATH so the viewer can be run from any directory?"; then
    mkdir -p "$LINK_DIRECTORY"
    if [ -e "$LINK_PATH" ] && [ ! -L "$LINK_PATH" ]; then
        echo "Skipped symlink: $LINK_PATH already exists and is not a symlink." >&2
        exit 0
    fi
    ln -sfn "$INSTALLED_BINARY" "$LINK_PATH"
    echo "Created command symlink: $LINK_PATH"
else
    echo "Skipped command symlink and PATH setup."
    exit 0
fi

case ":${PATH:-}:" in
    *":$LINK_DIRECTORY:"*)
        echo "$LINK_DIRECTORY is already on PATH."
        exit 0
        ;;
esac

SHELL_PATH=${VIEWER_INSTALL_SHELL:-${SHELL:-}}
case "$SHELL_PATH" in
    */zsh) PROFILE_PATH="$USER_HOME/.zprofile" ;;
    */bash) PROFILE_PATH="$USER_HOME/.bash_profile" ;;
    *) PROFILE_PATH="$USER_HOME/.profile" ;;
esac

if confirm "Add $LINK_DIRECTORY to PATH in $PROFILE_PATH?"; then
    PATH_LINE="export PATH=\"$LINK_DIRECTORY:\$PATH\""
    if [ -f "$PROFILE_PATH" ] && grep -Fqx "$PATH_LINE" "$PROFILE_PATH"; then
        echo "PATH setup already exists in $PROFILE_PATH."
    else
        {
            printf '\n# Parallel Book Viewer\n'
            printf '%s\n' "$PATH_LINE"
        } >> "$PROFILE_PATH"
        echo "Added PATH setup to $PROFILE_PATH. Open a new terminal before running book-viewer."
    fi
else
    echo "PATH was not changed. Run $LINK_PATH directly or add $LINK_DIRECTORY manually."
fi
