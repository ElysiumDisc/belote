"""Void inference under La Déluge + Le Républicain (4.8.2 T2).

La Déluge (`seven_eight_trump`) makes 7s and 8s of any suit rank as trump.
Le Républicain (`republicain_wild`) makes 7s and 8s wildly legal on any
trick — they may be played in lieu of following lead suit. The
intersection of these two rules is a void-inference edge case:

- Under plain La Déluge: an off-lead 7 or 8 *is* an admission of voidness,
  because the player must follow lead suit if able and the 7/8's
  trump-status doesn't override that rule.
- Under Le Républicain + La Déluge: an off-lead 7/8 is NO LONGER an
  admission of voidness — the wild rule explicitly permits playing it
  on any trick.

`_update_voids` already gates on `republicain_wild` in `_process_trick_voids`,
but no test covers the combined regime today. This pins the contract.
"""

from __future__ import annotations

from belote.ai import AIPlayer, Difficulty
from belote.deck import Card, Rank, Suit
from belote.game import GameState, Phase, Seat, TrickCard


def _state_with_completed_trick(
    completed: tuple[tuple[TrickCard, ...], ...],
    *,
    republicain_wild: bool,
    trump: Suit | None = Suit.HEARTS,
    seven_eight_trump: bool = False,
) -> GameState:
    from belote.game import BossModifiers
    bm = BossModifiers(seven_eight_trump=seven_eight_trump)
    joker_state: dict[str, object] = {}
    if republicain_wild:
        joker_state["republicain_wild"] = True
    return GameState(
        hands=((), (), (), ()),
        turn=Seat.SOUTH,
        phase=Phase.PLAYING,
        trump=trump,
        contract="hearts",
        taker=Seat.SOUTH,
        completed_tricks=completed,
        boss_modifiers=bm,
        _joker_state=joker_state,
    )


def test_deluge_off_lead_seven_infers_void_without_republicain() -> None:
    """Under La Déluge alone, a 7 played off-lead-suit is still proof of
    voidness in the lead suit — the trump-status of 7s doesn't change the
    suit-follow rule."""
    # Trick: SOUTH leads ♠J, WEST plays ♠Q, NORTH plays ♠K, EAST plays ♣7.
    # EAST played off-lead — must be void in spades.
    trick = (
        TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.JACK)),
        TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.QUEEN)),
        TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.KING)),
        TrickCard(Seat.EAST, Card(Suit.CLUBS, Rank.SEVEN)),
    )
    state = _state_with_completed_trick(
        (trick,), republicain_wild=False, seven_eight_trump=True
    )
    player = AIPlayer(Seat.SOUTH, Difficulty.HARD)
    player.update_memory(state)
    # `_update_voids` is what populates `known_voids` — it runs inside
    # `decide_card`, not `update_memory`. Call it directly so the test
    # stays at the unit-test layer.
    player._update_voids(state)

    assert Suit.SPADES in player.memory.known_voids[Seat.EAST], (
        "AI failed to infer EAST's spade void from an off-lead 7 under La Déluge"
    )


def test_republicain_wild_seven_does_not_infer_void() -> None:
    """Under Le Républicain (+/- La Déluge), an off-lead 7 or 8 is a wild
    play and NOT proof of voidness. The AI must NOT infer the void."""
    trick = (
        TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.JACK)),
        TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.QUEEN)),
        TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.KING)),
        TrickCard(Seat.EAST, Card(Suit.CLUBS, Rank.SEVEN)),  # wild!
    )
    state = _state_with_completed_trick(
        (trick,), republicain_wild=True, seven_eight_trump=False
    )
    player = AIPlayer(Seat.SOUTH, Difficulty.HARD)
    player.update_memory(state)
    # `_update_voids` is what populates `known_voids` — it runs inside
    # `decide_card`, not `update_memory`. Call it directly so the test
    # stays at the unit-test layer.
    player._update_voids(state)

    assert Suit.SPADES not in player.memory.known_voids[Seat.EAST], (
        "AI wrongly inferred a spade void from an off-lead 7 under Le Républicain"
    )


def test_republicain_plus_deluge_combined_does_not_infer_void() -> None:
    """Combined Le Républicain + La Déluge: 7s/8s are wild AND act as
    trumps. The wildness gate still suppresses void inference — the AI
    cannot conclude EAST is void in spades from a ♣7 play."""
    trick = (
        TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.JACK)),
        TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.QUEEN)),
        TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.KING)),
        TrickCard(Seat.EAST, Card(Suit.CLUBS, Rank.EIGHT)),
    )
    state = _state_with_completed_trick(
        (trick,), republicain_wild=True, seven_eight_trump=True
    )
    player = AIPlayer(Seat.SOUTH, Difficulty.HARD)
    player.update_memory(state)
    # `_update_voids` is what populates `known_voids` — it runs inside
    # `decide_card`, not `update_memory`. Call it directly so the test
    # stays at the unit-test layer.
    player._update_voids(state)

    assert Suit.SPADES not in player.memory.known_voids[Seat.EAST]


def test_republicain_does_not_block_void_inference_from_non_wild_card() -> None:
    """Sanity check: under Le Républicain, an off-lead NON-7/8 card still
    proves voidness — only 7s and 8s are wild, not all off-lead plays."""
    trick = (
        TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.JACK)),
        TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.QUEEN)),
        TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.KING)),
        TrickCard(Seat.EAST, Card(Suit.CLUBS, Rank.NINE)),  # 9 is NOT wild
    )
    state = _state_with_completed_trick(
        (trick,), republicain_wild=True, seven_eight_trump=False
    )
    player = AIPlayer(Seat.SOUTH, Difficulty.HARD)
    player.update_memory(state)
    # `_update_voids` is what populates `known_voids` — it runs inside
    # `decide_card`, not `update_memory`. Call it directly so the test
    # stays at the unit-test layer.
    player._update_voids(state)

    assert Suit.SPADES in player.memory.known_voids[Seat.EAST]
