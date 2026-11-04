import json
import unittest
from unittest import mock

import requests

from gamepresence import config as C
from gamepresence.core import Core
from tests.helpers import FakeBus, isolated_paths

DETECT = [
    {"id": "111", "name": "Cuphead", "icon": "ic1",
     "executables": [{"is_launcher": False, "name": "cuphead.exe", "os": "win32"}], "aliases": []},
    {"id": "222", "name": "Counter-Strike 2", "icon": "ic2",
     "executables": [{"is_launcher": False, "name": ">cs2.exe", "os": "win32"}], "aliases": ["CS2"]},
    {"id": "333", "name": "No Exe Game", "icon": None, "executables": [], "aliases": []},
]


class Resp:
    def __init__(self, data, code=200):
        self._d, self.status_code = data, code

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def fake_get(owned=None, vanity_ok=True, status=200):
    def get(url, params=None, timeout=0):
        if "detectable" in url:
            return Resp(DETECT)
        if "ResolveVanity" in url:
            return Resp({"response": {"success": 1 if vanity_ok else 42, "steamid": "7656119"}}, status)
        if "GetOwnedGames" in url:
            return Resp({"response": {"games": owned} if owned is not None else {}}, status)
        raise AssertionError(url)
    return get


OWNED = [{"appid": 268910, "name": "Cuphead™", "playtime_forever": 1500},
         {"appid": 730, "name": "Counter Strike 2", "playtime_forever": 9000},
         {"appid": 9, "name": "Unknown Thing", "playtime_forever": 5}]


class CoreTests(unittest.TestCase):
    def setUp(self):
        self._ctx = isolated_paths()
        self.tmp = self._ctx.__enter__()
        self.core = Core(FakeBus())

    def tearDown(self):
        self.core.shutdown()
        self._ctx.__exit__(None, None, None)

    # settings
    def test_defaults(self):
        s = self.core.settings()
        self.assertEqual((s["lang"], s["method"], s["duration"]), ("ar", "auto", 0))

    def test_migrates_old_config(self):
        self.core.cfg = {"duration": "30 minutes", "method": "Process detection", "details": "hi"}
        s = self.core.settings()
        self.assertEqual((s["duration"], s["method"], s["details"]), (30, "process", "hi"))

    def test_save_validates_input(self):
        self.core.save_settings({"lang": "en", "method": "rpc", "duration": 15, "minimize": True,
                                 "details": "  Dd  ", "bogus": 1})
        s = self.core.settings()
        self.assertEqual((s["lang"], s["method"], s["duration"], s["details"], s["minimize"]),
                         ("en", "rpc", 15, "Dd", True))
        self.core.save_settings({"duration": 999, "method": "zzz", "lang": "xx"})
        s = self.core.settings()
        self.assertEqual((s["lang"], s["method"], s["duration"]), ("en", "rpc", 15))
        self.assertEqual(json.loads(C.CONFIG_PATH.read_text())["method"], "rpc")

    # catalog
    def test_catalog_build_and_compact(self):
        with mock.patch("gamepresence.core.requests.get", fake_get()), \
                mock.patch.object(C, "IS_WIN", True), mock.patch.object(C, "IS_LINUX", False):
            self.assertIsNone(self.core.ensure_catalog())
            rows = {r[0]: r for r in self.core.compact_catalog()}
        self.assertEqual(rows["111"][3], 1)
        self.assertEqual(rows["333"][3], 0)
        self.assertTrue(C.CATALOG_CACHE.exists())

    def test_catalog_error_is_reported(self):
        with mock.patch("gamepresence.core.requests.get", side_effect=requests.ConnectionError("offline")):
            self.assertIn("offline", self.core.ensure_catalog())

    # steam
    def test_steam_matching_sorting_and_cache(self):
        with mock.patch("gamepresence.core.requests.get", fake_get(OWNED)), \
                mock.patch.object(C, "IS_WIN", True), mock.patch.object(C, "IS_LINUX", False):
            r = self.core.load_steam("KEY", "myvanityname")
        self.assertTrue(r["ok"])
        self.assertEqual(r["unmatched"], 1)
        self.assertEqual([g["name"] for g in r["games"]], ["Counter-Strike 2", "Cuphead"])
        top = r["games"][0]
        self.assertEqual((top["hours"], top["appid"], top["exe"]), (150, 730, 1))
        self.assertEqual(json.loads(C.STEAM_CACHE.read_text())["unmatched"], 1)

    def test_steam_error_codes(self):
        cases = [
            (fake_get(OWNED, status=403), "err_steam_key"),
            (fake_get(OWNED, vanity_ok=False), "err_steam_vanity"),
            (fake_get(owned=None), "err_steam_private"),
        ]
        for getter, code in cases:
            with self.subTest(code=code), mock.patch("gamepresence.core.requests.get", getter):
                sid = "myname" if code == "err_steam_vanity" or code == "err_steam_key" else "123"
                self.assertEqual(self.core.load_steam("KEY", sid)["code"], code)

    def test_steam_network_error(self):
        with mock.patch("gamepresence.core.requests.get", fake_get(OWNED)):
            self.core.ensure_catalog()
        with mock.patch("gamepresence.core.requests.get", side_effect=requests.ConnectionError("down")):
            r = self.core.load_steam("KEY", "123")
        self.assertEqual((r["ok"], r["code"]), (False, "err_net"))


if __name__ == "__main__":
    unittest.main()
