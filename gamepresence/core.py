"""Settings, the Discord game catalog and Steam library matching."""

import json
import threading
import time
import traceback
from typing import Optional

import requests

from . import config as C
from .bus import Bus
from .config import log, load_json, save_json
from .models import Game, norm
from .worker import Worker


class SteamError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Core:
    def __init__(self, bus: Bus):
        self.bus = bus
        self.cfg = load_json(C.CONFIG_PATH, {}) or {}
        self.worker = Worker(bus)
        self.worker.start()
        self.catalog: list = []
        self.by_id: dict = {}
        self.index: dict = {}

    # ---- settings
    def settings(self) -> dict:
        c = self.cfg
        m = c.get("method", "auto")
        m = C.CODE_BY_METHOD.get(m, m)
        if m not in C.METHOD_BY_CODE:
            m = "auto"
        d = c.get("duration", 0)
        if isinstance(d, str):
            d = C.OLD_DURATIONS.get(d, 0)
        if d not in C.ALLOWED_DURATIONS:
            d = 0
        return {"lang": c.get("lang") if c.get("lang") in ("ar", "en") else "ar",
                "method": m, "duration": d,
                "details": str(c.get("details", "")), "state": str(c.get("state", "")),
                "minimize": bool(c.get("minimize", False)),
                "steam_key": str(c.get("steam_key", "")), "steam_id": str(c.get("steam_id", ""))}

    def save_settings(self, s: dict) -> None:
        if not isinstance(s, dict):
            return
        if s.get("lang") in ("ar", "en"):
            self.cfg["lang"] = s["lang"]
        if s.get("method") in C.METHOD_BY_CODE:
            self.cfg["method"] = s["method"]
        if "duration" in s:
            try:
                if int(s["duration"]) in C.ALLOWED_DURATIONS:
                    self.cfg["duration"] = int(s["duration"])
            except (TypeError, ValueError):
                pass
        for k in ("details", "state", "steam_key", "steam_id"):
            if k in s:
                self.cfg[k] = str(s[k]).strip()[:200]
        if "minimize" in s:
            self.cfg["minimize"] = bool(s["minimize"])
        try:
            C.CONFIG_PATH.write_text(json.dumps(self.cfg, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ---- catalog
    @staticmethod
    def _fetch_catalog() -> list:
        r = requests.get(C.DETECTABLE_URL, timeout=30)
        r.raise_for_status()
        data = r.json()
        save_json(C.CATALOG_CACHE, data)
        return data

    def ensure_catalog(self) -> Optional[str]:
        """Load the Discord game list (cache first). Returns an error string, or None."""
        if self.catalog:
            return None
        data, stale = None, False
        if C.CATALOG_CACHE.exists():
            data = load_json(C.CATALOG_CACHE)
            stale = time.time() - C.CATALOG_CACHE.stat().st_mtime > 86400
        if not data:
            try:
                data = self._fetch_catalog()
            except Exception as e:  # noqa
                log(f"catalog fetch failed: {e}")
                return str(e)
        elif stale:
            threading.Thread(target=lambda: self._safe(self._fetch_catalog), daemon=True).start()
        self._build(data)
        return None

    @staticmethod
    def _safe(fn):
        try:
            fn()
        except Exception:
            pass

    def _build(self, data: list) -> None:
        games, by_id, index = [], {}, {}
        for app in data:
            name, cid = app.get("name"), app.get("id")
            if not name or not cid:
                continue
            g = Game(name, cid, app.get("icon"), app.get("executables") or [])
            games.append(g)
            by_id[cid] = g
            for n in [name] + list(app.get("aliases") or []):
                index.setdefault(norm(n), app)
        games.sort(key=lambda g: g.name.lower())
        self.catalog, self.by_id, self.index = games, by_id, index

    def compact_catalog(self) -> list:
        return [[g.client_id, g.name, g.icon or "", 1 if g.proc_exe() else 0] for g in self.catalog]

    # ---- steam
    def load_steam(self, key: str, sid: str) -> dict:
        try:
            err = self.ensure_catalog()
            if err:
                return {"ok": False, "code": "err_net", "detail": err}
            if not sid.isdigit():
                r = requests.get("https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/",
                                 params={"key": key, "vanityurl": sid}, timeout=15)
                if r.status_code in (401, 403):
                    raise SteamError("err_steam_key")
                resp = r.json().get("response", {})
                if resp.get("success") != 1:
                    raise SteamError("err_steam_vanity")
                sid = resp["steamid"]
            r = requests.get("https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/",
                             params={"key": key, "steamid": sid, "include_appinfo": 1, "format": "json"},
                             timeout=30)
            if r.status_code in (401, 403):
                raise SteamError("err_steam_key")
            r.raise_for_status()
            owned = r.json().get("response", {}).get("games")
            if not owned:
                raise SteamError("err_steam_private")

            games, seen, unmatched = [], set(), 0
            for g in sorted(owned, key=lambda x: x.get("playtime_forever", 0), reverse=True):
                app = self.index.get(norm(g.get("name", "")))
                if not app:
                    unmatched += 1
                    continue
                if app["id"] in seen:
                    continue
                seen.add(app["id"])
                game = self.by_id.get(app["id"])
                games.append({"id": app["id"], "name": app["name"], "icon": app.get("icon") or "",
                              "exe": 1 if game and game.proc_exe() else 0,
                              "appid": g.get("appid", 0), "hours": g.get("playtime_forever", 0) // 60})
            result = {"games": games, "unmatched": unmatched}
            save_json(C.STEAM_CACHE, result)
            return {"ok": True, **result}
        except SteamError as e:
            return {"ok": False, "code": e.code}
        except requests.RequestException as e:
            return {"ok": False, "code": "err_net", "detail": str(e)[:160]}
        except Exception as e:  # noqa
            log(traceback.format_exc())
            return {"ok": False, "code": "err_raw", "detail": f"{type(e).__name__}: {e}"}

    def shutdown(self):
        try:
            self.worker.q.put(("quit",))
            self.worker.join(timeout=5)
        except Exception:
            pass
