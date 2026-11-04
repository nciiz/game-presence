"""Game model and name helpers."""

import re
from dataclasses import dataclass, field
from typing import Optional

from . import config as C


def norm(s: str) -> str:
    """Lower-case and strip everything except a-z0-9, for fuzzy name matching."""
    s = s.lower()
    s = re.sub(r"[™®©]", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def exe_relpath(name: str) -> Optional[list]:
    """Turn a detectable-list executable name into safe relative path parts."""
    n = name.lstrip(">").replace("\\", "/")
    parts = [p for p in n.split("/") if p]
    if not parts or any(p in (".", "..") or ":" in p for p in parts):
        return None
    return parts


@dataclass
class Game:
    name: str
    client_id: str
    icon: Optional[str] = None
    executables: list = field(default_factory=list)

    def proc_exe(self) -> Optional[dict]:
        """The executable entry to imitate on this OS (Linux: native first, then Wine/Proton .exe)."""
        order = ["win32"] if C.IS_WIN else (["linux", "win32"] if C.IS_LINUX else [])
        for os_name in order:
            for e in self.executables:
                if (e.get("os") == os_name and not e.get("is_launcher") and e.get("name")
                        and exe_relpath(e["name"])):
                    return e
        return None
