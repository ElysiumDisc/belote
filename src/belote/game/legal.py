"""Rules of play: which cards are legal (memoised on card ids) and who
wins a trick, including per-trick trump rotation and Sans Atout."""

from __future__ import annotations

from functools import lru_cache
from typing import Final

from ..deck import Card, Contract, Rank, Suit, is_trump_card, make_deck, trick_rank
from .state import (
    GameState,
    Phase,
    Seat,
    TrickCard,
    partner,
    team_of,
)

# ---------------------------------------------------------------------------
# Trick play / caching
# ---------------------------------------------------------------------------

_CARD_TO_ID: Final = {c: i for i, c in enumerate(make_deck())}
_ID_TO_CARD: Final = {v: k for k, v in _CARD_TO_ID.items()}


def clear_legal_cards_cache() -> None:
    """Clear the legal cards cache."""
    _calculate_legal_cards_impl.cache_clear()
    _trick_winner_seat_impl.cache_clear()


@lru_cache(maxsize=2048)
def _calculate_legal_cards_impl(
    hand_ids: tuple[int, ...],
    trump: Suit | None,
    current_trick_ids: tuple[tuple[int, int], ...],
    seat_val: int,
    seven_eight_trump: bool = False,
    is_sans_atout: bool = False,
) -> tuple[int, ...]:
    """Calculate legal cards using card IDs (memoized).

    Cache-key analysis (3.5.0 P2 investigation): the key uses small-int IDs
    rather than Card objects, which is already the minimal hashable surface.
    Benchmarks (`scripts/benchmark.py::benchmark_legal_cards{_cached,}`) show
    cold ~9μs / warm ~6μs — the 33% gap is dominated by KEY BUILD in
    `legal_cards()` (above), not by lru_cache lookup. Slimming further would
    require caching `hand_ids` on the hand tuple itself, which isn't
    achievable without changing the hand representation.

    `is_sans_atout` discriminates the Sans Atout contract from "no trump set
    yet" (both have trump=None). Under SA, the player must follow the lead
    suit if able; if void, free discard (no trumping concept).
    """
    # Map IDs back to Cards for logic
    hand = tuple(_ID_TO_CARD[i] for i in hand_ids)
    seat = Seat(seat_val)

    if not current_trick_ids:
        return hand_ids

    if is_sans_atout:
        lead_suit = _ID_TO_CARD[current_trick_ids[0][1]].suit
        my_suit = tuple(c for c in hand if c.suit == lead_suit)
        res = my_suit if my_suit else hand
        return tuple(_CARD_TO_ID[c] for c in res)

    if trump is None:
        return hand_ids

    # Reconstruct TrickCard-like objects for the internal logic if needed,
    # but we can just use the IDs.
    lead_card_id = current_trick_ids[0][1]
    lead_card = _ID_TO_CARD[lead_card_id]
    lead_suit = lead_card.suit

    # Who is currently winning the trick?
    played_cards = [
        TrickCard(Seat(s), _ID_TO_CARD[c]) for s, c in current_trick_ids if s != seat_val
    ]

    current_winner = _current_trick_winner(
        played_cards, trump, lead_suit, seven_eight_trump, is_sans_atout
    )
    partner_winning = current_winner is not None and partner(seat) == current_winner

    my_suit_cards = [c for c in hand if c.suit == lead_suit]

    res_cards: tuple[Card, ...] = ()

    # Tout Atout: every suit acts as trump within its own led-suit group. Must
    # follow the lead suit if able and must rise within it; if void, discard
    # freely (off-suit cards never beat the lead suit, so there's no "trump
    # over" to force). Partner-winning gives no extra flexibility — the rise
    # rule applies regardless of who's winning, since rising is the only way
    # to beat opponents within the lead suit.
    if trump == Suit.TOUT_ATOUT:
        if my_suit_cards:
            highest_in_trick = max(
                (
                    trick_rank(tc.card, trump, seven_eight_trump)
                    for tc in played_cards
                    if tc.card.suit == lead_suit
                ),
                default=-1,
            )
            risers = tuple(
                c
                for c in my_suit_cards
                if trick_rank(c, trump, seven_eight_trump) > highest_in_trick
            )
            res_cards = risers or tuple(my_suit_cards)
        else:
            res_cards = hand
        return tuple(_CARD_TO_ID[c] for c in res_cards)

    # A card is trump if it's the trump suit, or — under La Déluge
    # (seven_eight_trump) — any 7 or 8 regardless of suit. Following a trump
    # lead means following with ANY trump, not just lead-suit cards: an off-suit
    # 7/8 is a trump too. Using `c.suit == lead_suit` here would drop those and
    # wrongly report the player as void (empty legal set → crash).
    def is_trump(c: Card) -> bool:
        return is_trump_card(c, trump, seven_eight_trump)

    is_trump_lead = is_trump(lead_card)

    if is_trump_lead:
        # Trump led: must follow with a trump if possible, must overtrump if possible
        my_trumps = [c for c in hand if is_trump(c)]
        if my_trumps:
            highest_in_trick = max(
                (trick_rank(tc.card, trump, seven_eight_trump) for tc in played_cards), default=-1
            )
            must_overtrump = any(
                trick_rank(c, trump, seven_eight_trump) > highest_in_trick for c in my_trumps
            )
            if must_overtrump:
                res_cards = tuple(
                    c
                    for c in my_trumps
                    if trick_rank(c, trump, seven_eight_trump) > highest_in_trick
                )
            else:
                res_cards = tuple(my_trumps)
        else:
            # No trumps at all - can play anything (every card is non-trump)
            res_cards = hand
    else:
        # Non-trump led
        if my_suit_cards:
            # Must follow suit
            res_cards = tuple(my_suit_cards)
        else:
            # Void in led suit
            if partner_winning:
                # Partner is winning - can discard
                res_cards = hand
            else:
                # Must trump if possible
                my_trumps = [c for c in hand if is_trump(c)]
                if my_trumps:
                    # Must trump; also must overtrump if possible
                    highest_trump_in_trick = max(
                        (
                            trick_rank(tc.card, trump, seven_eight_trump)
                            for tc in played_cards
                            if is_trump(tc.card)
                        ),
                        default=-1,
                    )
                    can_overtrump = any(
                        trick_rank(c, trump, seven_eight_trump) > highest_trump_in_trick
                        for c in my_trumps
                    )
                    if can_overtrump:
                        res_cards = tuple(
                            c
                            for c in my_trumps
                            if trick_rank(c, trump, seven_eight_trump) > highest_trump_in_trick
                        )
                    else:
                        res_cards = tuple(my_trumps)
                else:
                    # Can't follow, can't trump - discard
                    res_cards = hand

    return tuple(_CARD_TO_ID[c] for c in res_cards)


def legal_cards(state: GameState, seat: Seat) -> tuple[Card, ...]:
    """Return the set of legal cards for the given seat to play (memoized)."""
    if state.phase != Phase.PLAYING:
        return state.hand_of(seat)

    hand = state.hand_of(seat)
    hand_ids = tuple(_CARD_TO_ID[c] for c in hand)
    trick_ids = tuple((tc.seat.value, _CARD_TO_ID[tc.card]) for tc in state.current_trick)
    se_trump = state.variants.seven_eight_trump
    is_sa = state.contract == Contract.SANS_ATOUT

    res_ids = _calculate_legal_cards_impl(
        hand_ids, state.trump, trick_ids, seat.value, se_trump, is_sa
    )
    res_cards = tuple(_ID_TO_CARD[i] for i in res_ids)

    # Le Républicain deck: 7s/8s are wild and always legal in addition to the
    # normal options. Union (preserve order, don't double up).
    if state.variants.wild_seven_eight and state.current_trick:
        existing = set(res_cards)
        wild_extras = tuple(
            c for c in hand if c.rank in (Rank.SEVEN, Rank.EIGHT) and c not in existing
        )
        if wild_extras:
            res_cards = res_cards + wild_extras

    return res_cards


def _current_trick_winner(
    played: list[TrickCard],
    trump: Suit | None,
    lead_suit: Suit,
    seven_eight_trump: bool = False,
    is_sans_atout: bool = False,
) -> Seat | None:
    """Determine who is currently winning the trick based on cards played so far."""
    if not played:
        return None
    best = played[0]
    for tc in played[1:]:
        if _card_beats(tc.card, best.card, trump, lead_suit, seven_eight_trump, is_sans_atout):
            best = tc
    return best.seat


def _card_beats(
    card: Card,
    current_best: Card,
    trump: Suit | None,
    lead_suit: Suit,
    seven_eight_trump: bool = False,
    is_sans_atout: bool = False,
) -> bool:
    """Does card beat current_best?

    Sans Atout: only lead-suit cards can win; among lead-suit cards, the
    higher non-trump rank wins. Off-suit cards never beat the lead-suit hand.
    """
    if is_sans_atout:
        if card.suit == current_best.suit:
            # Both same suit. Use SANS_ATOUT_TRUMP placeholder is wrong; we want
            # the non-trump scale. Pass an unrelated suit so trick_rank treats
            # both as non-trump.
            return _NONTRUMP_RANK[card.rank] > _NONTRUMP_RANK[current_best.rank]
        # Different suits under SA: only the lead-suit card can win.
        return card.suit == lead_suit and current_best.suit != lead_suit

    if card.suit == current_best.suit:
        assert trump is not None  # legal_cards guarantees this for non-SA
        return trick_rank(card, trump, seven_eight_trump) > trick_rank(
            current_best, trump, seven_eight_trump
        )

    # Lead card is usually the first card in the trick.
    # We need to know if the LEAD was a trump (declared or 7/8 in Deluge).
    # Deliberately NOT deck.is_trump_card: under Tout Atout every card is
    # "trump", but cross-suit cards must still lose to the lead suit here.
    card_is_trump = (card.suit == trump) or (
        seven_eight_trump and card.rank in (Rank.SEVEN, Rank.EIGHT)
    )
    best_is_trump = (current_best.suit == trump) or (
        seven_eight_trump and current_best.rank in (Rank.SEVEN, Rank.EIGHT)
    )

    if card_is_trump and not best_is_trump:
        return True
    if not card_is_trump and best_is_trump:
        return False

    # Neither are trump (or both are trump but different suits - only possible with 7/8 deluge)
    if card_is_trump and best_is_trump:
        assert trump is not None
        # Both act as trumps, compare their trick_ranks
        return trick_rank(card, trump, seven_eight_trump) > trick_rank(
            current_best, trump, seven_eight_trump
        )

    return card.suit == lead_suit


# Inline copy of deck._NONTRUMP_ORDER so _card_beats can rank lead-suit cards
# under Sans Atout without importing private symbols. Match deck.py:111-121.
_NONTRUMP_RANK: dict[Rank, int] = {
    Rank.SEVEN: 0,
    Rank.EIGHT: 1,
    Rank.NINE: 2,
    Rank.JACK: 3,
    Rank.QUEEN: 4,
    Rank.KING: 5,
    Rank.TEN: 6,
    Rank.ACE: 7,
}


def per_trick_trumps(state: GameState, trump: Suit | None, n: int) -> list[Suit | None]:
    """Trump in force for each of the first `n` tricks of the round.

    Only L'Anarchie (`dynamic_trump`) changes trump mid-round; it is resolved
    from `state.trick_trumps`, recorded by `play_card`. Tricks not yet recorded
    (an in-flight projection that includes the current trick) use `trump`,
    which is the trump in force right now. Every other mode returns `trump`
    for all tricks, exactly as before.
    """
    if not state.variants.dynamic_trump:
        return [trump] * n
    recorded = state.trick_trumps
    return [recorded[i] if i < len(recorded) else trump for i in range(n)]


def compute_trick_winners(
    state: GameState,
    trump: Suit | None,
    is_sans_atout: bool,
    tricks: tuple[tuple[TrickCard, ...], ...] | list[tuple[TrickCard, ...]] | None = None,
) -> list[Seat | None]:
    """Resolve the winner of each completed trick, honoring La Rupture.

    La Rupture (`no_consecutive_team_wins`) flips the win to the opposing
    team when a trick's raw winner would be on the same team as the previous
    trick's resolved winner. Without this helper, `play_card` applied Rupture
    to live HUD but the final scoring path re-derived winners from raw
    `trick_winner_seat` — silently restoring the original winner and double-
    crediting the round.

    When `tricks` is None (the default), resolves `state.completed_tricks`.
    Callers building an in-flight trick list (live HUD CAPOT detection on the
    8th trick) may pass an explicit sequence so the same Rupture rule applies
    to the projected final state.
    """
    se_trump = state.variants.seven_eight_trump
    rupture = state.variants.no_consecutive_team_wins
    source = state.completed_tricks if tricks is None else tricks
    winners: list[Seat | None] = []
    prev_winner: Seat | None = None
    trumps = per_trick_trumps(state, trump, len(source))
    for trick, t_trump in zip(source, trumps, strict=True):
        w = trick_winner_seat(trick, t_trump, se_trump, is_sans_atout)
        if (
            rupture
            and prev_winner is not None
            and w is not None
            and team_of(w) == team_of(prev_winner)
        ):
            other_team_cards = [tc for tc in trick if team_of(tc.seat) != team_of(prev_winner)]
            if other_team_cards and (t_trump is not None or is_sans_atout):
                best_other = _current_trick_winner(
                    other_team_cards,
                    t_trump,
                    trick[0].card.suit,
                    se_trump,
                    is_sans_atout,
                )
                if best_other is not None:
                    w = best_other
        winners.append(w)
        prev_winner = w
    return winners


def trick_winner_seat(
    trick: tuple[TrickCard, ...],
    trump: Suit | None,
    seven_eight_trump: bool = False,
    is_sans_atout: bool = False,
) -> Seat | None:
    """Determine the winner of a completed trick.

    Returns None when the contract isn't established (e.g., during DEAL/BIDDING).
    Sans Atout has trump=None but produces a real winner when is_sans_atout=True.
    """
    if not trick:
        return None
    if trump is None and not is_sans_atout:
        return None

    # Use a primitive-only key for memoization
    trick_ids = tuple((tc.seat.value, _CARD_TO_ID[tc.card]) for tc in trick)
    return _trick_winner_seat_impl(trick_ids, trump, seven_eight_trump, is_sans_atout)


@lru_cache(maxsize=1024)
def _trick_winner_seat_impl(
    trick_ids: tuple[tuple[int, int], ...],
    trump: Suit | None,
    seven_eight_trump: bool = False,
    is_sans_atout: bool = False,
) -> Seat:
    """Internal memoized winner detection using primitives."""
    played = [TrickCard(Seat(s), _ID_TO_CARD[c]) for s, c in trick_ids]
    lead_suit = played[0].card.suit

    res = _current_trick_winner(played, trump, lead_suit, seven_eight_trump, is_sans_atout)
    assert res is not None  # Should not be None if trick_ids is not empty
    return res
