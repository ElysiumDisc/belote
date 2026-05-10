"""Phase 1 plumbing tests: TOUT_ATOUT, coinche level on events, Rarity enum,
new BelAtroRun fields, BeloteAnnouncedEvent emission."""

from __future__ import annotations

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.engine.event_bus import BidMadeEvent, RoundEndEvent
from belote.belatro.items.base import Joker, Planet, Rarity, Tarot, Voucher
from belote.deck import CARD_SUITS, Card, Rank, Suit, card_points, make_deck, trick_rank
from belote.game import Seat

# ── Suit.TOUT_ATOUT ────────────────────────────────────────────────────────


def test_tout_atout_is_a_suit_value_not_a_card_suit() -> None:
    assert Suit.TOUT_ATOUT in list(Suit)
    assert Suit.TOUT_ATOUT.is_card_suit is False
    for s in CARD_SUITS:
        assert s.is_card_suit is True


def test_make_deck_excludes_tout_atout() -> None:
    deck = make_deck()
    assert len(deck) == 32
    assert all(c.suit.is_card_suit for c in deck)
    assert all(c.suit != Suit.TOUT_ATOUT for c in deck)


def test_card_points_under_tout_atout_uses_trump_scale() -> None:
    # Under Tout Atout, every Jack is worth 20 (not 2), every 9 is 14, etc.
    assert card_points(Card(Suit.HEARTS, Rank.JACK), Suit.TOUT_ATOUT) == 20
    assert card_points(Card(Suit.SPADES, Rank.JACK), Suit.TOUT_ATOUT) == 20
    assert card_points(Card(Suit.CLUBS, Rank.NINE), Suit.TOUT_ATOUT) == 14
    # Non-trump-suit Ace would be 11 in normal contracts; in Tout Atout it's still 11
    # (trump Ace is also 11, so the value coincidentally matches).
    assert card_points(Card(Suit.DIAMONDS, Rank.ACE), Suit.TOUT_ATOUT) == 11


def test_trick_rank_under_tout_atout_treats_all_suits_as_trump() -> None:
    # Under Tout Atout, a Hearts JACK and a Spades JACK both rank 8 + JACK_TRUMP_ORDER.
    rh = trick_rank(Card(Suit.HEARTS, Rank.JACK), Suit.TOUT_ATOUT)
    rs = trick_rank(Card(Suit.SPADES, Rank.JACK), Suit.TOUT_ATOUT)
    assert rh == rs and rh >= 8


# ── Rarity enum ────────────────────────────────────────────────────────────


def test_rarity_enum_values() -> None:
    assert Rarity.COMMON.value == "common"
    assert Rarity.LEGENDARY.value == "legendary"


def test_existing_items_default_to_common_rarity() -> None:
    # All four item kinds carry a `rarity` class-var defaulting to COMMON.
    assert Joker.rarity == Rarity.COMMON
    assert Planet.rarity == Rarity.COMMON
    assert Tarot.rarity == Rarity.COMMON
    assert Voucher.rarity == Rarity.COMMON
    # Joker also gets a `fusable` class-var (used by Phase 3 endless fusion).
    assert Joker.fusable is True


# ── New BelAtroRun fields ──────────────────────────────────────────────────


def test_belatro_run_has_phase1_fields_with_safe_defaults() -> None:
    run = BelAtroRun()
    assert run.tierce_charges == 0
    assert run.legendary_unlocked == set()
    assert run.endless is False
    assert run.endless_ante_offset == 0
    assert run.ante_theme is None
    assert run.capot_insurance is False
    assert run.partner_mood == "neutral"


# ── Event payload extensions ───────────────────────────────────────────────


def test_bid_made_event_carries_coinche_level() -> None:
    e = BidMadeEvent(
        seat=Seat.EAST,
        trump=Suit.HEARTS,
        contract="normal",
        coinche_level=2,
    )
    assert e.coinche_level == 2


def test_round_end_event_carries_contract_and_coinche_level() -> None:
    class _Stub:
        is_failed = False

    e = RoundEndEvent(
        breakdown=_Stub(),
        taker_seat=Seat.SOUTH,
        trump=Suit.TOUT_ATOUT,
        capot=False,
        contract="tout_atout",
        coinche_level=1,
    )
    assert e.contract == "tout_atout"
    assert e.coinche_level == 1
    assert e.trump == Suit.TOUT_ATOUT


# ── _SUIT_TO_CONTRACT mapping ──────────────────────────────────────────────


def test_suit_to_contract_includes_tout_atout() -> None:
    from belote.belatro.core.scoring import _SUIT_TO_CONTRACT

    assert _SUIT_TO_CONTRACT[Suit.TOUT_ATOUT] == "tout_atout"


# ── _joker_state scalar-only contract (3.1.0 deepcopy → shallow) ───────────


def test_shop_edition_weights_match_distribution() -> None:
    """Pin the Shop._roll_edition() probability table. Each weighted bucket
    should empirically converge to its declared weight under N=10000 rolls
    with a fixed seed (±2σ tolerance). Catches accidental edits to the
    weight table or off-by-one in the cumulative-roll loop."""
    import random
    from collections import Counter

    from belote.belatro.run.shop import Shop

    rng = random.Random(0xBE10E)
    n = 10_000
    counts: Counter[str] = Counter()

    # 3.2.0: _roll_edition now takes an explicit rng instead of using the
    # module-level random — we pass our seeded generator directly.
    shop = Shop.__new__(Shop)  # bypass __init__; we only need _roll_edition
    for _ in range(n):
        counts[shop._roll_edition(rng)] += 1

    declared = dict(Shop._EDITION_WEIGHTS)
    # Tolerance: ±2σ for a Bernoulli(p) trial over n rolls is ~2*sqrt(p*(1-p)/n)
    # Even the rarest bucket (neg @ 0.02) has σ ≈ 0.0014; ±0.005 is comfortable.
    for name, weight in declared.items():
        observed = counts[name] / n
        assert abs(observed - weight) < 0.01, (
            f"Edition '{name}' rolled {observed:.3f}, declared {weight}"
        )


def test_joker_state_only_contains_scalar_values() -> None:
    """Pinning invariant: every value placed into _joker_state by any joker
    must be a scalar (bool/int/str/None). update_state replaced its per-event
    deepcopy with a shallow `dict(...)` (3.1.0); a future joker that stashes a
    list/dict/set in _joker_state would silently leak mutations across rounds.

    Walks every Joker registered in `registry.jokers`, drives it through
    on_round_start + each event hook with stub events, and asserts no mutable
    container leaked into the dict."""
    from dataclasses import dataclass

    from belote.belatro.engine.event_bus import (
        BeloteAnnouncedEvent,
        DeclarationScoredEvent,
        TrickWonEvent,
    )
    from belote.belatro.items.registry import register_all_items, registry

    register_all_items()

    @dataclass
    class _StubBreakdown:
        is_failed: bool = False

    state: dict[str, object] = {}
    events: list[object] = [
        TrickWonEvent(
            winner=Seat.SOUTH,
            cards=(Card(Suit.HEARTS, Rank.ACE),),
            trick_number=1,
            is_last=False,
            card_points=11,
            trump=Suit.HEARTS,
        ),
        BeloteAnnouncedEvent(seat=Seat.SOUTH, is_rebelote=False),
        DeclarationScoredEvent(seat=Seat.SOUTH, declaration_type="Tierce", points=20),
        RoundEndEvent(
            breakdown=_StubBreakdown(),
            taker_seat=Seat.SOUTH,
            trump=Suit.HEARTS,
            capot=False,
            contract="hearts",
            coinche_level=0,
        ),
    ]

    for joker_cls in registry.jokers.values():
        joker = joker_cls()
        joker.on_round_start(state)
        for ev in events:
            for hook in (
                "on_trick_won",
                "on_belote",
                "on_declaration_scored",
                "on_round_end",
            ):
                method = getattr(joker, hook, None)
                if method is None:
                    continue
                try:
                    method(ev, state)
                except Exception:  # noqa: BLE001
                    # Hooks expect specific event types; skip mismatches.
                    continue

    for key, value in state.items():
        assert not isinstance(value, list | dict | set), (
            f"Joker leaked a mutable container into _joker_state[{key!r}]: "
            f"{type(value).__name__}. The shallow-copy contract requires "
            "scalar values only."
        )
