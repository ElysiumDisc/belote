"""Single source of truth for where belote keeps files on disk.

Data (stats, BelAtro profile, run history, ghosts):
  * Windows: ``%APPDATA%\\belote``
  * otherwise: ``$XDG_DATA_HOME/belote``, else ``~/.local/share/belote``

Config (theme selection):
  * Windows: ``%APPDATA%\\belote``
  * otherwise: ``$XDG_CONFIG_HOME/belote``, else ``~/.config/belote``

Paths are resolved from the live environment on every call (tests redirect
them with ``monkeypatch.setenv``). Nothing here creates directories; writers
``mkdir`` at write time.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "belote"


def _is_windows() -> bool:
    # Indirection so tests can exercise the Windows branch without patching
    # os.name globally (pathlib picks its flavour from it).
    return os.name == "nt"


def _base(xdg_var: str, posix_default: Path) -> Path:
    appdata = os.environ.get("APPDATA")
    if _is_windows() and appdata:
        return Path(appdata)
    xdg = os.environ.get(xdg_var)
    return Path(xdg) if xdg else posix_default


def data_dir(app_name: str = APP_NAME) -> Path:
    """Directory for persistent game data (not created)."""
    return _base("XDG_DATA_HOME", Path.home() / ".local" / "share") / app_name


def config_dir(app_name: str = APP_NAME) -> Path:
    """Directory for user configuration (not created)."""
    return _base("XDG_CONFIG_HOME", Path.home() / ".config") / app_name
