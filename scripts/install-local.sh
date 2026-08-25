#!/bin/sh
set -eu

usage() {
    cat <<'EOF'
Usage: scripts/install-local.sh [options]

Install the built viewer in a stable per-user location and remember the book library path.

Options:
  --binary PATH      Executable to install (default: dist/book-viewer)
  --books-root PATH  Book library to remember (default: books)
  --yes              Answer yes to PATH setup prompts
  --no-path          Do not edit shell PATH setup
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
CONFIGURE_PATH=1

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
        --no-path)
            CONFIGURE_PATH=0
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
        CONFIG_ROOT="$USER_HOME/Library/Application Support/Parallel Book Viewer"
        ;;
    *)
        CONFIG_HOME=${XDG_CONFIG_HOME:-$USER_HOME/.config}
        CONFIG_ROOT="$CONFIG_HOME/parallel-book-viewer"
        ;;
esac

INSTALL_DIRECTORY="$USER_HOME/.local/bin"
INSTALLED_BINARY="$INSTALL_DIRECTORY/book-viewer"
CONFIG_PATH="$CONFIG_ROOT/config.toml"
BINARY_TEMP="$INSTALLED_BINARY.tmp.$$"
CONFIG_TEMP="$CONFIG_PATH.tmp.$$"

mkdir -p "$INSTALL_DIRECTORY" "$CONFIG_ROOT"
trap 'rm -f "$BINARY_TEMP" "$CONFIG_TEMP"' EXIT HUP INT TERM
install -m 755 "$BINARY_PATH" "$BINARY_TEMP"
mv "$BINARY_TEMP" "$INSTALLED_BINARY"
umask 077
if [ -f "$CONFIG_PATH" ]; then
    awk -v books_root="$BOOKS_ROOT" '
        BEGIN {
            print "schema_version = 1"
            in_root = 1
            in_viewer = 0
            saw_viewer = 0
            wrote_books_root = 0
        }
        /^\[[^]]+\][[:space:]]*$/ {
            if (in_viewer && !wrote_books_root) {
                print "books_root = \"" books_root "\""
                wrote_books_root = 1
            }
            in_root = 0
            in_viewer = ($0 == "[viewer]")
            if (in_viewer) saw_viewer = 1
            print
            next
        }
        in_root && /^[[:space:]]*(schema_version|books_root)[[:space:]]*=/ { next }
        in_viewer && /^[[:space:]]*books_root[[:space:]]*=/ {
            if (!wrote_books_root) {
                print "books_root = \"" books_root "\""
                wrote_books_root = 1
            }
            next
        }
        { print }
        END {
            if (in_viewer && !wrote_books_root) {
                print "books_root = \"" books_root "\""
            } else if (!saw_viewer) {
                print ""
                print "[viewer]"
                print "books_root = \"" books_root "\""
            }
        }
    ' "$CONFIG_PATH" > "$CONFIG_TEMP"
else
    printf 'schema_version = 1\n\n[viewer]\nbooks_root = "%s"\n' "$BOOKS_ROOT" > "$CONFIG_TEMP"
fi
mv "$CONFIG_TEMP" "$CONFIG_PATH"
trap - EXIT HUP INT TERM

echo "Installed viewer: $INSTALLED_BINARY"
echo "Remembered selected book library: $BOOKS_ROOT"

if [ "$CONFIGURE_PATH" -eq 0 ]; then
    echo "Skipped PATH setup. Run $INSTALLED_BINARY directly if it is not already on PATH."
    exit 0
fi

case ":${PATH:-}:" in
    *":$INSTALL_DIRECTORY:"*)
        echo "$INSTALL_DIRECTORY is already on PATH."
        exit 0
        ;;
esac

SHELL_PATH=${VIEWER_INSTALL_SHELL:-${SHELL:-}}
case "$SHELL_PATH" in
    */zsh) PROFILE_PATH="$USER_HOME/.zprofile" ;;
    */bash) PROFILE_PATH="$USER_HOME/.bash_profile" ;;
    *) PROFILE_PATH="$USER_HOME/.profile" ;;
esac

if confirm "Add $INSTALL_DIRECTORY to PATH in $PROFILE_PATH?"; then
    PATH_LINE="export PATH=\"$INSTALL_DIRECTORY:\$PATH\""
    if [ -f "$PROFILE_PATH" ] && grep -Fqx "$PATH_LINE" "$PROFILE_PATH"; then
        echo "PATH setup already exists in $PROFILE_PATH."
    else
        {
            printf '\n# >>> Parallel Book Viewer >>>\n'
            printf '%s\n' "$PATH_LINE"
            printf '# <<< Parallel Book Viewer <<<\n'
        } >> "$PROFILE_PATH"
        echo "Added PATH setup to $PROFILE_PATH. Open a new terminal before running book-viewer."
    fi
else
    echo "PATH was not changed. Run $INSTALLED_BINARY directly or add $INSTALL_DIRECTORY manually."
fi
