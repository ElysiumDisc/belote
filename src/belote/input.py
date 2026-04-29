from __future__ import annotations

import contextlib
import os
import select
import sys
import termios
import time
import tty
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Key(Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    UP = "UP"
    DOWN = "DOWN"
    ENTER = "ENTER"
    ESC = "ESC"
    SPACE = "SPACE"
    CHAR = "CHAR"
    QUIT = "QUIT"
    HELP = "HELP"
    SORT = "SORT"
    MUTE = "MUTE"
    THEME = "THEME"
    HIST = "HIST"


@dataclass(frozen=True, slots=True)
class KeyEvent:
    key: Key
    char: str | None = None


class _UnixKeyReader:
    """Context manager that sets up raw input and provides blocking read."""

    def __init__(self) -> None:
        self._old_termios: list[Any] | None = None
        self._stdin_fd: int = sys.stdin.fileno()
        self._restored: bool = False

    def __enter__(self) -> _UnixKeyReader:
        try:
            self._old_termios = termios.tcgetattr(self._stdin_fd)
            tty.setraw(self._stdin_fd)
        except termios.error:
            # Fallback if not a TTY (e.g. testing)
            self._old_termios = None
        return self

    def __exit__(self, *exc: object) -> None:
        self.restore()

    def restore(self) -> None:
        if not self._restored and self._old_termios is not None:
            self._restored = True
            with contextlib.suppress(Exception):
                termios.tcsetattr(
                    self._stdin_fd,
                    termios.TCSAFLUSH,
                    self._old_termios,
                )

    def read(self) -> KeyEvent:
        """Blocking read of a single key event."""
        result = self.read_timeout(None)
        return result if result is not None else KeyEvent(Key.QUIT)

    def read_timeout(self, timeout: float | None = None) -> KeyEvent | None:
        """Read a single key event with an optional timeout."""
        ready = select.select([self._stdin_fd], [], [], timeout)
        if not ready[0]:
            return None

        # Read first byte
        try:
            buf = os.read(self._stdin_fd, 1)
        except (EOFError, OSError):
            return KeyEvent(Key.QUIT)

        if not buf:
            return KeyEvent(Key.QUIT)

        byte = buf[0]

        # Accumulate remaining bytes for multi-byte UTF-8 sequences
        # 0xC0-0xDF → 2-byte, 0xE0-0xEF → 3-byte, 0xF0-0xF7 → 4-byte
        if byte >= 0xC0:
            if byte < 0xE0:
                extra = 1
            elif byte < 0xF0:
                extra = 2
            else:
                extra = 3
            for _ in range(extra):
                ready = select.select([self._stdin_fd], [], [], 0.05)
                if ready[0]:
                    try:
                        buf += os.read(self._stdin_fd, 1)
                    except (EOFError, OSError):
                        break

        # ESC sequence
        if byte == 0x1B:
            # Peek with timeout to distinguish ESC alone vs ESC sequence
            ready = select.select([self._stdin_fd], [], [], 0.1)
            if ready[0]:
                second = os.read(self._stdin_fd, 1)
                if second and second[0] == 0x5B:  # '['
                    ready = select.select([self._stdin_fd], [], [], 0.1)
                    if ready[0]:
                        third = os.read(self._stdin_fd, 1)
                        if third:
                            code = third[0]
                            if code == 0x41:  # 'A'
                                return KeyEvent(Key.UP)
                            if code == 0x42:  # 'B'
                                return KeyEvent(Key.DOWN)
                            if code == 0x43:  # 'C'
                                return KeyEvent(Key.RIGHT)
                            if code == 0x44:  # 'D'
                                return KeyEvent(Key.LEFT)
            return KeyEvent(Key.ESC)

        # Enter
        if byte in (0x0A, 0x0D):
            return KeyEvent(Key.ENTER)

        # Tab
        if byte == 0x09:
            return KeyEvent(Key.ENTER)

        # Space
        if byte == 0x20:
            return KeyEvent(Key.SPACE)

        # Printable character
        try:
            ch = buf.decode("utf-8", errors="replace")
            if ch.lower() == 'q':
                return KeyEvent(Key.QUIT)
            if ch == '?':
                return KeyEvent(Key.HELP)
            if ch == 'T':
                return KeyEvent(Key.THEME)
            if ch == 't':
                return KeyEvent(Key.HIST)
            if ch.lower() == 'h':
                return KeyEvent(Key.HELP)
            if ch.lower() == 'o':
                return KeyEvent(Key.SORT)
            if ch.lower() == 'm':
                return KeyEvent(Key.MUTE)
            return KeyEvent(Key.CHAR, ch)
        except Exception:
            return KeyEvent(Key.CHAR, chr(byte))


def interruptible_sleep(duration: float, reader: KeyReader) -> bool:
    """Sleep for duration, but return True if interrupted by Space/Esc."""
    if duration <= 0:
        return False

    end = time.time() + duration
    while True:
        remaining = end - time.time()
        if remaining <= 0:
            break
        event = reader.read_timeout(remaining)
        if event:
            if event.key in (Key.SPACE, Key.ESC):
                return True
            # For other keys, we continue sleeping if there's time left
        else:
            # Timeout reached
            break
    return False



# OS-specific reader selection
if sys.platform == "win32":
    import msvcrt  # type: ignore[import-not-found]

    class _WindowsKeyReader:  # noqa: N801
        def __enter__(self) -> _WindowsKeyReader:
            return self

        def __exit__(self, *exc: object) -> None:
            pass

        def restore(self) -> None:
            pass

        def read(self) -> KeyEvent:
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                ch2 = msvcrt.getwch()
                match ch2:
                    case "H":
                        return KeyEvent(Key.UP)
                    case "P":
                        return KeyEvent(Key.DOWN)
                    case "K":
                        return KeyEvent(Key.LEFT)
                    case "M":
                        return KeyEvent(Key.RIGHT)
                return KeyEvent(Key.CHAR, ch2)
            if ch == "\r":
                return KeyEvent(Key.ENTER)
            if ch == "\x1b":
                return KeyEvent(Key.ESC)
            if ch == " ":
                return KeyEvent(Key.SPACE)
            return KeyEvent(Key.CHAR, ch)

    KeyReader = _WindowsKeyReader  # type: ignore[misc, assignment]
else:
    KeyReader = _UnixKeyReader
