"""4.5.0 starting-deck tests.

- L'Infiltré (ghost_lead): +2 Mult / +$1 when NS wins a trick by playing a
  trump on a non-trump lead (the player must have been void of lead suit).
- L'Architecte (buy_contract + annonce_cash_x2): +$2 on NS-won tricks that
  contain a card from a declared NS Annonce. (buy_contract UI hook is
  exercised separately in test_buy_contract_ui.py once the BelAtro main
  loop integration lands.)
"""

from __future__ import annotations

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.core.scoring import ScoreAccumulator
from belote.belatro.engine.event_bus import (
    DeclarationScoredEvent,
    TrickWonEvent,
)
from belote.belatro.run.decks import STARTING_DECKS
from belote.deck import Card, Rank, Suit
from belote.game import Declaration, GameState, Seat, Sequence

# ── Deck registration ───────────────────────────────────────────────────────


def test_infiltre_and_architecte_decks_registered() -> None:
    ids = {d.id for d in STARTING_DECKS}
    assert "infiltre" in ids
    assert "architecte" in ids


def test_infiltre_sets_ghost_lead_flag() -> None:
    run = BelAtroRun(deck_id="infiltre")
    assert run.card_enhancements.get("ghost_lead") is True


def test_architecte_sets_buy_contract_and_annonce_flags() -> None:
    run = BelAtroRun(deck_id="architecte")
    assert run.card_enhancements.get("buy_contract") is True
    assert run.card_enhancements.get("annonce_cash_x2") is True
    # +$4 over baseline so the player can seat one buy on the first round.
    assert run.economy.money == 8


# ── L'Infiltré scoring ──────────────────────────────────────────────────────


def _state_with(flag: str) -> GameState:
    return GameState(hands=((), (), (), ()), _joker_state={flag: True})


def test_ghost_lead_pays_when_ns_trumps_void() -> None:
    """SOUTH leads ♥7, EAST plays ♥10, NORTH wins by playing trump ♠J
    (void of hearts), WEST follows ♥K. NORTH won via void-trump → +2 Mult, +$1."""
    state = _state_with("ghost_lead")
    acc = ScoreAccumulator()
    event = TrickWonEvent(
        winner=Seat.NORTH,
        cards=(
            Card(Suit.HEARTS, Rank.SEVEN),    # SOUTH (lead)
            Card(Suit.HEARTS, Rank.TEN),      # EAST
            Card(Suit.SPADES, Rank.JACK),     # NORTH — trump on heart lead = void
            Card(Suit.HEARTS, Rank.KING),     # WEST
        ),
        trick_number=3,
        is_last=False,
        card_points=30,
        trump=Suit.SPADES,
        leader_seat=Seat.SOUTH,
    )
    out = acc.update_state(state, event)
    # +30 base chips, +2 mult (from 1.0 → 3.0), +$1 bonus.
    assert out._chips == 30
    assert out._mult == 3.0
    assert out._bonus_money == 1


def test_ghost_lead_silent_when_flag_off() -> None:
    state = GameState(hands=((), (), (), ()))  # no flag
    acc = ScoreAccumulator()
    event = TrickWonEvent(
        winner=Seat.NORTH,
        cards=(
            Card(Suit.HEARTS, Rank.SEVEN),
            Card(Suit.HEARTS, Rank.TEN),
            Card(Suit.SPADES, Rank.JACK),
            Card(Suit.HEARTS, Rank.KING),
        ),
        trick_number=3,
        is_last=False,
        card_points=30,
        trump=Suit.SPADES,
        leader_seat=Seat.SOUTH,
    )
    out = acc.update_state(state, event)
    assert out._mult == 1.0
    assert out._bonus_money == 0


def test_ghost_lead_silent_on_trump_led_trick() -> None:
    """Trump-led tricks aren't 'void plays' — every trump play is legal."""
    state = _state_with("ghost_lead")
    acc = ScoreAccumulator()
    event = TrickWonEvent(
        winner=Seat.SOUTH,
        cards=(
            Card(Suit.SPADES, Rank.SEVEN),
            Card(Suit.SPADES, Rank.TEN),
            Card(Suit.SPADES, Rank.JACK),
            Card(Suit.SPADES, Rank.QUEEN),
        ),
        trick_number=1,
        is_last=False,
        card_points=20,
        trump=Suit.SPADES,
        leader_seat=Seat.SOUTH,
    )
    out = acc.update_state(state, event)
    assert out._mult == 1.0
    assert out._bonus_money == 0


def test_ghost_lead_silent_when_ew_wins_void_play() -> None:
    """The deck rewards NS only — EW winning a void trump doesn't pay."""
    state = _state_with("ghost_lead")
    acc = ScoreAccumulator()
    event = TrickWonEvent(
        winner=Seat.EAST,
        cards=(
            Card(Suit.HEARTS, Rank.SEVEN),    # SOUTH (lead)
            Card(Suit.SPADES, Rank.JACK),     # EAST — void trump, EW team
            Card(Suit.HEARTS, Rank.TEN),      # NORTH
            Card(Suit.HEARTS, Rank.KING),     # WEST
        ),
        trick_number=3,
        is_last=False,
        card_points=30,
        trump=Suit.SPADES,
        leader_seat=Seat.SOUTH,
    )
    out = acc.update_state(state, event)
    # No NS-team gate fires → no bonus.
    assert out._mult == 1.0
    assert out._bonus_money == 0


def test_ghost_lead_silent_when_winner_didnt_trump_void() -> None:
    """SOUTH wins by following the lead with a higher card — no trump
    voiding involved, no bonus."""
    state = _state_with("ghost_lead")
    acc = ScoreAccumulator()
    event = TrickWonEvent(
        winner=Seat.SOUTH,
        cards=(
            Card(Suit.HEARTS, Rank.ACE),      # SOUTH (lead, wins with Ace)
            Card(Suit.HEARTS, Rank.SEVEN),    # EAST
            Card(Suit.HEARTS, Rank.EIGHT),    # NORTH
            Card(Suit.HEARTS, Rank.NINE),     # WEST
        ),
        trick_number=2,
        is_last=False,
        card_points=11,
        trump=Suit.SPADES,
        leader_seat=Seat.SOUTH,
    )
    out = acc.update_state(state, event)
    assert out._mult == 1.0
    assert out._bonus_money == 0


# ── L'Architecte annonce-cash-x2 ────────────────────────────────────────────


def _state_with_ns_tierce_in_hearts() -> GameState:
    """Inject a SOUTH Tierce of 9-10-J-hearts so on_trick_won can detect
    tricks that contain any of those cards."""
    seq = Sequence(
        length=3,
        top_rank=10,  # arbitrary; not consulted by our consumer
        suit=Suit.HEARTS,
        is_trump=True,
        cards=(
            Card(Suit.HEARTS, Rank.NINE),
            Card(Suit.HEARTS, Rank.TEN),
            Card(Suit.HEARTS, Rank.JACK),
        ),
    )
    decl = Declaration(seat=Seat.SOUTH, kind="sequence", detail=seq)
    return GameState(
        hands=((), (), (), ()),
        _joker_state={"annonce_cash_x2": True},
        declarations=(decl,),
    )


def test_annonce_cash_x2_pays_on_qualifying_trick() -> None:
    """A trick won by NS that contains one of the declared Annonce cards
    pays +$2 on top of normal scoring."""
    state = _state_with_ns_tierce_in_hearts()
    acc = ScoreAccumulator()
    # First the declaration scores — populates the joker_state card set.
    state = acc.update_state(
        state, DeclarationScoredEvent(Seat.SOUTH, "Tierce", 20)
    )
    # Then a trick with the J♥ (which is in the Tierce).
    event = TrickWonEvent(
        winner=Seat.SOUTH,
        cards=(
            Card(Suit.HEARTS, Rank.JACK),     # in the annonce
            Card(Suit.HEARTS, Rank.SEVEN),
            Card(Suit.HEARTS, Rank.EIGHT),
            Card(Suit.HEARTS, Rank.QUEEN),
        ),
        trick_number=2,
        is_last=False,
        card_points=20,
        trump=Suit.HEARTS,
        leader_seat=Seat.SOUTH,
    )
    out = acc.update_state(state, event)
    # +$2 from the deck rule on top of any other payouts.
    assert out._bonus_money == 2


def test_annonce_cash_x2_silent_on_non_annonce_trick() -> None:
    state = _state_with_ns_tierce_in_hearts()
    acc = ScoreAccumulator()
    state = acc.update_state(
        state, DeclarationScoredEvent(Seat.SOUTH, "Tierce", 20)
    )
    # A trick with none of {9♥, 10♥, J♥}.
    event = TrickWonEvent(
        winner=Seat.SOUTH,
        cards=(
            Card(Suit.SPADES, Rank.ACE),
            Card(Suit.SPADES, Rank.SEVEN),
            Card(Suit.SPADES, Rank.EIGHT),
            Card(Suit.SPADES, Rank.QUEEN),
        ),
        trick_number=3,
        is_last=False,
        card_points=11,
        trump=Suit.HEARTS,
        leader_seat=Seat.SOUTH,
    )
    out = acc.update_state(state, event)
    assert out._bonus_money == 0


def test_annonce_cache_cleared_between_rounds() -> None:
    """trigger_round_start must drop the cached card-set so a stale
    previous-round annonce doesn't double-pay in a round without declarations."""
    state = _state_with_ns_tierce_in_hearts()
    acc = ScoreAccumulator()
    state = acc.update_state(
        state, DeclarationScoredEvent(Seat.SOUTH, "Tierce", 20)
    )
    assert "_architecte_ns_annonce_cards" in state._joker_state

    next_round = acc.trigger_round_start(state)
    assert "_architecte_ns_annonce_cards" not in next_round._joker_state


def test_le_mime_suppresses_architecte_annonce_cash() -> None:
    """4.6.4: Le Mime (declarations_zero) must suppress L'Architecte's
    annonce-cash bonus.

    Pre-4.6.4 the DeclarationScoredEvent handler stamped
    `_ns_annonce_cards` into joker_state unconditionally, even when
    `state.boss_modifiers.declarations_zero` zeroed `event.points`. Le
    Mime's promise is "all declaration value zeroed" — the L'Architecte
    +$2/trick payout is declaration-derived, so it must be gated too.
    """
    from dataclasses import replace

    from belote.game import BossModifiers

    state = _state_with_ns_tierce_in_hearts()
    # Activate Le Mime on the state.
    state = replace(
        state, boss_modifiers=BossModifiers(declarations_zero=True)
    )
    acc = ScoreAccumulator()
    # Declaration scores 0 chips under Le Mime — the round_driver passes
    # points=0 in that case; the handler must also skip the harvest.
    state = acc.update_state(
        state, DeclarationScoredEvent(Seat.SOUTH, "Tierce", 0)
    )
    # The annonce-cards key must NOT have been stamped.
    assert "_architecte_ns_annonce_cards" not in state._joker_state
    assert "_ns_annonce_cards" not in state._joker_state

    # A subsequent trick that WOULD have qualified pre-4.6.4 must pay $0.
    event = TrickWonEvent(
        winner=Seat.SOUTH,
        cards=(
            Card(Suit.HEARTS, Rank.JACK),
            Card(Suit.HEARTS, Rank.SEVEN),
            Card(Suit.HEARTS, Rank.EIGHT),
            Card(Suit.HEARTS, Rank.QUEEN),
        ),
        trick_number=2,
        is_last=False,
        card_points=20,
        trump=Suit.HEARTS,
        leader_seat=Seat.SOUTH,
    )
    out = acc.update_state(state, event)
    assert out._bonus_money == 0, (
        f"Le Mime should suppress the L'Architecte $2 bonus; got "
        f"_bonus_money={out._bonus_money}."
    )


# ── L'Architecte buy-contract picker ────────────────────────────────────────


def test_buy_contract_picker_returns_chosen_suit() -> None:
    """Arrow-key navigate to the second option (Hearts) and press Enter →
    returns Suit.HEARTS."""
    from unittest.mock import MagicMock

    from belote.belatro.ui.announce import BelAtroAnnounce
    from belote.input import Key, KeyEvent

    reader = MagicMock()
    reader.read.side_effect = [
        KeyEvent(Key.DOWN),
        KeyEvent(Key.ENTER),
    ]
    out = BelAtroAnnounce.buy_contract_picker(reader)
    assert out is Suit.HEARTS


def test_buy_contract_picker_returns_sans_atout_sentinel() -> None:
    """Navigate to the last option (Sans Atout) and confirm — returns the
    SANS_ATOUT_BID string sentinel that `process_bid` recognises."""
    from unittest.mock import MagicMock

    from belote.belatro.ui.announce import BelAtroAnnounce
    from belote.game import SANS_ATOUT_BID
    from belote.input import Key, KeyEvent

    reader = MagicMock()
    # 6 options total (♠ ♥ ♦ ♣ TA SA). UP from index 0 wraps to index 5 (SA).
    reader.read.side_effect = [
        KeyEvent(Key.UP),
        KeyEvent(Key.ENTER),
    ]
    out = BelAtroAnnounce.buy_contract_picker(reader)
    assert out == SANS_ATOUT_BID


def test_buy_contract_picker_cancel_returns_none() -> None:
    from unittest.mock import MagicMock

    from belote.belatro.ui.announce import BelAtroAnnounce
    from belote.input import Key, KeyEvent

    reader = MagicMock()
    reader.read.return_value = KeyEvent(Key.ESC)
    assert BelAtroAnnounce.buy_contract_picker(reader) is None


def test_buy_contract_picker_eof_returns_none() -> None:
    """EOF on stdin must exit cleanly (mirrors the broader EOF discipline
    from 3.5.0 — see tests/test_input_eof.py)."""
    from unittest.mock import MagicMock

    from belote.belatro.ui.announce import BelAtroAnnounce
    from belote.input import Key, KeyEvent

    reader = MagicMock()
    reader.read.return_value = KeyEvent(Key.EOF)
    assert BelAtroAnnounce.buy_contract_picker(reader) is None
