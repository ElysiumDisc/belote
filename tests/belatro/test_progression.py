from unittest.mock import MagicMock

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.engine.event_bus import RoundEndEvent
from belote.belatro.items.planets import Saturn
from belote.belatro.progression.save import Profile
from belote.belatro.progression.unlocks import UnlockTracker
from belote.belatro.run.ante import calculate_target
from belote.deck import Suit
from belote.game import Seat


def test_planet_level_up():
    """39. Planet level-up - Verify planet level increments and reward applies."""
    run = BelAtroRun()
    planet = Saturn()
    reward = planet.level_up_reward()
    run.contract_levels[planet.contract_id] = reward
    # Saturn level 1 reward for spades is +8 chips
    assert run.contract_levels["spades"] == {"add_chips": 8}

def test_ante_progression():
    """40. Ante progression - Verify all 8 antes cycle correctly."""
    run = BelAtroRun()
    # Ante 1: Small -> Big -> Boss
    assert run.ante_number == 1
    assert run.blind_index == 0

    run.advance_blind() # -> Big
    assert run.blind_index == 1

    run.advance_blind() # -> Boss
    assert run.blind_index == 2

    run.advance_blind() # -> Ante 2, Small
    assert run.ante_number == 2
    assert run.blind_index == 0

    # Verify final progression to win
    run.ante_number = 8
    run.blind_index = 2
    run.advance_blind()
    assert run.run_won is True


def test_endless_target_scales_2_2x_per_offset():
    """Each completed ante past 8 multiplies the target by 2.2 (ante.py:26).

    Compound int() truncation makes ratios slightly inexact; use the formula
    (which int()s once at the end) as the source of truth.
    """
    base = 100 * (1.5 ** (8 - 1)) * 2.0  # ante 8, boss blind, offset 0
    assert calculate_target(8, 2, 0) == int(base)
    assert calculate_target(8, 2, 1) == int(base * 2.2)
    assert calculate_target(8, 2, 2) == int(base * 2.2 * 2.2)
    # Ratio check (loose, robust to int truncation)
    ratio = calculate_target(8, 2, 1) / calculate_target(8, 2, 0)
    assert abs(ratio - 2.2) < 0.001


def test_advance_blind_increments_endless_offset_after_ante_8():
    """In endless mode, finishing ante 8 boss restarts at ante 8 small with offset+1."""
    run = BelAtroRun()
    run.ante_number = 8
    run.blind_index = 2
    run.endless = True
    run.advance_blind()
    assert run.endless_ante_offset == 1
    assert run.blind_index == 0
    assert run.ante_number == 8
    assert run.run_won is False


def test_advance_blind_sets_run_won_when_not_endless():
    """Without endless, finishing ante 8 boss flips run_won."""
    run = BelAtroRun()
    run.ante_number = 8
    run.blind_index = 2
    run.endless = False
    run.advance_blind()
    assert run.run_won is True
    assert run.endless_ante_offset == 0


def test_current_blind_uses_endless_ante_when_offset_positive():
    """current_blind dispatches to endless_ante() once the offset is non-zero."""
    run = BelAtroRun()
    run.ante_number = 8
    run.blind_index = 1
    run.endless = True
    run.endless_ante_offset = 2
    blind = run.current_blind
    assert blind.target == calculate_target(8, 1, 2)


def test_current_blind_uses_static_table_when_not_endless():
    """The static ANTE_TABLE is used while offset is 0, even with endless=True."""
    run = BelAtroRun()
    run.ante_number = 3
    run.blind_index = 0
    run.endless = True
    run.endless_ante_offset = 0
    blind = run.current_blind
    assert blind.target == calculate_target(3, 0, 0)


# ── 3.0.0: Tout Atout win unlocks le_fanatique ─────────────────────────────


def _ta_win_event(taker: Seat = Seat.SOUTH, is_failed: bool = False) -> RoundEndEvent:
    bd = MagicMock()
    bd.is_failed = is_failed
    return RoundEndEvent(
        breakdown=bd,
        taker_seat=taker,
        trump=Suit.TOUT_ATOUT,
        capot=False,
        contract="tout_atout",
    )


def test_tout_atout_win_increments_counter_and_unlocks_le_fanatique() -> None:
    """A successful TA round taken by South must increment tout_atout_wins
    and unlock le_fanatique on the first occurrence."""
    profile = Profile()
    save = MagicMock()
    tracker = UnlockTracker(profile, save)

    assert profile.stats["tout_atout_wins"] == 0
    assert not profile.is_unlocked("le_fanatique")

    tracker.on_event(_ta_win_event())

    assert profile.stats["tout_atout_wins"] == 1
    assert profile.is_unlocked("le_fanatique")
    save.save_profile.assert_called()


def test_tout_atout_failed_round_does_not_unlock() -> None:
    """A FAILED TA round must NOT increment the counter or trigger the unlock."""
    profile = Profile()
    save = MagicMock()
    tracker = UnlockTracker(profile, save)

    tracker.on_event(_ta_win_event(is_failed=True))

    assert profile.stats["tout_atout_wins"] == 0
    assert not profile.is_unlocked("le_fanatique")


def test_tout_atout_win_by_opponents_does_not_unlock() -> None:
    """If East/West takes TA and wins, NS doesn't get the unlock."""
    profile = Profile()
    save = MagicMock()
    tracker = UnlockTracker(profile, save)

    tracker.on_event(_ta_win_event(taker=Seat.EAST))

    assert profile.stats["tout_atout_wins"] == 0
    assert not profile.is_unlocked("le_fanatique")


# ── 3.9.3 Phase 8: Quinte Royale unlock + save corruption recovery ─────────


def test_quinte_declaration_unlocks_quinte_royale() -> None:
    """3.9.3 Phase 8 regression: Quinte Royale was marked is_unlockable but
    had no path to unlock — pre-3.9.3 the joker was unreachable. NS
    announcing a Quinte (sequence ≥ 100 pts) now grants the unlock."""
    from belote.belatro.engine.event_bus import DeclarationScoredEvent

    profile = Profile()
    save = MagicMock()
    tracker = UnlockTracker(profile, save)
    assert not profile.is_unlocked("quinte_royale")

    tracker.on_event(
        DeclarationScoredEvent(
            seat=Seat.SOUTH, declaration_type="sequence", points=100
        )
    )
    assert profile.is_unlocked("quinte_royale")
    save.save_profile.assert_called()
    assert any("Quinte Royale" in msg for msg in tracker.pending_announcements)


def test_quinte_short_sequence_does_not_unlock() -> None:
    """A Tierce (20 pts) or Quarte (50 pts) must NOT unlock Quinte Royale —
    the gate is strictly ≥ 100 points (Quinte threshold)."""
    from belote.belatro.engine.event_bus import DeclarationScoredEvent

    profile = Profile()
    tracker = UnlockTracker(profile, MagicMock())
    tracker.on_event(
        DeclarationScoredEvent(seat=Seat.SOUTH, declaration_type="sequence", points=50)
    )
    assert not profile.is_unlocked("quinte_royale")


def test_quinte_by_opponents_does_not_unlock() -> None:
    """Opponent (EW) Quinte must NOT unlock NS's Quinte Royale."""
    from belote.belatro.engine.event_bus import DeclarationScoredEvent

    profile = Profile()
    tracker = UnlockTracker(profile, MagicMock())
    tracker.on_event(
        DeclarationScoredEvent(seat=Seat.EAST, declaration_type="sequence", points=100)
    )
    assert not profile.is_unlocked("quinte_royale")


def test_save_corruption_recovery_returns_fresh_profile(tmp_path) -> None:
    """A corrupted profile.json must not crash the menu — SaveManager.load
    catches JSONDecodeError and returns a fresh Profile so the user can
    keep playing (losing only the corrupted save)."""
    from belote.belatro.progression.save import SaveManager

    # Point SaveManager at a tmpdir, write garbage to the profile file.
    mgr = SaveManager()
    mgr._save_path = tmp_path / "profile.json"
    mgr._save_path.write_text("{not valid json at all", encoding="utf-8")

    profile = mgr.load_profile()
    # Fresh defaults — starter unlocks restored.
    assert "le_classique" in profile.unlocked_ids
    assert profile.stats["runs_won"] == 0


def test_save_missing_file_returns_fresh_profile(tmp_path) -> None:
    from belote.belatro.progression.save import SaveManager

    mgr = SaveManager()
    mgr._save_path = tmp_path / "nonexistent.json"
    profile = mgr.load_profile()
    assert "le_classique" in profile.unlocked_ids


def test_save_atomic_write_creates_no_orphan_tmpfile(tmp_path) -> None:
    """Atomic write via NamedTemporaryFile + os.replace must leave the
    target directory containing exactly one file (the final profile.json)
    after a successful save — no orphan .tmp leftover."""
    from belote.belatro.progression.save import Profile, SaveManager

    mgr = SaveManager()
    mgr._save_path = tmp_path / "profile.json"
    mgr.save_profile(Profile())
    assert mgr._save_path.exists()
    # No orphan tmp file from the NamedTemporaryFile dance.
    tmp_files = [p for p in tmp_path.iterdir() if p.name.startswith(".profile-")]
    assert tmp_files == [], f"orphan tmpfile(s) left behind: {tmp_files}"
