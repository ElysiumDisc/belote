from __future__ import annotations

import os
import select
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

# termios/tty are Unix-only; importing them unconditionally made the module
# (and so the whole game) unimportable on Windows even though a
# `_WindowsKeyReader` exists. `select` stays top-level: the module exists on
# Windows too, it just only works on sockets there (see interruptible_sleep).
if sys.platform != "win32":
    import termios
    import tty


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
    THEME = "THEME"
    HIST = "HIST"
    OVERLAY = "OVERLAY"
    # 4.7.0: the V key was a duplicate of I (both Key.OVERLAY). Split so V
    # opens the BelAtro inventory overlay (jokers / vouchers / consumables /
    # permanent bonuses / contract levels) while I keeps its existing top-HUD
    # toggle role. Wired in `belote/ui/prompts.py::prompt_card` and consumed
    # by `belote/belatro/main.py::UICallbacks._show_inventory`.
    INVENTORY = "INVENTORY"
    # End-of-file on stdin (closed pipe, headless harness, Ctrl-D on a real
    # tty). Distinct from ESC so the outermost game loops can recognise a
    # closed input stream and exit cleanly instead of spinning through
    # menu-pop reads. Most prompt loops treat EOF like ESC ("back/cancel"),
    # which is fine because the next read() will return EOF again and propagate.
    EOF = "EOF"
    # An escape sequence we parsed but don't bind (F-keys, Delete, PgUp,
    # Ctrl+arrows, ...). Consumed whole so its trailing bytes don't leak as
    # keystrokes, and distinct from ESC because ESC means "back" in most
    # screens. Prompt loops ignore it; "[Any Key]" screens treat it as a key.
    UNKNOWN = "UNKNOWN"
    # 5.0.0: a left-button click (SGR mouse mode); `KeyEvent.pos` holds the
    # 1-based (col, row). Screens hit-test it via `ui.hitmap`; the wheel
    # arrives as UP / DOWN.
    MOUSE = "MOUSE"


@dataclass(frozen=True, slots=True)
class KeyEvent:
    key: Key
    char: str | None = None
    pos: tuple[int, int] | None = None  # (col, row) of a Key.MOUSE click


# ── 5.0.0: mouse ──────────────────────────────────────────────────────────
# Settings → Mouse (BELOTE_NO_MOUSE=1 forces off). The Unix reader turns
# terminal mouse reporting on while it is active and off on restore;
# `set_mouse_enabled` flips it live from the Settings screen.
_mouse_wanted = True
_active_unix_reader: _UnixKeyReader | None = None


def set_mouse_enabled(on: bool) -> None:
    global _mouse_wanted
    _mouse_wanted = on
    if _active_unix_reader is not None:
        _active_unix_reader.set_mouse(on)


def mouse_enabled() -> bool:
    return _mouse_wanted


_MOUSE_WHEEL: dict[int, Key] = {64: Key.UP, 65: Key.DOWN}


def parse_sgr_mouse(params: bytes, final: bytes) -> KeyEvent | None:
    """An SGR mouse report (`ESC [ < b ; col ; row M|m`, params without the
    leading `<`) → a click / wheel event, or None for reports screens ignore
    (releases, motion, right / middle buttons, malformed)."""
    try:
        button, col, row = (int(p) for p in params.decode("ascii").split(";"))
    except ValueError:
        return None
    if final != b"M" or button & 32:  # a release, or motion
        return None
    base = button & ~(4 | 8 | 16)  # drop the Shift / Alt / Ctrl bits
    wheel = _MOUSE_WHEEL.get(base)
    if wheel is not None:
        return KeyEvent(wheel)
    if base == 0 and col > 0 and row > 0:
        return KeyEvent(Key.MOUSE, pos=(col, row))
    return None


# Single-character shortcuts shared by the Unix and Windows readers (they used
# to keep separate if/elif chains that drifted). Case-insensitive. WASD nav
# aliases (4.5.0) are mapped at the reader so every selection screen inherits
# them; the bid prompt's quick keys moved to X/N to make room.
#
# 4.11.0: rebindable (Settings → Controls). `CHAR_ALIASES` is the *live*
# table — `set_bindings` rewrites it in place, so importers see the change.
CHAR_ALIASES: dict[str, Key] = {
    "w": Key.UP,
    "a": Key.LEFT,
    "s": Key.DOWN,
    "d": Key.RIGHT,
    "q": Key.QUIT,
    "?": Key.HELP,
    "h": Key.HIST,
    "t": Key.THEME,
    "o": Key.SORT,
    "i": Key.OVERLAY,
    "v": Key.INVENTORY,
}


@dataclass(frozen=True, slots=True)
class Binding:
    """A rebindable single-character action.

    `key` actions become that `Key` (typed char kept in `char`). Undo has no
    `Key`: the prompts recognise the typed letter "z" (`canonical`), so a
    rebound undo key is delivered as ``KeyEvent(Key.CHAR, "z")``.
    """

    action: str
    label: str
    default: str
    key: Key | None = None
    canonical: str | None = None


BINDINGS: tuple[Binding, ...] = (
    Binding("help", "Help", "?", Key.HELP),
    Binding("quit", "Quit", "q", Key.QUIT),
    Binding("history", "Round history", "h", Key.HIST),
    Binding("theme", "Cycle theme", "t", Key.THEME),
    Binding("sort", "Sort hand", "o", Key.SORT),
    Binding("overlay", "HUD overlay (BelAtro)", "i", Key.OVERLAY),
    Binding("inventory", "Inventory (BelAtro)", "v", Key.INVENTORY),
    Binding("undo", "Undo", "z", canonical="z"),
    Binding("up", "Move up", "w", Key.UP),
    Binding("left", "Move left", "a", Key.LEFT),
    Binding("down", "Move down", "s", Key.DOWN),
    Binding("right", "Move right", "d", Key.RIGHT),
)
_BINDING_BY_ACTION: dict[str, Binding] = {b.action: b for b in BINDINGS}
DEFAULT_BINDINGS: dict[str, str] = {b.action: b.default for b in BINDINGS}

# Letters that prompts read as typed characters. Binding one to an action
# would steal it from that prompt, so only its own default action may hold
# it (S stays DOWN and A stays LEFT: those prompts check `typed()` first).
RESERVED_KEYS: dict[str, str] = {
    "a": "Activate (BelAtro inventory)",
    "c": "Coinche / consumables",
    "l": "Rules language",
    "n": "Sans Atout bid / No",
    "p": "Pass (bidding)",
    "s": "Surcoinche / Sell",
    "x": "Tout Atout bid",
    "y": "Yes",
    "z": "Undo",
}

# Undo remap: typed key → the letter the prompts expect. Empty by default.
_CHAR_REMAP: dict[str, str] = {}
# Default letters whose action moved away and that would otherwise still be
# read as that action by the prompts (undo's "z"): delivered as UNKNOWN.
_SILENCED: set[str] = set()
# Settings → Controls captures a raw key while this is set.
_raw_capture = False


def check_binding(action: str, key: str, bindings: dict[str, str]) -> str | None:
    """Why `action` can't be bound to `key` given the other `bindings`, or
    None if it can. Keys are single printable ASCII characters; digits and
    space are quick-select keys; arrows / Enter / Esc are never rebindable."""
    binding = _BINDING_BY_ACTION.get(action)
    if binding is None:
        return f"Unknown action {action!r}"
    k = key.lower()
    if len(k) != 1 or not k.isascii() or not k.isprintable() or k == " ":
        return "Use a single letter or symbol key"
    if k.isdigit():
        return f"{k.upper()} is reserved for quick select"
    if k in RESERVED_KEYS and k != binding.default:
        return f"{k.upper()} is reserved for {RESERVED_KEYS[k]}"
    for other, other_key in bindings.items():
        if other != action and other_key == k:
            return f"{k.upper()} is already used by {_BINDING_BY_ACTION[other].label}"
    return None


def validate_bindings(overrides: dict[str, str]) -> str | None:
    """Error for the first invalid entry of `overrides` (merged over the
    defaults), or None when the whole map is usable."""
    merged = {**DEFAULT_BINDINGS, **{a: k.lower() for a, k in overrides.items()}}
    for action, key in merged.items():
        err = check_binding(action, key, merged)
        if err is not None:
            return err
    return None


def set_bindings(overrides: dict[str, str]) -> None:
    """Install `overrides` (action → key, merged over `DEFAULT_BINDINGS`) as
    the live alias table. Raises ValueError (and changes nothing) if invalid."""
    err = validate_bindings(overrides)
    if err is not None:
        raise ValueError(err)
    merged = {**DEFAULT_BINDINGS, **{a: k.lower() for a, k in overrides.items()}}
    CHAR_ALIASES.clear()
    _CHAR_REMAP.clear()
    _SILENCED.clear()
    for b in BINDINGS:
        k = merged[b.action]
        if b.key is not None:
            CHAR_ALIASES[k] = b.key
        elif b.canonical is not None and k != b.canonical:
            _CHAR_REMAP[k] = b.canonical
            _SILENCED.add(b.canonical)


def current_bindings() -> dict[str, str]:
    """The live action → key map."""
    out: dict[str, str] = {}
    for b in BINDINGS:
        if b.key is not None:
            out[b.action] = next((c for c, k in CHAR_ALIASES.items() if k is b.key), "")
        else:
            out[b.action] = next(
                (c for c, canon in _CHAR_REMAP.items() if canon == b.canonical), b.default
            )
    return out


def key_label(action: str) -> str:
    """Display label of the key bound to `action` ("Q", "?") — for help text."""
    return current_bindings().get(action, "").upper()


class raw_capture:  # noqa: N801 — used like a function: `with raw_capture():`
    """While active, `char_event` skips every alias / remap (Settings →
    Controls reads the literal key the player presses)."""

    def __enter__(self) -> None:
        global _raw_capture
        _raw_capture = True

    def __exit__(self, *_args: object) -> None:
        global _raw_capture
        _raw_capture = False


def char_event(ch: str) -> KeyEvent:
    """Map a decoded printable character to its event (alias or plain CHAR).

    4.11.0: aliased events keep the typed character in `char`, so a screen
    with a letter hotkey that is also an alias (S=surcoinche/sell vs S=DOWN,
    A=activate vs A=LEFT) can tell the letter from the arrow key. Check
    `typed(event, "s")` for those, before the navigation branches. A rebound
    undo key arrives as CHAR "z" (what the prompts check); "z" itself is then
    UNKNOWN.
    """
    if _raw_capture:
        return KeyEvent(Key.CHAR, ch)
    low = ch.lower()
    key = CHAR_ALIASES.get(low)
    if key is not None:
        return KeyEvent(key, ch)
    if _CHAR_REMAP:
        canon = _CHAR_REMAP.get(low)
        if canon is not None:
            return KeyEvent(Key.CHAR, canon)
        if low in _SILENCED:
            return KeyEvent(Key.UNKNOWN, ch)
    return KeyEvent(Key.CHAR, ch)


def typed(event: KeyEvent, letter: str) -> bool:
    """True if `event` came from typing `letter` (either case), whether or
    not that letter is also a navigation alias. Arrow keys never match."""
    return event.char is not None and event.char.lower() == letter


# Final bytes shared by CSI (ESC [ X) and SS3 (ESC O X) cursor keys.
_ARROW_FINALS: dict[bytes, Key] = {
    b"A": Key.UP,
    b"B": Key.DOWN,
    b"C": Key.RIGHT,
    b"D": Key.LEFT,
}


# Single control bytes under raw mode. Ctrl-C arrives as a plain 0x03 (ISIG
# is off), so it is "quit" rather than an unbound control character.
_CONTROL_BYTES: dict[int, Key] = {
    0x03: Key.QUIT,
    0x0A: Key.ENTER,
    0x0D: Key.ENTER,
    0x09: Key.TAB,
    0x20: Key.SPACE,
}


def _utf8_continuations(lead: int) -> int | None:
    """Continuation bytes after a UTF-8 leading byte, or None if invalid."""
    if (lead & 0xE0) == 0xC0:
        return 1
    if (lead & 0xF0) == 0xE0:
        return 2
    if (lead & 0xF8) == 0xF0:
        return 3
    return None


class _UnixKeyReader:
    """Context manager that sets up raw input and provides blocking read."""

    def __init__(self) -> None:
        self._old_termios: list[Any] | None = None
        self._stdin_fd: int = sys.stdin.fileno()
        self._restored: bool = False
        self._mouse_on: bool = False

    def __enter__(self) -> _UnixKeyReader:
        global _active_unix_reader
        try:
            self._old_termios = termios.tcgetattr(self._stdin_fd)
            tty.setraw(self._stdin_fd)
        except termios.error:
            self._old_termios = None
        _active_unix_reader = self
        self.set_mouse(_mouse_wanted)
        return self

    def __exit__(self, *args: Any) -> None:
        self.restore()

    def set_mouse(self, on: bool) -> None:
        """Switch terminal mouse reporting (only on a real terminal)."""
        from .ansi import mouse_off, mouse_on

        if on == getattr(self, "_mouse_on", False) or self._old_termios is None:
            return
        import contextlib

        with contextlib.suppress(OSError, ValueError):
            sys.stdout.write(mouse_on() if on else mouse_off())
            sys.stdout.flush()
            self._mouse_on = on

    def restore(self) -> None:
        global _active_unix_reader
        self.set_mouse(False)
        if _active_unix_reader is self:
            _active_unix_reader = None
        if self._old_termios and not self._restored:
            # A dropped SSH session / broken pipe can make tcsetattr raise.
            # We swallow the error and mark restored anyway so a re-entrant
            # restore() (e.g. from __exit__ after a prior failed restore) is
            # a no-op rather than another raise.
            import contextlib

            with contextlib.suppress(termios.error, OSError):
                termios.tcsetattr(self._stdin_fd, termios.TCSADRAIN, self._old_termios)
            self._restored = True

    def read(self) -> KeyEvent:
        """Read a single key (handling escape sequences and multi-byte UTF-8).
        Mouse reports screens ignore (button releases, motion) are skipped."""
        while True:
            event = self._read_one()
            if event is not None:
                return event

    def _read_one(self) -> KeyEvent | None:
        buf = os.read(self._stdin_fd, 1)
        if not buf:
            # EOF — stdin is closed (broken pipe, headless harness, Ctrl-D).
            # Distinct from ESC so callers can react differently if needed.
            return KeyEvent(Key.EOF)

        byte = buf[0]
        if byte == 0x1B:
            return self._read_escape()
        control = _CONTROL_BYTES.get(byte)
        if control is not None:
            return KeyEvent(control)
        if byte >= 0x80:
            return self._read_utf8(byte)
        # Printable character
        try:
            return char_event(chr(byte))
        except (ValueError, UnicodeDecodeError):
            return KeyEvent(Key.ESC)

    def _read_escape(self) -> KeyEvent | None:
        """After ESC: a bare ESC, a CSI / SS3 sequence, or ESC + junk."""
        # 50ms is the conventional ESC vs. arrow-key disambiguation window.
        # 10ms (the previous value) was tight enough that arrow keys over SSH
        # or in slow terminals could be mis-classified as bare ESC presses.
        r, _, _ = select.select([sys.stdin], [], [], 0.05)
        if not r:
            return KeyEvent(Key.ESC)
        next_byte = os.read(self._stdin_fd, 1)
        if next_byte == b"[":
            return self._read_csi()
        if next_byte == b"O":
            # SS3: ESC O <final>. Application-cursor-mode arrows (OA-OD)
            # and xterm F1-F4 (OP-OS). F2 used to become ESC + QUIT ('Q').
            b = self._read_seq_byte()
            arrow = _ARROW_FINALS.get(b) if b is not None else None
            return KeyEvent(arrow) if arrow is not None else KeyEvent(Key.UNKNOWN)
        return KeyEvent(Key.ESC)

    def _read_csi(self) -> KeyEvent | None:
        """CSI: ESC [ <params 0x30-0x3F>* <intermediates 0x20-0x2F>* <final
        0x40-0x7E>. Consumed whole so e.g. Ctrl+Right (ESC [ 1 ; 5 C) doesn't
        leak ';', '5', 'C' as keystrokes. Every byte read is bounded by the
        same window. Only parameterless arrows are bound."""
        params = b""
        while True:
            b = self._read_seq_byte()
            if b is None:
                return KeyEvent(Key.UNKNOWN)
            if 0x20 <= b[0] <= 0x3F:
                params += b
                continue
            if 0x40 <= b[0] <= 0x7E and not params:
                arrow = _ARROW_FINALS.get(b)
                if arrow is not None:
                    return KeyEvent(arrow)
            if params.startswith(b"<") and b in (b"M", b"m"):
                # 5.0.0 SGR mouse report; None = an ignored release / motion.
                return parse_sgr_mouse(params[1:], b)
            # A non-arrow final, or not a valid CSI byte: give up on it.
            return KeyEvent(Key.UNKNOWN)

    def _read_utf8(self, byte: int) -> KeyEvent:
        """A multi-byte UTF-8 character from its leading byte."""
        continuation_bytes = _utf8_continuations(byte)
        if continuation_bytes is None:
            return KeyEvent(Key.ESC)
        total_bytes = continuation_bytes + 1
        full_buf = bytes([byte])
        while len(full_buf) < total_bytes:
            # Bound the wait for the rest of a multi-byte UTF-8 sequence: an
            # unterminated leading byte (paste of garbage, killed remote, etc.)
            # used to block the reader forever.
            r, _, _ = select.select([sys.stdin], [], [], 0.05)
            if not r:
                break
            chunk = os.read(self._stdin_fd, total_bytes - len(full_buf))
            if not chunk:
                break
            full_buf += chunk
        try:
            return KeyEvent(Key.CHAR, full_buf.decode("utf-8"))
        except UnicodeDecodeError:
            return KeyEvent(Key.ESC)

    def _read_seq_byte(self) -> bytes | None:
        """Read one byte of an escape sequence, or None on timeout / EOF."""
        r, _, _ = select.select([sys.stdin], [], [], 0.05)
        if not r:
            return None
        b = os.read(self._stdin_fd, 1)
        return b or None

    def read_timeout(self, timeout: float) -> KeyEvent | None:
        """Read a key with a timeout. Returns None if no key is pressed (an
        ignored mouse report doesn't count as one)."""
        deadline = time.monotonic() + timeout
        remaining = timeout
        while True:
            r, _, _ = select.select([sys.stdin], [], [], remaining)
            if not r:
                return None
            event = self._read_one()
            if event is not None:
                return event
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None


def interruptible_sleep(
    seconds: float,
    reader: KeyReader | None = None,
    granularity: float = 0.05,
) -> KeyEvent | None:
    """Sleep for `seconds`, but return immediately if a key is pressed.

    `granularity` is the poll interval (seconds). Default 0.05 matches the ESC
    vs. arrow-key disambiguation window. Animation callers (trick dwell, score
    ticker) may pass a tighter value (e.g. 0.01) for snappier interruption.
    """
    start = time.time()
    while time.time() - start < seconds:
        if reader and os.name == "nt":
            # select() only works on sockets on Windows; the Windows reader
            # polls msvcrt.kbhit() in read_timeout instead.
            ev = reader.read_timeout(granularity)
            if ev is not None:
                return ev
        elif reader:
            r, _, _ = select.select([sys.stdin], [], [], granularity)
            if r:
                return reader.read()
        else:
            time.sleep(granularity)
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

    def __new__(cls, *args: Any, **kwargs: Any) -> KeyReader:  # noqa: ARG004 — ctor args
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
            # 4.6.5: empty bytes mean stdin is closed (EOF). Without this guard
            # control fell through to `ch.decode("utf-8")` → KeyEvent(CHAR, "")
            # and any prompt loop that ignores empty CHAR events would hot-spin.
            # Matches `_UnixKeyReader.read` EOF behaviour.
            if not ch:
                return KeyEvent(Key.EOF)
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
                # Other extended keys (F-keys, Delete, PgUp, ...): their
                # second byte must not be reinterpreted as a letter (Delete's
                # b"S" used to become DOWN). Matches the Unix reader.
                return KeyEvent(Key.UNKNOWN)
            if ch == b"\x03":
                return KeyEvent(Key.QUIT)
            if ch in (b"\r", b"\n"):
                return KeyEvent(Key.ENTER)
            if ch == b"\t":
                return KeyEvent(Key.TAB)
            if ch == b" ":
                return KeyEvent(Key.SPACE)
            try:
                return char_event(ch.decode("utf-8"))
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
