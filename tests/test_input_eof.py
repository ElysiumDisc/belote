"""H2 audit fix: EOF on stdin is distinct from ESC.

Pre-3.5.0 `KeyReader.read()` returned `KeyEvent(Key.ESC)` when `os.read()`
returned empty bytes. A closed stdin (broken pipe, headless harness) made
every prompt loop spin: the loop popped one menu level on ESC, fell through,
re-read stdin, got another "ESC", popped again — burning CPU on rapid pops
until the outermost loop happened to exit.

These tests pin:
1. EOF returns `Key.EOF`, not `Key.ESC`.
2. `prompt_card` / `prompt_bid` exit cleanly on `Key.EOF` (no spin).
3. Menu/shop/announce/collection/rules consumers accept `Key.EOF` as
   equivalent to ESC ("back / cancel") so EOF propagates to the outer layer.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from belote.deck import Suit
from belote.game import Phase, Seat, new_game, start_round
from belote.input import Key, KeyEvent
from belote.ui import prompts as prompts_module

# ── Direct enum + reader behaviour ──────────────────────────────────────────


def test_key_eof_is_distinct_enum_value() -> None:
    """Defensive — keep EOF separate from ESC so callers can branch on it."""
    assert Key.EOF is not Key.ESC
    assert Key.EOF.value == "EOF"


def test_unix_reader_returns_eof_on_empty_read() -> None:
    """`_UnixKeyReader.read()` must return Key.EOF when stdin is at EOF."""
    from belote.input import _UnixKeyReader

    reader = _UnixKeyReader.__new__(_UnixKeyReader)
    reader._old_termios = None
    reader._stdin_fd = 0
    reader._restored = False

    with patch("belote.input.os.read", return_value=b""):
        event = reader.read()
    assert event.key is Key.EOF


# ── prompt_card / prompt_bid: must exit on EOF, not spin ────────────────────


def _state_in_playing_phase() -> object:
    """Minimal helper to drop a fresh game into PLAYING with South to act."""
    import random
    state = new_game()
    state = start_round(state, random.Random(0))
    from dataclasses import replace
    return replace(state, phase=Phase.PLAYING, trump=Suit.SPADES, taker=Seat.SOUTH, turn=Seat.SOUTH)


def test_prompt_card_exits_on_eof() -> None:
    """prompt_card must return (None, state) on EOF — not spin re-reading."""
    state = _state_in_playing_phase()
    reader = MagicMock()
    reader.read.return_value = KeyEvent(Key.EOF)

    card, _ = prompts_module.prompt_card(state, reader, show_north_hand=False)
    assert card is None
    # Only one read; the EOF branch returns immediately.
    assert reader.read.call_count == 1


def test_prompt_bid_exits_on_eof() -> None:
    """prompt_bid must return 'QUIT' on EOF — not spin re-reading."""
    state = new_game()
    import random
    state = start_round(state, random.Random(0))
    reader = MagicMock()
    reader.read.return_value = KeyEvent(Key.EOF)

    result = prompts_module.prompt_bid(state, reader)
    assert result == "QUIT"
    assert reader.read.call_count == 1


# ── Outer loops route EOF to clean exit (smoke-check) ───────────────────────


def test_eof_in_consumables_overlay_returns_false() -> None:
    """The consumables overlay treats EOF like Esc — return False, no spin."""
    from belote.belatro.core.run_state import BelAtroRun
    from belote.belatro.items.tarots import LeChariot
    from belote.belatro.ui.consumables import ConsumablesOverlay

    run = BelAtroRun()
    run.consumables.append(LeChariot())
    reader = MagicMock()
    reader.read.return_value = KeyEvent(Key.EOF)

    overlay = ConsumablesOverlay(run, reader)
    assert overlay.open() is False
    assert reader.read.call_count == 1


def test_announce_yes_no_returns_false_on_eof() -> None:
    """BelAtroAnnounce.yes_no must exit on EOF — pre-3.9.0 it spun forever
    when stdin was closed during the post-Ante-8 or surcoinche prompt.

    Sibling methods banner() and score_popup() in the same file already
    handle EOF; this test pins the inconsistency closed."""
    from belote.belatro.ui.announce import BelAtroAnnounce

    reader = MagicMock()
    reader.read.return_value = KeyEvent(Key.EOF)
    assert BelAtroAnnounce.yes_no("Continue?", reader) is False
    assert reader.read.call_count == 1
