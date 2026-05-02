from __future__ import annotations

from belote.deck import Rank
from belote.game import Seat

from ...engine.event_bus import RoundEndEvent, TrickWonEvent
from ..base import Joker, JokerResult


class LAvare(Joker):
    id = "lavare"
    name = "L'Avare"
    description = "For each 7 or 8 still in your hand at round end, gain +$1 and +3 chips."
    cost = 5

    def on_round_end(self, event: RoundEndEvent) -> JokerResult | None:
        count = sum(1 for c in event.hand_remainder if c.rank in (Rank.SEVEN, Rank.EIGHT))
        if count > 0:
            return JokerResult(add_chips=count * 3, add_money=count)
        return None


class LaSentinelle(Joker):
    id = "la_sentinelle"
    name = "La Sentinelle"
    description = (
        "If the trump Jack never leaves your hand (you win no trick with it), gain ×3 Mult."
    )
    cost = 9

    def on_round_end(self, event: RoundEndEvent) -> JokerResult | None:
        trump = event.trump
        if not trump:
            return None
        has_trump_jack = any(c.suit == trump and c.rank == Rank.JACK for c in event.hand_remainder)
        if has_trump_jack:
            return JokerResult(times_mult=3.0)
        return None


class LeFantome(Joker):
    id = "le_fantome"
    name = "Le Fantôme"
    description = "Any card left unplayed in your hand at round end contributes +0.5 Mult per card."
    cost = 7

    def on_round_end(self, event: RoundEndEvent) -> JokerResult | None:
        count = len(event.hand_remainder)
        if count > 0:
            return JokerResult(add_mult=0.5 * count)
        return None


class LAccumulateur(Joker):
    id = "laccumulateur"
    name = "L'Accumulateur"
    description = "For every 7 or 8 you win in a trick, gain +5 chips at round end."
    cost = 6

    def __init__(self) -> None:
        self._stored_chips = 0

    def on_round_start(self) -> JokerResult | None:
        self._stored_chips = 0
        return None

    def on_trick_won(self, event: TrickWonEvent) -> JokerResult | None:
        if event.winner == Seat.SOUTH:
            count = sum(1 for c in event.cards if c.rank in (Rank.SEVEN, Rank.EIGHT))
            self._stored_chips += count * 5
        return None

    def on_round_end(self, event: RoundEndEvent) -> JokerResult | None:
        if self._stored_chips > 0:
            return JokerResult(add_chips=self._stored_chips)
        return None
