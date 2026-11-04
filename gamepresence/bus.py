"""Pushes events from Python threads into the web UI."""

import json
import traceback

from .config import log


class Bus:
    def __init__(self):
        self.window = None

    def emit(self, evt: dict) -> None:
        w = self.window
        if not w:
            return
        try:
            w.evaluate_js("window.onEvent && window.onEvent(%s)" % json.dumps(evt))
        except Exception:
            log("emit failed: " + traceback.format_exc())

    def put(self, msg: tuple) -> None:
        kind = msg[0]
        if kind == "started":
            _, game, end_at, mode = msg
            self.emit({"type": "started", "game": {"id": game.client_id, "name": game.name},
                       "end_at": end_at, "mode": mode})
        elif kind == "stopped":
            self.emit({"type": "stopped"})
        elif kind == "status":
            _, level, code, detail = msg
            self.emit({"type": "status", "kind": level, "code": code, "detail": detail})
