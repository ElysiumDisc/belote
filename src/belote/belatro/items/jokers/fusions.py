"""5.0.0 — fusion jokers: what two named jokers become under Le Serment.

None of these is ever stocked by the shop (`shop_excluded`); the only way to
own one is to fuse its recipe's two jokers (see `belatro/run/fusion.py`).
Each is its parents' effects, combined and stronger.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from belote.deck import Rank
from belote.game import Seat, team_of

from ...engine.event_bus import BeloteAnnouncedEvent, RoundEndEvent, TrickWonEvent
from ..base import Joker, JokerResult, Rarity, is_trump_card
from .rivals import is_honor

if TYPE_CHECKING:
    from ...core.run_state import BelAtroRun

_NS, _EW = 0, 1


class _FusionJoker(Joker):
    shop_excluded = True
    fusable = False
    rarity = Rarity.RARE
    cost = 14


class LeGeneral(_FusionJoker):
    """Le Maréchal + Le Capitaine."""

    id = "le_general"
    name = "Le Général"
    description = "Your team wins the first trick: ×2 Mult. You (South) take the contract and make it: +6 Mult."

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.trick_number == 1 and team_of(event.winner) == _NS:
            return JokerResult(times_mult=2.0)
        return None

    def on_round_end(self, event: RoundEndEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.taker_seat == Seat.SOUTH and not event.breakdown.is_failed:
            return JokerResult(add_mult=6.0)
        return None


_TAMBOUR_MAX = 4


class LeTambourMajor(_FusionJoker):
    """Le Sergent + Le Métronome."""

    id = "le_tambour_major"
    name = "Le Tambour-Major"
    description = (
        "Each trick your team wins in a row adds +1 Mult per beat (+1, +2, … max +4). "
        "The first lost trick only skips a beat; the second in a row resets the drum."
    )

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        state[self.state_key("beat")] = 0
        state[self.state_key("missed")] = 0
        return None

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        beat_key, missed_key = self.state_key("beat"), self.state_key("missed")
        if team_of(event.winner) != _NS:
            missed = int(state.get(missed_key, 0)) + 1
            state[missed_key] = missed
            if missed >= 2:
                state[beat_key] = 0
            return None
        state[missed_key] = 0
        beat = min(int(state.get(beat_key, 0)) + 1, _TAMBOUR_MAX)
        state[beat_key] = beat
        return JokerResult(add_mult=float(beat))


class LAlphaEtLOmega(_FusionJoker):
    """Le Premier Sang + Le Dernier Mot."""

    id = "l_alpha_et_l_omega"
    name = "L'Alpha et l'Oméga"
    description = (
        "Your team wins the first trick: +3 Mult. Your team wins the last trick: ×2.5 Mult."
    )

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if team_of(event.winner) != _NS:
            return None
        if event.trick_number == 1:
            return JokerResult(add_mult=3.0)
        if event.is_last:
            return JokerResult(times_mult=2.5)
        return None


class LeCoupleRoyal(_FusionJoker):
    """Le Rebelle + Écho de Rebelote."""

    id = "le_couple_royal"
    name = "Le Couple Royal"
    description = "Your team's Belote: ×2 Mult. Its Rebelote: ×3 Mult (the 20 points stay)."

    def on_belote(self, event: BeloteAnnouncedEvent, state: dict[str, Any]) -> JokerResult | None:
        if team_of(event.seat) != _NS:
            return None
        return JokerResult(times_mult=3.0 if event.is_rebelote else 2.0)


class LeCorsaire(_FusionJoker):
    """Le Contrebandier + Le Maître d'Atout."""

    id = "le_corsaire"
    name = "Le Corsaire"
    description = (
        "Each opponent honor your team captures: +2 Mult. "
        "Your team wins a trick with the trump Jack: +4 Mult; with the trump 9: +3 Mult."
    )

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if team_of(event.winner) != _NS:
            return None
        mult = 2.0 * sum(1 for c in event.cards_by(_EW) if is_honor(c, event.trump))
        card = event.winning_card
        if card is not None and is_trump_card(card, event.trump):
            if card.rank == Rank.JACK:
                mult += 4.0
            elif card.rank == Rank.NINE:
                mult += 3.0
        return JokerResult(add_mult=mult) if mult else None


class Lucifer(_FusionJoker):
    """Le Traître + Le Démon — the curse fuses too."""

    id = "lucifer"
    name = "Lucifer"
    description = (
        "+4 Mult per trick your team wins, ×1.5 more when you (South) win it. "
        "Your partner still throws a trick every round."
    )
    is_corrupted = True
    rarity = Rarity.LEGENDARY
    cost = 16

    def on_purchase(self, run: BelAtroRun) -> None:
        run.partner_throws_trick = True

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if team_of(event.winner) != _NS:
            return None
        return JokerResult(add_mult=4.0, times_mult=1.5 if event.winner == Seat.SOUTH else 0.0)
