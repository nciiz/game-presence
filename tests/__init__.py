"""Test package. Installs light stand-ins for GUI/Discord libraries so tests run anywhere."""

import sys
import types


class _FakeWindow:
    def __init__(self):
        self.js = []

    def evaluate_js(self, code):
        self.js.append(code)


def _install_stubs():
    wv = types.ModuleType("webview")
    wv.calls = {}

    def create_window(*args, **kwargs):
        wv.calls["create_window"] = kwargs
        wv.calls["window"] = _FakeWindow()
        return wv.calls["window"]

    def start(func=None, **kwargs):
        wv.calls["start"] = kwargs

    wv.create_window, wv.start = create_window, start
    sys.modules["webview"] = wv

    pp = types.ModuleType("pypresence")

    class DiscordNotFound(Exception):
        pass

    class Presence:
        def __init__(self, client_id):
            self.client_id = client_id

        def connect(self):
            raise DiscordNotFound("Discord isn't running")

    pp.Presence, pp.DiscordNotFound = Presence, DiscordNotFound
    sys.modules["pypresence"] = pp


_install_stubs()
