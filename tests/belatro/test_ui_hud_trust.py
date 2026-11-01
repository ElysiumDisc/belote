"""BelAtro HUD (verbose + compact layouts) and the partner trust bar,
rendered into a fake terminal and asserted on visible text."""

from __future__ import annotations

from dataclasses import replace

import pytest

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.core.scoring import ScoreAccumulator
from belote.belatro.items.base import Edition
from belote.belatro.items.registry import register_all_items, registry
from belote.belatro.partner.trust import TrustTrack
from belote.belatro.ui import announce, hud
from belote.belatro.ui.hud import BelAtroHUD
from belote.belatro.ui.trust_bar import TrustBar, _bar_color, _void_label
from belote.deck import CARD_SUITS, Card, Rank, Suit
from belote.game import GameState, Phase, new_game
from belote.ui import anim
from tests.harness import TUI


@pytest.fixture
def run() -> BelAtroRun:
    register_all_items()
    return BelAtroRun(seed=1)


def _acc(state: GameState) -> ScoreAccumulator:
    acc = ScoreAccumulator()
    acc.trigger_round_start(state)
    return acc


def _variants(state: GameState, **kw: bool) -> GameState:
    return replace(state, variants=replace(state.variants, **kw))


def _synergy_jokers() -> list[object]:
    return [
        registry.jokers[i]()
        for i in ("coinche_stack", "tout_streak", "la_sentinelle", "le_fanatique")
    ]


# ── verbose (standard) HUD ──────────────────────────────────────────────────


def test_verbose_hud_shows_ante_blind_target_score_and_jokers(tui: TUI, run: BelAtroRun) -> None:
    tui.resize(140, 50)  # ≥120x48 → verbose layout
    jokers = _synergy_jokers()
    jokers[0].edition = Edition.HOLO  # type: ignore[attr-defined]
    run.jokers = jokers  # type: ignore[assignment]
    run.joker_slots = 5
    state = new_game()
    acc = _acc(state)
    acc._log.append("La Sentinelle: +25 chips")
    BelAtroHUD(run).render(acc, state)
    text = tui.text
    assert f"Ante: {run.ante_number}/8" in text
    assert f"Blind: {run.current_blind.name}" in text
    assert f"Target: {run.target_score}" in text
    assert "Partner: ○" in text
    assert f"= {acc.get_total(state)}" in text
    assert "(+25 chips from La Sentinelle)" in text  # latest contributor
    assert "★ SYN×2" in text
    assert "Coinched Tout-Atout wins ramp" in text  # synergy tooltip
    assert "J:" in text and "*" in text  # pip strip marks synergetic jokers
    assert "\x1b[38;5;201m" in tui.screen.raw  # holo edition colour


def test_verbose_hud_without_log_or_jokers(tui: TUI, run: BelAtroRun) -> None:
    tui.resize(140, 50)
    state = new_game()
    BelAtroHUD(run).render(_acc(state), state)
    text = tui.text
    assert " from " not in text
    assert "SYN" not in text
    assert "[··]" in text  # empty joker slots


def test_verbose_hud_competition_disclaimer(tui: TUI, run: BelAtroRun) -> None:
    tui.resize(140, 50)
    state = _variants(new_game(), separate_scoring=True)
    BelAtroHUD(run).render(_acc(state), state)
    assert "Compétition: score par siège" in tui.text


def test_verbose_hud_brouillard_hides_score_strip_and_tally(tui: TUI, run: BelAtroRun) -> None:
    tui.resize(140, 50)
    announce._last_tally_readout = ["TALLY-LINE-1", "TALLY-LINE-2"]  # type: ignore[attr-defined]
    state = _variants(new_game(), hide_hud=True)
    acc = _acc(state)
    BelAtroHUD(run).render(acc, state)
    text = tui.text
    assert "Ante:" in text
    assert " x " not in text  # no chips × mult line
    assert "J:" not in text
    assert "TALLY-LINE" not in text


def test_verbose_hud_paints_persistent_tally_readout(tui: TUI, run: BelAtroRun) -> None:
    tui.resize(140, 50)
    announce._last_tally_readout = ["TALLY-LINE-1", "TALLY-LINE-2"]  # type: ignore[attr-defined]
    state = new_game()
    BelAtroHUD(run).render(_acc(state), state)
    assert "TALLY-LINE-1" in tui.text and "TALLY-LINE-2" in tui.text
    assert "\x1b[46;1H" in tui.screen.raw  # rows term_h-4 .. term_h-3


def test_hud_hidden_when_top_hud_toggled_off(tui: TUI, run: BelAtroRun) -> None:
    announce.toggle_top_hud()
    state = new_game()
    BelAtroHUD(run).render(_acc(state), state)
    assert tui.screen.raw == ""


# ── compact HUD ─────────────────────────────────────────────────────────────


def test_compact_hud_summary_and_joker_count(tui: TUI, run: BelAtroRun) -> None:
    tui.resize(100, 34)
    run.jokers = _synergy_jokers()[:2]  # type: ignore[assignment]
    state = new_game()
    acc = _acc(state)
    BelAtroHUD(run).render(acc, state)
    text = tui.text
    assert f"A{run.ante_number}/8" in text
    assert f"T{run.target_score}" in text
    assert f"J:2/{run.joker_slots} [J]" in text
    assert f"={acc.get_total(state)}" in text


def test_compact_hud_empty_inventory_competition_and_tally(tui: TUI, run: BelAtroRun) -> None:
    tui.resize(100, 34)
    announce._last_tally_readout = ["COMPACT-TALLY"]  # type: ignore[attr-defined]
    state = _variants(new_game(), separate_scoring=True)
    BelAtroHUD(run).render(_acc(state), state)
    text = tui.text
    assert f"J:0/{run.joker_slots}" in text
    assert "[Compétition]" in text
    assert "COMPACT-TALLY" in text


def test_compact_hud_brouillard(tui: TUI, run: BelAtroRun) -> None:
    tui.resize(100, 34)
    state = _variants(new_game(), hide_hud=True)
    BelAtroHUD(run).render(_acc(state), state)
    assert "×" not in tui.text and "Compétition" not in tui.text


def test_tally_readout_skipped_on_tiny_terminal(run: BelAtroRun) -> None:
    announce._last_tally_readout = ["X"]  # type: ignore[attr-defined]
    try:
        parts: list[str] = []
        hud._emit_tally_readout(parts, new_game(), 80, 5)
        assert parts == []
    finally:
        announce.reset_tally_state()


# ── pip strip / tooltip helpers ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("edition", "sgr"),
    [
        (Edition.FOIL, "\x1b[38;5;51m"),
        (Edition.HOLO, "\x1b[38;5;201m"),
        (Edition.POLYCHROME, "\x1b[38;5;213m"),
        (Edition.NEGATIVE, "\x1b[7m"),
    ],
)
def test_pip_strip_edition_colours(run: BelAtroRun, edition: Edition, sgr: str) -> None:
    j = _synergy_jokers()[0]
    j.edition = edition  # type: ignore[attr-defined]
    run.jokers = [j]  # type: ignore[assignment]
    assert sgr in hud.build_joker_pip_strip(run, 80)


def test_pip_strip_suppressed_on_narrow_terminal(run: BelAtroRun) -> None:
    assert hud.build_joker_pip_strip(run, 20) == ""


def test_standalone_strip_and_tooltip_writers(tui: TUI, run: BelAtroRun) -> None:
    jokers = _synergy_jokers()
    run.jokers = jokers  # type: ignore[assignment]
    hud.render_joker_pip_strip(run, 80)
    hud.render_synergy_tooltip(jokers, 80)
    text = tui.text
    assert "J:" in text
    assert "Sentinelle locks Jack" in text
    tui.screen.clear()
    hud.render_synergy_tooltip([], 80)  # no synergy → no write
    hud.render_joker_pip_strip(run, 10)  # too narrow → no write
    assert tui.screen.raw == ""


def test_synergy_tooltip_truncates_and_summarises_overflow(monkeypatch: pytest.MonkeyPatch) -> None:
    pairs = (
        ("a", "b", "first synergy with a really quite long description indeed"),
        ("c", "d", "second synergy"),
        ("e", "f", "third synergy"),
    )
    monkeypatch.setattr(hud, "_SYNERGY_PAIRS", pairs)
    jokers = [type("J", (), {"id": i})() for i in "abcdef"]
    out = hud.build_synergy_tooltip(jokers, term_w=30)
    assert "+1 more synergies" in out
    assert ".." in out  # first description trimmed to the width


# ── trust bar ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("value", "glyph"), [(0, "✗"), (3, "♡"), (5, "♥"), (7, "♦"), (10, "★")])
def test_trust_bar_glyph_and_fill(tui: TUI, value: int, glyph: str) -> None:
    TrustBar(TrustTrack(value=value)).render()
    text = tui.text
    assert f"Trust: {glyph} [" in text
    assert "█" * value + "░" * (10 - value) in text


def test_trust_bar_colour_ramp() -> None:
    colours = [_bar_color(v) for v in (1, 4, 6, 9)]
    assert len(set(colours)) == 4
    assert colours[1] == "\x1b[38;5;208m"


def test_trust_bar_degraded_status(tui: TUI) -> None:
    TrustBar(TrustTrack(value=1)).render()
    assert "⚠ Degraded" in tui.text


def _playing_with_north(cards: tuple[Card, ...]) -> GameState:
    s = new_game()
    return replace(s, phase=Phase.PLAYING, hands=((), (), cards, ()))


def test_trust_bar_void_info_lists_norths_empty_suits(tui: TUI) -> None:
    state = _playing_with_north((Card(Suit.HEARTS, Rank.ACE), Card(Suit.CLUBS, Rank.SEVEN)))
    TrustBar(TrustTrack(value=5)).render(state)
    voids = "".join(s.symbol for s in CARD_SUITS if s not in (Suit.HEARTS, Suit.CLUBS))
    assert f"✦ Void: {voids}" in tui.text


def test_trust_bar_void_info_hidden_under_boss(tui: TUI) -> None:
    state = _playing_with_north((Card(Suit.HEARTS, Rank.ACE),))
    TrustBar(TrustTrack(value=5), show_voids=False).render(state)
    assert "Void" not in tui.text


def test_void_label_fallbacks() -> None:
    assert _void_label(None) == "Void Info"
    assert _void_label(new_game()) == "Void Info"  # not playing
    assert _void_label(_playing_with_north(())) == "Void Info"  # empty hand
    full = tuple(Card(s, Rank.ACE) for s in (Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS))
    assert _void_label(_playing_with_north(full)) == "Void: —"


def test_trust_bar_animate_change_ticks_and_restores_value(tui: TUI) -> None:
    anim.set_animations_enabled(True)
    track = TrustTrack(value=8)
    bar = TrustBar(track)
    r = tui.reader(idle_timeouts=True)
    bar.animate_change(3, r)
    assert track.value == 8  # true value restored after the frames
    assert r.timeouts  # frames polled the (real KeyReader-typed) reader
    assert tui.screen.count("Trust:") >= 3
    assert "█" * 8 + "░" * 2 in tui.text.split("Trust:")[-1]


def test_trust_bar_animate_change_skippable(tui: TUI) -> None:
    anim.set_animations_enabled(True)
    track = TrustTrack(value=9)
    r = tui.reader("space")
    TrustBar(track).animate_change(2, r)
    assert track.value == 9
    assert r.exhausted


def test_trust_bar_animate_change_noops(tui: TUI) -> None:
    track = TrustTrack(value=6)
    # Animations off → a single final render.
    TrustBar(track).animate_change(2)
    assert tui.screen.count("Trust:") == 1
    tui.screen.clear()
    anim.set_animations_enabled(True)
    TrustBar(track).animate_change(6)  # unchanged value
    assert tui.screen.raw == ""
    announce.toggle_top_hud()
    TrustBar(track).animate_change(1)  # hidden HUD
    assert tui.screen.raw == ""
