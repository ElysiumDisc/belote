"""Layout system tests: preset selection, card sizing, HUD verbosity, vertical
centering, and rejection of too-small terminals."""

from __future__ import annotations

from belote.ansi import visible_len
from belote.deck import Card, Rank, Suit
from belote.game import BossModifiers, GameState, Seat, new_game
from belote.ui.layout import (
    ALL_LAYOUTS,
    COMPACT,
    MIN_COLS,
    MIN_ROWS,
    SPACIOUS,
    STANDARD,
    choose_layout,
    fits_minimum,
)

# ── choose_layout boundaries ────────────────────────────────────────────────


def test_compact_picked_at_minimum() -> None:
    assert choose_layout(80, 32) is COMPACT
    assert choose_layout(95, 37) is COMPACT  # one row/col below standard


def test_standard_picked_at_its_threshold() -> None:
    assert choose_layout(96, 38) is STANDARD
    assert choose_layout(119, 47) is STANDARD


def test_spacious_picked_when_room() -> None:
    assert choose_layout(120, 48) is SPACIOUS
    assert choose_layout(200, 80) is SPACIOUS


def test_below_minimum_falls_back_to_compact() -> None:
    # We don't reject inside choose_layout — caller does that. We just
    # always return *something* so render code never hits a None layout.
    assert choose_layout(40, 20) is COMPACT


def test_fits_minimum() -> None:
    assert fits_minimum(80, 32) is True
    assert fits_minimum(79, 32) is False
    assert fits_minimum(80, 31) is False
    assert fits_minimum(200, 60) is True


def test_min_constants_match_compact_preset() -> None:
    assert COMPACT.min_cols == MIN_COLS
    assert COMPACT.min_rows == MIN_ROWS


# ── Preset shape sanity ─────────────────────────────────────────────────────


def test_all_presets_have_increasing_dimensions() -> None:
    # SPACIOUS > STANDARD > COMPACT on every relevant axis.
    cw_chain = [p.card_w for p in (COMPACT, STANDARD, SPACIOUS)]
    ch_chain = [p.card_h for p in (COMPACT, STANDARD, SPACIOUS)]
    cols_chain = [p.min_cols for p in (COMPACT, STANDARD, SPACIOUS)]
    rows_chain = [p.min_rows for p in (COMPACT, STANDARD, SPACIOUS)]
    for chain in (cw_chain, ch_chain, cols_chain, rows_chain):
        assert chain == sorted(chain), f"Chain not strictly increasing: {chain}"


def test_all_layouts_lookup_is_largest_first() -> None:
    # Largest first → choose_layout iterates and picks the first that fits.
    assert ALL_LAYOUTS[0] is SPACIOUS
    assert ALL_LAYOUTS[-1] is COMPACT


def test_compact_layout_disables_last_trick_sidebar() -> None:
    assert COMPACT.show_last_trick_sidebar is False
    assert STANDARD.show_last_trick_sidebar is True
    assert SPACIOUS.show_last_trick_sidebar is True


def test_hud_styles_per_tier() -> None:
    # Compact + standard both use the abbreviated HUD that fits in 80 cols.
    # Only spacious (≥120 cols) gets the full verbose form with help hints + theme.
    assert COMPACT.hud_style == "compact"
    assert STANDARD.hud_style == "compact"
    assert SPACIOUS.hud_style == "verbose"


# ── Card rendering under different layouts ─────────────────────────────────


def test_card_face_height_matches_layout_card_h() -> None:
    from belote.ui.render import _get_card_face

    card = Card(Suit.HEARTS, Rank.JACK)
    for preset in (COMPACT, STANDARD, SPACIOUS):
        face = _get_card_face(card, layout=preset)
        assert len(face) == preset.card_h, (
            f"{preset.name}: expected {preset.card_h} rows, got {len(face)}"
        )


def test_card_face_visible_width_matches_layout_card_w() -> None:
    from belote.ui.render import _get_card_face

    card = Card(Suit.SPADES, Rank.TEN)  # "10" is the widest rank string
    for preset in (COMPACT, STANDARD, SPACIOUS):
        face = _get_card_face(card, layout=preset)
        for line in face:
            assert visible_len(line) == preset.card_w, (
                f"{preset.name}: line {line!r} has visible width "
                f"{visible_len(line)}, expected {preset.card_w}"
            )


def test_card_face_cache_separates_layouts() -> None:
    """The same card requested at different sizes must not collide in the cache."""
    from belote.ui.render import _get_card_face

    card = Card(Suit.CLUBS, Rank.ACE)
    compact_face = _get_card_face(card, layout=COMPACT)
    standard_face = _get_card_face(card, layout=STANDARD)
    spacious_face = _get_card_face(card, layout=SPACIOUS)
    assert len(compact_face) != len(standard_face)
    assert len(standard_face) != len(spacious_face)


# ── HUD verbosity ───────────────────────────────────────────────────────────


def _hud_state() -> GameState:
    return new_game()


def test_hud_compact_omits_help_hints_and_theme() -> None:
    from belote.ui.render import _build_hud

    state = _hud_state()
    bar_compact = _build_hud(state, term_w=80, layout=COMPACT)
    bar_spacious = _build_hud(state, term_w=140, layout=SPACIOUS)
    # Compact bar shouldn't carry the help-hint substring or the "Theme: " label.
    assert "[H]Hist" not in bar_compact
    assert "Theme:" not in bar_compact
    # Spacious does carry both — there's room.
    assert "[H]Hist" in bar_spacious
    assert "Theme:" in bar_spacious


def test_hud_compact_fits_in_80_cols() -> None:
    from belote.ui.render import _build_hud

    bar = _build_hud(_hud_state(), term_w=80, layout=COMPACT)
    assert visible_len(bar) <= 80, (
        f"Compact HUD overflows 80 cols: width={visible_len(bar)}"
    )


def test_hud_handles_hide_hud_boss_under_compact() -> None:
    from dataclasses import replace

    from belote.ui.render import _build_hud

    state = new_game()
    state = replace(state, boss_modifiers=BossModifiers(hide_hud=True))
    bar = _build_hud(state, term_w=80, layout=COMPACT)
    assert "HIDDEN BY BOSS" in bar
    assert visible_len(bar) <= 80


# ── Vertical centering ─────────────────────────────────────────────────────


def test_render_pads_vertically_when_terminal_taller_than_content(monkeypatch) -> None:
    """When the terminal is much taller than the content, render() should add
    blank padding rows above the first line so the game centres vertically.
    """
    import sys

    # `belote.ui.render` resolves to the *function* via __init__ re-export, so
    # grab the module directly out of sys.modules.
    render_mod = sys.modules["belote.ui.render"]

    monkeypatch.setattr(render_mod, "get_term_size", lambda: (200, 60))

    state = new_game()
    out = render_mod.render(state)
    body = out.split("\r\n")
    first_visible = next(
        (i for i, ln in enumerate(body) if visible_len(ln) > 0), len(body)
    )
    assert first_visible >= 5, (
        f"Expected vertical padding above content, got first visible at row {first_visible}"
    )


# ── Trick mat dimensions ───────────────────────────────────────────────────


def test_trick_mat_height_scales_with_layout() -> None:
    from belote.ui.render import _render_trick_mat

    seat_map = {Seat.NORTH: Card(Suit.HEARTS, Rank.JACK)}
    for preset in (COMPACT, STANDARD, SPACIOUS):
        rows = _render_trick_mat(seat_map, center_w=preset.min_cols // 2, layout=preset)
        expected_rows = 6 + 3 * preset.card_h
        assert len(rows) == expected_rows, (
            f"{preset.name}: expected {expected_rows} mat rows, got {len(rows)}"
        )


def test_trick_row_offsets_consistent_with_mat() -> None:
    from belote.ui.render import _trick_row_offsets

    for preset in (COMPACT, STANDARD, SPACIOUS):
        offsets = _trick_row_offsets(preset)
        # North card top should always be 2 rows in (top pad + N label).
        assert offsets[Seat.NORTH] == 2
        # West/East are below North card + 1 gap.
        assert offsets[Seat.WEST] == 2 + preset.card_h + 1
        assert offsets[Seat.EAST] == offsets[Seat.WEST]
        # South is below W/E card + 1 gap.
        assert offsets[Seat.SOUTH] == offsets[Seat.WEST] + preset.card_h + 1


# ── KeyReader factory regression ───────────────────────────────────────────


def test_keyreader_factory_returns_initialised_concrete_reader(monkeypatch) -> None:
    """`KeyReader()` must return a concrete reader with __init__ already run.

    Regression: an earlier refactor made `__new__` return a bare instance via
    `_UnixKeyReader.__new__(cls)` which skipped `__init__`, so attributes like
    `_stdin_fd` and `_restored` weren't set and `__enter__` crashed at runtime.
    """
    import os as _os
    import sys as _sys

    # pytest's captured stdin has no fileno(); patch it for this test only.
    if _os.name != "nt":
        class _FakeStdin:
            def fileno(self) -> int:
                return 0

        monkeypatch.setattr(_sys, "stdin", _FakeStdin())

    from belote.input import KeyReader

    reader = KeyReader()
    # Both platform readers must expose `_restored` (used by main.py's guard)
    # plus the platform-specific state needed for context entry.
    assert hasattr(reader, "_restored")
    assert reader._restored is False
    # On POSIX the unix reader must carry the stdin fd, used in __enter__.
    if _os.name != "nt":
        assert hasattr(reader, "_stdin_fd")
