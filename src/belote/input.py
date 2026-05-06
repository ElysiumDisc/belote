from __future__ import annotations

import os
import select
import sys
import termios
import time
import tty
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast


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
            # 50ms is the conventional ESC vs. arrow-key disambiguation
            # window. 10ms (the previous value) was tight enough that arrow
            # keys over SSH or in slow terminals could be mis-classified as
            # bare ESC presses.
            r, _, _ = select.select([sys.stdin], [], [], 0.05)
            if not r:
                return KeyEvent(Key.ESC)

            next_byte = os.read(self._stdin_fd, 1)
            if next_byte == b"[":
                # Likely an arrow key
                code_byte = os.read(self._stdin_fd, 1)
                match code_byte:
                    case b"A":
                        return KeyEvent(Key.UP)
                    case b"B":
                        return KeyEvent(Key.DOWN)
                    case b"C":
                        return KeyEvent(Key.RIGHT)
                    case b"D":
                        return KeyEvent(Key.LEFT)
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
            # Number of UTF-8 continuation bytes that follow the leading byte.
            if (byte & 0xE0) == 0xC0:
                continuation_bytes = 1
            elif (byte & 0xF0) == 0xE0:
                continuation_bytes = 2
            elif (byte & 0xF8) == 0xF0:
                continuation_bytes = 3
            else:
                return KeyEvent(Key.ESC)

            total_bytes = continuation_bytes + 1
            full_buf = bytes([byte])
            while len(full_buf) < total_bytes:
                # Bound the wait for the rest of a multi-byte UTF-8 sequence:
                # an unterminated leading byte (paste of garbage, killed
                # remote, etc.) used to block the reader forever.
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
                if not r:
                    break
                chunk = os.read(self._stdin_fd, total_bytes - len(full_buf))
                if not chunk:
                    break
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
            if ch.lower() == "i" or ch.lower() == "v":
                return KeyEvent(Key.OVERLAY)

            return KeyEvent(Key.CHAR, ch)
        except Exception:
            return KeyEvent(Key.ESC)

    def read_timeout(self, timeout: float) -> KeyEvent | None:
        """Read a key with a timeout. Returns None if no key is pressed."""
        r, _, _ = select.select([sys.stdin], [], [], timeout)
        if r:
            return self.read()
        return None

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
    """Polymorphic base + factory.

    `KeyReader()` returns a fully-constructed concrete platform reader
    (`_UnixKeyReader` or `_WindowsKeyReader`). The concrete classes don't
    inherit from `KeyReader` (they were defined that way historically); we
    therefore call them as plain factories and skip the `KeyReader.__init__`
    machinery entirely. Type-checks treat the result as `KeyReader`.
    """

    _restored: bool = False

    def __new__(cls, *args: Any, **kwargs: Any) -> KeyReader:
        if cls is KeyReader:
            # Construct the concrete reader fully (its own __new__ + __init__
            # run); cast for the caller's type narrowing.
            if os.name == "nt":
                return cast(KeyReader, _WindowsKeyReader())
            return cast(KeyReader, _UnixKeyReader())
        return super().__new__(cls)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # When __new__ returned a concrete reader (not a KeyReader instance),
        # Python skips this __init__ — the concrete class's __init__ already ran.
        # When called on a real KeyReader subclass, this is a no-op.
        return

    def __enter__(self) -> KeyReader:
        raise NotImplementedError

    def __exit__(self, *args: Any) -> None:
        raise NotImplementedError

    def read(self) -> KeyEvent:
        raise NotImplementedError

    def read_timeout(self, timeout: float) -> KeyEvent | None:
        raise NotImplementedError

    def restore(self) -> None:
        """Restore terminal state. No-op on platforms that don't need it."""


# `_UnixKeyReader` and `_WindowsKeyReader` are structurally compatible with
# `KeyReader`; we don't make them subclass it to avoid `__new__` recursion.

if os.name == "nt":

    class _WindowsKeyReader:
        _restored: bool = False

        def __enter__(self) -> _WindowsKeyReader:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def restore(self) -> None:
            self._restored = True

        def read(self) -> KeyEvent:
            import msvcrt

            ch: bytes = msvcrt.getch()  # type: ignore[attr-defined]
            if ch in (b"\x00", b"\xe0"):
                ch = msvcrt.getch()  # type: ignore[attr-defined]
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
            if ch.lower() == b"h":
                return KeyEvent(Key.HELP)
            if ch.lower() == b"s":
                return KeyEvent(Key.SORT)
            if ch.lower() == b"m":
                return KeyEvent(Key.MUTE)
            if ch.lower() == b"t":
                return KeyEvent(Key.HIST)
            if ch.lower() in (b"i", b"v"):
                return KeyEvent(Key.OVERLAY)

            try:
                char = ch.decode("utf-8")
                return KeyEvent(Key.CHAR, char)
            except Exception:
                return KeyEvent(Key.ESC)

        def read_timeout(self, timeout: float) -> KeyEvent | None:
            import msvcrt

            start = time.time()
            while time.time() - start < timeout:
                if msvcrt.kbhit():  # type: ignore[attr-defined]
                    return self.read()
                time.sleep(0.01)
            return None
