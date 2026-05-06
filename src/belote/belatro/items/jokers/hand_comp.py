from __future__ import annotations

from typing import Any

from belote.deck import Rank
from belote.game import Seat

from ...engine.event_bus import RoundEndEvent, TrickWonEvent
from ..base import Joker, JokerResult


class LAvare(Joker):
    id = "lavare"
    name = "L'Avare"
    description = "For each 7 or 8 still in your hand at round end, gain +$1 and +3 chips."
    cost = 5

    def on_round_end(self, event: RoundEndEvent, state: dict[str, Any]) -> JokerResult | None:
        count = sum(1 for c in event.hand_remainder if c.rank in (Rank.SEVEN, Rank.EIGHT))
        if count > 0:
            return JokerResult(add_chips=count * 3, add_money=count)
        return None


class LaSentinelle(Joker):
    id = "la_sentinelle"
    name = "La Sentinelle"
    description = (
        "If you are dealt the trump Jack and win NO trick with it, gain ×3 Mult."
    )
    cost = 9

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        # We can't see the dealt hand from on_round_start, but we can detect
        # whether South was the player who held the trump Jack by inspecting
        # the trick in which it was played (each player plays only their own
        # cards, so the seat that played the Jack is the seat that was dealt
        # it). See on_trick_won.
        state[f"{self.id}_had_jack"] = False
        state[f"{self.id}_won_with_jack"] = False
        return None

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        trump = event.trump
        if not trump:
            return None

        # Reconstruct who played each card from leader_seat + card index.
        # Seat order: SOUTH→EAST→NORTH→WEST→SOUTH.
        seat = event.leader_seat
        for card in event.cards:
            if card.suit == trump and card.rank == Rank.JACK and seat == Seat.SOUTH:
                # Only South being dealt the Jack matters for this joker.
                state[f"{self.id}_had_jack"] = True
                if event.winner == Seat.SOUTH:
                    state[f"{self.id}_won_with_jack"] = True
            seat = seat.next_seat()
        return None

    def on_round_end(self, event: RoundEndEvent, state: dict[str, Any]) -> JokerResult | None:
        if state.get(f"{self.id}_had_jack") and not state.get(f"{self.id}_won_with_jack"):
            return JokerResult(times_mult=3.0)
        return None


class LeFantome(Joker):
    id = "le_fantome"
    name = "Le Fantôme"
    description = "Any card left unplayed in your hand at round end contributes +0.5 Mult per card."
    cost = 7

    def on_round_end(self, event: RoundEndEvent, state: dict[str, Any]) -> JokerResult | None:
        count = len(event.hand_remainder)
        if count > 0:
            return JokerResult(add_mult=0.5 * count)
        return None


class LAccumulateur(Joker):
    id = "laccumulateur"
    name = "L'Accumulateur"
    description = "For every 7 or 8 you win in a trick, gain +5 chips at round end."
    cost = 6

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        state[f"{self.id}_stored_chips"] = 0
        return None

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.winner == Seat.SOUTH:
            count = sum(1 for c in event.cards if c.rank in (Rank.SEVEN, Rank.EIGHT))
            stored = state.get(f"{self.id}_stored_chips", 0)
            state[f"{self.id}_stored_chips"] = stored + (count * 5)
        return None

    def on_round_end(self, event: RoundEndEvent, state: dict[str, Any]) -> JokerResult | None:
        stored = state.get(f"{self.id}_stored_chips", 0)
        if stored > 0:
            return JokerResult(add_chips=stored)
        return None
