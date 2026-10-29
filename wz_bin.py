"""Binary resolver used by BinConfig.

The original deployment shipped a compiled ``wz_bin`` helper. This pure-Python
replacement looks binaries up in a local ``bin/`` folder, then on PATH, and
returns a plain executable name when nothing is found so callers can still
report a clear "not found" error.

Override any binary with an environment variable, e.g.
``ARIA2C_BIN=/usr/local/bin/aria2c python main.py``.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_BIN_DIR = Path(os.getenv("WZ_BIN_DIR") or Path(__file__).resolve().parent / "bin")
_EXE = ".exe" if sys.platform == "win32" else ""

# index -> (base name, env override)
_BINARIES = {
    0: ("aria2c", "ARIA2C_BIN"),
    1: ("qbittorrent-nox", "QBIT_BIN"),
    2: ("ffmpeg", "FFMPEG_BIN"),
    3: ("rclone", "RCLONE_BIN"),
    4: ("sabnzbdplus", "SABNZBD_BIN"),
}


def _resolve(name: str, env_key: str) -> str:
    override = (os.getenv(env_key) or "").strip()
    if override:
        return override

    for candidate in (name + _EXE, name):
        local = _BIN_DIR / candidate
        if local.is_file() and os.access(local, os.X_OK):
            return str(local)
        found = shutil.which(candidate)
        if found:
            return found

    # Last resort: let the OS resolve it and raise a normal FileNotFoundError.
    return name + _EXE


def bin_name(index: int) -> str:
    try:
        name, env_key = _BINARIES[int(index)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Unknown binary index: {index!r}") from exc
    return _resolve(name, env_key)
