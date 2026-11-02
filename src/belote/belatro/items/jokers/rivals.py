"""4.11.0 — jokers that profit from the opponents (East / West)."""

from __future__ import annotations

from typing import Any

from belote.deck import Card, Rank, Suit
from belote.game import Seat, team_of

from ...engine.event_bus import (
    BeloteAnnouncedEvent,
    DeclarationScoredEvent,
    RoundEndEvent,
    TrickWonEvent,
)
from ..base import Joker, JokerResult, Rarity, is_trump_card

_EW = 1  # team index of the opponents


def is_honor(card: Card, trump: Suit | None) -> bool:
    """Belote honors: J / 9 / A of trump, A / 10 of the other suits.

    Under Sans Atout (`trump=None`) every suit is a plain suit (A / 10);
    under Tout Atout every suit is trump (J / 9 / A).
    """
    if is_trump_card(card, trump):
        return card.rank in (Rank.JACK, Rank.NINE, Rank.ACE)
    return card.rank in (Rank.ACE, Rank.TEN)


class LeContrebandier(Joker):
    """Smuggles the opponents' best cards out of their hands."""

    id = "le_contrebandier"
    name = "Le Contrebandier"
    description = "Each opponent honor your team captures (trump J/9/A, other suits A/10): +1 Mult."
    cost = 6

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if team_of(event.winner) != 0:
            return None
        honors = sum(1 for c in event.cards_by(_EW) if is_honor(c, event.trump))
        return JokerResult(add_mult=float(honors)) if honors else None


class LaCommere(Joker):
    """Annonces are public — the village gossip just sells the story."""

    id = "la_commere"
    name = "La Commère"
    description = (
        "Whenever the opponents score an annonce (Tierce, Carré…) or complete Belote-Rebelote: +$2."
    )
    cost = 5

    def on_declaration(
        self, event: DeclarationScoredEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        # points > 0: a declaration zeroed by Le Mime is nothing to gossip about.
        if team_of(event.seat) == _EW and event.points > 0:
            return JokerResult(add_money=2)
        return None

    def on_belote(self, event: BeloteAnnouncedEvent, state: dict[str, Any]) -> JokerResult | None:
        if getattr(event, "re_emit", False):
            return None
        if team_of(event.seat) == _EW and event.is_rebelote:
            return JokerResult(add_money=2)
        return None


class LeRempart(Joker):
    """Rewards defence: the opponents took the contract and went down."""

    id = "le_rempart"
    name = "Le Rempart"
    description = "When the opponents take the contract and fail it: +$3 and ×2 Mult."
    cost = 7
    rarity = Rarity.UNCOMMON

    def on_round_end(self, event: RoundEndEvent, state: dict[str, Any]) -> JokerResult | None:
        if getattr(event, "re_emit", False):
            return None
        if event.taker_seat in (Seat.EAST, Seat.WEST) and event.breakdown.is_failed:
            return JokerResult(add_money=3, times_mult=2.0)
        return None


class LaRemontee(Joker):
    """The comeback: lose the first three tricks, make the contract anyway."""

    id = "la_remontee"
    name = "La Remontée"
    description = (
        "The opponents win at least 2 of the first 3 tricks, yet your team makes "
        "its contract: ×3 Mult."
    )
    cost = 8
    rarity = Rarity.RARE

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        state[self.state_key("early_losses")] = 0
        return None

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.trick_number <= 3 and team_of(event.winner) == _EW:
            state[self.state_key("early_losses")] = (
                int(state.get(self.state_key("early_losses"), 0)) + 1
            )
        return None

    def on_round_end(self, event: RoundEndEvent, state: dict[str, Any]) -> JokerResult | None:
        if getattr(event, "re_emit", False):
            return None
        made = event.taker_seat in (Seat.SOUTH, Seat.NORTH) and not event.breakdown.is_failed
        if made and state.get(self.state_key("early_losses"), 0) >= 2:
            return JokerResult(times_mult=3.0)
        return None
