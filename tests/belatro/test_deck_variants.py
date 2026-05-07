from __future__ import annotations

from dataclasses import replace

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.core.scoring import ScoreAccumulator
from belote.belatro.engine.event_bus import TrickWonEvent
from belote.deck import Card, Rank, Suit
from belote.game import GameState, Seat


def make_trick_event(
    winner: Seat = Seat.SOUTH,
    trick_number: int = 1,
    is_last: bool = False,
    card_points: int = 0,
    cards: tuple[Card, ...] = (),
    trump: Suit | None = None,
) -> TrickWonEvent:
    return TrickWonEvent(
        winner=winner,
        cards=cards,
        trick_number=trick_number,
        is_last=is_last,
        card_points=card_points,
        trump=trump,
    )


class TestDeckVariants:
    # 6. Républicain deck: team-restricted bonus (Fixed B6)
    def test_republicain_deck_bonus(self) -> None:
        """Verify +5 chips per 7 or 8 in any trick for Républicain deck."""
        acc = ScoreAccumulator(deck_id="republicain")
        state = GameState(hands=((), (), (), ()))
        state = replace(state, _chips=0, _mult=1.0)

        # Trick with a 7 and an 8
        cards = (
            Card(Suit.SPADES, Rank.SEVEN),
            Card(Suit.HEARTS, Rank.EIGHT),
            Card(Suit.DIAMONDS, Rank.ACE),
            Card(Suit.CLUBS, Rank.KING),
        )
        # card_points is what the trick itself scored (e.g. from Ace and King)
        evt = make_trick_event(cards=cards, card_points=15)

        new_state = acc.update_state(state, evt)

        # Base chips (15) + 2 wild cards * 5 chips = 25
        assert new_state._chips == 25

    def test_aristocrate_deck_initial_money(self) -> None:
        """Verify L'Aristocrate starts with $6."""
        run = BelAtroRun(deck_id="aristocrate")
        assert run.economy.money == 6

    def test_anarchiste_deck_initial_money(self) -> None:
        """Verify L'Anarchiste starts with $19."""
        run = BelAtroRun(deck_id="anarchiste")
        assert run.economy.money == 19

    def test_joueur_deck_initial_money(self) -> None:
        """Verify Le Joueur starts with $14."""
        run = BelAtroRun(deck_id="joueur")
        assert run.economy.money == 14

    def test_joueur_deck_boss_every_2_flag_set(self) -> None:
        """Le Joueur starts with the boss_every_2 enhancement so even-ante Big
        Blinds also roll a boss in main.py."""
        run = BelAtroRun(deck_id="joueur")
        assert run.card_enhancements.get("boss_every_2") is True

    def test_other_decks_do_not_set_boss_every_2(self) -> None:
        """Sanity: only Le Joueur has boss_every_2 — guards against accidental
        regressions if the dispatcher in run_state.py changes shape."""
        for deck_id in ("classique", "republicain", "aristocrate", "ermite", "veteran",
                        "flambeur", "anarchiste", "marseille", "coinche"):
            run = BelAtroRun(deck_id=deck_id)
            assert not run.card_enhancements.get("boss_every_2"), (
                f"unexpected boss_every_2 on {deck_id}"
            )

    def test_ermite_deck_initial_joker(self) -> None:
        """Verify L'Ermite starts with La Sentinelle."""
        run = BelAtroRun(deck_id="ermite")
        assert len(run.jokers) == 1
        assert run.jokers[0].id == "la_sentinelle"

    def test_flambeur_deck_initial_joker(self) -> None:
        """Verify Le Flambeur starts with L'Aventurier."""
        run = BelAtroRun(deck_id="flambeur")
        assert len(run.jokers) == 1
        assert run.jokers[0].id == "l_aventurier"

    def test_veteran_deck_free_planet(self) -> None:
        """Verify Le Vétéran starts with one free planet applied."""
        run = BelAtroRun(deck_id="veteran")
        # In __post_init__, if free_planet is True, it applies a random planet reward
        assert len(run.contract_levels) == 1
