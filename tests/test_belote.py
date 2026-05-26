"""Belote test suite – covers all 18 required test cases."""

from __future__ import annotations

import random

from belote.config import GLOBAL_CONFIG
from belote.deck import Card, Rank, Suit, card_points, make_deck, trick_rank
from belote.game import (
    GameState,
    Phase,
    Seat,
    TrickCard,
    legal_cards,
    new_game,
    partner,
    start_round,
    team_of,
    trick_winner_seat,
)
from belote.scoring import (
    detect_belote,
    detect_carres,
    detect_sequences,
    resolve_declarations,
    score_round,
)

BELOTE_POINTS = GLOBAL_CONFIG.BELOTE_POINTS
LAST_TRICK_BONUS = GLOBAL_CONFIG.LAST_TRICK_BONUS
CAPOT_BASE = GLOBAL_CONFIG.CAPOT_BASE
TOTAL_POINTS = GLOBAL_CONFIG.TOTAL_POINTS


# ---------------------------------------------------------------------------
# 1. Deck integrity
# ---------------------------------------------------------------------------


class TestDeckIntegrity:
    def test_32_unique_cards(self) -> None:
        deck = make_deck()
        assert len(deck) == 32
        assert len(set(deck)) == 32

    def test_all_suits_and_ranks(self) -> None:
        deck = make_deck()
        suits = {c.suit for c in deck}
        ranks = {c.rank for c in deck}
        # The deck contains exactly the four card-bearing suits (TOUT_ATOUT is
        # a contract identifier, not a card suit).
        assert suits == {s for s in Suit if s.is_card_suit}
        assert ranks == set(Rank)

    def test_total_points_consistency(self) -> None:
        """TOTAL_POINTS (152) + LAST_TRICK_BONUS (10) must equal 162.

        Also verifies card_points over the full deck sums to TOTAL_POINTS for every
        standard trump. Tout Atout (every card scored as trump) sums higher and is
        not part of this invariant.
        """
        assert GLOBAL_CONFIG.TOTAL_POINTS == 152
        assert GLOBAL_CONFIG.LAST_TRICK_BONUS == 10

        for trump in Suit:
            if not trump.is_card_suit:
                continue
            deck = make_deck()
            total = sum(card_points(c, trump) for c in deck)
            assert total == GLOBAL_CONFIG.TOTAL_POINTS, f"Sum for trump {trump} = {total}"


# ---------------------------------------------------------------------------
# 2-3. Ranking order
# ---------------------------------------------------------------------------


class TestRanking:
    def test_trump_ranking_order(self) -> None:
        """Trump: J > 9 > A > 10 > K > Q > 8 > 7."""
        trump = Suit.SPADES
        order = [
            Rank.JACK,
            Rank.NINE,
            Rank.ACE,
            Rank.TEN,
            Rank.KING,
            Rank.QUEEN,
            Rank.EIGHT,
            Rank.SEVEN,
        ]
        ranks = [Card(trump, r) for r in order]
        for i in range(len(ranks) - 1):
            assert trick_rank(ranks[i], trump) > trick_rank(ranks[i + 1], trump), (
                f"{ranks[i]} should beat {ranks[i + 1]}"
            )

    def test_nontrump_ranking_order(self) -> None:
        """Non-trump: A > 10 > K > Q > J > 9 > 8 > 7."""
        trump = Suit.SPADES
        order = [
            Rank.ACE,
            Rank.TEN,
            Rank.KING,
            Rank.QUEEN,
            Rank.JACK,
            Rank.NINE,
            Rank.EIGHT,
            Rank.SEVEN,
        ]
        suit = Suit.HEARTS  # non-trump
        ranks = [Card(suit, r) for r in order]
        for i in range(len(ranks) - 1):
            assert trick_rank(ranks[i], trump) > trick_rank(ranks[i + 1], trump), (
                f"{ranks[i]} should beat {ranks[i + 1]}"
            )


# ---------------------------------------------------------------------------
# 4. Trump points
# ---------------------------------------------------------------------------


class TestTrumpPoints:
    def test_trump_card_points(self) -> None:
        trump = Suit.SPADES
        expected = {
            Rank.JACK: 20,
            Rank.NINE: 14,
            Rank.ACE: 11,
            Rank.TEN: 10,
            Rank.KING: 4,
            Rank.QUEEN: 3,
            Rank.EIGHT: 0,
            Rank.SEVEN: 0,
        }
        for rank, pts in expected.items():
            assert card_points(Card(trump, rank), trump) == pts

    def test_nontrump_card_points(self) -> None:
        trump = Suit.SPADES
        expected = {
            Rank.JACK: 2,
            Rank.NINE: 0,
            Rank.ACE: 11,
            Rank.TEN: 10,
            Rank.KING: 4,
            Rank.QUEEN: 3,
            Rank.EIGHT: 0,
            Rank.SEVEN: 0,
        }
        for rank, pts in expected.items():
            assert card_points(Card(Suit.HEARTS, rank), trump) == pts


# ---------------------------------------------------------------------------
# Helper: build a game state for trick-testing
# ---------------------------------------------------------------------------


def _make_play_state(
    hands: dict[Seat, list[Card]],
    trump: Suit,
    taker: Seat = Seat.SOUTH,
    current_trick: list[tuple[Seat, Card]] | None = None,
) -> GameState:
    """Build a minimal PLAYING state for testing."""
    hands_tuple: list[tuple[Card, ...]] = []
    for s in Seat:
        hands_tuple.append(tuple(hands.get(s, [])))

    trick_tuple = tuple(TrickCard(s, c) for s, c in (current_trick or []))
    turn = Seat.SOUTH
    if trick_tuple:
        last_seat = trick_tuple[-1].seat
        turn = last_seat.next_seat()

    return GameState(
        hands=tuple(hands_tuple),
        trump=trump,
        dealer=Seat.SOUTH,
        leader=Seat.SOUTH,
        turn=turn,
        phase=Phase.PLAYING,
        bids=(),
        taker=taker,
        current_trick=trick_tuple,
        completed_tricks=(),
        last_trick_winner=None,
        declarations=(),
        team_scores=(0, 0),
        current_round_points=(0, 0),
        score_history=(),
        target=1000,
        up_card=None,
        remaining_cards=(),
        bidder_index=0,
        bidding_round=1,
        announced=None,
        belote_tracker=(False, False),
        first_trick_done=False,
    )


# ---------------------------------------------------------------------------
# 5-9. Legal moves
# ---------------------------------------------------------------------------


class TestLegalMoves:
    def test_must_follow_suit(self) -> None:
        """If you have the led suit, you must follow."""
        trump = Suit.SPADES
        state = _make_play_state(
            hands={
                Seat.SOUTH: [Card(Suit.HEARTS, Rank.ACE), Card(Suit.HEARTS, Rank.KING)],
                Seat.EAST: [Card(Suit.HEARTS, Rank.QUEEN), Card(Suit.SPADES, Rank.JACK)],
            },
            trump=trump,
            current_trick=[(Seat.SOUTH, Card(Suit.HEARTS, Rank.ACE))],
        )
        legal = legal_cards(state, Seat.EAST)
        # East must follow hearts
        assert all(c.suit == Suit.HEARTS for c in legal)
        assert Card(Suit.HEARTS, Rank.QUEEN) in legal
        assert Card(Suit.SPADES, Rank.JACK) not in legal

    def test_void_can_discard_when_partner_winning(self) -> None:
        """Void in led suit + partner currently winning → may discard or trump (not forced)."""
        trump = Suit.SPADES
        state = _make_play_state(
            hands={
                Seat.SOUTH: [Card(Suit.HEARTS, Rank.ACE)],
                Seat.EAST: [Card(Suit.HEARTS, Rank.QUEEN)],
                Seat.NORTH: [Card(Suit.SPADES, Rank.JACK), Card(Suit.DIAMONDS, Rank.ACE)],
            },
            trump=trump,
            current_trick=[
                (Seat.SOUTH, Card(Suit.HEARTS, Rank.ACE)),
                (Seat.EAST, Card(Suit.HEARTS, Rank.QUEEN)),
            ],
        )
        # North is partner of South (who's winning). North is void in hearts.
        # Partner (South) IS winning → North can discard a non-trump.
        legal = legal_cards(state, Seat.NORTH)
        assert Card(Suit.DIAMONDS, Rank.ACE) in legal
        # And trump is also legal (not forced when partner is winning).
        assert Card(Suit.SPADES, Rank.JACK) in legal

    def test_must_overtrump(self) -> None:
        """Must overtrump when possible."""
        trump = Suit.SPADES
        state = _make_play_state(
            hands={
                Seat.SOUTH: [Card(Suit.HEARTS, Rank.ACE)],
                Seat.EAST: [Card(Suit.SPADES, Rank.NINE)],
                Seat.NORTH: [Card(Suit.SPADES, Rank.JACK), Card(Suit.SPADES, Rank.SEVEN)],
            },
            trump=trump,
            current_trick=[
                (Seat.SOUTH, Card(Suit.HEARTS, Rank.ACE)),
                (Seat.EAST, Card(Suit.SPADES, Rank.NINE)),
            ],
        )
        # North is void in hearts, partner (South) is NOT winning (East's 9♠ trumps)
        # Must trump, and must overtrump if possible
        legal = legal_cards(state, Seat.NORTH)
        # Only JACK (overtrumps 9) should be legal, not SEVEN (undertrumps)
        assert Card(Suit.SPADES, Rank.JACK) in legal
        assert Card(Suit.SPADES, Rank.SEVEN) not in legal

    def test_must_overtrump_trump_led(self) -> None:
        """Must overtrump when trump is led and someone already played a trump."""
        trump = Suit.SPADES
        state = _make_play_state(
            hands={
                Seat.SOUTH: [Card(Suit.SPADES, Rank.NINE)],
                Seat.EAST: [Card(Suit.SPADES, Rank.JACK), Card(Suit.SPADES, Rank.SEVEN)],
            },
            trump=trump,
            current_trick=[
                (Seat.SOUTH, Card(Suit.SPADES, Rank.NINE)),
            ],
        )
        # NINE of Spades led. East has JACK (higher) and SEVEN (lower).
        # Must follow suit (both are Spades) AND must overtrump if possible (JACK).
        legal = legal_cards(state, Seat.EAST)
        assert Card(Suit.SPADES, Rank.JACK) in legal
        assert Card(Suit.SPADES, Rank.SEVEN) not in legal

    def test_partner_winning_exception(self) -> None:
        """Void + partner winning + non-trump lead → discard allowed."""
        trump = Suit.SPADES
        state = _make_play_state(
            hands={
                Seat.SOUTH: [Card(Suit.HEARTS, Rank.ACE)],
                Seat.EAST: [Card(Suit.HEARTS, Rank.SEVEN)],
                Seat.NORTH: [Card(Suit.SPADES, Rank.JACK), Card(Suit.DIAMONDS, Rank.ACE)],
            },
            trump=trump,
            current_trick=[
                (Seat.SOUTH, Card(Suit.HEARTS, Rank.ACE)),
                (Seat.EAST, Card(Suit.HEARTS, Rank.SEVEN)),
            ],
        )
        # North's partner (South) is winning with A♥
        # North is void in hearts → can discard
        legal = legal_cards(state, Seat.NORTH)
        assert Card(Suit.DIAMONDS, Rank.ACE) in legal

    def test_trump_lead_no_partner_exception(self) -> None:
        """Trump lead: partner-winning exception does NOT apply."""
        trump = Suit.SPADES
        state = _make_play_state(
            hands={
                Seat.SOUTH: [Card(Suit.SPADES, Rank.ACE)],
                Seat.WEST: [Card(Suit.SPADES, Rank.SEVEN)],
                Seat.NORTH: [Card(Suit.SPADES, Rank.JACK), Card(Suit.DIAMONDS, Rank.ACE)],
            },
            trump=trump,
            current_trick=[
                (Seat.SOUTH, Card(Suit.SPADES, Rank.ACE)),
                (Seat.WEST, Card(Suit.SPADES, Rank.SEVEN)),
            ],
        )
        # Trump led. North's partner (South) is winning.
        # But trump led → must follow trump, no exception
        legal = legal_cards(state, Seat.NORTH)
        assert all(c.suit == trump for c in legal)
        assert Card(Suit.DIAMONDS, Rank.ACE) not in legal


# ---------------------------------------------------------------------------
# 10. Belote detection
# ---------------------------------------------------------------------------


class TestBelote:
    def test_belote_detected(self) -> None:
        trump = Suit.HEARTS
        hand = (
            Card(trump, Rank.KING),
            Card(trump, Rank.QUEEN),
            Card(Suit.SPADES, Rank.ACE),
        )
        assert detect_belote(hand, trump) is True

    def test_belote_not_detected_missing_king(self) -> None:
        trump = Suit.HEARTS
        hand = (
            Card(trump, Rank.QUEEN),
            Card(Suit.SPADES, Rank.KING),
            Card(Suit.SPADES, Rank.ACE),
        )
        assert detect_belote(hand, trump) is False

    def test_belote_not_detected_wrong_suit(self) -> None:
        trump = Suit.HEARTS
        hand = (
            Card(Suit.SPADES, Rank.KING),
            Card(Suit.SPADES, Rank.QUEEN),
            Card(Suit.HEARTS, Rank.ACE),
        )
        assert detect_belote(hand, trump) is False


# ---------------------------------------------------------------------------
# 11. Sequence detection
# ---------------------------------------------------------------------------


class TestSequences:
    def test_tierce_detected(self) -> None:
        hand = (
            Card(Suit.HEARTS, Rank.NINE),
            Card(Suit.HEARTS, Rank.TEN),
            Card(Suit.HEARTS, Rank.JACK),
        )
        seqs = detect_sequences(hand)
        assert len(seqs) == 1
        assert seqs[0].length == 3

    def test_quarte_detected(self) -> None:
        hand = (
            Card(Suit.HEARTS, Rank.EIGHT),
            Card(Suit.HEARTS, Rank.NINE),
            Card(Suit.HEARTS, Rank.TEN),
            Card(Suit.HEARTS, Rank.JACK),
        )
        seqs = detect_sequences(hand)
        assert len(seqs) == 1
        assert seqs[0].length == 4

    def test_quinte_detected(self) -> None:
        hand = (
            Card(Suit.SPADES, Rank.SEVEN),
            Card(Suit.SPADES, Rank.EIGHT),
            Card(Suit.SPADES, Rank.NINE),
            Card(Suit.SPADES, Rank.TEN),
            Card(Suit.SPADES, Rank.JACK),
        )
        seqs = detect_sequences(hand)
        assert len(seqs) == 1
        assert seqs[0].length == 5

    def test_no_sequence_two_cards(self) -> None:
        hand = (
            Card(Suit.HEARTS, Rank.ACE),
            Card(Suit.HEARTS, Rank.KING),
        )
        seqs = detect_sequences(hand)
        assert len(seqs) == 0

    def test_no_sequence_different_suits(self) -> None:
        hand = (
            Card(Suit.HEARTS, Rank.NINE),
            Card(Suit.SPADES, Rank.TEN),
            Card(Suit.DIAMONDS, Rank.JACK),
        )
        seqs = detect_sequences(hand)
        assert len(seqs) == 0


# ---------------------------------------------------------------------------
# 12. Carré detection
# ---------------------------------------------------------------------------


class TestCarres:
    def test_carre_jacks(self) -> None:
        hand = tuple(Card(s, Rank.JACK) for s in Suit if s.is_card_suit)
        carres = detect_carres(hand)
        assert len(carres) == 1

    def test_carre_nines(self) -> None:
        hand = tuple(Card(s, Rank.NINE) for s in Suit if s.is_card_suit)
        carres = detect_carres(hand)
        assert len(carres) == 1

    def test_carre_sevens_no_count(self) -> None:
        hand = tuple(Card(s, Rank.SEVEN) for s in Suit if s.is_card_suit)
        carres = detect_carres(hand)
        assert len(carres) == 1  # detected but worth 0 points

    def test_no_carre(self) -> None:
        hand = (
            Card(Suit.SPADES, Rank.ACE),
            Card(Suit.HEARTS, Rank.KING),
            Card(Suit.DIAMONDS, Rank.QUEEN),
        )
        carres = detect_carres(hand)
        assert len(carres) == 0


# ---------------------------------------------------------------------------
# 13. Declaration priority
# ---------------------------------------------------------------------------


class TestDeclarationPriority:
    def test_carre_beats_sequence(self) -> None:
        """Carré outranks any sequence."""
        from belote.scoring import Carre, Sequence

        trump = Suit.SPADES
        jack_carre = Carre(rank=5, cards=tuple(Card(s, Rank.JACK) for s in Suit if s.is_card_suit))
        seq = Sequence(length=5, top_rank=8, suit=Suit.HEARTS, is_trump=False, cards=())

        decls = {
            Seat.SOUTH: {"sequences": [seq], "carres": [], "belote": False},
            Seat.NORTH: {"sequences": [], "carres": [], "belote": False},
            Seat.EAST: {"sequences": [], "carres": [jack_carre], "belote": False},
            Seat.WEST: {"sequences": [], "carres": [], "belote": False},
        }
        resolved = resolve_declarations(decls, trump)
        assert resolved.scoring_team == 1  # EW has carré

    def test_longer_sequence_wins(self) -> None:
        from belote.scoring import Sequence

        trump = Suit.SPADES
        quarte = Sequence(length=4, top_rank=8, suit=Suit.HEARTS, is_trump=False, cards=())
        tierce = Sequence(length=3, top_rank=8, suit=Suit.DIAMONDS, is_trump=False, cards=())

        decls = {
            Seat.SOUTH: {"sequences": [quarte], "carres": [], "belote": False},
            Seat.NORTH: {"sequences": [], "carres": [], "belote": False},
            Seat.EAST: {"sequences": [tierce], "carres": [], "belote": False},
            Seat.WEST: {"sequences": [], "carres": [], "belote": False},
        }
        resolved = resolve_declarations(decls, trump)
        assert resolved.scoring_team == 0  # NS has longer sequence

    def test_trump_sequence_beats_equal_nontrump(self) -> None:
        from belote.scoring import Sequence

        trump = Suit.SPADES
        trump_seq = Sequence(length=3, top_rank=6, suit=Suit.SPADES, is_trump=True, cards=())
        nontrump_seq = Sequence(length=3, top_rank=6, suit=Suit.HEARTS, is_trump=False, cards=())

        decls = {
            Seat.SOUTH: {"sequences": [trump_seq], "carres": [], "belote": False},
            Seat.NORTH: {"sequences": [], "carres": [], "belote": False},
            Seat.EAST: {"sequences": [nontrump_seq], "carres": [], "belote": False},
            Seat.WEST: {"sequences": [], "carres": [], "belote": False},
        }
        resolved = resolve_declarations(decls, trump)
        assert resolved.scoring_team == 0  # NS has trump sequence


# ---------------------------------------------------------------------------
# 14. Capot scoring
# ---------------------------------------------------------------------------


class TestCapot:
    def test_capot_base_score(self) -> None:
        trump = Suit.SPADES
        # 8 tricks where NS wins ALL tricks = capot.
        # South's ♠: J,9,A,10,K,Q (6 trumps) | North's ♠: none
        # East's ♠: 7,K | West's ♠: 8
        # Tricks 1-5: South leads high trump → South wins
        # Tricks 6-7: North leads A♥,K♥ → North wins (no trump played)
        # Trick 8: South leads Q♠ → beats East's K♠ and West's 8♠
        trick_data = [
            (
                Card(Suit.SPADES, Rank.JACK),
                Card(Suit.HEARTS, Rank.SEVEN),
                Card(Suit.DIAMONDS, Rank.SEVEN),
                Card(Suit.CLUBS, Rank.SEVEN),
            ),
            (
                Card(Suit.SPADES, Rank.NINE),
                Card(Suit.HEARTS, Rank.EIGHT),
                Card(Suit.DIAMONDS, Rank.EIGHT),
                Card(Suit.CLUBS, Rank.EIGHT),
            ),
            (
                Card(Suit.SPADES, Rank.ACE),
                Card(Suit.HEARTS, Rank.NINE),
                Card(Suit.DIAMONDS, Rank.NINE),
                Card(Suit.CLUBS, Rank.NINE),
            ),
            (
                Card(Suit.SPADES, Rank.TEN),
                Card(Suit.HEARTS, Rank.TEN),
                Card(Suit.DIAMONDS, Rank.TEN),
                Card(Suit.CLUBS, Rank.TEN),
            ),
            (
                Card(Suit.SPADES, Rank.KING),
                Card(Suit.HEARTS, Rank.JACK),
                Card(Suit.DIAMONDS, Rank.JACK),
                Card(Suit.CLUBS, Rank.JACK),
            ),
            (
                Card(Suit.CLUBS, Rank.EIGHT),
                Card(Suit.HEARTS, Rank.JACK),
                Card(Suit.DIAMONDS, Rank.ACE),
                Card(Suit.HEARTS, Rank.QUEEN),
            ),
            (
                Card(Suit.CLUBS, Rank.NINE),
                Card(Suit.HEARTS, Rank.KING),
                Card(Suit.DIAMONDS, Rank.QUEEN),
                Card(Suit.HEARTS, Rank.TEN),
            ),
            (
                Card(Suit.SPADES, Rank.QUEEN),
                Card(Suit.CLUBS, Rank.KING),
                Card(Suit.DIAMONDS, Rank.KING),
                Card(Suit.SPADES, Rank.EIGHT),
            ),
        ]
        tricks = []
        for cards in trick_data:
            trick = tuple(TrickCard(list(Seat)[i], cards[i]) for i in range(4))
            tricks.append(trick)

        # Verify: all tricks won by NS team
        for i, trick in enumerate(tricks):
            w = trick_winner_seat(trick, trump)
            assert w is not None and team_of(w) == 0, f"Trick {i + 1}: Expected NS to win, got {w}"

        # Reconstruct hands for scoring to work
        hands_by_seat: list[list[Card]] = [[] for _ in range(4)]
        for trick in tricks:
            for tc in trick:
                hands_by_seat[tc.seat.value].append(tc.card)
        initial_hands = tuple(tuple(h) for h in hands_by_seat)

        state = GameState(
            hands=tuple(() for _ in range(4)),
            initial_hands=initial_hands,
            trump=trump,
            dealer=Seat.SOUTH,
            leader=Seat.SOUTH,
            turn=Seat.SOUTH,
            phase=Phase.SCORING,
            bids=(),
            taker=Seat.SOUTH,
            current_trick=(),
            completed_tricks=tuple(tricks),
            last_trick_winner=Seat.SOUTH,
            declarations=(),
            team_scores=(0, 0),
            current_round_points=(0, 0),
            score_history=(),
            target=1000,
            up_card=None,
            remaining_cards=(),
            bidder_index=0,
            bidding_round=1,
            announced=None,
            belote_holders={trump: Seat.SOUTH},
            belote_tracker=(True, False),
            first_trick_done=True,
        )

        breakdown = score_round(state)
        assert breakdown.is_capot is True
        # South has K♠+Q♠ (trump honors) so belote is detected → CAPOT_BASE + BELOTE_POINTS
        # South and North each hold sequences (detected from tricks) → +200 decls
        assert breakdown.taker_total == CAPOT_BASE + BELOTE_POINTS + 200
        assert breakdown.taker_belote == BELOTE_POINTS

# ---------------------------------------------------------------------------
# 14b. Capot per contract (3.0.0 fix)
# ---------------------------------------------------------------------------


def _make_capot_state(contract: str | None, trump: Suit | None) -> GameState:
    """Build an 8-trick state where NS wins all tricks.

    South holds all 8 hearts; North/East/West each hold 8 cards of a single
    other suit. Each trick is led by South in HEARTS; the others discard from
    their (different) suits. Lead-suit-only winner = South.
    """
    south_hand = [Card(Suit.HEARTS, r) for r in Rank]
    north_hand = [Card(Suit.DIAMONDS, r) for r in Rank]
    east_hand = [Card(Suit.CLUBS, r) for r in Rank]
    west_hand = [Card(Suit.SPADES, r) for r in Rank]

    tricks = []
    for i in range(8):
        tc = (
            TrickCard(Seat.SOUTH, south_hand[i]),
            TrickCard(Seat.WEST, west_hand[i]),
            TrickCard(Seat.NORTH, north_hand[i]),
            TrickCard(Seat.EAST, east_hand[i]),
        )
        tricks.append(tc)

    initial_hands = (
        tuple(south_hand),
        tuple(west_hand),
        tuple(north_hand),
        tuple(east_hand),
    )

    return GameState(
        hands=tuple(() for _ in range(4)),
        initial_hands=initial_hands,
        trump=trump,
        dealer=Seat.SOUTH,
        leader=Seat.SOUTH,
        turn=Seat.SOUTH,
        phase=Phase.SCORING,
        bids=(),
        taker=Seat.SOUTH,
        current_trick=(),
        completed_tricks=tuple(tricks),
        last_trick_winner=Seat.SOUTH,
        declarations=(),
        team_scores=(0, 0),
        current_round_points=(0, 0),
        score_history=(),
        target=1000,
        up_card=None,
        remaining_cards=(),
        bidder_index=0,
        bidding_round=2,
        announced=None,
        belote_holders={},
        belote_tracker=(False, False),
        first_trick_done=True,
        contract=contract,
    )


class TestCapotPerContract:
    """Capot base scales by contract: SA→220, TA→348, normal→252."""

    def test_capot_base_sans_atout(self) -> None:
        state = _make_capot_state(contract="sans_atout", trump=None)
        breakdown = score_round(state)
        assert breakdown.is_capot is True
        # Base 220 + 200 from NS sequences (South's 8 hearts + North's 8 diamonds)
        assert breakdown.taker_total == GLOBAL_CONFIG.CAPOT_BASE_SANS_ATOUT + 200, (
            f"SA Capot must use base 220 (+200 decls), got {breakdown.taker_total}"
        )

    def test_capot_base_tout_atout(self) -> None:
        state = _make_capot_state(contract="tout_atout", trump=Suit.TOUT_ATOUT)
        breakdown = score_round(state)
        assert breakdown.is_capot is True
        # Base 348 + 200 from NS sequences
        assert breakdown.taker_total == GLOBAL_CONFIG.CAPOT_BASE_TOUT_ATOUT + 200, (
            f"TA Capot must use base 348 (+200 decls), got {breakdown.taker_total}"
        )

    def test_capot_base_normal_unchanged(self) -> None:
        state = _make_capot_state(contract=None, trump=Suit.HEARTS)
        breakdown = score_round(state)
        assert breakdown.is_capot is True
        # Hearts trump means South's K+Q hearts trigger Belote (BELOTE_POINTS=20).
        # Plus 200 from NS sequences.
        assert breakdown.taker_total == GLOBAL_CONFIG.CAPOT_BASE + breakdown.taker_belote + 200



# ---------------------------------------------------------------------------
# 15. Bid failure
# ---------------------------------------------------------------------------


class TestBidFailure:
    def test_failed_bid_scoring(self) -> None:
        """When taker_pts < defender_pts, taker scores 0, defenders get 162 + declarations."""
        trump = Suit.SPADES
        # Build tricks where defenders win more points
        tricks: list[tuple[TrickCard, ...]] = []
        for _i in range(8):
            trick = (
                TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.SEVEN)),
                TrickCard(Seat.EAST, Card(Suit.SPADES, Rank.JACK)),  # 20 pts
                TrickCard(Seat.NORTH, Card(Suit.DIAMONDS, Rank.SEVEN)),
                TrickCard(Seat.WEST, Card(Suit.CLUBS, Rank.SEVEN)),
            )
            tricks.append(trick)

        state = GameState(
            hands=tuple(() for _ in range(4)),
            trump=trump,
            dealer=Seat.SOUTH,
            leader=Seat.SOUTH,
            turn=Seat.SOUTH,
            phase=Phase.SCORING,
            bids=(),
            taker=Seat.SOUTH,
            current_trick=(),
            completed_tricks=tuple(tricks),
            last_trick_winner=Seat.EAST,
            declarations=(),
            team_scores=(0, 0),
            current_round_points=(0, 0),
            score_history=(),
            target=1000,
            up_card=None,
            remaining_cards=(),
            bidder_index=0,
            bidding_round=1,
            announced=None,
            belote_tracker=(False, False),
            first_trick_done=True,
        )

        breakdown = score_round(state)
        assert breakdown.is_failed is True
        # Taker scores 0 (except belote, which they don't have)
        assert breakdown.taker_total == 0
        # Defenders won all tricks -> Capot (252)
        assert breakdown.defender_total == GLOBAL_CONFIG.CAPOT_BASE


# ---------------------------------------------------------------------------
# 16. Last-trick bonus
# ---------------------------------------------------------------------------


class TestLastTrickBonus:
    def test_capot_subsumes_last_trick_bonus(self) -> None:
        """Capot scoring is a fixed base — the +10 dix-de-der is folded in,
        not added on top. Pins both `is_capot` AND the numeric taker total
        so a regression that breaks the capot constant (or accidentally
        adds the +10 twice) is caught."""
        trump = Suit.SPADES
        trick_data = [
            (
                Card(Suit.SPADES, Rank.JACK),
                Card(Suit.HEARTS, Rank.SEVEN),
                Card(Suit.DIAMONDS, Rank.SEVEN),
                Card(Suit.CLUBS, Rank.SEVEN),
            ),
            (
                Card(Suit.SPADES, Rank.NINE),
                Card(Suit.HEARTS, Rank.EIGHT),
                Card(Suit.DIAMONDS, Rank.EIGHT),
                Card(Suit.CLUBS, Rank.EIGHT),
            ),
            (
                Card(Suit.SPADES, Rank.ACE),
                Card(Suit.HEARTS, Rank.NINE),
                Card(Suit.DIAMONDS, Rank.NINE),
                Card(Suit.CLUBS, Rank.NINE),
            ),
            (
                Card(Suit.SPADES, Rank.TEN),
                Card(Suit.HEARTS, Rank.TEN),
                Card(Suit.DIAMONDS, Rank.TEN),
                Card(Suit.CLUBS, Rank.TEN),
            ),
            (
                Card(Suit.SPADES, Rank.KING),
                Card(Suit.HEARTS, Rank.JACK),
                Card(Suit.DIAMONDS, Rank.JACK),
                Card(Suit.CLUBS, Rank.JACK),
            ),
            (
                Card(Suit.DIAMONDS, Rank.EIGHT),
                Card(Suit.HEARTS, Rank.QUEEN),
                Card(Suit.HEARTS, Rank.ACE),
                Card(Suit.HEARTS, Rank.KING),
            ),
            (
                Card(Suit.DIAMONDS, Rank.NINE),
                Card(Suit.HEARTS, Rank.KING),
                Card(Suit.HEARTS, Rank.QUEEN),
                Card(Suit.HEARTS, Rank.JACK),
            ),
            (
                Card(Suit.SPADES, Rank.QUEEN),
                Card(Suit.CLUBS, Rank.KING),
                Card(Suit.DIAMONDS, Rank.KING),
                Card(Suit.SPADES, Rank.EIGHT),
            ),
        ]
        tricks = []
        for cards in trick_data:
            trick = tuple(TrickCard(list(Seat)[i], cards[i]) for i in range(4))
            tricks.append(trick)

        state = GameState(
            hands=tuple(() for _ in range(4)),
            trump=trump,
            dealer=Seat.SOUTH,
            leader=Seat.SOUTH,
            turn=Seat.SOUTH,
            phase=Phase.SCORING,
            bids=(),
            taker=Seat.SOUTH,
            current_trick=(),
            completed_tricks=tuple(tricks),
            last_trick_winner=Seat.SOUTH,
            declarations=(),
            team_scores=(0, 0),
            current_round_points=(0, 0),
            score_history=(),
            target=1000,
            up_card=None,
            remaining_cards=(),
            bidder_index=0,
            bidding_round=1,
            announced=None,
            belote_tracker=(False, False),
            first_trick_done=True,
        )

        breakdown = score_round(state)
        assert breakdown.is_capot is True
        # Capot base is the entire taker total — no separate +10 last-trick
        # row stacked on top. (CAPOT_BASE already accounts for the bonus.)
        assert breakdown.taker_total == CAPOT_BASE

    def test_last_trick_bonus_applied_in_normal_round(self) -> None:
        """Non-capot round where NS (the taker) wins the final trick: the
        table_taker_pts must include the +10 dix-de-der bonus. Pins the
        actual mechanic the original test name promised."""
        trump = Suit.SPADES
        # 8 distinct tricks covering all 32 cards. NS wins tricks 1, 2, 7, 8;
        # EW wins tricks 3, 4, 5, 6. Last trick (8) goes to SOUTH → +10 lands
        # on the taker (NS) side.
        # NS card points: 11 + 19 + 24 + 38 = 92  ;  + 10 dix-de-der = 102
        # EW card points: 10 + 20 + 10 + 20      = 60
        # 92 + 60 + 10 = 162 (TOTAL_POINTS + LAST_TRICK_BONUS) ✓
        trick_data = [
            # T1: ♣ lead, SOUTH wins A♣ — 11 pts
            (Card(Suit.CLUBS, Rank.ACE), Card(Suit.CLUBS, Rank.SEVEN),
             Card(Suit.CLUBS, Rank.EIGHT), Card(Suit.CLUBS, Rank.NINE)),
            # T2: ♣ lead, SOUTH wins 10♣ — 19 pts
            (Card(Suit.CLUBS, Rank.TEN), Card(Suit.CLUBS, Rank.QUEEN),
             Card(Suit.CLUBS, Rank.KING), Card(Suit.CLUBS, Rank.JACK)),
            # T3: ♥ lead, EAST wins 10♥ — 10 pts to EW
            (Card(Suit.HEARTS, Rank.SEVEN), Card(Suit.HEARTS, Rank.EIGHT),
             Card(Suit.HEARTS, Rank.NINE), Card(Suit.HEARTS, Rank.TEN)),
            # T4: ♥ lead, EAST wins A♥ — 20 pts to EW
            (Card(Suit.HEARTS, Rank.JACK), Card(Suit.HEARTS, Rank.QUEEN),
             Card(Suit.HEARTS, Rank.KING), Card(Suit.HEARTS, Rank.ACE)),
            # T5: ♦ lead, EAST wins 10♦ — 10 pts to EW
            (Card(Suit.DIAMONDS, Rank.SEVEN), Card(Suit.DIAMONDS, Rank.EIGHT),
             Card(Suit.DIAMONDS, Rank.NINE), Card(Suit.DIAMONDS, Rank.TEN)),
            # T6: ♦ lead, EAST wins A♦ — 20 pts to EW
            (Card(Suit.DIAMONDS, Rank.JACK), Card(Suit.DIAMONDS, Rank.QUEEN),
             Card(Suit.DIAMONDS, Rank.KING), Card(Suit.DIAMONDS, Rank.ACE)),
            # T7: ♠ TRUMP lead, NORTH wins 9♠ (trump rank: J>9>A>10>K>Q>8>7)
            # — 24 pts to NS
            (Card(Suit.SPADES, Rank.SEVEN), Card(Suit.SPADES, Rank.EIGHT),
             Card(Suit.SPADES, Rank.NINE), Card(Suit.SPADES, Rank.TEN)),
            # T8 (last): ♠ TRUMP lead, SOUTH wins J♠ — 38 pts + 10 dix-de-der
            (Card(Suit.SPADES, Rank.JACK), Card(Suit.SPADES, Rank.QUEEN),
             Card(Suit.SPADES, Rank.KING), Card(Suit.SPADES, Rank.ACE)),
        ]
        tricks = tuple(
            tuple(TrickCard(list(Seat)[i], cards[i]) for i in range(4))
            for cards in trick_data
        )

        state = GameState(
            hands=tuple(() for _ in range(4)),
            trump=trump,
            dealer=Seat.SOUTH,
            leader=Seat.SOUTH,
            turn=Seat.SOUTH,
            phase=Phase.SCORING,
            bids=(),
            taker=Seat.SOUTH,
            current_trick=(),
            completed_tricks=tricks,
            last_trick_winner=Seat.SOUTH,
            declarations=(),
            team_scores=(0, 0),
            current_round_points=(0, 0),
            score_history=(),
            target=1000,
            up_card=None,
            remaining_cards=(),
            bidder_index=0,
            bidding_round=1,
            announced=None,
            belote_tracker=(False, False),
            first_trick_done=True,
        )

        breakdown = score_round(state)
        assert breakdown.is_capot is False
        assert breakdown.last_trick_team == 0, (
            "Fixture invariant: NS must win the last trick for the +10 to "
            "land on the taker side."
        )
        # Card points NS won (92) + 10 dix-de-der = 102
        assert breakdown.table_taker_pts == 92 + LAST_TRICK_BONUS
        assert breakdown.table_defender_pts == 60
        # Conservation: every point on the table is accounted for.
        assert (
            breakdown.table_taker_pts + breakdown.table_defender_pts
            == TOTAL_POINTS + LAST_TRICK_BONUS
        )


# ---------------------------------------------------------------------------
# 17. Round point conservation
# ---------------------------------------------------------------------------


class TestPointConservation:
    def test_non_capot_points_sum_162(self) -> None:
        """In non-capot non-failure rounds, ns_card_pts + ew_card_pts == 162."""
        trump = Suit.SPADES
        deck = make_deck()
        # Distribute cards so each team wins some tricks
        tricks: list[tuple[TrickCard, ...]] = []
        card_idx = 0
        for _i in range(8):
            trick = tuple(TrickCard(list(Seat)[j], deck[card_idx + j]) for j in range(4))
            tricks.append(trick)
            card_idx += 4

        # Determine actual winners
        winners = []
        for trick in tricks:
            w = trick_winner_seat(trick, trump)
            winners.append(w)

        state = GameState(
            hands=tuple(() for _ in range(4)),
            trump=trump,
            dealer=Seat.SOUTH,
            leader=Seat.SOUTH,
            turn=Seat.SOUTH,
            phase=Phase.SCORING,
            bids=(),
            taker=Seat.SOUTH,
            current_trick=(),
            completed_tricks=tuple(tricks),
            last_trick_winner=winners[-1] if winners else Seat.SOUTH,
            declarations=(),
            team_scores=(0, 0),
            current_round_points=(0, 0),
            score_history=(),
            target=1000,
            up_card=None,
            remaining_cards=(),
            bidder_index=0,
            bidding_round=1,
            announced=None,
            belote_tracker=(False, False),
            first_trick_done=True,
        )

        breakdown = score_round(state)
        # Pin the fixture-invariant: the deterministic `make_deck()` ordering
        # used here MUST produce a non-capot round, otherwise the conservation
        # check below is meaningless. Pre-fix this was a silent `if not capot`
        # which made the test vacuous if a future change to `make_deck()`
        # ordering flipped the outcome.
        assert not breakdown.is_capot, (
            "Fixture assumption violated: make_deck() trick layout produced "
            "a capot — the conservation check needs a non-capot scenario."
        )
        total = breakdown.table_taker_pts + breakdown.table_defender_pts
        expected = TOTAL_POINTS + LAST_TRICK_BONUS
        assert total == expected, f"Expected {expected}, got {total}"


# ---------------------------------------------------------------------------
# 18. Round determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_seed_same_deal(self) -> None:
        seed = 42
        rng1 = random.Random(seed)
        state1 = start_round(new_game(), rng1)

        rng2 = random.Random(seed)
        state2 = start_round(new_game(), rng2)

        assert state1.hands == state2.hands

    def test_different_seed_different_deal(self) -> None:
        rng1 = random.Random(42)
        state1 = start_round(new_game(), rng1)

        rng2 = random.Random(99)
        state2 = start_round(new_game(), rng2)

        assert state1.hands != state2.hands


# ---------------------------------------------------------------------------
# Additional: team_of / partner
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_team_of(self) -> None:
        assert team_of(Seat.SOUTH) == 0
        assert team_of(Seat.NORTH) == 0
        assert team_of(Seat.EAST) == 1
        assert team_of(Seat.WEST) == 1

    def test_partner(self) -> None:
        assert partner(Seat.SOUTH) == Seat.NORTH
        assert partner(Seat.NORTH) == Seat.SOUTH
        assert partner(Seat.EAST) == Seat.WEST
        assert partner(Seat.WEST) == Seat.EAST

    def test_seat_order(self) -> None:
        """Counter-clockwise: S → E → N → W → S."""
        assert Seat.SOUTH.next_seat() == Seat.EAST
        assert Seat.EAST.next_seat() == Seat.NORTH
        assert Seat.NORTH.next_seat() == Seat.WEST
        assert Seat.WEST.next_seat() == Seat.SOUTH


def test_package_version_matches_pyproject() -> None:
    """`belote.__version__` is the source of truth for both `--version` flags
    (`belote --version` and `belatro --version`). It must match the version
    declared in pyproject.toml — pre-3.1.0 the two drifted by two releases
    (pyproject said 3.0.3, __init__.py said 3.0.2). This test catches a future
    drift before it ships."""
    import re
    from pathlib import Path

    from belote import __version__

    pyproject = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, flags=re.MULTILINE)
    assert match is not None, "pyproject.toml is missing a top-level `version = \"…\"` line"
    declared = match.group(1)
    assert __version__ == declared, (
        f"belote.__version__ is {__version__!r} but pyproject.toml declares {declared!r}. "
        "Bump src/belote/__init__.py in lockstep with pyproject.toml — both --version flags "
        "read from __init__.py."
    )


# ---------------------------------------------------------------------------
# 3.9.3 R2: L'Anarchie preserves rebelote across mid-belote trump rotation
# ---------------------------------------------------------------------------


def test_belote_announcer_without_tracker_flag_raises() -> None:
    """4.8.2 (B5) regression pin: `belote_announcer` and `belote_tracker[0]`
    must advance in lockstep — `game.py::_record_belote_announcement` only
    sets the announcer at the moment the tracker flips True. A state with
    announcer set but tracker[0]=False would be corruption from replay
    tooling or a hand-built fixture; `_compute_belote_points` must surface
    the invariant violation rather than silently credit belote points.
    """
    import pytest

    from belote.game import BossModifiers
    from belote.scoring import _compute_belote_points, _ScoringContext

    bad_state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        contract="hearts",
        taker=Seat.SOUTH,
        belote_holders={Suit.HEARTS: Seat.SOUTH},
        belote_tracker=(False, False),  # tracker NOT flipped
        belote_announcer=Seat.SOUTH,  # but announcer set — invariant violated
        belote_trump=None,
        boss_modifiers=BossModifiers(),
    )
    ctx = _ScoringContext(
        state=bad_state,
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        taker_team=0,
        defender_team=1,
        is_sa=False,
        winners=[],
        tricks_ns=0,
        tricks_ew=0,
    )
    with pytest.raises(AssertionError, match="belote_announcer set without belote_tracker"):
        _compute_belote_points(ctx)


def test_anarchie_rebelote_survives_cross_rotation_play() -> None:
    """3.9.3 R2 regression: under `dynamic_trump` (L'Anarchie) the trump
    rotates after every 2 completed tricks. If South played K-trump in
    trick 2 and Q-of-original-trump in trick 3 (after the rotation), the
    pre-3.9.3 code compared `card.suit == current_trump` and silently
    dropped the rebelote. The fix captures `belote_trump` at first-belote
    and matches the Q against the captured suit.
    """
    from belote.game import BossModifiers, _PlayContext, _record_belote_announcement

    # Construct a state mid-round where:
    #   - belote_tracker = (True, False) — belote already announced
    #   - belote_announcer = Seat.SOUTH
    #   - belote_trump = HEARTS (captured at K♥ play)
    #   - state.trump = SPADES (rotated post-belote, pre-Q play)
    #   - belote_holders[HEARTS] = SOUTH
    south_seat = Seat.SOUTH
    state = GameState(
        hands=((Card(Suit.HEARTS, Rank.QUEEN),), (), (), ()),
        turn=south_seat,
        phase=Phase.PLAYING,
        trump=Suit.SPADES,  # post-rotation
        belote_holders={Suit.HEARTS: south_seat},
        belote_tracker=(True, False),
        belote_announcer=south_seat,
        belote_trump=Suit.HEARTS,
        boss_modifiers=BossModifiers(dynamic_trump=True),
    )
    ctx = _PlayContext(
        state=state,
        trump=state.trump,
        is_sa=False,
        se_trump=False,
    )
    tracker, announcer, blt_trump, announced = _record_belote_announcement(
        ctx, Card(Suit.HEARTS, Rank.QUEEN)
    )
    assert tracker == (True, True), (
        f"rebelote did not fire across trump rotation: tracker={tracker}, "
        f"belote_trump={blt_trump}, current_trump={state.trump}"
    )
    assert announcer == south_seat
    assert blt_trump == Suit.HEARTS
    assert announced == "Rebelote!"


def test_anarchie_normal_belote_still_works_without_rotation() -> None:
    """Sanity check: when trump has NOT rotated, the rebelote path uses
    the current trump (which equals belote_trump). Pre-3.9.3 behavior
    must remain unchanged in the no-rotation case."""
    from belote.game import BossModifiers, _PlayContext, _record_belote_announcement

    south_seat = Seat.SOUTH
    state = GameState(
        hands=((Card(Suit.HEARTS, Rank.QUEEN),), (), (), ()),
        turn=south_seat,
        phase=Phase.PLAYING,
        trump=Suit.HEARTS,  # no rotation
        belote_holders={Suit.HEARTS: south_seat},
        belote_tracker=(True, False),
        belote_announcer=south_seat,
        belote_trump=Suit.HEARTS,
        boss_modifiers=BossModifiers(),
    )
    ctx = _PlayContext(
        state=state,
        trump=state.trump,
        is_sa=False,
        se_trump=False,
    )
    tracker, _, _, announced = _record_belote_announcement(
        ctx, Card(Suit.HEARTS, Rank.QUEEN)
    )
    assert tracker == (True, True)
    assert announced == "Rebelote!"
