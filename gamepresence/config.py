"""Paths, platform flags and small file helpers shared by the whole app."""

import json
import os
import sys
import time
from pathlib import Path

APP_NAME = "GamePresence"

IS_WIN = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
SUPPORTS_PROC = IS_WIN or IS_LINUX  # placeholder-process detection

if IS_LINUX:
    BASE_DIR = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "gamepresence"
else:
    BASE_DIR = Path.home() / "GamePresence"

CONFIG_PATH = Path.home() / ".gamepresence.json"
CATALOG_CACHE = Path.home() / ".gamepresence_catalog.json"
STEAM_CACHE = BASE_DIR / "steam_cache.json"
GAMES_DIR = BASE_DIR / "games"
LOG_PATH = BASE_DIR / "log.txt"
DETECTABLE_URL = "https://discord.com/api/v9/applications/detectable"

METHOD_BY_CODE = {"auto": "Auto", "process": "Process detection", "rpc": "Rich Presence"}
CODE_BY_METHOD = {v: k for k, v in METHOD_BY_CODE.items()}
OLD_DURATIONS = {"Until I stop": 0, "5 minutes": 5, "15 minutes": 15,
                 "30 minutes": 30, "1 hour": 60, "3 hours": 180}
ALLOWED_DURATIONS = {0, 5, 15, 30, 60, 180}


def log(msg: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S  ") + msg + "\n")
    except Exception:
        pass


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass
