"""`belote.input` reader internals: raw-mode setup/restore, escape-sequence
parsing, UTF-8, Ctrl-C / EOF, timeouts, `interruptible_sleep`, the
`KeyReader` factory and (via a sandboxed re-import) the Windows reader.

The byte stream is faked by swapping the module's `os` / `select` bindings for
small namespaces, so nothing global is patched and no real stdin is touched.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from collections import deque
from collections.abc import Iterator
from typing import Any

import pytest

import belote.input as inp
from belote.input import Key, KeyEvent, _UnixKeyReader
from tests.harness import ScriptedReader


class FakeStdin:
    """Byte queue standing in for fd 0: `os.read` pops, `select` reports
    readiness while bytes remain."""

    def __init__(self, data: bytes = b"") -> None:
        self.buf = bytearray(data)
        self.selects: list[float | None] = []
        self.force_ready: bool | None = None

    def read(self, _fd: int, n: int) -> bytes:
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out

    def select(
        self, r: list[Any], _w: list[Any], _x: list[Any], timeout: float | None = None
    ) -> Any:
        self.selects.append(timeout)
        ready = bool(self.buf) if self.force_ready is None else self.force_ready
        return (r if ready else []), [], []


@pytest.fixture
def stdin(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeStdin]:
    fake = FakeStdin()
    monkeypatch.setattr(inp, "os", types.SimpleNamespace(read=fake.read, name="posix"))
    monkeypatch.setattr(inp, "select", types.SimpleNamespace(select=fake.select))
    yield fake


def _reader() -> _UnixKeyReader:
    r = _UnixKeyReader.__new__(_UnixKeyReader)
    r._old_termios = None
    r._stdin_fd = 0
    r._restored = False
    return r


def _read(stdin: FakeStdin, data: bytes) -> KeyEvent:
    stdin.buf[:] = data
    return _reader().read()


# ── single bytes ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("data", "key"),
    [
        (b"\x03", Key.QUIT),  # Ctrl-C under raw mode
        (b"\r", Key.ENTER),
        (b"\n", Key.ENTER),
        (b"\t", Key.TAB),
        (b" ", Key.SPACE),
        (b"q", Key.QUIT),
        (b"?", Key.HELP),
        (b"h", Key.HIST),
        (b"t", Key.THEME),
        (b"o", Key.SORT),
        (b"i", Key.OVERLAY),
        (b"V", Key.INVENTORY),
        (b"", Key.EOF),
    ],
)
def test_single_byte_keys(stdin: FakeStdin, data: bytes, key: Key) -> None:
    assert _read(stdin, data).key is key


def test_plain_char_carries_payload(stdin: FakeStdin) -> None:
    assert _read(stdin, b"7") == KeyEvent(Key.CHAR, "7")


# ── escape sequences ────────────────────────────────────────────────────────


def test_bare_escape_after_timeout(stdin: FakeStdin) -> None:
    ev = _read(stdin, b"\x1b")
    assert ev.key is Key.ESC
    assert stdin.selects == [0.05]  # the ESC-vs-sequence disambiguation window


def test_escape_followed_by_unrelated_byte_is_esc(stdin: FakeStdin) -> None:
    # Alt+x style: ESC then a non-sequence byte → ESC (byte consumed).
    assert _read(stdin, b"\x1bx").key is Key.ESC


@pytest.mark.parametrize(
    ("seq", "key"),
    [
        (b"\x1b[A", Key.UP),
        (b"\x1b[B", Key.DOWN),
        (b"\x1b[C", Key.RIGHT),
        (b"\x1b[D", Key.LEFT),
        (b"\x1bOA", Key.UP),  # SS3 application-cursor arrows
        (b"\x1bOD", Key.LEFT),
        (b"\x1bOP", Key.UNKNOWN),  # F1 — must not become ESC + 'P'
        (b"\x1bOQ", Key.UNKNOWN),  # F2 — used to become ESC + QUIT
        (b"\x1b[1;5C", Key.UNKNOWN),  # Ctrl+Right: params → unbound
        (b"\x1b[3~", Key.UNKNOWN),  # Delete
        (b"\x1b[H", Key.UNKNOWN),  # Home: final w/o params, not an arrow
        (b"\x1b[15~", Key.UNKNOWN),  # F5
    ],
)
def test_escape_sequences(stdin: FakeStdin, seq: bytes, key: Key) -> None:
    assert _read(stdin, seq).key is key
    assert not stdin.buf, "whole sequence must be consumed"


def test_csi_sequence_truncated_mid_way_is_unknown(stdin: FakeStdin) -> None:
    assert _read(stdin, b"\x1b[1;").key is Key.UNKNOWN


def test_csi_invalid_byte_aborts_sequence(stdin: FakeStdin) -> None:
    # 0x07 is outside the CSI parameter/intermediate/final ranges.
    stdin.buf[:] = b"\x1b[\x07z"
    assert _reader().read().key is Key.UNKNOWN
    assert stdin.buf == bytearray(b"z")


def test_ss3_truncated_is_unknown(stdin: FakeStdin) -> None:
    assert _read(stdin, b"\x1bO").key is Key.UNKNOWN


def test_seq_byte_eof_is_treated_like_timeout(stdin: FakeStdin) -> None:
    # select says "ready" but the read returns b"" (stdin closed mid-sequence).
    stdin.buf[:] = b"\x1b["
    stdin.force_ready = True
    assert _reader().read().key is Key.UNKNOWN


def test_following_keys_are_not_polluted_by_sequences(stdin: FakeStdin) -> None:
    stdin.buf[:] = b"\x1b[1;5Cx\x1b[Aq"
    r = _reader()
    assert [r.read() for _ in range(3)] == [
        KeyEvent(Key.UNKNOWN),
        KeyEvent(Key.CHAR, "x"),
        KeyEvent(Key.UP),
    ]
    assert r.read().key is Key.QUIT


# ── UTF-8 ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ch", ["é", "♠", "€", "🂡"])
def test_multibyte_utf8_chars(stdin: FakeStdin, ch: str) -> None:
    assert _read(stdin, ch.encode()) == KeyEvent(Key.CHAR, ch)


def test_invalid_utf8_leading_byte_is_esc(stdin: FakeStdin) -> None:
    assert _read(stdin, b"\xff").key is Key.ESC


def test_truncated_utf8_times_out_instead_of_blocking(stdin: FakeStdin) -> None:
    # Leading byte of a 3-byte sequence with nothing after it.
    assert _read(stdin, b"\xe2").key is Key.ESC
    assert stdin.selects == [0.05]


def test_truncated_utf8_eof_mid_sequence(stdin: FakeStdin) -> None:
    stdin.buf[:] = b"\xe2\x99"
    stdin.force_ready = True  # select keeps saying "ready", read hits EOF
    assert _reader().read().key is Key.ESC


def test_utf8_bad_continuation_is_esc(stdin: FakeStdin) -> None:
    assert _read(stdin, b"\xc3\x28").key is Key.ESC


# ── read_timeout ────────────────────────────────────────────────────────────


def test_read_timeout_returns_none_when_idle(stdin: FakeStdin) -> None:
    assert _reader().read_timeout(0.25) is None
    assert stdin.selects == [0.25]


def test_read_timeout_reads_when_ready(stdin: FakeStdin) -> None:
    stdin.buf[:] = b"\r"
    assert _reader().read_timeout(0.25) == KeyEvent(Key.ENTER)


# ── raw-mode lifecycle ──────────────────────────────────────────────────────


class FakeTermios:
    error = type("error", (Exception,), {})
    TCSADRAIN = 1

    def __init__(self, *, fail_get: bool = False, fail_set: bool = False) -> None:
        self.fail_get = fail_get
        self.fail_set = fail_set
        self.set_calls: list[tuple[int, int, object]] = []

    def tcgetattr(self, fd: int) -> list[int]:
        if self.fail_get:
            raise self.error("not a tty")
        return [fd, 42]

    def tcsetattr(self, fd: int, when: int, attrs: object) -> None:
        self.set_calls.append((fd, when, attrs))
        if self.fail_set:
            raise OSError("broken pipe")


@pytest.fixture
def fake_tty(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    raw_calls: list[int] = []
    monkeypatch.setattr(inp, "tty", types.SimpleNamespace(setraw=raw_calls.append))
    monkeypatch.setattr(inp.sys, "stdin", types.SimpleNamespace(fileno=lambda: 7))
    return types.SimpleNamespace(raw_calls=raw_calls)


def test_context_manager_enters_raw_mode_and_restores_once(
    monkeypatch: pytest.MonkeyPatch, fake_tty: types.SimpleNamespace
) -> None:
    termios = FakeTermios()
    monkeypatch.setattr(inp, "termios", termios)
    with _UnixKeyReader() as r:
        assert r._stdin_fd == 7
        assert r._old_termios == [7, 42]
        assert fake_tty.raw_calls == [7]
        assert termios.set_calls == []
    assert termios.set_calls == [(7, 1, [7, 42])]
    assert r._restored
    r.restore()  # idempotent
    assert len(termios.set_calls) == 1


def test_non_tty_stdin_skips_raw_mode(
    monkeypatch: pytest.MonkeyPatch, fake_tty: types.SimpleNamespace
) -> None:
    termios = FakeTermios(fail_get=True)
    monkeypatch.setattr(inp, "termios", termios)
    with _UnixKeyReader() as r:
        assert r._old_termios is None
    assert termios.set_calls == []
    assert fake_tty.raw_calls == []
    assert not r._restored  # nothing to restore


def test_restore_swallows_dropped_terminal_errors(
    monkeypatch: pytest.MonkeyPatch, fake_tty: types.SimpleNamespace
) -> None:
    termios = FakeTermios(fail_set=True)
    monkeypatch.setattr(inp, "termios", termios)
    r = _UnixKeyReader().__enter__()
    r.__exit__(None, None, None)  # must not raise
    r.restore()
    assert r._restored and len(termios.set_calls) == 1


# ── KeyReader factory / base ────────────────────────────────────────────────


def test_keyreader_factory_returns_platform_reader(
    monkeypatch: pytest.MonkeyPatch, fake_tty: types.SimpleNamespace
) -> None:
    r = inp.KeyReader()
    assert isinstance(r, _UnixKeyReader)
    assert r._stdin_fd == 7


def test_keyreader_subclass_uses_base_interface() -> None:
    class Sub(inp.KeyReader):
        pass

    s = Sub()
    assert type(s) is Sub
    s.restore()  # base restore is a no-op
    for call in (s.__enter__, s.read, lambda: s.read_timeout(0.1), lambda: s.__exit__()):
        with pytest.raises(NotImplementedError):
            call()


# ── interruptible_sleep ─────────────────────────────────────────────────────


def test_interruptible_sleep_returns_key_pressed(stdin: FakeStdin) -> None:
    stdin.buf[:] = b"x"
    ev = inp.interruptible_sleep(5.0, _reader())  # type: ignore[arg-type]
    assert ev == KeyEvent(Key.CHAR, "x")
    assert stdin.selects[0] == 0.05


def test_interruptible_sleep_times_out_with_idle_reader(stdin: FakeStdin) -> None:
    assert inp.interruptible_sleep(0.02, _reader(), granularity=0.001) is None  # type: ignore[arg-type]
    assert stdin.selects and all(t == 0.001 for t in stdin.selects)


def test_interruptible_sleep_without_reader_just_sleeps(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []
    clock = iter([0.0, 0.0, 0.03, 0.06])
    monkeypatch.setattr(
        inp, "time", types.SimpleNamespace(time=lambda: next(clock), sleep=slept.append)
    )
    assert inp.interruptible_sleep(0.05, None, granularity=0.03) is None
    assert slept == [0.03, 0.03]


def test_interruptible_sleep_windows_polls_read_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inp, "os", types.SimpleNamespace(name="nt"))
    r = ScriptedReader(None, None, "enter")
    assert inp.interruptible_sleep(5.0, r.as_reader(), granularity=0.01) == KeyEvent(Key.ENTER)
    assert r.timeouts == [0.01, 0.01, 0.01]


def test_interruptible_sleep_windows_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inp, "os", types.SimpleNamespace(name="nt"))
    clock = iter([0.0, 0.0, 0.004, 0.008, 0.012])
    monkeypatch.setattr(inp, "time", types.SimpleNamespace(time=lambda: next(clock)))
    r = ScriptedReader(default=None)
    assert inp.interruptible_sleep(0.01, r.as_reader(), granularity=0.002) is None
    assert r.timeouts == [0.002, 0.002, 0.002]


# ── Windows reader (sandboxed re-import with os.name == "nt") ───────────────


class FakeMsvcrt:
    def __init__(self, data: bytes = b"", *, hit: bool = True) -> None:
        self.data = deque(bytes([b]) for b in data)
        self.hit = hit

    def getch(self) -> bytes:
        return self.data.popleft() if self.data else b""

    def kbhit(self) -> bool:
        return self.hit and bool(self.data)


@pytest.fixture
def win_input(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """Execute input.py again as a separate module with `os.name == "nt"` so
    the Windows-only class body (and its coverage) materialises on POSIX."""
    spec = importlib.util.spec_from_file_location("_belote_input_nt", inp.__file__)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "_belote_input_nt", mod)
    real_name = os.name
    os.name = "nt"  # type: ignore[misc]  # restored immediately below
    try:
        spec.loader.exec_module(mod)
    finally:
        os.name = real_name  # type: ignore[misc]
    return mod


def _win_read(monkeypatch: pytest.MonkeyPatch, mod: types.ModuleType, data: bytes) -> Any:
    monkeypatch.setitem(sys.modules, "msvcrt", FakeMsvcrt(data))
    return mod._WindowsKeyReader().read()


@pytest.mark.parametrize(
    ("data", "key", "char"),
    [
        (b"", "EOF", None),
        (b"\xe0H", "UP", None),
        (b"\x00P", "DOWN", None),
        (b"\xe0M", "RIGHT", None),
        (b"\xe0K", "LEFT", None),
        (b"\xe0S", "UNKNOWN", None),  # Delete must not become DOWN ('s')
        (b"\x03", "QUIT", None),
        (b"\r", "ENTER", None),
        (b"\n", "ENTER", None),
        (b"\t", "TAB", None),
        (b" ", "SPACE", None),
        (b"w", "UP", "w"),  # 4.11.0: aliases keep the typed letter
        (b"x", "CHAR", "x"),
        (b"\xff", "ESC", None),  # undecodable
    ],
)
def test_windows_reader_keys(
    monkeypatch: pytest.MonkeyPatch,
    win_input: types.ModuleType,
    data: bytes,
    key: str,
    char: str | None,
) -> None:
    ev = _win_read(monkeypatch, win_input, data)
    assert ev.key.name == key
    assert ev.char == char


def test_windows_reader_lifecycle_and_timeout(
    monkeypatch: pytest.MonkeyPatch, win_input: types.ModuleType
) -> None:
    r = win_input._WindowsKeyReader()
    with r as entered:
        assert entered is r
    r.restore()
    assert r._restored
    monkeypatch.setitem(sys.modules, "msvcrt", FakeMsvcrt(b"\r"))
    assert r.read_timeout(1.0).key.name == "ENTER"
    monkeypatch.setitem(sys.modules, "msvcrt", FakeMsvcrt(b"", hit=False))
    assert r.read_timeout(0.02) is None


def test_windows_keyreader_factory(
    monkeypatch: pytest.MonkeyPatch, win_input: types.ModuleType
) -> None:
    monkeypatch.setattr(win_input, "os", types.SimpleNamespace(name="nt"))
    assert type(win_input.KeyReader()).__name__ == "_WindowsKeyReader"
