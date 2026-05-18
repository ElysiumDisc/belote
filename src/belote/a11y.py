"""3.0.0: optional screen-reader hints.

When the env var ``BELOTE_A11Y`` is truthy, key in-game events emit a plain-text
line to stderr — readable by terminal screen readers such as Orca, NVDA in WSL,
or VoiceOver via iTerm2. Disabled by default so it doesn't pollute output for
sighted players.

**Invariant**: ``BELOTE_A11Y`` is read **once at module import**. Toggling the
env var mid-session has no effect on production code — restart the process
to enable/disable. Tests that mutate the env may call ``_refresh_enabled_from_env()``
to re-read the cached flag.

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


def announce_contract(taker: Seat, contract_label: str, coinche_level: int = 0) -> None:
    """Speak the locked contract at the bid→play transition (4.6.5).

    `contract_label` is the human-readable trump or special form (e.g. "hearts",
    "tout atout", "sans atout"). `coinche_level` is 0 (normal), 1 (coinched),
    or 2 (surcoinched).
    """
    suffix = ""
    if coinche_level == 1:
        suffix = ", coinched"
    elif coinche_level >= 2:
        suffix = ", surcoinched"
    speak(f"contract: {taker.name.lower()} takes {contract_label}{suffix}.")


def announce_declaration(seat: Seat, kind: str, points: int) -> None:
    """Speak a scored declaration (carre, sequence, belote). 4.6.5."""
    speak(f"{seat.name.lower()} scores {kind} for {points} points.")


def announce_round_result(
    taker_total: int,
    defender_total: int,
    taker_team_label: str,
    contract: str | None = None,
) -> None:
    """Round-end summary line. 4.6.5: optional `contract` adds trump context."""
    contract_phrase = f" on {contract}" if contract else ""
    speak(
        f"round complete{contract_phrase}. {taker_team_label} taker "
        f"scores {taker_total}; defenders score {defender_total}."
    )
