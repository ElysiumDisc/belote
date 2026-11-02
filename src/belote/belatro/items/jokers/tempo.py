"""4.11.0 — tempo, command and fortune jokers (plus the secret Petit Poucet)."""

from __future__ import annotations

from typing import Any

from belote.deck import Rank
from belote.game import Seat, team_of

from ...engine.event_bus import DeclarationScoredEvent, RoundEndEvent, TrickWonEvent
from ..base import Joker, JokerResult, Rarity, is_trump_card

# L'Horloger's run-scoped counter (its first copy's `state_key("rounds")`):
# outlives the round via `Joker.persistent_keys` — `_harvest_round_state`
# copies it into `run.card_enhancements`, which seeds the next round.
HORLOGER_KEY = "l_horloger_rounds"


class LeMarechal(Joker):
    """Leads the opening charge."""

    id = "le_marechal"
    name = "Le Maréchal"
    description = "Your team wins the first trick of the round: ×1.5 Mult."
    cost = 7
    rarity = Rarity.UNCOMMON

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.trick_number == 1 and team_of(event.winner) == 0:
            return JokerResult(times_mult=1.5)
        return None


_METRONOME_MAX = 3


class LeMetronome(Joker):
    """Keeps the beat: consecutive trick wins speed up the tempo."""

    id = "le_metronome"
    name = "Le Métronome"
    description = (
        "Your team's winning streak keeps the beat: each trick won after the first "
        "in a row adds +1 Mult per beat (+1, +2, max +3). A lost trick resets the tempo."
    )
    cost = 8
    rarity = Rarity.UNCOMMON

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        state[self.state_key("tempo")] = 0
        return None

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if team_of(event.winner) != 0:
            state[self.state_key("tempo")] = 0
            return None
        tempo = int(state.get(self.state_key("tempo"), 0)) + 1
        state[self.state_key("tempo")] = tempo
        beat = min(tempo - 1, _METRONOME_MAX)  # the first win only starts the tempo
        return JokerResult(add_mult=float(beat)) if beat > 0 else None


_HORLOGER_STEP = 0.5
_HORLOGER_CAP_ROUNDS = 12


class LHorloger(Joker):
    """Winds up over the run; a failed contract breaks the spring."""

    id = "l_horloger"
    name = "L'Horloger"
    description = (
        "+0.5 Mult per consecutive round this run without a failed contract "
        "(max +6). Resets when your team fails a contract."
    )
    cost = 7
    rarity = Rarity.UNCOMMON
    persistent_keys = ("rounds",)

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        rounds = min(int(state.get(self.state_key("rounds"), 0)), _HORLOGER_CAP_ROUNDS)
        if rounds <= 0:
            return None
        return JokerResult(add_mult=_HORLOGER_STEP * rounds)

    def on_round_end(self, event: RoundEndEvent, state: dict[str, Any]) -> JokerResult | None:
        if getattr(event, "re_emit", False) or event.taker_seat is None:
            return None  # no contract played: the clock neither ticks nor stops
        if event.taker_seat in (Seat.SOUTH, Seat.NORTH) and event.breakdown.is_failed:
            state[self.state_key("rounds")] = 0
        else:
            key = self.state_key("rounds")
            state[key] = int(state.get(key, 0)) + 1
        return None


class LeCapitaine(Joker):
    """Rewards the player taking command."""

    id = "le_capitaine"
    name = "Le Capitaine"
    description = "You (South) take the contract and make it: +4 Mult."
    cost = 5

    def on_round_end(self, event: RoundEndEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.taker_seat == Seat.SOUTH and not event.breakdown.is_failed:
            return JokerResult(add_mult=4.0)
        return None


class LeMaitreDAtout(Joker):
    """The master trumps — Jack and Nine — earn their keep."""

    id = "le_maitre_d_atout"
    name = "Le Maître d'Atout"
    description = "Your team wins a trick with the trump Jack: +3 Mult; with the trump 9: +2 Mult."
    cost = 6

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if team_of(event.winner) != 0:
            return None
        card = event.winning_card
        if card is None or not is_trump_card(card, event.trump):
            return None
        if card.rank == Rank.JACK:
            return JokerResult(add_mult=3.0)
        if card.rank == Rank.NINE:
            return JokerResult(add_mult=2.0)
        return None


class LeRentier(Joker):
    """Lives off his savings."""

    id = "le_rentier"
    name = "Le Rentier"
    description = "Round start: +1 Mult per $10 you hold (max +4)."
    cost = 6

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        # `current_money` is the pre-round wallet snapshot (see LePreteur).
        bonus = min(int(state.get("current_money", 0)) // 10, 4)
        return JokerResult(add_mult=float(bonus)) if bonus > 0 else None


class LeJoaillier(Joker):
    """Carrés are jewels."""

    id = "le_joaillier"
    name = "Le Joaillier"
    description = "Each Carré your team declares: +$3 and ×2 Mult. Each other annonce: +$1."
    cost = 6

    def on_declaration(
        self, event: DeclarationScoredEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        if team_of(event.seat) != 0 or event.points <= 0:
            return None
        if event.declaration_type == "carre":
            return JokerResult(add_money=3, times_mult=2.0)
        return JokerResult(add_money=1)


class LePetitPoucet(Joker):
    """Secret (4.11.0): the smallest cards have the last word.

    Unlocked by `UnlockTracker._handle_trick` when South takes Dix de Der
    (the last trick) with a 7. Hidden from the Collection until then.
    """

    id = "le_petit_poucet"
    name = "Le Petit Poucet"
    description = "Each trick your team wins with a 7 or an 8: ×1.5 Mult."
    cost = 8
    rarity = Rarity.RARE
    is_unlockable = True
    is_secret = True
    secret_hint = "A secret joker hides here… let the smallest card have the very last word."

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if team_of(event.winner) != 0:
            return None
        card = event.winning_card
        if card is not None and card.rank in (Rank.SEVEN, Rank.EIGHT):
            return JokerResult(times_mult=1.5)
        return None
