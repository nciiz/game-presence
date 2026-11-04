import unittest
from unittest import mock

from gamepresence import config as C
from gamepresence.models import Game, exe_relpath, norm


class NormTests(unittest.TestCase):
    def test_strips_symbols_and_case(self):
        self.assertEqual(norm("Cuphead™"), "cuphead")
        self.assertEqual(norm("Counter-Strike 2"), "counterstrike2")
        self.assertEqual(norm("Call of Duty®: Modern Warfare® 4"), "callofdutymodernwarfare4")

    def test_non_latin_becomes_empty(self):
        self.assertEqual(norm("لعبة"), "")


class ExePathTests(unittest.TestCase):
    def test_plain_and_prefixed(self):
        self.assertEqual(exe_relpath("cuphead.exe"), ["cuphead.exe"])
        self.assertEqual(exe_relpath(">cs2.exe"), ["cs2.exe"])
        self.assertEqual(exe_relpath("dir\\sub/Game.exe"), ["dir", "sub", "Game.exe"])

    def test_rejects_traversal_and_drives(self):
        self.assertIsNone(exe_relpath("../x.exe"))
        self.assertIsNone(exe_relpath("a/../../x.exe"))
        self.assertIsNone(exe_relpath("C:/x.exe"))
        self.assertIsNone(exe_relpath(""))
        self.assertIsNone(exe_relpath(">"))


class ProcExeTests(unittest.TestCase):
    EXES = [{"os": "win32", "name": "a.exe"}, {"os": "linux", "name": ">a_native"},
            {"os": "linux", "name": "launcher", "is_launcher": True}, {"os": "darwin", "name": "a.app"}]

    def test_windows_picks_win32(self):
        with mock.patch.object(C, "IS_WIN", True), mock.patch.object(C, "IS_LINUX", False):
            self.assertEqual(Game("A", "1", None, self.EXES).proc_exe()["name"], "a.exe")

    def test_linux_prefers_native_then_wine(self):
        with mock.patch.object(C, "IS_WIN", False), mock.patch.object(C, "IS_LINUX", True):
            self.assertEqual(Game("A", "1", None, self.EXES).proc_exe()["name"], ">a_native")
            wine_only = Game("B", "2", None, [{"os": "win32", "name": "b.exe"}])
            self.assertEqual(wine_only.proc_exe()["name"], "b.exe")

    def test_launchers_and_other_os_ignored(self):
        with mock.patch.object(C, "IS_WIN", False), mock.patch.object(C, "IS_LINUX", True):
            self.assertIsNone(Game("C", "3", None, [{"os": "darwin", "name": "c.app"},
                                                    {"os": "linux", "name": "l", "is_launcher": True}]).proc_exe())

    def test_unsupported_platform(self):
        with mock.patch.object(C, "IS_WIN", False), mock.patch.object(C, "IS_LINUX", False):
            self.assertIsNone(Game("A", "1", None, self.EXES).proc_exe())


if __name__ == "__main__":
    unittest.main()
