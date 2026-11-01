"""Unix key reader: full escape-sequence consumption.

Pre-fix the reader only understood ``ESC [ A-D``. Anything else leaked its
trailing bytes as keystrokes: F2 (``ESC O Q``) became ESC then QUIT ('Q'),
Ctrl+Right (``ESC [ 1 ; 5 C``) became ';', '5', 'C' — and '5' plays card 5 —
and Delete (``ESC [ 3 ~``) leaked '~'. Ctrl-C (0x03 under raw mode) was an
unbound control char even though the fit-guard docs promise it quits.

These tests feed bytes through a fake stdin where ``select`` reports readiness
only while bytes remain, so we can assert each sequence is consumed whole.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest

from belote.input import Key, KeyEvent, _UnixKeyReader


def _make_reader() -> _UnixKeyReader:
    reader = _UnixKeyReader.__new__(_UnixKeyReader)
    reader._old_termios = None
    reader._stdin_fd = 0
    reader._restored = False
    return reader


@contextmanager
def _fake_stdin(data: bytes) -> Iterator[bytearray]:
    buf = bytearray(data)

    def fake_read(_fd: int, n: int) -> bytes:
        chunk = bytes(buf[:n])
        del buf[:n]
        return chunk

    def fake_select(*_a: Any, **_k: Any) -> tuple[list[int], list[int], list[int]]:
        return ([0] if buf else [], [], [])

    with (
        patch("belote.input.os.read", side_effect=fake_read),
        patch("belote.input.select.select", side_effect=fake_select),
    ):
        yield buf


def _read_all(data: bytes) -> list[KeyEvent]:
    reader = _make_reader()
    events: list[KeyEvent] = []
    with _fake_stdin(data) as buf:
        while buf:
            events.append(reader.read())
    return events


@pytest.mark.parametrize(
    ("seq", "key"),
    [
        (b"\x1b[A", Key.UP),
        (b"\x1b[B", Key.DOWN),
        (b"\x1b[C", Key.RIGHT),
        (b"\x1b[D", Key.LEFT),
        # Application cursor mode (DECCKM) arrows.
        (b"\x1bOA", Key.UP),
        (b"\x1bOB", Key.DOWN),
        (b"\x1bOC", Key.RIGHT),
        (b"\x1bOD", Key.LEFT),
    ],
)
def test_arrow_sequences(seq: bytes, key: Key) -> None:
    assert [e.key for e in _read_all(seq)] == [key]


@pytest.mark.parametrize(
    "seq",
    [
        b"\x1bOP",  # F1 (xterm)
        b"\x1bOQ",  # F2 (xterm) — 'Q' used to leak as QUIT
        b"\x1b[3~",  # Delete — '~' used to leak
        b"\x1b[6~",  # PgDn
        b"\x1b[1;5C",  # Ctrl+Right — ';', '5', 'C' used to leak
        b"\x1b[15~",  # F5
        b"\x1b[1;2A",  # Shift+Up — modified arrows are not plain arrows
    ],
)
def test_unbound_sequences_consumed_whole(seq: bytes) -> None:
    events = _read_all(seq)
    assert [e.key for e in events] == [Key.UNKNOWN]


def test_sequence_followed_by_real_key_keeps_the_key() -> None:
    """Consuming a sequence must stop at its final byte, not swallow input."""
    events = _read_all(b"\x1b[1;5C5")
    assert [(e.key, e.char) for e in events] == [(Key.UNKNOWN, None), (Key.CHAR, "5")]


def test_bare_escape_still_esc() -> None:
    assert [e.key for e in _read_all(b"\x1b")] == [Key.ESC]


def test_truncated_csi_does_not_block() -> None:
    """``ESC [ 1`` with nothing after it times out instead of hanging."""
    assert [e.key for e in _read_all(b"\x1b[1")] == [Key.UNKNOWN]


def test_ctrl_c_maps_to_quit() -> None:
    assert [e.key for e in _read_all(b"\x03")] == [Key.QUIT]


def test_unknown_is_distinct_from_esc() -> None:
    """ESC means "back" on most screens; unbound keys must be a no-op."""
    assert Key.UNKNOWN is not Key.ESC


def test_module_imports_without_termios(monkeypatch: pytest.MonkeyPatch) -> None:
    """termios/tty are Unix-only; a top-level import made the module (and the
    game) unimportable on Windows. Simulate Windows: block those modules and
    report sys.platform == "win32", then load a fresh copy of the module."""
    import importlib.util
    import sys

    import belote.input as input_module

    monkeypatch.setitem(sys.modules, "termios", None)
    monkeypatch.setitem(sys.modules, "tty", None)
    monkeypatch.setattr(sys, "platform", "win32")
    assert input_module.__file__ is not None
    spec = importlib.util.spec_from_file_location("_belote_input_win", input_module.__file__)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, mod)  # dataclasses need it
    spec.loader.exec_module(mod)
    assert mod.Key.UNKNOWN.value == "UNKNOWN"
