"""WASD nav aliases (4.5.0).

Pre-4.5.0: only arrow keys moved the selection on every BelAtro/Belote screen.
Post-4.5.0: `w` / `a` / `s` / `d` (lower or upper case) are aliased at the
reader layer to `Key.UP` / `Key.LEFT` / `Key.DOWN` / `Key.RIGHT`. Aliasing
at the source means every consumer's `case Key.LEFT | Key.UP:` branch fires
automatically — no per-screen edits needed.

A/S were previously bidding-only quick-keys (Tout Atout / Sans Atout). They
moved to X/N to make room for WASD.
"""

from __future__ import annotations

from unittest.mock import patch

from belote.input import Key, _UnixKeyReader


def _make_reader() -> _UnixKeyReader:
    reader = _UnixKeyReader.__new__(_UnixKeyReader)
    reader._old_termios = None
    reader._stdin_fd = 0
    reader._restored = False
    return reader


def _read_char(ch: str) -> Key:
    reader = _make_reader()
    with patch("belote.input.os.read", return_value=ch.encode("ascii")):
        return reader.read().key


def test_wasd_lower_case_aliases() -> None:
    assert _read_char("w") is Key.UP
    assert _read_char("a") is Key.LEFT
    assert _read_char("s") is Key.DOWN
    assert _read_char("d") is Key.RIGHT


def test_wasd_upper_case_aliases() -> None:
    """Upper-case WASD must alias identically — most consumers don't care
    about case, but pinning this prevents a future shift-key regression."""
    assert _read_char("W") is Key.UP
    assert _read_char("A") is Key.LEFT
    assert _read_char("S") is Key.DOWN
    assert _read_char("D") is Key.RIGHT


def test_arrow_keys_still_work() -> None:
    """Sanity — arrow keys still produce the same Key enum values."""
    reader = _make_reader()
    # ESC [ A → UP
    with patch("belote.input.os.read", side_effect=[b"\x1b", b"[", b"A"]), \
         patch("belote.input.select.select", return_value=([0], [], [])):
        assert reader.read().key is Key.UP


def test_a_no_longer_returns_char() -> None:
    """4.5.0 regression-pin: pressing `a` used to mint Key.CHAR with char='a'
    so prompt_bid could read it as the Tout Atout quick-key. That quick-key
    moved to `x`; reading `a` now produces Key.LEFT instead."""
    event_a = _make_reader()
    with patch("belote.input.os.read", return_value=b"a"):
        ev = event_a.read()
    assert ev.key is Key.LEFT
    # No char payload — Key.LEFT events don't carry one.
    assert ev.char is None


def test_s_no_longer_returns_char() -> None:
    """4.5.0 regression-pin: same as test_a_no_longer_returns_char but for
    the Sans Atout quick-key, which moved from `s` to `n`."""
    reader = _make_reader()
    with patch("belote.input.os.read", return_value=b"s"):
        ev = reader.read()
    assert ev.key is Key.DOWN
    assert ev.char is None


def test_x_still_returns_char_for_bid() -> None:
    """The new TA quick-key `x` must reach the Key.CHAR branch so prompt_bid
    can read it. WASD aliasing must NOT swallow `x`."""
    reader = _make_reader()
    with patch("belote.input.os.read", return_value=b"x"):
        ev = reader.read()
    assert ev.key is Key.CHAR
    assert ev.char == "x"


def test_n_still_returns_char_for_bid() -> None:
    """The new SA quick-key `n` must reach the Key.CHAR branch."""
    reader = _make_reader()
    with patch("belote.input.os.read", return_value=b"n"):
        ev = reader.read()
    assert ev.key is Key.CHAR
    assert ev.char == "n"
