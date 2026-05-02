from __future__ import annotations

from belote.deck import Rank, Suit, card_points
from belote.game import Seat

from ...engine.event_bus import BeloteAnnouncedEvent, RoundEndEvent, TrickWonEvent
from ..base import Joker, JokerResult


class LIdeologue(Joker):
    id = "l_ideologue"
    name = "L'Idéologue"
    description = "Only activates on Sans Atout. Jacks score as 20 points each."
    cost = 8
    is_unlockable = True

    def on_trick_won(self, event: TrickWonEvent) -> JokerResult | None:
        # Sans Atout has event.trump as None
        if event.winner == Seat.SOUTH and event.trump is None:
            jacks = sum(1 for c in event.cards if c.rank == Rank.JACK)
            if jacks > 0:
                # In Sans Atout, Jack is worth 2. We want it to be 20.
                return JokerResult(add_chips=jacks * 18)
        return None


class LeFanatique(Joker):
    id = "le_fanatique"
    name = "Le Fanatique"
    description = "Only activates on Tout Atout. Every trick you win beyond the 4th adds ×1.5 Mult."
    cost = 8
    is_unlockable = True

    def __init__(self) -> None:
        self._wins = 0

    def on_round_start(self) -> JokerResult | None:
        self._wins = 0
        return None

    def on_trick_won(self, event: TrickWonEvent) -> JokerResult | None:
        # DEFERRED: Needs contract check (Tout Atout)
        if event.winner == Seat.SOUTH:
            self._wins += 1
            if self._wins > 4:
                return JokerResult(times_mult=1.5)
        return None


class LeDiplomate(Joker):
    id = "le_diplomate"
    name = "Le Diplomate"
    description = (
        "Win a trick containing both a King AND Queen of the same suit → that trick scores ×2."
    )
    cost = 7

    def on_trick_won(self, event: TrickWonEvent) -> JokerResult | None:
        if event.winner == Seat.SOUTH:
            suits: dict[Suit, set[Rank]] = {}
            for c in event.cards:
                if c.rank in (Rank.KING, Rank.QUEEN):
                    suits.setdefault(c.suit, set()).add(c.rank)

            for ranks in suits.values():
                if len(ranks) == 2:  # Both King and Queen present
                    return JokerResult(times_mult=2.0)
        return None


class LePatriote(Joker):
    id = "le_patriote"
    name = "Le Patriote"
    description = "All Trump cards score +50% extra points when they win a trick."
    cost = 6

    def on_trick_won(self, event: TrickWonEvent) -> JokerResult | None:
        if event.winner == Seat.SOUTH and event.trump:
            trump_pts = sum(
                card_points(c, event.trump) for c in event.cards if c.suit == event.trump
            )
            if trump_pts > 0:
                return JokerResult(add_chips=trump_pts // 2)
        return None


class LeRebelle(Joker):
    id = "le_rebelle"
    name = "Le Rebelle"
    description = "The Belote/Rebelote declaration gives ×3 Mult instead of a flat 20 points."
    cost = 8

    def on_belote(self, event: BeloteAnnouncedEvent) -> JokerResult | None:
        if event.seat == Seat.SOUTH:
            return JokerResult(add_chips=-20, times_mult=3.0)
        return None


class LePuriste(Joker):
    id = "le_puriste"
    name = "Le Puriste"
    description = "If you win a round playing Sans Atout, double your cash payout."
    cost = 7

    def on_round_end(self, event: RoundEndEvent) -> JokerResult | None:
        # Sans Atout means trump is None.
        if (
            event.trump is None
            and not getattr(event.breakdown, "is_failed", True)
            and event.taker_seat in (Seat.SOUTH, Seat.NORTH)
        ):
            return JokerResult(
                add_money=10
            )  # Using a fixed $10 as a stand-in for "double cash payout"
        return None


class LIllusionniste(Joker):
    id = "lillusionniste"
    name = "L'Illusionniste"
    description = (
        "Jacks of non-trump suits take on the value of Trump Jacks (20 points) for the round."
    )
    cost = 9

    def on_trick_won(self, event: TrickWonEvent) -> JokerResult | None:
        if event.winner == Seat.SOUTH and event.trump:
            extra_pts = sum(
                18 for c in event.cards if c.rank == Rank.JACK and c.suit != event.trump
            )
            if extra_pts > 0:
                return JokerResult(add_chips=extra_pts)
        return None
