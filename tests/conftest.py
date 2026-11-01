"""Suite-wide test isolation.

`belote.themes.theme_manager` reads ``~/.config/belote/theme.json`` at import
time and ``set_current()`` writes it back; stats, saves, run summaries and
ghost runs live under ``$XDG_DATA_HOME`` / ``~/.local/share``. Without this
file the suite (a) renders with whatever theme the developer last picked, so
golden snapshots only pass on the machine that pinned them, and (b) writes into
the developer's real config/data directories.

This runs at conftest import — before any test module imports ``belote`` — so
the redirected HOME is in place when the theme singleton is constructed.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_SANDBOX = Path(tempfile.mkdtemp(prefix="belote-test-home-"))
os.environ["HOME"] = str(_SANDBOX)
os.environ["XDG_CONFIG_HOME"] = str(_SANDBOX / ".config")
os.environ["XDG_DATA_HOME"] = str(_SANDBOX / ".local" / "share")
os.environ.pop("NO_COLOR", None)
