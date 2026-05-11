from __future__ import annotations

import shutil
import sys


class TerminalContext:
    def __init__(self) -> None:
        self._size_cache: tuple[int, int] | None = None
        self.has_utf8 = sys.stdout.encoding and sys.stdout.encoding.lower() in ("utf-8", "utf8")

    def get_size(self) -> tuple[int, int]:
        if self._size_cache is None:
            self._size_cache = shutil.get_terminal_size(fallback=(120, 40))
        return self._size_cache

    def clear_cache(self) -> None:
        self._size_cache = None


TERMINAL = TerminalContext()
