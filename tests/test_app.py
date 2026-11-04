import json
import sys
import unittest
from unittest import mock

import tests  # installs stubs  # noqa: F401
from gamepresence import __version__, app
from gamepresence import config as C
from gamepresence.core import Core
from gamepresence.models import Game
from tests.helpers import FakeBus, isolated_paths


class UiFileTests(unittest.TestCase):
    def test_ui_is_bundled_and_wired(self):
        html = app.ui_html()
        self.assertIn("pywebviewready", html)
        self.assertIn("window.onEvent", html)
        self.assertNotIn('"""', html)  # safe to embed in a Python string if ever needed

    def test_every_api_call_used_by_the_ui_exists(self):
        import re
        html = app.ui_html()
        used = set(re.findall(r"api\(\)\.(\w+)\(", html))
        exposed = {n for n in dir(app.Api) if not n.startswith("_")}
        self.assertTrue(used, "UI should call the Python API")
        self.assertEqual(used - exposed, set())


class ApiTests(unittest.TestCase):
    def setUp(self):
        self._ctx = isolated_paths()
        self._ctx.__enter__()
        self.core = Core(FakeBus())
        self.api = app.Api(self.core)
        self.core.catalog = [Game("Cuphead", "111", "i", [{"os": "win32", "name": "cuphead.exe"}])]
        self.core.by_id = {"111": self.core.catalog[0]}

    def tearDown(self):
        self.core.shutdown()
        self._ctx.__exit__(None, None, None)

    def test_private_state_is_not_exposed(self):
        self.assertNotIn("_core", [n for n in dir(self.api) if not n.startswith("_")])

    def test_boot_shape(self):
        b = self.api.boot()
        self.assertEqual(b["version"], __version__)
        self.assertEqual(b["catalog"][0][:2], ["111", "Cuphead"])
        self.assertIn(b["platform"], ("win32", "linux", sys.platform))
        self.assertEqual(b["settings"]["lang"], "ar")

    def test_start_unknown_game(self):
        self.assertFalse(self.api.start("nope", {})["ok"])

    def test_start_queues_and_persists_options(self):
        with mock.patch.object(self.core.worker.q, "put") as put:
            r = self.api.start("111", {"method": "process", "duration": 15, "details": "In a match",
                                       "state": "", "minimize": True})
        self.assertTrue(r["ok"])
        cmd = put.call_args[0][0]
        self.assertEqual((cmd[0], cmd[1].client_id, cmd[2], cmd[4], cmd[5], cmd[6]),
                         ("start", "111", "In a match", 15, "Process detection", True))
        self.assertEqual(json.loads(C.CONFIG_PATH.read_text())["method"], "process")

    def test_start_sanitises_bad_options(self):
        with mock.patch.object(self.core.worker.q, "put") as put:
            self.api.start("111", {"method": "x", "duration": "abc"})
        cmd = put.call_args[0][0]
        self.assertEqual((cmd[4], cmd[5]), (0, "Auto"))

    def test_open_url_allowlist(self):
        with mock.patch("gamepresence.app.webbrowser.open") as op:
            self.api.open_url("https://evil.example/")
            self.api.open_url("https://steamcommunity.com/dev/apikey")
        op.assert_called_once_with("https://steamcommunity.com/dev/apikey")


class MainTests(unittest.TestCase):
    def test_main_creates_window_and_wires_bus(self):
        with isolated_paths():
            app.main()
        wv = sys.modules["webview"]
        kw = wv.calls["create_window"]
        self.assertEqual(kw["background_color"], "#13122b")
        self.assertIn("pywebviewready", kw["html"])
        self.assertIsInstance(kw["js_api"], app.Api)
        self.assertIn("start", wv.calls)


if __name__ == "__main__":
    unittest.main()
