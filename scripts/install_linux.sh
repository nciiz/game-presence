#!/usr/bin/env bash
# GamePresence installer for Linux.
#   bash scripts/install_linux.sh              install (or update)
#   bash scripts/install_linux.sh --uninstall  remove the app (your settings are kept)
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA/gamepresence-app"
BIN_DIR="$HOME/.local/bin"
DESKTOP_FILE="$DATA/applications/gamepresence.desktop"

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

if [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$APP_DIR" "$BIN_DIR/gamepresence" "$DESKTOP_FILE"
    have update-desktop-database && update-desktop-database "$DATA/applications" 2>/dev/null || true
    say "GamePresence removed. Your settings stay in ~/.gamepresence.json and $DATA/gamepresence."
    exit 0
fi

[ -f "$SRC/gamepresence/app.py" ] || { echo "Run this script from a full copy of the project."; exit 1; }
have python3 || { echo "python3 is required. Install it with your package manager first."; exit 1; }

gtk_ok() {
    "${1:-python3}" - <<'PY' >/dev/null 2>&1
import gi
gi.require_version("Gtk", "3.0")
try:
    gi.require_version("WebKit2", "4.1")
except ValueError:
    gi.require_version("WebKit2", "4.0")
from gi.repository import Gtk, WebKit2
PY
}

install_system_packages() {
    local sudo=""
    [ "$(id -u)" -ne 0 ] && sudo="sudo"
    if have apt-get; then
        $sudo apt-get update
        $sudo apt-get install -y python3-venv python3-pip python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1 \
            || $sudo apt-get install -y python3-venv python3-pip python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.0
    elif have dnf; then
        $sudo dnf install -y python3-pip python3-gobject gtk3 webkit2gtk4.1
    elif have pacman; then
        $sudo pacman -S --needed --noconfirm python-pip python-gobject gtk3 webkit2gtk-4.1
    elif have zypper; then
        $sudo zypper --non-interactive install python3-pip python3-gobject-Gdk typelib-1_0-Gtk-3_0 typelib-1_0-WebKit2-4_1
    else
        return 1
    fi
}

mkdir -p "$APP_DIR" "$BIN_DIR" "$DATA/applications"

if [ "${GP_SKIP_DEPS:-0}" != "1" ]; then
    need_pkgs=0
    gtk_ok python3 || need_pkgs=1
    python3 -c 'import ensurepip' 2>/dev/null || need_pkgs=1
    if [ "$need_pkgs" = "1" ]; then
        say "GamePresence needs a few system packages (GTK + WebKit + python venv)."
        reply="y"
        if [ -t 0 ]; then read -r -p "Install them now? This uses sudo. [Y/n] " reply || reply="y"; fi
        case "${reply:-y}" in
            [nN]*) echo "Skipping system packages." ;;
            *) install_system_packages || echo "Couldn't install system packages automatically." ;;
        esac
    fi

    say "Creating a private Python environment..."
    python3 -m venv --system-site-packages "$APP_DIR/venv" || {
        echo "Couldn't create a virtual environment. On Debian/Ubuntu install python3-venv and try again."
        exit 1
    }
    PY="$APP_DIR/venv/bin/python"
    "$PY" -m pip install --upgrade pywebview requests pypresence

    if ! gtk_ok "$PY"; then
        say "GTK/WebKit not found, using the Qt backend instead (bigger download)..."
        "$PY" -m pip install --upgrade "pywebview[qt]" \
            || echo "Qt backend install failed too. Install GTK + WebKit2 packages for your distro and re-run."
    fi
else
    python3 -m venv "$APP_DIR/venv"
fi

rm -rf "$APP_DIR/gamepresence"
cp -r "$SRC/gamepresence" "$APP_DIR/gamepresence"
find "$APP_DIR/gamepresence" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
[ -f "$SRC/assets/icon.png" ] && cp "$SRC/assets/icon.png" "$APP_DIR/icon.png"

cat > "$BIN_DIR/gamepresence" <<LAUNCH
#!/usr/bin/env bash
# Works around blank WebKitGTK windows on some GPU/Wayland setups. Override by exporting it yourself.
export WEBKIT_DISABLE_DMABUF_RENDERER="\${WEBKIT_DISABLE_DMABUF_RENDERER:-1}"
cd "$APP_DIR"
exec "$APP_DIR/venv/bin/python" -m gamepresence "\$@"
LAUNCH
chmod +x "$BIN_DIR/gamepresence"

cat > "$DESKTOP_FILE" <<DESKTOP
[Desktop Entry]
Type=Application
Name=GamePresence
Comment=Show any game as your Discord activity
Exec=$BIN_DIR/gamepresence
Icon=$APP_DIR/icon.png
Terminal=false
Categories=Game;Utility;
StartupWMClass=GamePresence
DESKTOP
have update-desktop-database && update-desktop-database "$DATA/applications" 2>/dev/null || true

say "Done! Open GamePresence from your app menu, or run: gamepresence"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "Note: $BIN_DIR isn't in your PATH yet. The app menu entry works anyway." ;;
esac
