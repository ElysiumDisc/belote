"""Reusable interaction-layer test harness.

Drives the terminal UI (menus, prompts, overlays, BelAtro screens) headlessly:

* :class:`ScriptedReader` — a fake ``KeyReader`` fed from a queue of key
  specs. Exhausting the queue returns ``Key.EOF`` (or a chosen default) so
  every prompt loop terminates instead of blocking on real stdin, and a hard
  read budget turns an accidental hot loop into a test failure, not a hang.
* :func:`keys` / :func:`key_event` — terse key specs: ``"down"``, ``"enter"``,
  ``"esc"`` … map to :class:`Key` members; a single character goes through the
  real reader's alias table (``"s"`` → DOWN, ``"x"`` → CHAR x), so tests see
  exactly what a keyboard would produce.
* :class:`Screen` — captured ``sys.stdout`` with :attr:`Screen.text`, the
  output with ANSI escapes stripped, for assertions on visible text.
* :class:`FakeTerminal` — pins the terminal size every UI module reads (all of
  them go through ``belote.context.TERMINAL``), resizable mid-test.
* :func:`isolate_dirs` — redirects config/data dirs into ``tmp_path``.
* The ``tui`` fixture (registered in ``tests/conftest.py``) wires all of the
  above, disables animations, and snapshots/restores the process-wide UI state
  (theme, settings, BelAtro HUD flags, prompt extension hooks) so tests can't
  leak into each other.
"""

from __future__ import annotations

import re
import sys
from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeAlias

import pytest

from belote.input import Key, KeyEvent, KeyReader, char_event

# A key spec: a Key member, a ready KeyEvent, a name ("down", "enter", ...),
# a single printable character, or None (a read_timeout() that times out).
KeySpec: TypeAlias = "Key | KeyEvent | str | None"

_NAMED: dict[str, Key] = {
    "esc": Key.ESC,
    "escape": Key.ESC,
    "return": Key.ENTER,
    "ctrl-c": Key.QUIT,
    "ctrl-d": Key.EOF,
    **{k.name.lower(): k for k in Key},
}


def key_event(spec: KeySpec) -> KeyEvent | None:
    """Normalise one key spec. ``None`` stays ``None`` (a timeout)."""
    if spec is None or isinstance(spec, KeyEvent):
        return spec
    if isinstance(spec, Key):
        return KeyEvent(spec)
    if len(spec) == 1:
        return char_event(spec)
    try:
        return KeyEvent(_NAMED[spec.lower()])
    except KeyError:
        raise ValueError(f"unknown key spec {spec!r}") from None


def keys(*specs: KeySpec) -> list[KeyEvent | None]:
    """``keys("down", "down", "enter")`` → list of events."""
    return [key_event(s) for s in specs]


def raw_char(ch: str) -> KeyEvent:
    """A CHAR event that bypasses the WASD/shortcut alias table."""
    return KeyEvent(Key.CHAR, ch)


def text_keys(text: str) -> list[KeyEvent | None]:
    """One event per character of `text` (aliases applied, like typing)."""
    return [char_event(c) for c in text]


class ScriptExhaustedError(AssertionError):
    """The UI under test kept reading far past the end of its script."""


class ScriptedReader(KeyReader):
    """Fake ``KeyReader`` replaying a script of key events.

    Subclasses ``belote.input.KeyReader`` (so ``isinstance`` checks in the UI
    see a real reader) and implements its whole surface: ``read()``,
    ``read_timeout(t)``, ``restore()``, ``_restored`` and context-manager use.

    * ``read()`` skips ``None`` entries (they model timeouts only).
    * ``read_timeout()`` returns ``None`` for a ``None`` entry.
    * Once the script is empty both return ``default`` (``Key.EOF`` unless
      overridden), so loops that honour EOF terminate.
    * After ``max_reads`` total reads :class:`ScriptExhaustedError` is raised,
      so a loop that ignores EOF fails fast instead of hanging the suite.
    * ``idle_timeouts=True`` makes every ``read_timeout()`` time out without
      consuming the script — a player who never touches the keyboard during
      animations / banners, so the script only feeds blocking ``read()``s.
    """

    def __init__(
        self,
        *specs: KeySpec | Iterable[KeySpec],
        default: KeySpec = Key.EOF,
        max_reads: int = 2_000,
        idle_timeouts: bool = False,
    ) -> None:
        self._queue: deque[KeyEvent | None] = deque()
        self.push(*specs)
        self.default = key_event(default)
        self.max_reads = max_reads
        self.idle_timeouts = idle_timeouts
        self.reads = 0
        self.timeouts: list[float] = []
        self.returned: list[KeyEvent | None] = []
        self._restored = False
        self.entered = 0

    # ── script management ──────────────────────────────────────────────

    def push(self, *specs: KeySpec | Iterable[KeySpec]) -> None:
        """Append keys; accepts specs or iterables of specs (e.g. ``keys(...)``)."""
        for spec in specs:
            if isinstance(spec, (list, tuple, deque)):
                self._queue.extend(key_event(s) for s in spec)
            else:
                self._queue.append(key_event(spec))  # type: ignore[arg-type]

    @property
    def remaining(self) -> int:
        """Number of scripted entries not yet consumed."""
        return len(self._queue)

    @property
    def exhausted(self) -> bool:
        return not self._queue

    def _next(self) -> KeyEvent | None:
        self.reads += 1
        if self.reads > self.max_reads:
            raise ScriptExhaustedError(
                f"UI read {self.reads} keys (budget {self.max_reads}); "
                "it is probably looping without honouring EOF"
            )
        ev = self._queue.popleft() if self._queue else self.default
        self.returned.append(ev)
        return ev

    # ── KeyReader interface ────────────────────────────────────────────

    def read(self) -> KeyEvent:
        while True:
            ev = self._next()
            if ev is not None:
                return ev
            if not self._queue and self.default is None:
                return KeyEvent(Key.EOF)

    def read_timeout(self, timeout: float) -> KeyEvent | None:
        self.timeouts.append(timeout)
        if self.idle_timeouts:
            return None
        return self._next()

    def restore(self) -> None:
        self._restored = True

    def __enter__(self) -> ScriptedReader:
        self.entered += 1
        return self

    def __exit__(self, *_args: object) -> None:
        self.restore()

    def as_reader(self) -> KeyReader:
        """The reader itself, typed as ``KeyReader`` (kept for readability)."""
        return self


# ── screen capture ─────────────────────────────────────────────────────────

# CSI (incl. private "?" params), OSC (BEL or ST terminated), and 2-byte ESC.
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")


def strip_ansi(s: str) -> str:
    """Remove ANSI escape sequences, leaving the visible characters."""
    return _ANSI_RE.sub("", s)


class Screen:
    """Everything the UI wrote to ``sys.stdout`` during the test.

    Built on pytest's ``capsys`` rather than swapping ``sys.stdout`` directly:
    pytest re-installs its own capture stream between the setup and call
    phases, which would silently detach a stream patched in by a fixture.
    """

    def __init__(self, capsys: pytest.CaptureFixture[str]) -> None:
        self._capsys = capsys
        self._buf: list[str] = []

    def _drain(self) -> None:
        out = self._capsys.readouterr().out
        if out:
            self._buf.append(out)

    @property
    def raw(self) -> str:
        """Raw output, escapes included."""
        self._drain()
        return "".join(self._buf)

    @property
    def text(self) -> str:
        """Output with ANSI escapes stripped."""
        return strip_ansi(self.raw)

    def lines(self) -> list[str]:
        """Visible text split on CR/LF, blank lines dropped, right-stripped."""
        return [ln.rstrip() for ln in re.split(r"[\r\n]+", self.text) if ln.strip()]

    def clear(self) -> None:
        self._drain()
        self._buf.clear()

    def take(self, *, raw: bool = False) -> str:
        """Return the output written so far (visible text, or raw with escapes
        when ``raw=True``) and reset the buffer."""
        out = self.raw if raw else self.text
        self.clear()
        return out

    def frames(self) -> list[str]:
        """Raw output split into full-screen repaints (on ``clear_screen()``);
        anything written before the first clear is dropped."""
        from belote.ansi import clear_screen

        return self.raw.split(clear_screen())[1:]

    def __contains__(self, needle: str) -> bool:
        return needle in self.text

    def count(self, needle: str) -> int:
        return self.text.count(needle)


# ── terminal size ──────────────────────────────────────────────────────────


class FakeTerminal:
    """Pins ``belote.context.TERMINAL.get_size()`` — the single source every
    UI module (``render.get_term_size``, fit_guard, BelAtro overlays) reads.

    ``queue_sizes`` makes successive polls return a scripted sequence (the
    last one sticks), for exercising resize / fit-guard paths.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch, cols: int = 120, rows: int = 40) -> None:
        from belote.context import TERMINAL

        self.cols = cols
        self.rows = rows
        self._sizes: deque[tuple[int, int]] = deque()
        self.polls = 0
        monkeypatch.setattr(TERMINAL, "get_size", self._get_size)

    def _get_size(self) -> tuple[int, int]:
        self.polls += 1
        if self._sizes:
            self.cols, self.rows = self._sizes.popleft()
        return self.cols, self.rows

    def resize(self, cols: int, rows: int) -> None:
        self.cols, self.rows = cols, rows

    def queue_sizes(self, *sizes: tuple[int, int]) -> None:
        self._sizes.extend(sizes)


# ── filesystem isolation ───────────────────────────────────────────────────

_ENV_FLAGS = ("BELOTE_NO_ANIM", "BELOTE_NO_DIFF", "BELOTE_A11Y", "BELOTE_REPLAY", "BELOTE_GHOST")


def isolate_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point HOME / XDG config+data dirs at `tmp_path` and clear BELOTE_* flags.

    (``tests/conftest.py`` already sandboxes the whole session; this narrows it
    to one test so files a test writes can be asserted on and never leak.)
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    for var in _ENV_FLAGS:
        monkeypatch.delenv(var, raising=False)
    return tmp_path


# ── global UI state snapshot ───────────────────────────────────────────────


@dataclass
class _UIState:
    theme: str
    settings: Any
    extension_keys: set[Key]
    history_override: Any
    bid_hint: Any
    animations: bool


def _current_bid_hint() -> Any:
    """The installed bid-hint provider, wherever the render split put it."""
    for name in ("belote.ui.hud_classic", "belote.ui.render"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "_bid_hint_provider"):
            return mod._bid_hint_provider
    return None


def _snapshot() -> _UIState:
    from belote import settings as settings_mod
    from belote.themes import theme_manager
    from belote.ui import anim, prompts

    return _UIState(
        theme=theme_manager.current_name,
        settings=settings_mod.current(),
        extension_keys=set(prompts._EXTENSION_KEYS),
        history_override=prompts._history_override,
        bid_hint=_current_bid_hint(),
        animations=anim.animations_enabled(),
    )


def _restore(snap: _UIState) -> None:
    from belote import settings as settings_mod
    from belote.belatro.ui import announce as b_announce
    from belote.themes import theme_manager
    from belote.ui import anim, prompts
    from belote.ui.render import invalidate_diff, set_bid_hint_provider

    if theme_manager.current_name != snap.theme:
        theme_manager.set_current(snap.theme)
    settings_mod.apply(snap.settings)
    prompts._EXTENSION_KEYS.clear()
    prompts._EXTENSION_KEYS.update(snap.extension_keys)
    prompts.set_history_override(snap.history_override)
    set_bid_hint_provider(snap.bid_hint)
    anim.set_animations_enabled(snap.animations)
    b_announce.reset_top_hud_state()
    b_announce.reset_tally_state()
    invalidate_diff()


# ── the composite fixture object ───────────────────────────────────────────


@dataclass
class TUI:
    """Handle returned by the ``tui`` fixture."""

    screen: Screen
    term: FakeTerminal
    monkeypatch: pytest.MonkeyPatch
    home: Path
    readers: list[ScriptedReader] = field(default_factory=list)

    def reader(
        self,
        *specs: KeySpec | Iterable[KeySpec],
        default: KeySpec = Key.EOF,
        idle_timeouts: bool = False,
    ) -> ScriptedReader:
        r = ScriptedReader(*specs, default=default, idle_timeouts=idle_timeouts)
        self.readers.append(r)
        return r

    def resize(self, cols: int, rows: int) -> None:
        self.term.resize(cols, rows)

    @property
    def text(self) -> str:
        return self.screen.text


@pytest.fixture
def tui(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> Iterator[TUI]:
    """Headless UI sandbox: 120x40 terminal, captured stdout, isolated dirs,
    animations off, process-wide UI state restored afterwards."""
    from belote.belatro.ui import announce as b_announce
    from belote.ui import anim

    home = isolate_dirs(monkeypatch, tmp_path)
    snap = _snapshot()
    term = FakeTerminal(monkeypatch)
    screen = Screen(capsys)
    anim.set_animations_enabled(False)
    b_announce.reset_top_hud_state()
    b_announce.reset_tally_state()
    try:
        yield TUI(screen=screen, term=term, monkeypatch=monkeypatch, home=home)
    finally:
        _restore(snap)
