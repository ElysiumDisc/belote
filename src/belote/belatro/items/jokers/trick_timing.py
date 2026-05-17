from __future__ import annotations

from typing import Any

from belote.deck import Suit
from belote.game import team_of

from ...engine.event_bus import TrickWonEvent
from ..base import Joker, JokerResult, Rarity


class LePremierSang(Joker):
    id = "le_premier_sang"
    name = "Le Premier Sang"
    description = "Win trick 1: +2 Mult for the rest of the round."
    cost = 6

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        state[f"{self.id}_active"] = False
        return None

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        # Arm on a trick-1 NS win, then keep paying out +2 Mult on every
        # subsequent NS-won trick for the rest of the round.
        active = state.get(f"{self.id}_active", False)
        if event.trick_number == 1:
            if team_of(event.winner) == 0:
                state[f"{self.id}_active"] = True
                return JokerResult(add_mult=2.0)
            return None
        if active and team_of(event.winner) == 0:
            return JokerResult(add_mult=2.0)
        return None


class LeSergent(Joker):
    id = "le_sergent"
    name = "Le Sergent"
    description = "Each consecutive trick win: +0.5 Mult. Resets on losing."
    cost = 7

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        state[f"{self.id}_streak"] = 0
        return None

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if team_of(event.winner) == 0:
            streak = state.get(f"{self.id}_streak", 0) + 1
            state[f"{self.id}_streak"] = streak
            return JokerResult(add_mult=0.5)
        state[f"{self.id}_streak"] = 0
        return None


class LeDernierMot(Joker):
    id = "le_dernier_mot"
    name = "Le Dernier Mot"
    description = "Dix de Der is worth ×2 Mult, not 10 flat points."
    cost = 8

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        # Dix de Der is awarded to whichever team wins the last trick — so the
        # joker must fire whenever the NS team won it (South *or* North), not
        # only when South personally won. The pre-3.2 code keyed on
        # event.winner == Seat.SOUTH and silently failed to apply when North
        # took the last trick.
        if event.is_last and team_of(event.winner) == 0:
            # Remove the flat Dix de Der bonus and replace with ×2 mult.
            # If no_dix_de_der boss is active the bonus was already 0, so don't subtract.
            dix_de_der = 0 if state.get("no_dix_de_der", False) else 10
            return JokerResult(add_chips=-dix_de_der, times_mult=2.0)
        return None


class LExecuteur(Joker):
    id = "l_executeur"
    name = "L'Exécuteur"
    description = "The last trick is worth 50 points instead of 10, and applies a ×1.5 multiplier."
    cost = 8
    is_unlockable = True

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.is_last and team_of(event.winner) == 0:
            return JokerResult(add_chips=40, times_mult=1.5)
        return None


# ── 4.5.0 Conditional Engines ──────────────────────────────────────────────


def _winning_card(event: TrickWonEvent) -> Any:
    """Find the card the trick winner played by walking the seat order."""
    seat = event.leader_seat
    for card in event.cards:
        if seat == event.winner:
            return card
        seat = seat.next_seat()
    return None


class LeCavalierNoir(Joker):
    """Crossing suits — rewards taking a Heart-led trick with a Spade."""

    id = "le_cavalier_noir"
    name = "Le Cavalier Noir"
    description = "Win a Heart-led trick with a Spade: ×3 Mult."
    cost = 7
    rarity = Rarity.UNCOMMON

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if team_of(event.winner) != 0 or not event.cards:
            return None
        if event.cards[0].suit != Suit.HEARTS:
            return None
        winning = _winning_card(event)
        if winning is not None and winning.suit == Suit.SPADES:
            return JokerResult(times_mult=3.0)
        return None


class LArcEnCiel(Joker):
    """Chaos jester — every trick won by a suit different from the lead suit
    adds +2 Mult. The +2s accumulate naturally across the round."""

    id = "l_arc_en_ciel"
    name = "L'Arc-en-Ciel"
    description = "Each NS trick whose winning card's suit ≠ lead suit: +2 Mult."
    cost = 8
    rarity = Rarity.UNCOMMON

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if team_of(event.winner) != 0 or len(event.cards) < 2:
            return None
        lead_suit = event.cards[0].suit
        winning = _winning_card(event)
        if winning is not None and winning.suit != lead_suit:
            return JokerResult(add_mult=2.0)
        return None

