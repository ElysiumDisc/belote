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
    TAB = "TAB"
    ESC = "ESC"
    SPACE = "SPACE"
    CHAR = "CHAR"
    QUIT = "QUIT"
    HELP = "HELP"
    SORT = "SORT"
    MUTE = "MUTE"
    THEME = "THEME"
    HIST = "HIST"
    OVERLAY = "OVERLAY"


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
            self._old_termios = None
        return self

    def __exit__(self, *args: Any) -> None:
        self.restore()

    def restore(self) -> None:
        if self._old_termios and not self._restored:
            termios.tcsetattr(self._stdin_fd, termios.TCSADRAIN, self._old_termios)
            self._restored = True

    def read(self) -> KeyEvent:
        """Read a single key (handling escape sequences and multi-byte UTF-8)."""
        # Read the first byte
        buf = os.read(self._stdin_fd, 1)
        if not buf:
            return KeyEvent(Key.ESC)

        byte = buf[0]

        # Escape sequence
        if byte == 0x1B:
            # Check if more data is available immediately (for sequences)
            r, _, _ = select.select([sys.stdin], [], [], 0.01)
            if not r:
                return KeyEvent(Key.ESC)
            
            next_byte = os.read(self._stdin_fd, 1)
            if next_byte == b"[":
                # Likely an arrow key
                code_byte = os.read(self._stdin_fd, 1)
                match code_byte:
                    case b"A": return KeyEvent(Key.UP)
                    case b"B": return KeyEvent(Key.DOWN)
                    case b"C": return KeyEvent(Key.RIGHT)
                    case b"D": return KeyEvent(Key.LEFT)
            return KeyEvent(Key.ESC)

        # Enter
        if byte in (0x0A, 0x0D):
            return KeyEvent(Key.ENTER)

        # Tab
        if byte == 0x09:
            return KeyEvent(Key.TAB)

        # Space
        if byte == 0x20:
            return KeyEvent(Key.SPACE)

        # Multi-byte UTF-8 handling
        if byte >= 0x80:
            # Determine how many bytes to read based on UTF-8 encoding
            if (byte & 0xE0) == 0xC0: n = 1
            elif (byte & 0xF0) == 0xE0: n = 2
            elif (byte & 0xF8) == 0xF0: n = 3
            else: return KeyEvent(Key.ESC)
            
            full_buf = bytes([byte])
            while len(full_buf) < n + 1:
                chunk = os.read(self._stdin_fd, n + 1 - len(full_buf))
                if not chunk: break
                full_buf += chunk

            try:
                ch = full_buf.decode("utf-8")
                return KeyEvent(Key.CHAR, ch)
            except Exception:
                return KeyEvent(Key.ESC)

        # Printable character
        try:
            ch = chr(byte)
            if ch.lower() == "q":
                return KeyEvent(Key.QUIT)
            if ch.lower() == "h":
                return KeyEvent(Key.HELP)
            if ch.lower() == "s":
                return KeyEvent(Key.SORT)
            if ch.lower() == "m":
                return KeyEvent(Key.MUTE)
            if ch.lower() == "t":
                return KeyEvent(Key.HIST)
            if ch.lower() == "v":
                return KeyEvent(Key.OVERLAY)

            return KeyEvent(Key.CHAR, ch)
        except Exception:
            return KeyEvent(Key.ESC)


def interruptible_sleep(seconds: float, reader: KeyReader | None = None) -> KeyEvent | None:
    """Sleep for some time, but return immediately if a key is pressed."""
    start = time.time()
    while time.time() - start < seconds:
        if reader:
            # Check if input is available
            r, _, _ = select.select([sys.stdin], [], [], 0.05)
            if r:
                return reader.read()
        else:
            time.sleep(0.05)
    return None


class KeyReader:
    """Stub for type hinting."""

    def __enter__(self) -> KeyReader: ...
    def __exit__(self, *args: Any) -> None: ...
    def read_key(self) -> KeyEvent: ...


if os.name == "nt":

    class _WindowsKeyReader:
        def __enter__(self) -> _WindowsKeyReader:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def read_key(self) -> KeyEvent:
            import msvcrt  # type: ignore[import-not-found]

            ch = msvcrt.getch()
            if ch in (b"\x00", b"\xe0"):
                ch = msvcrt.getch()
                match ch:
                    case b"H":
                        return KeyEvent(Key.UP)
                    case b"P":
                        return KeyEvent(Key.DOWN)
                    case b"M":
                        return KeyEvent(Key.RIGHT)
                    case b"K":
                        return KeyEvent(Key.LEFT)
            if ch in (b"\r", b"\n"):
                return KeyEvent(Key.ENTER)
            if ch == b"\t":
                return KeyEvent(Key.TAB)
            if ch == b" ":
                return KeyEvent(Key.SPACE)
            if ch.lower() == b"q":
                return KeyEvent(Key.QUIT)

            try:
                char = ch.decode("utf-8")
                return KeyEvent(Key.CHAR, char)
            except Exception:
                return KeyEvent(Key.ESC)

    KeyReader = _WindowsKeyReader  # type: ignore[misc, assignment]
else:
    KeyReader = _UnixKeyReader
