#!/bin/sh
set -eu

usage() {
    cat <<'EOF'
Usage: scripts/uninstall-local.sh [options]

Remove the per-user viewer installation without touching the book library.

Options:
  --yes        Uninstall without the first confirmation; preserve reading data
  --purge-data Also delete saved reading progress and other reader data
  -h, --help   Show this help
EOF
}

confirm() {
    prompt=$1
    printf '%s [y/N] ' "$prompt"
    read -r answer || return 1
    case "$answer" in
        y | Y | yes | YES | Yes) return 0 ;;
        *) return 1 ;;
    esac
}

remove_file() {
    path=$1
    if [ -e "$path" ] || [ -L "$path" ]; then
        rm -f "$path"
        echo "Removed: $path"
    fi
}

remove_managed_path_block() {
    profile_path=$1
    [ -f "$profile_path" ] || return 0

    temporary_path="$profile_path.book-viewer-uninstall.$$"
    cp -p "$profile_path" "$temporary_path"
    sed '/^# >>> Parallel Book Viewer >>>$/,/^# <<< Parallel Book Viewer <<<$/{d;}' \
        "$profile_path" > "$temporary_path"
    if cmp -s "$profile_path" "$temporary_path"; then
        rm -f "$temporary_path"
        return 0
    fi
    mv "$temporary_path" "$profile_path"
    echo "Removed installer-managed PATH setup from: $profile_path"
}

ASSUME_YES=0
PURGE_DATA=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --yes)
            ASSUME_YES=1
            shift
            ;;
        --purge-data)
            PURGE_DATA=1
            shift
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            echo "Error: unknown option: $1" >&2
            exit 1
            ;;
    esac
done

if [ "$ASSUME_YES" -eq 0 ] && ! confirm "Uninstall Parallel Book Viewer for this user?"; then
    echo "Uninstallation cancelled."
    exit 0
fi

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

INSTALLED_BINARY="$USER_HOME/.local/bin/book-viewer"
CONFIG_PATH="$CONFIG_ROOT/config.toml"
READER_DATA_PATH="$APP_ROOT/reader-data.sqlite3"

if [ "$PURGE_DATA" -eq 0 ] && [ "$ASSUME_YES" -eq 0 ]; then
    if [ -e "$READER_DATA_PATH" ] && confirm "Also delete saved reading progress?"; then
        PURGE_DATA=1
    fi
fi

remove_file "$INSTALLED_BINARY"
remove_file "$CONFIG_PATH"

for profile_path in "$USER_HOME/.zprofile" "$USER_HOME/.bash_profile" "$USER_HOME/.profile"; do
    remove_managed_path_block "$profile_path"
done

if [ "$PURGE_DATA" -eq 1 ]; then
    remove_file "$READER_DATA_PATH"
    remove_file "$READER_DATA_PATH-wal"
    remove_file "$READER_DATA_PATH-shm"
    remove_file "$READER_DATA_PATH-journal"
    echo "Deleted saved reader data."
else
    echo "Preserved saved reader data."
fi

rmdir "$CONFIG_ROOT" 2>/dev/null || :
rmdir "$APP_ROOT" 2>/dev/null || :

echo "Parallel Book Viewer was uninstalled. Your book library was not removed."
