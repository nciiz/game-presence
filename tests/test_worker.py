import os
import sys
import time
import unittest
from unittest import mock

from gamepresence import config as C
from gamepresence.models import Game
from gamepresence.worker import Worker
from tests.helpers import FakeBus, isolated_paths, wait_for


def make_worker():
    bus = FakeBus()
    w = Worker(bus)
    w.start()
    return w, bus


class ErrorPathTests(unittest.TestCase):
    def setUp(self):
        self._ctx = isolated_paths()
        self._ctx.__enter__()
        self.w, self.bus = make_worker()

    def tearDown(self):
        self.w.q.put(("quit",))
        self.w.join(5)
        self._ctx.__exit__(None, None, None)

    def test_forced_process_on_unsupported_os(self):
        g = Game("G", "1", None, [{"os": "win32", "name": "g.exe"}])
        with mock.patch.object(C, "SUPPORTS_PROC", False):
            self.w.q.put(("start", g, "", "", 0, "Process detection"))
            self.assertTrue(wait_for(lambda: "err_win_only" in self.bus.codes()))

    def test_forced_process_without_known_exe(self):
        g = Game("G", "1", None, [])
        with mock.patch.object(C, "SUPPORTS_PROC", True):
            self.w.q.put(("start", g, "", "", 0, "Process detection"))
            self.assertTrue(wait_for(lambda: "err_no_exe" in self.bus.codes()))

    def test_rpc_without_discord(self):
        g = Game("G", "1", None, [])
        self.w.q.put(("start", g, "", "", 0, "Rich Presence"))
        self.assertTrue(wait_for(lambda: "err_no_discord" in self.bus.codes()))
        self.assertIn("stopped", self.bus.kinds())

    def test_thread_can_be_joined(self):
        # Regression: a method named `_stop` used to clash with threading.Thread._stop.
        self.w.q.put(("quit",))
        self.w.join(5)
        self.assertFalse(self.w.is_alive())


@unittest.skipUnless(sys.platform.startswith("linux"), "needs Linux")
class LinuxProcessTests(unittest.TestCase):
    def setUp(self):
        self._ctx = isolated_paths()
        self._ctx.__enter__()
        self.w, self.bus = make_worker()
        self.game = Game("Native", "42", None, [{"os": "linux", "name": ">dir/Game.x86_64"}])

    def tearDown(self):
        self.w.q.put(("quit",))
        self.w.join(5)
        self._ctx.__exit__(None, None, None)

    def _pid(self):
        return int(self.w.dummy_info.split()[1].rstrip(","))

    def test_placeholder_has_game_name_and_dies_on_stop(self):
        self.w.q.put(("start", self.game, "", "", 0, "Process detection"))
        self.assertTrue(wait_for(lambda: "started" in self.bus.kinds()))
        pid = self._pid()
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            argv0 = f.read().split(b"\0")[0].decode()
        self.assertTrue(argv0.endswith("/42/dir/Game.x86_64"), argv0)
        self.w.q.put(("stop",))
        self.assertTrue(wait_for(lambda: not os.path.exists(f"/proc/{pid}")))

    def test_session_ends_automatically(self):
        self.w.q.put(("start", self.game, "", "", 5, "Auto"))
        self.assertTrue(wait_for(lambda: "started" in self.bus.kinds()))
        pid = self._pid()
        self.w.end_at = time.time() - 1
        self.assertTrue(wait_for(lambda: "finished" in self.bus.codes()))
        self.assertTrue(wait_for(lambda: not os.path.exists(f"/proc/{pid}")))

    def test_dead_placeholder_is_reported(self):
        self.w.q.put(("start", self.game, "", "", 0, "Auto"))
        self.assertTrue(wait_for(lambda: "started" in self.bus.kinds()))
        os.kill(self._pid(), 9)
        self.assertTrue(wait_for(lambda: "proc_exited" in self.bus.codes()))


if __name__ == "__main__":
    unittest.main()
