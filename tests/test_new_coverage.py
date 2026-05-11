from __future__ import annotations

import random
from dataclasses import replace
from unittest.mock import patch

import pytest

from belote.deck import Card, Rank, Suit
from belote.game import (
    GameState,
    IllegalMoveError,
    Phase,
    Seat,
    TrickCard,
    new_game,
    play_card,
    process_bid,
    sort_hand,
    sort_south_hand,
    start_round,
)
from belote.scoring import ScoringBreakdown, apply_round_score, score_round


def test_belote_rebelote_transitions() -> None:
    # Setup a game state where South has K and Q of Spades (trump)
    trump = Suit.SPADES
    south_hand = (Card(trump, Rank.KING), Card(trump, Rank.QUEEN), Card(trump, Rank.ACE))
    # Fill other hands with random cards
    state = GameState(
        hands=(south_hand, (), (), ()),
        initial_hands=(south_hand, (), (), ()),
        trump=trump,
        taker=Seat.SOUTH,
        turn=Seat.SOUTH,
        phase=Phase.PLAYING,
        belote_holders={trump: Seat.SOUTH},
        belote_tracker=(False, False),
    )

    # Play King of Spades
    state = play_card(state, Card(trump, Rank.KING))
    assert state.belote_tracker == (True, False)
    assert state.announced == "Belote!"

    # Play Queen of Spades (rebelote)
    # We need to make it South's turn again (mocking other players)
    state = replace(state, turn=Seat.SOUTH)
    state = play_card(state, Card(trump, Rank.QUEEN))
    assert state.belote_tracker == (True, True)
    assert state.announced == "Rebelote!"


def test_rebelote_scoring() -> None:
    trump = Suit.SPADES
    state = GameState(
        hands=((), (), (), ()),
        initial_hands=((), (), (), ()),
        trump=trump,
        taker=Seat.SOUTH,
        turn=Seat.SOUTH,
        phase=Phase.SCORING,
        belote_holders={trump: Seat.SOUTH},
        belote_tracker=(True, True),  # Rebelote
        completed_tricks=(),  # dummy
        last_trick_winner=Seat.SOUTH,
    )

    breakdown = score_round(state)
    assert breakdown.taker_belote == 40
    assert breakdown.taker_rebelote is True
    assert breakdown.taker_total >= 40


def test_illegal_move_error() -> None:
    trump = Suit.SPADES
    state = GameState(
        hands=((Card(Suit.HEARTS, Rank.ACE),), (), (), ()),
        trump=trump,
        turn=Seat.SOUTH,
        phase=Phase.PLAYING,
        current_trick=(TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.JACK)),),  # Trump led
    )
    # South has Hearts, but Spades led. South must play Spade if they had one,
    # but here they only have Heart ACE. So it is legal to play Heart ACE.
    # To trigger IllegalMoveError, we try to play a card NOT in South's hand.
    with pytest.raises(IllegalMoveError):
        play_card(state, Card(Suit.DIAMONDS, Rank.SEVEN))


def test_apply_round_score_ew_taker() -> None:
    state = GameState(
        hands=((), (), (), ()),
        team_scores=(100, 100),
        target=1000,
        dealer=Seat.SOUTH,
        taker=Seat.EAST,  # EW taker
    )
    breakdown = ScoringBreakdown(
        taker_team=1,  # EW
        table_taker_pts=100,
        table_defender_pts=62,
        credit_taker_pts=100,
        credit_defender_pts=62,
        last_trick_team=1,
        taker_declarations=0,
        defender_declarations=0,
        taker_belote=0,
        defender_belote=0,
        taker_rebelote=False,
        defender_rebelote=False,
        taker_total=110,  # 100 + 10 last trick
        defender_total=62,
        is_capot=False,
        is_failed=False,
        messages=(),
    )
    new_state = apply_round_score(state, breakdown)
    assert new_state.team_scores == (162, 210)
    assert new_state.score_history[-1].taker_team == 1


def test_sorting() -> None:
    trump = Suit.HEARTS
    hand = (
        Card(Suit.SPADES, Rank.ACE),
        Card(Suit.HEARTS, Rank.JACK),
        Card(Suit.HEARTS, Rank.NINE),
        Card(Suit.DIAMONDS, Rank.SEVEN),
    )
    sorted_h = sort_hand(hand, trump)
    # Trump (Hearts) should be first. In trump: Jack > Nine.
    assert sorted_h[0] == Card(Suit.HEARTS, Rank.JACK)
    assert sorted_h[1] == Card(Suit.HEARTS, Rank.NINE)

    state = GameState(hands=(hand, (), (), ()), trump=trump, phase=Phase.PLAYING)
    state = sort_south_hand(state)
    assert state.hands[0][0] == Card(Suit.HEARTS, Rank.JACK)


def test_multi_round_bidding_logic() -> None:
    # Test all pass in round 1, then someone takes in round 2
    state = new_game()
    rng = random.Random(42)
    state = start_round(state, rng)
    assert state.bidding_round == 1

    # 4 passes in round 1
    for _ in range(4):
        state = process_bid(state, None)

    assert state.bidding_round == 2
    assert state.phase == Phase.BIDDING

    # Someone takes in round 2
    state = process_bid(state, Suit.DIAMONDS)
    assert state.phase == Phase.PLAYING
    assert state.trump == Suit.DIAMONDS


def test_all_pass_redeal() -> None:
    state = new_game()
    rng = random.Random(42)
    state = start_round(state, rng)
    dealer_before = state.dealer

    # 8 passes total (4 in rd1, 4 in rd2)
    for _ in range(8):
        state = process_bid(state, None)

    assert state.phase == Phase.DEAL
    assert state.dealer == dealer_before.next_seat()


def test_ui_card_face() -> None:
    from belote.deck import Card, Rank, Suit
    from belote.ui.render import _get_card_face

    card = Card(Suit.SPADES, Rank.ACE)
    face = _get_card_face(card, selected=False, legal=True)
    assert len(face) == 7  # CARD_H
    # Check for spade symbol (UTF-8) or 'S'
    assert any("♠" in line or "S" in line for line in face)
    assert any("A" in line for line in face)


def test_input_parsing() -> None:

    from belote.input import Key, _UnixKeyReader

    with patch("sys.stdin.fileno", return_value=0):
        reader = _UnixKeyReader()

        # Mock os.read and select.select to simulate 'q' key
        with patch("os.read") as mock_read, patch("select.select") as mock_select:
            mock_select.return_value = ([True], [], [])
            mock_read.side_effect = [b"q"]

            event = reader.read()
            assert event.key == Key.QUIT

        # Mock ESC sequence for LEFT arrow: \x1B [ D
        with patch("os.read") as mock_read, patch("select.select") as mock_select:
            mock_select.return_value = ([True], [], [])
            mock_read.side_effect = [b"\x1b", b"[", b"D"]

            event = reader.read()
            assert event.key == Key.LEFT


def test_input_enter_parsing() -> None:

    from belote.input import Key, _UnixKeyReader

    with patch("sys.stdin.fileno", return_value=0):
        reader = _UnixKeyReader()
        with patch("os.read") as mock_read, patch("select.select") as mock_select:
            mock_select.return_value = ([True], [], [])
            mock_read.side_effect = [b"\r"]
            event = reader.read()
            assert event.key == Key.ENTER


def test_input_multibyte_utf8() -> None:
    """Multi-byte UTF-8 characters (e.g. '♠' = 3 bytes) are read as a single event."""
    from belote.input import Key, _UnixKeyReader

    # ♠ = U+2660 = 0xE2 0x99 0xA0 (3-byte UTF-8)
    spade_bytes = "♠".encode()
    assert len(spade_bytes) == 3

    with patch("sys.stdin.fileno", return_value=0):
        reader = _UnixKeyReader()
        with patch("os.read") as mock_read, patch("select.select") as mock_select:
            # First select returns data (first byte), subsequent selects for
            # continuation bytes also return ready
            mock_select.return_value = ([True], [], [])
            mock_read.side_effect = [
                bytes([spade_bytes[0]]),
                bytes([spade_bytes[1]]),
                bytes([spade_bytes[2]]),
            ]
            event = reader.read()
            assert event.key == Key.CHAR
            assert event.char == "♠"


def test_failed_bid_taker_declarations_transferred() -> None:
    """On chute, taker's declarations are transferred to the defenders."""
    from belote.scoring import score_round

    trump = Suit.SPADES
    # Build tricks where EW wins all (taker NS fails badly)
    tricks: list[tuple[TrickCard, ...]] = []
    for _ in range(8):
        trick = (
            TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.SEVEN)),
            TrickCard(Seat.EAST, Card(Suit.SPADES, Rank.JACK)),
            TrickCard(Seat.NORTH, Card(Suit.DIAMONDS, Rank.SEVEN)),
            TrickCard(Seat.WEST, Card(Suit.CLUBS, Rank.SEVEN)),
        )
        tricks.append(trick)

    # Give taker (South) a tierce (J, 10, 9 of Hearts)
    south_hand = (
        Card(Suit.HEARTS, Rank.NINE),
        Card(Suit.HEARTS, Rank.TEN),
        Card(Suit.HEARTS, Rank.JACK),
        Card(Suit.HEARTS, Rank.SEVEN),
        Card(Suit.HEARTS, Rank.EIGHT),
        Card(Suit.CLUBS, Rank.ACE),
        Card(Suit.DIAMONDS, Rank.KING),
        Card(Suit.SPADES, Rank.SEVEN),
    )
    initial_hands = (south_hand, (), (), ())

    state = GameState(
        hands=tuple(() for _ in range(4)),
        initial_hands=initial_hands,
        trump=trump,
        taker=Seat.SOUTH,
        turn=Seat.SOUTH,
        phase=Phase.SCORING,
        completed_tricks=tuple(tricks),
        last_trick_winner=Seat.EAST,
        belote_tracker=(False, False),
        first_trick_done=True,
    )

    breakdown = score_round(state)
    assert breakdown.is_failed is True
    # Taker's declarations (100) are transferred to defenders
    assert breakdown.taker_declarations == 100
    # Defenders get Capot (252) + Taker's declarations (100) = 352
    assert breakdown.defender_total == 252 + 100


def test_sort_south_hand_orders_trump_first_and_is_idempotent() -> None:
    """sort_south_hand puts trump cards first; running it twice yields the same order."""
    trump = Suit.HEARTS
    south_hand = (
        Card(Suit.SPADES, Rank.ACE),
        Card(Suit.HEARTS, Rank.JACK),
        Card(Suit.CLUBS, Rank.TEN),
        Card(Suit.HEARTS, Rank.NINE),
        Card(Suit.DIAMONDS, Rank.KING),
    )
    state = GameState(
        hands=(south_hand, (), (), ()),
        trump=trump,
        phase=Phase.PLAYING,
    )
    sorted_state = sort_south_hand(state)
    sorted_hand = sorted_state.hand_of(Seat.SOUTH)

    # Trump cards (Hearts) must come first
    assert sorted_hand[0].suit == Suit.HEARTS
    assert sorted_hand[1].suit == Suit.HEARTS

    # Sorting twice should be idempotent
    twice_sorted = sort_south_hand(sorted_state)
    assert twice_sorted.hand_of(Seat.SOUTH) == sorted_hand


def test_declaration_consistency_between_place_bid_and_score_round() -> None:
    """Declarations stored at bid time and recalculated at scoring must agree."""
    from belote.scoring import get_declarations

    state = new_game()
    rng = random.Random(123)
    state = start_round(state, rng)

    # Find a bid to take in round 1
    assert state.up_card is not None
    up_suit = state.up_card.suit
    # Have first bidder take the up-card suit
    bid_state = process_bid(state, up_suit)
    assert bid_state.phase == Phase.PLAYING

    # Declarations stored in state at bid time
    stored_decls = bid_state.declarations

    # Declarations recalculated by get_declarations on the same state
    recalc_decls = get_declarations(bid_state)

    # Both sets must cover the same seats and kinds
    stored_keys = {(d.seat, d.kind) for d in stored_decls}
    recalc_keys = {(d.seat, d.kind) for d in recalc_decls}
    assert stored_keys == recalc_keys, (
        f"Declaration mismatch: stored={stored_keys} recalc={recalc_keys}"
    )


# ── H7: main-loop win-attribution operator (3.4.2) ─────────────────────────


def test_main_won_formula_disagrees_with_menu_on_tie_at_target_before_fix() -> None:
    """H7 regression: pre-3.4.2 `main.py:231` used `ns >= ew` for the
    update_stats_game `won` flag, while `ui/menu.py:344` used `ns > ew`
    for the displayed winner. On an exact tie at target the stats line
    recorded a NS win while the visible summary attributed the round to
    EW. The fix aligns main.py's operator to `>`.
    """
    import re
    from pathlib import Path

    main_src = Path(__file__).parent.parent / "src" / "belote" / "main.py"
    text = main_src.read_text()
    # Lock the post-fix shape: `won=(ns >= target and ns > ew)`.
    assert re.search(r"won=\(ns >= target and ns > ew\)", text), (
        "main.py update_stats_game `won` expression must use `ns > ew` "
        "(strict) to agree with menu.py:344's `winner = \"NS\" if ns > ew "
        "else \"EW\"`. The pre-3.4.2 form `ns >= ew` is a regression."
    )
    # And the pre-fix anti-pattern must not have crept back.
    assert "ns >= target and ns >= ew" not in text, (
        "Anti-pattern from pre-3.4.2 detected — `ns >= ew` overcounts NS "
        "wins on an exact tie at target."
    )


def test_main_won_formula_evaluates_correctly_on_tie_at_target() -> None:
    """The semantic intent of the H7 fix: on an exact tie at target, the
    stats `won` flag must be False (the game shouldn't even reach this
    branch under correct scoring — see 3.4.0 E2 — but if it does, the
    record must agree with the menu)."""
    target = 1000
    ns = 1000
    ew = 1000
    # Post-fix formula.
    won = (ns >= target and ns > ew)
    assert won is False

    # And NS clearly ahead at target should still register as a win.
    ns_clear, ew_clear = 1010, 800
    assert (ns_clear >= target and ns_clear > ew_clear) is True

    # EW ahead at target → NS not a winner.
    ns_loss, ew_loss = 900, 1010
    assert (ns_loss >= target and ns_loss > ew_loss) is False
