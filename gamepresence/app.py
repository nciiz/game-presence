"""Window, JS bridge and entry point."""

import sys
import time
import traceback
import webbrowser
from pathlib import Path

import webview

from . import __version__
from . import config as C
from .bus import Bus
from .config import APP_NAME, load_json, log
from .core import Core


class Api:
    """Public methods are callable from the UI as window.pywebview.api.<name>()."""

    def __init__(self, core: Core):
        self._core = core

    def boot(self):
        c = self._core
        err = c.ensure_catalog()
        platform = "win32" if C.IS_WIN else ("linux" if C.IS_LINUX else sys.platform)
        return {"settings": c.settings(), "catalog": c.compact_catalog(),
                "steam": load_json(C.STEAM_CACHE), "error": err, "version": __version__,
                "platform": platform}

    def load_steam(self, key, sid):
        return self._core.load_steam(str(key).strip(), str(sid).strip())

    def start(self, game_id, opts):
        c = self._core
        g = c.by_id.get(str(game_id))
        if not g:
            return {"ok": False, "code": "err_raw", "detail": "Unknown game"}
        opts = opts if isinstance(opts, dict) else {}
        c.save_settings({k: opts[k] for k in ("method", "duration", "details", "state", "minimize")
                         if k in opts})
        method = C.METHOD_BY_CODE.get(opts.get("method"), "Auto")
        try:
            minutes = int(opts.get("duration", 0))
        except (TypeError, ValueError):
            minutes = 0
        if minutes not in C.ALLOWED_DURATIONS:
            minutes = 0
        c.worker.q.put(("start", g, str(opts.get("details", "")).strip(),
                        str(opts.get("state", "")).strip(), minutes, method,
                        bool(opts.get("minimize", False))))
        return {"ok": True}

    def stop(self):
        self._core.worker.q.put(("stop",))
        return {"ok": True}

    def save_settings(self, s):
        self._core.save_settings(s)
        return {"ok": True}

    def open_url(self, url):
        if isinstance(url, str) and url.startswith("https://steamcommunity.com/"):
            webbrowser.open(url)
        return {"ok": True}


def ui_html() -> str:
    """Read the bundled UI (works from source and from a PyInstaller build)."""
    root = Path(getattr(sys, "_MEIPASS", "") or Path(__file__).resolve().parent.parent)
    return (root / "gamepresence" / "ui" / "index.html").read_text(encoding="utf-8")


def dark_titlebar(title: str) -> None:
    """Make the native title bar match the dark UI (Windows 10/11)."""
    if not C.IS_WIN:
        return
    try:
        import ctypes
        for _ in range(40):
            hwnd = ctypes.windll.user32.FindWindowW(None, title)
            if hwnd:
                on = ctypes.c_int(1)
                for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), 4)
                color = ctypes.c_int(0x002B1213)  # caption color #13122b (Windows 11)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), 4)
                return
            time.sleep(0.25)
    except Exception:
        log(traceback.format_exc())


def main() -> None:
    log(f"{APP_NAME} {__version__} starting")
    bus = Bus()
    core = Core(bus)
    window = webview.create_window(APP_NAME, html=ui_html(), js_api=Api(core), width=1200, height=780,
                                   min_size=(900, 600), background_color="#13122b")
    bus.window = window
    try:
        webview.start(lambda: dark_titlebar(APP_NAME), gui="edgechromium" if C.IS_WIN else None)
    except Exception:
        log(traceback.format_exc())
        if C.IS_WIN:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, "GamePresence needs the Microsoft Edge WebView2 runtime.\n\n"
                   "Download it from:\nhttps://go.microsoft.com/fwlink/p/?LinkId=2124703",
                APP_NAME, 0x10)
    finally:
        core.shutdown()
