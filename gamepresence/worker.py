"""Background worker: owns the placeholder process / Rich Presence connection."""

import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Optional

from pypresence import Presence

from . import config as C
from .bus import Bus
from .config import log
from .models import Game, exe_relpath


class Worker(threading.Thread):
    def __init__(self, bus: Bus):
        super().__init__(daemon=True)
        self.q: queue.Queue = queue.Queue()
        self.bus = bus
        self.rpc: Optional[Presence] = None
        self.proc: Optional[subprocess.Popen] = None
        self.payload: dict = {}
        self.end_at: Optional[float] = None
        self.last_ping = 0.0
        self.dummy_info = ""

    # ---- main loop
    def run(self):
        while True:
            try:
                if self._step():
                    return
            except Exception:
                log(traceback.format_exc())
                self._error("err_raw", "Internal error, see " + str(C.LOG_PATH))
                time.sleep(1)

    def _step(self) -> bool:
        try:
            cmd = self.q.get(timeout=1)
        except queue.Empty:
            cmd = None

        if cmd:
            if cmd[0] == "start":
                self._start(*cmd[1:])
            elif cmd[0] == "stop":
                self._stop_session("stopped")
            elif cmd[0] == "quit":
                self._close()
                return True

        if self.rpc or self.proc:
            now = time.time()
            if self.end_at and now >= self.end_at:
                self._stop_session("finished")
            elif self.proc and self.proc.poll() is not None:
                log(f"placeholder process exited with code {self.proc.poll()}")
                self._stop_session("proc_exited")
            elif self.rpc and now - self.last_ping >= 20:
                self._ping()
        return False

    # ---- start
    def _start(self, game: Game, details: str, state: str, minutes: int, method: str,
               minimize: bool = False):
        self._close()
        has_exe = C.SUPPORTS_PROC and game.proc_exe() is not None
        if method == "Process detection":
            if not C.SUPPORTS_PROC:
                return self._error("err_win_only")
            if not has_exe:
                return self._error("err_no_exe")
            use_proc = True
        elif method == "Rich Presence":
            use_proc = False
        else:
            use_proc = has_exe

        log(f"start '{game.name}' id={game.client_id} method={method} use_proc={use_proc} "
            f"exe={game.proc_exe()} minimize={minimize}")
        try:
            if use_proc:
                self.proc = self._launch_dummy(game, minimize)
            else:
                self._start_rpc(game, details, state)
        except Exception as e:  # noqa
            self._close()
            return self._fail(e)

        self.end_at = time.time() + minutes * 60 if minutes else None
        self.last_ping = time.time()
        self.bus.put(("started", game, self.end_at, "process" if use_proc else "rpc"))
        if use_proc:
            self.bus.put(("status", "ok", "running", {"name": game.name, "info": self.dummy_info}))
        else:
            self.bus.put(("status", "ok", "rpc_running",
                          {"name": game.name, "fallback": method != "Rich Presence"}))

    def _start_rpc(self, game: Game, details: str, state: str):
        rpc = Presence(game.client_id)
        rpc.connect()
        payload = {"start": int(time.time())}
        if len(details) >= 2:
            payload["details"] = details
        if len(state) >= 2:
            payload["state"] = state
        rpc.update(**payload)
        self.rpc, self.payload = rpc, payload

    # ---- placeholder processes
    def _launch_dummy(self, game: Game, minimize: bool = False) -> subprocess.Popen:
        return self._launch_dummy_linux(game) if C.IS_LINUX else self._launch_dummy_win(game, minimize)

    def _launch_dummy_linux(self, game: Game) -> subprocess.Popen:
        """Start a harmless `sleep` whose file name/path matches the game's executable."""
        parts = exe_relpath(game.proc_exe()["name"])
        target = C.GAMES_DIR.joinpath(game.client_id, *parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        sleep_bin = shutil.which("sleep") or "/bin/sleep"
        secs = "31536000"

        def fresh():
            try:
                target.unlink()
            except FileNotFoundError:
                pass

        def a_copy():
            fresh()
            shutil.copy2(sleep_bin, target)
            target.chmod(0o755)
            return [str(target), secs]

        def a_link():
            fresh()
            os.symlink(os.path.realpath(sleep_bin), target)
            return [str(target), secs]

        def a_script():
            fresh()
            target.write_text(f"#!/bin/sh\nsleep {secs}\n")
            target.chmod(0o755)
            return [str(target)]

        errors = []
        for label, build in (("copy", a_copy), ("symlink", a_link), ("script", a_script)):
            try:
                argv = build()
                p = subprocess.Popen(argv, cwd=str(target.parent), stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True)
                time.sleep(0.8)
                if p.poll() is None:
                    self.dummy_info = f"PID {p.pid}, {target} ({label})"
                    log(f"launched {self.dummy_info}")
                    return p
                errors.append(f"{label}: exited with code {p.returncode}")
            except Exception as e:  # noqa
                errors.append(f"{label}: {e}")
        log("launch failed: " + "; ".join(errors))
        raise RuntimeError("Couldn't start placeholder process (" + "; ".join(errors) + ")")

    def _launch_dummy_win(self, game: Game, minimize: bool = False) -> subprocess.Popen:
        """Start a harmless process whose name/path matches the game's detectable .exe."""
        parts = exe_relpath(game.proc_exe()["name"])
        target = C.GAMES_DIR.joinpath(game.client_id, *parts)
        target.parent.mkdir(parents=True, exist_ok=True)

        attempts = []
        ping = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "ping.exe"
        if ping.exists():
            attempts.append((ping, ["-t", "127.0.0.1"], {}, True))
        pyw = Path(sys.base_prefix) / "pythonw.exe"
        if pyw.exists():
            attempts.append((pyw, ["-c", "import time; time.sleep(86400)"],
                             {"PYTHONHOME": sys.base_prefix}, False))

        errors = []
        for src, args, extra_env, visible in attempts:
            try:
                try:
                    target.unlink()
                except FileNotFoundError:
                    pass
                except PermissionError:
                    pass  # leftover copy still running; reuse it
                if not target.exists():
                    shutil.copy2(src, target)
                if src.name.lower() == "pythonw.exe":
                    for dll in Path(sys.base_prefix).glob("*.dll"):
                        dst = target.parent / dll.name
                        if not dst.exists():
                            shutil.copy2(dll, dst)
                env = os.environ.copy()
                env.update(extra_env)
                if visible:
                    # Same as a manual `start`: a real console window (optionally minimized)
                    si = None
                    if minimize:
                        si = subprocess.STARTUPINFO()
                        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        si.wShowWindow = 7  # SW_SHOWMINNOACTIVE
                    p = subprocess.Popen([str(target), *args], cwd=str(target.parent), env=env,
                                         creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=si)
                else:
                    p = subprocess.Popen(
                        [str(target), *args], cwd=str(target.parent), env=env,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                time.sleep(1.2)
                if p.poll() is None:
                    self.dummy_info = f"PID {p.pid}, {target}"
                    log(f"launched {self.dummy_info}")
                    return p
                errors.append(f"{src.name} exited immediately")
            except Exception as e:  # noqa
                errors.append(f"{src.name}: {e}")
        log("launch failed: " + "; ".join(errors))
        raise RuntimeError("Couldn't start placeholder process (" + "; ".join(errors) + ")")

    # ---- keepalive / stop
    def _ping(self):
        try:
            self.rpc.update(**self.payload)
            self.last_ping = time.time()
        except Exception:
            self._close()
            self._error("err_lost")

    def _stop_session(self, code: str):
        self._close()
        self.bus.put(("stopped",))
        self.bus.put(("status", "idle", code, None))

    def _close(self):
        if self.rpc:
            try:
                self.rpc.clear()
            except Exception:
                pass
            try:
                self.rpc.close()
            except Exception:
                pass
        if self.proc:
            self._kill(self.proc)
        self.rpc = self.proc = None
        self.end_at = None

    @staticmethod
    def _kill(p: subprocess.Popen):
        def send(sig):
            if C.IS_LINUX:
                try:
                    os.killpg(p.pid, sig)
                except ProcessLookupError:
                    pass
            elif sig == signal.SIGTERM:
                p.terminate()
            else:
                p.kill()
        try:
            send(signal.SIGTERM)
            p.wait(timeout=3)
        except Exception:
            try:
                send(getattr(signal, "SIGKILL", signal.SIGTERM))
            except Exception:
                pass

    def _error(self, code: str, detail=None):
        self.bus.put(("stopped",))
        self.bus.put(("status", "error", code, detail))

    def _fail(self, e: Exception):
        name = type(e).__name__
        if name == "DiscordNotFound":
            self._error("err_no_discord")
        elif name == "InvalidID":
            self._error("err_bad_id")
        else:
            self._error("err_raw", f"{name}: {e}")
