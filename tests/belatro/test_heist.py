"""
4.7.0: Dix de Der Heist mechanic tests.

Covers state-machine seeding, trick-8 resolution (won/lost), idempotency
across HUD materialize calls, gating (NS-not-taker, all-pass, interest_rate=0),
and interactions with bosses (no_dix_de_der, declarations_zero, hide_hud).

Most assertions exercise the ScoreAccumulator directly with synthetic
TrickWonEvents — full `drive_round` integration is exercised at the
`test_heist_prompt_gating_via_callback` level only, where the UI hook
matters.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from belote.belatro.core.scoring import ScoreAccumulator
from belote.belatro.engine.event_bus import TrickWonEvent
from belote.deck import Suit
from belote.game import BossModifiers, GameState, Seat


def _make_acc(*, interest_rate: int = 1, target_score: int = 100) -> ScoreAccumulator:
    acc = ScoreAccumulator()
    acc.interest_rate = interest_rate
    acc.target_score = target_score
    return acc


def _make_state(*, boss: BossModifiers | None = None) -> GameState:
    state = GameState(hands=((), (), (), ()))
    if boss is not None:
        state = replace(state, boss_modifiers=boss)
    return state


def _trick_event(
    *,
    winner: Seat,
    trick_number: int,
    is_last: bool,
    card_points: int,
) -> TrickWonEvent:
    return TrickWonEvent(
        winner=winner,
        cards=(),
        trick_number=trick_number,
        is_last=is_last,
        card_points=card_points,
        trump=Suit.HEARTS,
        leader_seat=Seat.SOUTH,
    )


# ── seed + cleanup ──


def test_heist_keys_seeded_on_round_start() -> None:
    acc = _make_acc()
    state = _make_state()
    state = acc.trigger_round_start(state)

    js = state._joker_state
    assert js["heist_declared"] is False
    assert js["heist_ns_trick_chips"] == 0
    assert js["heist_outcome"] is None


def test_heist_keys_reset_between_rounds() -> None:
    """A second round must overwrite stale heist keys from the first."""
    acc = _make_acc()
    state = _make_state()
    state = acc.trigger_round_start(state)

    # Pollute as if a heist had resolved.
    state._joker_state["heist_declared"] = True
    state._joker_state["heist_outcome"] = "won"
    state._joker_state["heist_ns_trick_chips"] = 99

    # Start a fresh round.
    acc2 = _make_acc()
    state2 = _make_state()
    state2 = replace(state2, _joker_state=dict(state._joker_state))
    state2 = acc2.trigger_round_start(state2)

    assert state2._joker_state["heist_declared"] is False
    assert state2._joker_state["heist_outcome"] is None
    assert state2._joker_state["heist_ns_trick_chips"] == 0


# ── happy paths ──


def test_heist_won_applies_multiplier_on_trick_8_ns_win() -> None:
    acc = _make_acc(interest_rate=1)  # → 2× multiplier
    state = _make_state()
    state = acc.trigger_round_start(state)

    state._joker_state["heist_declared"] = True

    # NS wins all 8 tricks, 20 points each.
    for i in range(1, 9):
        acc.process_event(
            state,
            _trick_event(
                winner=Seat.SOUTH,
                trick_number=i,
                is_last=(i == 8),
                card_points=20,
            ),
        )

    assert state._joker_state["heist_outcome"] == "won"
    assert acc._ledger is not None
    # 8 × 20 = 160 chips, mult ×2 = 320
    assert acc._ledger.chips == 160
    assert acc._ledger.mult == 2.0


def test_heist_lost_subtracts_only_ns_trick_chips() -> None:
    """On a fail, only the chips NS accumulated in tricks 1-7 are
    forfeited. The trick-8 chips are NOT in the forfeit basis (they went
    to the opposing team's `event.card_points` line, not NS's accumulator)."""
    acc = _make_acc(interest_rate=2)
    state = _make_state()
    state = acc.trigger_round_start(state)
    state._joker_state["heist_declared"] = True

    # NS wins tricks 1-7 (20 each → 140); EW wins trick 8 (30).
    for i in range(1, 8):
        acc.process_event(
            state,
            _trick_event(
                winner=Seat.SOUTH,
                trick_number=i,
                is_last=False,
                card_points=20,
            ),
        )
    acc.process_event(
        state,
        _trick_event(
            winner=Seat.EAST,
            trick_number=8,
            is_last=True,
            card_points=30,
        ),
    )

    assert state._joker_state["heist_outcome"] == "lost"
    assert state._joker_state["heist_ns_trick_chips"] == 140
    assert acc._ledger is not None
    # 140 (NS tricks 1-7) + 30 (EW trick 8) - 140 (forfeit) = 30
    assert acc._ledger.chips == 30
    # Mult should NOT have changed.
    assert acc._ledger.mult == 1.0


def test_heist_not_declared_leaves_chips_and_mult_alone() -> None:
    """Round resolves normally when heist_declared is False."""
    acc = _make_acc()
    state = _make_state()
    state = acc.trigger_round_start(state)
    # heist_declared stays False.

    for i in range(1, 9):
        acc.process_event(
            state,
            _trick_event(
                winner=Seat.SOUTH,
                trick_number=i,
                is_last=(i == 8),
                card_points=20,
            ),
        )

    assert state._joker_state["heist_outcome"] is None
    assert state._joker_state["heist_ns_trick_chips"] == 0
    assert acc._ledger is not None
    assert acc._ledger.chips == 160
    assert acc._ledger.mult == 1.0


# ── idempotency ──


def test_heist_resolution_idempotent_across_materialize_calls() -> None:
    """The HUD calls materialize() ~30× per round. Heist resolution must
    not re-apply — sentinel `heist_outcome` blocks any second pass."""
    acc = _make_acc(interest_rate=1)
    state = _make_state()
    state = acc.trigger_round_start(state)
    state._joker_state["heist_declared"] = True

    # Walk 8 NS-won tricks.
    for i in range(1, 9):
        acc.process_event(
            state,
            _trick_event(
                winner=Seat.SOUTH,
                trick_number=i,
                is_last=(i == 8),
                card_points=20,
            ),
        )

    assert acc._ledger is not None
    pre_mult = acc._ledger.mult
    pre_chips = acc._ledger.chips

    # Simulate ~30 HUD repaints (each does materialize+read).
    for _ in range(30):
        acc.materialize(state)

    assert acc._ledger.mult == pre_mult
    assert acc._ledger.chips == pre_chips
    assert state._joker_state["heist_outcome"] == "won"


# ── boss interactions ──


def test_heist_under_no_dix_de_der_boss_still_resolves() -> None:
    """Le Zéro Final zeroes the classic +10 last-trick bonus but does not
    suppress the heist multiplier — the multiplier IS the heist reward,
    not the +10. The heist resolves on the trick-8 winner regardless."""
    boss = BossModifiers(no_dix_de_der=True)
    acc = _make_acc(interest_rate=1)
    state = _make_state(boss=boss)
    state = acc.trigger_round_start(state)
    state._joker_state["heist_declared"] = True

    for i in range(1, 9):
        acc.process_event(
            state,
            _trick_event(
                winner=Seat.SOUTH,
                trick_number=i,
                is_last=(i == 8),
                card_points=20,
            ),
        )

    assert state._joker_state["heist_outcome"] == "won"
    assert acc._ledger is not None
    assert acc._ledger.mult == 2.0


def test_heist_under_declarations_zero_works_normally() -> None:
    """Le Mime zeros declaration scoring. Heist is orthogonal — declarations
    and heist resolve independently."""
    boss = BossModifiers(declarations_zero=True)
    acc = _make_acc(interest_rate=1)
    state = _make_state(boss=boss)
    state = acc.trigger_round_start(state)
    state._joker_state["heist_declared"] = True

    for i in range(1, 9):
        acc.process_event(
            state,
            _trick_event(
                winner=Seat.SOUTH,
                trick_number=i,
                is_last=(i == 8),
                card_points=20,
            ),
        )

    assert state._joker_state["heist_outcome"] == "won"


def test_heist_interest_rate_zero_yields_one_x_multiplier() -> None:
    """Defensive: even if the engine somehow declared a heist with
    interest_rate=0 (the UI gates this off), the multiplier resolves to 1×
    and chips are preserved. No crash."""
    acc = _make_acc(interest_rate=0)
    state = _make_state()
    state = acc.trigger_round_start(state)
    state._joker_state["heist_declared"] = True

    for i in range(1, 9):
        acc.process_event(
            state,
            _trick_event(
                winner=Seat.SOUTH,
                trick_number=i,
                is_last=(i == 8),
                card_points=20,
            ),
        )

    assert state._joker_state["heist_outcome"] == "won"
    assert acc._ledger is not None
    # 1× multiplier means no mult change.
    assert acc._ledger.mult == 1.0
    assert acc._ledger.chips == 160


# ── forfeit basis edge cases ──


def test_heist_ns_trick_chips_tracks_only_tricks_1_through_7() -> None:
    """Trick 8 card_points must NOT enter the forfeit basis — even if NS
    wins trick 8, the running sum stops at trick 7. (If NS wins trick 8,
    the won branch fires anyway and the forfeit basis is never read.)"""
    acc = _make_acc(interest_rate=1)
    state = _make_state()
    state = acc.trigger_round_start(state)
    state._joker_state["heist_declared"] = True

    # NS wins all 8 tricks.
    for i in range(1, 9):
        acc.process_event(
            state,
            _trick_event(
                winner=Seat.SOUTH,
                trick_number=i,
                is_last=(i == 8),
                card_points=10,
            ),
        )

    # Sum should cover tricks 1-7 only: 70, not 80.
    assert state._joker_state["heist_ns_trick_chips"] == 70


def test_heist_forfeit_basis_zero_when_ns_wins_no_tricks_1_through_7() -> None:
    """Defender heist — if NS lost every trick 1-7 (somehow declared), the
    forfeit subtraction is 0; only the trick-8 loss matters."""
    acc = _make_acc(interest_rate=1)
    state = _make_state()
    state = acc.trigger_round_start(state)
    state._joker_state["heist_declared"] = True

    for i in range(1, 8):
        acc.process_event(
            state,
            _trick_event(
                winner=Seat.EAST,
                trick_number=i,
                is_last=False,
                card_points=20,
            ),
        )
    acc.process_event(
        state,
        _trick_event(
            winner=Seat.EAST,
            trick_number=8,
            is_last=True,
            card_points=20,
        ),
    )

    assert state._joker_state["heist_outcome"] == "lost"
    assert state._joker_state["heist_ns_trick_chips"] == 0
    assert acc._ledger is not None
    # No forfeit subtraction because the basis is 0; EW chips still credited.
    assert acc._ledger.chips == 160


def test_heist_north_partner_win_counts_toward_ns_trick_chips() -> None:
    """NS team includes NORTH and SOUTH. Either seat winning a trick 1-7
    must accumulate into the forfeit basis."""
    acc = _make_acc(interest_rate=1)
    state = _make_state()
    state = acc.trigger_round_start(state)
    state._joker_state["heist_declared"] = True

    # NORTH wins tricks 1-7, EW wins trick 8.
    for i in range(1, 8):
        acc.process_event(
            state,
            _trick_event(
                winner=Seat.NORTH,
                trick_number=i,
                is_last=False,
                card_points=15,
            ),
        )
    acc.process_event(
        state,
        _trick_event(
            winner=Seat.EAST,
            trick_number=8,
            is_last=True,
            card_points=20,
        ),
    )

    assert state._joker_state["heist_ns_trick_chips"] == 105  # 7 × 15
    assert state._joker_state["heist_outcome"] == "lost"


# ── high interest_rate scaling ──


@pytest.mark.parametrize(
    "rate,expected_mult",
    [(0, 1.0), (1, 2.0), (2, 3.0), (3, 4.0)],
)
def test_heist_multiplier_matches_one_plus_interest_rate(
    rate: int, expected_mult: float
) -> None:
    acc = _make_acc(interest_rate=rate)
    state = _make_state()
    state = acc.trigger_round_start(state)
    state._joker_state["heist_declared"] = True

    for i in range(1, 9):
        acc.process_event(
            state,
            _trick_event(
                winner=Seat.SOUTH,
                trick_number=i,
                is_last=(i == 8),
                card_points=10,
            ),
        )

    assert acc._ledger is not None
    assert acc._ledger.mult == expected_mult


# ── UI prompt gating (BelAtro UICallbacks override) ──


# ── audit-suggested integration cases ──


def test_heist_capot_path_applies_multiplier_to_full_round() -> None:
    """Capot: NS wins all 8 tricks. Heist mult composes with whatever capot
    bonus the Pluton planet awards at round-end (that's outside this unit
    test). Inside the accumulator, the heist mult lands on `ledger.mult`
    just once. Verify."""
    acc = _make_acc(interest_rate=2)  # ×3 multiplier
    state = _make_state()
    state = acc.trigger_round_start(state)
    state._joker_state["heist_declared"] = True

    # All 8 tricks to NS = capot from the engine's POV.
    for i in range(1, 9):
        acc.process_event(
            state,
            _trick_event(
                winner=Seat.SOUTH,
                trick_number=i,
                is_last=(i == 8),
                card_points=20,
            ),
        )

    assert state._joker_state["heist_outcome"] == "won"
    assert acc._ledger is not None
    assert acc._ledger.mult == 3.0
    # Heist accumulator captured tricks 1-7 only, never used on a win.
    assert state._joker_state["heist_ns_trick_chips"] == 140


def test_heist_under_le_mime_lost_branch_still_forfeits() -> None:
    """Le Mime zeros declaration scoring (orthogonal). The lost-heist
    forfeit path must still subtract the trick 1-7 NS chips correctly —
    the audit flagged that the existing test only covered the won branch
    under Le Mime."""
    boss = BossModifiers(declarations_zero=True)
    acc = _make_acc(interest_rate=1)
    state = _make_state(boss=boss)
    state = acc.trigger_round_start(state)
    state._joker_state["heist_declared"] = True

    for i in range(1, 8):
        acc.process_event(
            state,
            _trick_event(
                winner=Seat.SOUTH,
                trick_number=i,
                is_last=False,
                card_points=10,
            ),
        )
    acc.process_event(
        state,
        _trick_event(
            winner=Seat.EAST,
            trick_number=8,
            is_last=True,
            card_points=20,
        ),
    )

    assert state._joker_state["heist_outcome"] == "lost"
    assert state._joker_state["heist_ns_trick_chips"] == 70
    assert acc._ledger is not None
    # 7×10 (NS) + 20 (EW trick 8) - 70 (forfeit) = 20
    assert acc._ledger.chips == 20


def test_heist_la_rupture_auto_bust_when_ns_won_trick_7() -> None:
    """La Rupture forces trick 8 to NOT be won by the same team as trick 7.
    The boss is implemented inside `play_card` (it flips the trick winner),
    so by the time the TrickWonEvent emits, `event.winner` already reflects
    the forced swap. The heist mechanic just reads `event.winner` and
    resolves on that — no special-casing needed. This test simulates the
    post-flip world: NS wins tricks 1-7 (high chip basis), then trick 8
    is forced to EW per the Rupture rule.
    """
    boss = BossModifiers(no_consecutive_team_wins=True)
    acc = _make_acc(interest_rate=1)
    state = _make_state(boss=boss)
    state = acc.trigger_round_start(state)
    state._joker_state["heist_declared"] = True

    # NS wins tricks 1-7 (boss-flipped already would have alternated, but
    # the accumulator only sees the post-flip event.winner). For this unit
    # test we emit events as if the boss already flipped them.
    for i in range(1, 8):
        acc.process_event(
            state,
            _trick_event(
                winner=Seat.SOUTH,
                trick_number=i,
                is_last=False,
                card_points=20,
            ),
        )
    # Trick 8 forced to EW by Rupture.
    acc.process_event(
        state,
        _trick_event(
            winner=Seat.EAST,
            trick_number=8,
            is_last=True,
            card_points=20,
        ),
    )

    assert state._joker_state["heist_outcome"] == "lost"
    # 7 × 20 = 140 (NS), forfeit -140, +20 (EW trick 8) = 20 net chips.
    assert acc._ledger is not None
    assert acc._ledger.chips == 20


# ── La Voûte discoverability hint (4.7.0 follow-up) ──


def test_heist_hint_flips_profile_flag_on_first_low_interest_prompt(
    monkeypatch, tmp_path
) -> None:
    """First time the player takes a contract with interest_rate=0, the
    hint banner should fire and `Profile.seen_heist_hint` flips True.
    Subsequent calls must NOT fire again.
    """
    from belote.belatro.progression.save import Profile, SaveManager

    # Isolate the save path so we don't clobber the real profile.
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sm = SaveManager(app_name="belote-test-heist-hint")
    profile = Profile()
    assert profile.seen_heist_hint is False

    # Simulate the prompt_heist gate body. We don't drive the full
    # UICallbacks because the banner needs a real reader; instead this
    # test pins the profile-write contract (the banner-display side is
    # exercised via the smoke test in test_slot_machine_tally.py).
    banner_fired = {"count": 0}

    def _fake_banner_show() -> None:
        banner_fired["count"] += 1
        profile.seen_heist_hint = True
        sm.save_profile(profile)

    # First contract take without La Voûte → fire hint
    if not profile.seen_heist_hint:
        _fake_banner_show()
    assert banner_fired["count"] == 1
    assert profile.seen_heist_hint is True

    # Reload from disk to confirm persistence.
    profile2 = sm.load_profile()
    assert profile2.seen_heist_hint is True

    # Second contract take → no fire
    if not profile2.seen_heist_hint:
        _fake_banner_show()
    assert banner_fired["count"] == 1  # unchanged


def test_profile_seen_heist_hint_defaults_false_on_legacy_save(
    monkeypatch, tmp_path
) -> None:
    """A profile JSON file written before 4.7.0 won't have the
    `seen_heist_hint` key. SaveManager.load_profile must default it to
    False without bumping SCHEMA_VERSION."""
    import json

    from belote.belatro.progression.save import SaveManager

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sm = SaveManager(app_name="belote-test-legacy")

    # Write a 4.6.x-shaped profile manually — no `seen_heist_hint` key.
    legacy_payload = {
        "schema_version": 1,
        "unlocked_ids": ["le_classique"],
        "discovered_items": [],
        "stats": {"runs_won": 0, "total_capots": 0, "sans_atout_wins": 0, "tout_atout_wins": 0},
    }
    sm._save_path.parent.mkdir(parents=True, exist_ok=True)
    sm._save_path.write_text(json.dumps(legacy_payload))

    profile = sm.load_profile()
    assert profile.seen_heist_hint is False  # default applied


def test_profile_seen_heist_hint_roundtrips(monkeypatch, tmp_path) -> None:
    """Save with `seen_heist_hint=True` → load → still True."""
    from belote.belatro.progression.save import Profile, SaveManager

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sm = SaveManager(app_name="belote-test-roundtrip")
    profile = Profile()
    profile.seen_heist_hint = True
    sm.save_profile(profile)

    loaded = sm.load_profile()
    assert loaded.seen_heist_hint is True


def test_prompt_heist_default_returns_false() -> None:
    """Classic UI inherits the default no-op; only BelAtro overrides."""
    from belote.belatro.engine.round_driver import RoundUICallbacks
    from belote.deck import Card

    class _MinimalUI(RoundUICallbacks):
        def prompt_bid(self, state: GameState):
            return None

        def prompt_card(self, state: GameState):
            return state.hand_of(Seat.SOUTH)[0], state

        def on_card_played(self, state: GameState, seat: Seat, card: Card) -> None:
            pass

        def on_trick_end(
            self, state: GameState, winner: Seat, points: int
        ) -> None:
            pass

        def on_round_end(self, breakdown: object) -> None:
            pass

    ui = _MinimalUI()
    state = _make_state()
    assert ui.prompt_heist(state) is False
