"""Sans Atout hard-AI play correctness (4.8.2 — B1 + B2).

Pins the fix for two SA-specific bugs in `_score_winning_strategy`:

- **B1**: An off-suit card cannot win a trick under SA (per `_card_beats`),
  but pre-4.8.2 the candidate's rank was `_NONTRUMP_ORDER[card.rank]`
  regardless of suit. So an off-suit Ace (rank 7) compared against the
  lead-suit highest rank (e.g. a Jack at rank 3) would fire `win_bonus`
  and the AI would burn its high off-suit card thinking it won.

- **B2**: The 2-PLY opponent-trump-fear penalty assumes opponents can
  trump the candidate winner. Under SA there is no trump, so the penalty
  is moot. Pre-4.8.2 it still fired (because `None not in opp_voids` is
  True and `card.suit != trump` always holds), wrongly penalizing
  winning plays by -8.
"""

from __future__ import annotations

from belote.ai import AIPlayer, Difficulty
from belote.deck import Card, Contract, Rank, Suit
from belote.game import GameState, Phase, Seat, TrickCard


def _sa_state(
    hand: tuple[Card, ...],
    current_trick: tuple[TrickCard, ...],
    *,
    completed_tricks: tuple[tuple[TrickCard, ...], ...] = (),
) -> GameState:
    return GameState(
        hands=(hand, (), (), ()),  # SOUTH is index 0
        turn=Seat.SOUTH,
        phase=Phase.PLAYING,
        trump=None,
        contract=Contract.SANS_ATOUT,
        taker=Seat.SOUTH,
        current_trick=current_trick,
        completed_tricks=completed_tricks,
    )


def test_sa_void_in_lead_does_not_burn_high_off_suit_card() -> None:
    """When void in lead under SA, the hard AI must discard low — not its
    highest off-suit card. The pre-B1 bug made the AI score an off-suit
    Ace as a winning play.
    """
    player = AIPlayer(Seat.SOUTH, Difficulty.HARD)
    # SOUTH is void in clubs (the lead suit). Legal cards: any non-club.
    # Without the B1 fix, A♠ would be scored as winning (rank 7 > Jack 3)
    # even though no off-suit card can win the trick under SA.
    hand = (
        Card(Suit.SPADES, Rank.ACE),
        Card(Suit.SPADES, Rank.SEVEN),
        Card(Suit.HEARTS, Rank.SEVEN),
    )
    trick = (TrickCard(Seat.EAST, Card(Suit.CLUBS, Rank.JACK)),)
    state = _sa_state(hand, trick)
    card = player.decide_card(state)

    # The AI must discard low — not the Ace.
    assert card != Card(Suit.SPADES, Rank.ACE), (
        f"AI burned A♠ on a SA trick where it cannot win (off-suit). got={card}"
    )


def test_sa_score_winning_strategy_off_suit_gets_no_win_bonus() -> None:
    """Directly exercise `_score_winning_strategy` under SA with an off-suit
    candidate. The function must NOT credit a `win_bonus` because the card
    cannot win the trick.
    """
    player = AIPlayer(Seat.SOUTH, Difficulty.HARD)
    # Trick lead is C♣J; my candidate is S♠A (off-suit Ace).
    trick = (TrickCard(Seat.EAST, Card(Suit.CLUBS, Rank.JACK)),)
    state = _sa_state((Card(Suit.SPADES, Rank.ACE),), trick)

    score_off_suit = player._score_winning_strategy(
        Card(Suit.SPADES, Rank.ACE),
        state,
        trump=None,
        trick=trick,
        partner_winning=False,
        points=11,  # A's SA point value (set to its known value; not load-bearing)
        is_sa=True,
        highest_rank=3,  # Jack of lead = rank 3 in _NONTRUMP_ORDER
        opp_voids=set(),
    )
    # Without B1, this would have been ≥10 (win_bonus). With B1 it's
    # firmly negative (no win bonus, losing-and-partner-losing penalty).
    assert score_off_suit < 10.0, (
        f"Off-suit candidate scored {score_off_suit} (≥10 suggests win_bonus "
        "was still credited — B1 regression)."
    )


def test_sa_two_ply_trump_fear_suppressed() -> None:
    """The 2-PLY trump-fear penalty must NOT fire under SA. Build a state
    where the conditions would have fired pre-B2: void opponent in lead,
    one card already played, the candidate would win.
    """
    player = AIPlayer(Seat.SOUTH, Difficulty.HARD)
    # SOUTH is leading suit C; EAST played a low C (so SOUTH's J♣ wins
    # in-suit). Right-hand opponent (EAST again on next play) is "known
    # void" in clubs. Pre-B2 this triggered the -8 penalty.
    player.memory.known_voids[Seat.EAST] = {Suit.CLUBS}

    trick = (TrickCard(Seat.WEST, Card(Suit.CLUBS, Rank.SEVEN)),)
    candidate = Card(Suit.CLUBS, Rank.JACK)
    state = _sa_state((candidate,), trick)

    score_with_fear = player._score_winning_strategy(
        candidate,
        state,
        trump=None,
        trick=trick,
        partner_winning=False,
        points=2,  # Jack SA value (placeholder; not load-bearing)
        is_sa=True,
        highest_rank=0,  # 7 of clubs = rank 0 in _NONTRUMP_ORDER
        opp_voids={Suit.CLUBS},  # pre-B2 the penalty would fire
    )
    # Win bonus (10 mid-trick) must not be cancelled by the -8 trump-fear.
    # Threshold: win_bonus alone ≥ 10; if -8 fired the score would drop to ~2.
    assert score_with_fear >= 9.0, (
        f"Score {score_with_fear} suggests 2-PLY trump-fear fired under SA "
        "(should be suppressed by B2)."
    )
