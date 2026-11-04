import contextlib
import tempfile
import time
from pathlib import Path
from unittest import mock

from gamepresence import config as C


@contextlib.contextmanager
def isolated_paths():
    """Point every app path at a temporary directory."""
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        with contextlib.ExitStack() as st:
            for name, rel in (("BASE_DIR", "base"), ("CONFIG_PATH", "config.json"),
                              ("CATALOG_CACHE", "catalog.json"), ("STEAM_CACHE", "steam.json"),
                              ("GAMES_DIR", "games"), ("LOG_PATH", "log.txt")):
                st.enter_context(mock.patch.object(C, name, t / rel))
            yield t


def wait_for(cond, timeout=6.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return False


class FakeBus:
    """Collects events instead of sending them to a window."""

    def __init__(self):
        self.events = []

    def put(self, msg):
        self.events.append(msg)

    def codes(self):
        return [m[2] for m in self.events if m[0] == "status"]

    def kinds(self):
        return [m[0] for m in self.events]
