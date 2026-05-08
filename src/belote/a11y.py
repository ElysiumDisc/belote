"""3.0.0: optional screen-reader hints.

When the env var ``BELOTE_A11Y`` is truthy, key in-game events emit a plain-text
line to stderr — readable by terminal screen readers such as Orca, NVDA in WSL,
or VoiceOver via iTerm2. Disabled by default so it doesn't pollute output for
sighted players.

Hooked from gameflow.py (card plays, trick winners, round results) and from
belatro/main.py (boss reveal, ante advance, run won/lost). Each hook is a
single line — no rich formatting — so the screen reader can speak it cleanly.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .deck import Card
    from .game import Seat


# 3.0.1: resolve the env var once at import. The flag is read on every card
# play (~32 times/round); a dict lookup is cheap but bypassing it keeps
# `speak()` essentially free in the disabled path.
_TRUTHY = {"1", "true", "yes", "on"}
_ENABLED: bool = os.environ.get("BELOTE_A11Y", "").lower() in _TRUTHY


def is_enabled() -> bool:
    """Return whether a11y hints are enabled.

    Reads the cached module-level value (set at import). Tests that use
    `monkeypatch.setenv("BELOTE_A11Y", ...)` should call
    `_refresh_enabled_from_env()` after the patch.
    """
    return _ENABLED


def _refresh_enabled_from_env() -> None:
    """Re-read BELOTE_A11Y from the live environment. Public for tests."""
    global _ENABLED
    _ENABLED = os.environ.get("BELOTE_A11Y", "").lower() in _TRUTHY


def speak(line: str) -> None:
    """Emit one line to stderr — only when BELOTE_A11Y is enabled."""
    if _ENABLED:
        sys.stderr.write(line + "\n")
        sys.stderr.flush()


# ── Convenience formatters ────────────────────────────────────────────────


def _suit_word(suit_symbol: str) -> str:
    return {
        "♠": "spades",
        "♥": "hearts",
        "♦": "diamonds",
        "♣": "clubs",
    }.get(suit_symbol, suit_symbol)


def card_word(card: Card) -> str:
    rank = card.rank.value
    rank_word = {
        "7": "seven",
        "8": "eight",
        "9": "nine",
        "10": "ten",
        "J": "jack",
        "Q": "queen",
        "K": "king",
        "A": "ace",
    }.get(rank, rank)
    return f"{rank_word} of {_suit_word(card.suit.symbol)}"


def announce_play(seat: Seat, card: Card) -> None:
    speak(f"{seat.name.lower()} plays {card_word(card)}.")


def announce_trick_won(winner: Seat, points: int) -> None:
    speak(f"{winner.name.lower()} wins the trick worth {points} points.")


def announce_round_result(taker_total: int, defender_total: int, taker_team_label: str) -> None:
    speak(
        f"round complete. {taker_team_label} taker scores {taker_total}; "
        f"defenders score {defender_total}."
    )
