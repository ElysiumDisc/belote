from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import TYPE_CHECKING

from belote.ansi import (
    BOLD,
    DIM,
    RESET,
    ansi_center,
    ansi_truncate,
    gold_fg,
    green_fg,
    move,
    red_fg,
    visible_len,
    white_fg,
)
from belote.ui.layout import choose_layout

if TYPE_CHECKING:
    from belote.game import GameState

    from ..core.run_state import BelAtroRun
    from ..core.scoring import ScoreAccumulator


_BLIND_NAMES = ["Small Blind", "Big Blind", "Boss Blind"]

_MOOD_GLYPH = {
    "degraded": "✗",
    "sulking": "·",
    "neutral": "○",
    "eager": "●",
    "elated": "★",
}


# 3.0.0: known joker synergies — when both ids in a pair are present, the
# HUD surfaces a SYN★ badge so the player notices the combo. New combos
# extend this tuple; pairs are order-insensitive (both directions matched).
# Every id here MUST resolve in the joker registry — see
# `validate_synergy_ids()` below; a startup self-check raises on typos.
# 3.4.0: now a 3-tuple with a human-readable description rendered in the
# synergy tooltip when both jokers are active.
_SYNERGY_PAIRS: tuple[tuple[str, str, str], ...] = (
    # Coinche stacking with the Tout-Atout streak ramp
    (
        "coinche_stack",
        "tout_streak",
        "Coinched Tout-Atout wins ramp the streak multiplier",
    ),
    # La Sentinelle's trump-Jack lock plus a contract-level Mult booster
    (
        "la_sentinelle",
        "le_fanatique",
        "Sentinelle locks Jack; Fanatique amplifies contract-suit Mult",
    ),
)


def validate_synergy_ids() -> list[str]:
    """Return the list of synergy IDs that are NOT registered as jokers.

    Called from `register_all_items()` after registration completes. An
    empty result means the registry is consistent. A non-empty result
    means a typo or a removed joker — caller decides whether to fail
    loud (assert) or warn.
    """
    from ..items.registry import registry

    seen: set[str] = set()
    for entry in _SYNERGY_PAIRS:
        seen.add(entry[0])
        seen.add(entry[1])
    return sorted(s for s in seen if s not in registry.jokers)


def detect_synergies(jokers: Sequence[object]) -> list[tuple[str, str]]:
    """Return the (id_a, id_b) pairs that are both present in `jokers`.

    Backward-compatible with pre-3.4.0 2-tuple callers — the description
    field is dropped here. Use `detect_synergies_full()` to keep it.
    """
    ids = {getattr(j, "id", "") for j in jokers}
    found: list[tuple[str, str]] = []
    for a, b, _desc in _SYNERGY_PAIRS:
        if a in ids and b in ids:
            found.append((a, b))
    # Generic catch-all: if the player has 3+ jokers but no specific pair
    # matched, still flag a generic "stack" synergy.
    if not found and len(ids) >= 3:
        found.append(("stack", str(len(ids))))
    return found


def _emit_tally_readout(
    parts: list[str],
    state: GameState,
    term_w: int,
    term_h: int,
) -> None:
    """4.7.0 follow-up: paint the persistent slot-machine tally readout.

    Appends 2 centered rows (bucket + odometer lines from the most recent
    trick's final animation frame) to `parts`. No-op when:
      - `_last_tally_readout is None` (round start or no trick has fired yet)
      - `hide_hud` boss flag is active (Le Brouillard hides the score)
      - the terminal is too short to fit the rows without colliding with
        the upper HUD (matches the `term_h < 6` gate in
        `slot_machine_tally`, which is the symmetric write-side guard)

    The caller has already short-circuited on `is_top_hud_visible()`, so
    `I` press → top HUD hidden → tally readout hidden in one shot.
    """
    from .announce import _last_tally_readout

    if _last_tally_readout is None:
        return
    if state.boss_modifiers.hide_hud:
        return
    if term_h < 6:
        return
    base_row = term_h - len(_last_tally_readout) - 2
    for i, line in enumerate(_last_tally_readout):
        parts.append(move(base_row + i, 1) + ansi_center(line, term_w) + "\n")


def detect_synergies_full(jokers: Sequence[object]) -> list[tuple[str, str, str]]:
    """Like `detect_synergies` but returns the description too.

    The generic 3+-joker stack synergy is NOT included — it has no specific
    description and is purely a HUD nudge for variety.
    """
    ids = {getattr(j, "id", "") for j in jokers}
    return [(a, b, desc) for (a, b, desc) in _SYNERGY_PAIRS if a in ids and b in ids]


class BelAtroHUD:
    """Renders the roguelite HUD elements during gameplay."""

    def __init__(self, run: BelAtroRun) -> None:
        self.run = run

    def render(self, acc: ScoreAccumulator, state: GameState) -> None:
        """Render HUD elements, with verbosity scaled to the current layout."""
        from belote.ui.render import get_term_size

        # 4.6.3: I/V toggles the top HUD off so the classic row-1 bar (Trump:
        # … / Taker: …) isn't covered by the joker pip strip + score line.
        from .announce import is_top_hud_visible

        if not is_top_hud_visible():
            return

        term_w, term_h = get_term_size()
        layout = choose_layout(term_w, term_h)
        run = self.run

        # 3.4.0: joker pip strip on row 1 (above the existing HUD lines), shown
        # in every layout including compact. Cheap — empty inventory still
        # paints the dotted-slot capacity so the player learns the slot count.
        #
        # 4.7.3: the strip + tooltip are BUILT into strings here and embedded
        # in the same write as the rest of the HUD. Pre-4.7.3 each helper
        # did its own write+flush, so the HUD render syscalled 2–3 times
        # instead of once. Compact path mirrors this (see `_render_compact`).
        pip_strip = ""
        synergy_tip = ""
        if not state.boss_modifiers.hide_hud:
            pip_strip = build_joker_pip_strip(run, term_w, row=1)
            tooltip_row = 4 if layout.hud_style == "compact" else 5
            synergy_tip = build_synergy_tooltip(list(run.jokers), term_w, row=tooltip_row)

        if layout.hud_style == "compact":
            self._render_compact(acc, state, term_w, pip_strip, synergy_tip)
            return

        # Standard / verbose path (current behaviour, with a small mood glyph
        # appended to the row-2 left). 3.9.3: collected into a single
        # write+flush so the BelAtro HUD lays down all rows in one syscall.
        target_str = str(run.target_score)
        mood = _MOOD_GLYPH.get(run.partner_mood, "○")
        # 4.7.3: prepend the row-1 pip strip + the row-{4|5} synergy tooltip
        # so the whole HUD ships in one write+flush below.
        parts: list[str] = []
        if pip_strip:
            parts.append(pip_strip)
        parts.append(
            move(2, 2)
            + white_fg()
            + "Ante: "
            + RESET
            + gold_fg()
            + str(run.ante_number)
            + "/8"
            + RESET
            + "   "
            + white_fg()
            + "Blind: "
            + RESET
            + gold_fg()
            + run.current_blind.name
            + RESET
            + "   "
            + white_fg()
            + "Target: "
            + RESET
            + gold_fg()
            + target_str
            + RESET
            + "   "
            + DIM
            + f"Partner: {mood}"
            + RESET
            + "\n"
        )

        # Row 3: Score (hidden by Le Brouillard boss). Also suppressed under
        # La Compétition (`separate_scoring`) because the live running total
        # adds trick points sequentially while the final score takes the
        # per-seat max — the two diverge, so showing a misleading running
        # total during play would confuse the player. 3.9.3.
        if not state.boss_modifiers.hide_hud:
            if state.boss_modifiers.separate_scoring:
                disclaimer = "[Compétition: score par siège — total final caché]"
                col = max(2, term_w - len(disclaimer) - 2)
                parts.append(move(3, col) + DIM + disclaimer + RESET + "\n")
            else:
                # 4.6.2: read live ledger values via the accumulator rather
                # than state._chips/_mult — those are stale between events now
                # (sealed once at round-end via acc.seal_round). Cost: zero
                # replaces per HUD render.
                score_str = (
                    f"{acc.current_chips(state)} x "
                    f"{acc.current_mult(state):.1f} = "
                    f"{acc.get_total(state)}"
                )
                # 4.9.0 / U4: inline most-recent-contributor annotation.
                # `acc._log` entries are shaped "JokerName: +25 chips" /
                # ":x2.5 Mult" / ":+$3". Display only the payload + source
                # so the line stays scannable. Skip if the log is empty.
                contrib_str = ""
                if acc._log:
                    raw = acc._log[-1]
                    if ":" in raw:
                        name_part, payload_part = raw.split(":", 1)
                        contrib_str = f"  ({payload_part.strip()} from {name_part.strip()})"
                full = score_str + contrib_str
                score_col = max(2, term_w - len(full) - 2)
                if contrib_str:
                    parts.append(
                        move(3, score_col)
                        + red_fg() + BOLD + score_str + RESET
                        + DIM + contrib_str + RESET
                        + "\n"
                    )
                else:
                    parts.append(move(3, score_col) + red_fg() + BOLD + score_str + RESET + "\n")

        # Show jokers on row 2 right side as compact list (full names at standard,
        # truncated names at compact widths).
        if run.jokers:
            names = "  ".join(j.name for j in run.jokers)
            parts.append(
                move(2, max(2, term_w // 2))
                + gold_fg() + ansi_truncate(names, term_w // 2 - 2) + RESET + "\n"
            )
            # 3.0.0: synergy badge — render below the joker line if any pair
            # matches. Cheap O(N) per render; the table is short.
            synergies = detect_synergies(list(run.jokers))
            if synergies:
                badge = f"{gold_fg()}{BOLD}★ SYN×{len(synergies)}{RESET}"
                parts.append(move(4, max(2, term_w // 2)) + badge + "\n")

        # 4.7.0 follow-up: persistent slot-machine tally readout. Paints the
        # last trick's odometer + mult line near the bottom of the screen
        # between tricks. Gated by `is_top_hud_visible()` (the caller already
        # short-circuited if False at the top of `render`) so pressing `I`
        # also hides the readout. `hide_hud` boss skip is here too —
        # `slot_machine_tally` already suppresses the animation under
        # Le Brouillard, so `_last_tally_readout` would normally be None,
        # but a tally produced before the boss flag flipped (impossible
        # today but defensive) wouldn't paint either.
        _emit_tally_readout(parts, state, term_w, term_h)

        # 4.7.3: tooltip ships in the same batched write as everything else.
        if synergy_tip:
            parts.append(synergy_tip)

        sys.stdout.write("".join(parts))
        sys.stdout.flush()
        # This write bypasses display(); invalidate the render-diff baseline so
        # the next display() repaints rows the HUD overwrote (4.0.0 convention).
        from belote.ui.render import invalidate_diff
        invalidate_diff()

    def _render_compact(
        self,
        acc: ScoreAccumulator,
        state: GameState,
        term_w: int,
        pip_strip: str = "",
        synergy_tip: str = "",
    ) -> None:
        """Compact HUD: single-line summary, joker count instead of names.

        Press J for the full joker list (handled by the gameplay loop, not here).

        4.7.3: `pip_strip` / `synergy_tip` are pre-built by the caller so the
        compact HUD also ships in a single write+flush.
        """
        run = self.run
        mood = _MOOD_GLYPH.get(run.partner_mood, "○")
        # Row 2: ultra-short summary on the left
        left = (
            f"{white_fg()}A{RESET}{gold_fg()}{run.ante_number}/8{RESET} "
            f"{white_fg()}B{RESET}{gold_fg()}{run.current_blind.name[0]}{RESET} "
            f"{white_fg()}T{RESET}{gold_fg()}{run.target_score}{RESET} "
            f"{DIM}P:{mood}{RESET}"
        )
        # Joker count on the right
        if run.jokers:
            joker_label = f"{gold_fg()}J:{len(run.jokers)}/{run.joker_slots}{RESET} {DIM}[J]{RESET}"
        else:
            joker_label = f"{DIM}J:0/{run.joker_slots}{RESET}"

        # Compose both halves on row 2. 3.9.3: batched into a single
        # write/flush so the compact HUD lays down all rows atomically.
        # 4.7.3: prepend the pip strip so the row-1/row-2 strip + summary
        # ship in the same write.
        right_col = max(2, term_w - visible_len(joker_label) - 1)
        parts: list[str] = []
        if pip_strip:
            parts.append(pip_strip)
        parts.extend([
            move(2, 2) + left + "\n",
            move(2, right_col) + joker_label + "\n",
        ])

        # Row 3: chips × mult on the right (hidden by Le Brouillard, also
        # suppressed under La Compétition since the running total diverges
        # from the per-seat-max final score — 3.9.3).
        if not state.boss_modifiers.hide_hud:
            if state.boss_modifiers.separate_scoring:
                disclaimer = "[Compétition]"
                col = max(2, term_w - len(disclaimer) - 2)
                parts.append(move(3, col) + DIM + disclaimer + RESET + "\n")
            else:
                # 4.6.2: live ledger values via the accumulator (see standard
                # branch for rationale).
                score_str = (
                    f"{acc.current_chips(state)}×"
                    f"{acc.current_mult(state):.1f}="
                    f"{acc.get_total(state)}"
                )
                score_col = max(2, term_w - len(score_str) - 2)
                parts.append(move(3, score_col) + red_fg() + BOLD + score_str + RESET + "\n")

        # 4.7.0 follow-up: persistent slot-machine tally readout, matched to
        # the standard branch (see comment there).
        from belote.ui.render import get_term_size as _gt
        _, term_h = _gt()
        _emit_tally_readout(parts, state, term_w, term_h)

        # 4.7.3: synergy tooltip ships in the same batched write.
        if synergy_tip:
            parts.append(synergy_tip)

        sys.stdout.write("".join(parts))
        sys.stdout.flush()
        # Bypasses display(); invalidate the render-diff baseline (4.0.0 conv).
        from belote.ui.render import invalidate_diff
        invalidate_diff()


# ── 3.4.0: joker pip strip + synergy tooltip ────────────────────────────────

# Edition glyph & colour for the pip strip. Polychrome cycles colours but we
# keep a stable accent so the strip doesn't flicker — the visual interest
# comes from the colour difference between editions, not animation.
_EDITION_GLYPH: dict[str, str] = {
    "none": " ",
    "foil": "F",
    "holo": "H",
    "poly": "P",
    "neg": "N",
}


def _edition_color(ed_value: str) -> str:
    """ANSI prefix for an edition. Falls back to white for NONE."""
    if ed_value == "foil":
        return "\x1b[38;5;51m"   # bright cyan
    if ed_value == "holo":
        return "\x1b[38;5;201m"  # magenta
    if ed_value == "poly":
        return "\x1b[38;5;213m"  # pink-violet (stand-in for rainbow)
    if ed_value == "neg":
        return "\x1b[7m"         # reverse video
    return str(white_fg())


def build_joker_pip_strip(run: BelAtroRun, term_w: int, row: int = 1) -> str:
    """Build the joker pip strip as a string (caller decides when to write).

    Layout: `J: [Co][To*][..][..][..]` — 4 chars per slot, leading "J: " label,
    `*` marker on slots involved in an active synergy pair. Empty slots are
    rendered with `··` so the player sees their capacity at a glance.

    Returns "" when the strip should be suppressed (HUD toggled off, or
    `term_w < 24` — not enough room for a 5-slot strip).
    """
    from .announce import is_top_hud_visible

    if not is_top_hud_visible():
        return ""
    if term_w < 24:
        return ""
    slots = max(1, run.joker_slots)
    jokers = list(run.jokers)
    # Detect which joker ids are in an active synergy so we can mark their pips
    synergetic_ids: set[str] = set()
    for a, b, _desc in detect_synergies_full(jokers):
        synergetic_ids.add(a)
        synergetic_ids.add(b)

    parts: list[str] = [f"{white_fg()}J:{RESET} "]
    for i in range(slots):
        if i < len(jokers):
            j = jokers[i]
            ed_value = getattr(getattr(j, "edition", None), "value", "none")
            ed_color = _edition_color(ed_value)
            shortcode = (getattr(j, "shortcode", "??") or "??")[:2]
            marker = "*" if getattr(j, "id", "") in synergetic_ids else " "
            # Pip cell: `[Xx*]` with edition-coloured content (4 cells wide
            # excluding the gold brackets).
            parts.append(
                f"{gold_fg()}[{RESET}"
                f"{ed_color}{shortcode}{marker}{RESET}"
                f"{gold_fg()}]{RESET}"
            )
        else:
            parts.append(f"{DIM}[··]{RESET}")
    # Center is overkill; anchor at col 2 so it doesn't fight the score line
    # on the right of row 2.
    strip: str = move(row, 2) + "".join(parts) + "\n"
    return strip


def render_joker_pip_strip(run: BelAtroRun, term_w: int, row: int = 1) -> None:
    """Standalone writer for callers/tests that paint the pip strip directly.

    BelAtroHUD's main render path embeds `build_joker_pip_strip` output in
    its single batched write (4.7.3) — call this only when there's no
    surrounding `parts` list to compose into.
    """
    strip = build_joker_pip_strip(run, term_w, row=row)
    if not strip:
        return
    sys.stdout.write(strip)
    sys.stdout.flush()
    from belote.ui.render import invalidate_diff
    invalidate_diff()


def build_synergy_tooltip(jokers: Sequence[object], term_w: int, row: int = 5) -> str:
    """Build synergy tooltip lines as a single string (caller decides when to write).

    Returns "" when there are no active synergies, the HUD is hidden, or the
    tooltip should otherwise be suppressed.
    """
    from .announce import is_top_hud_visible

    if not is_top_hud_visible():
        return ""
    pairs = detect_synergies_full(list(jokers))
    if not pairs:
        return ""
    # Show up to two synergies; further ones are summarised as "+N more".
    max_w = max(20, term_w - 4)
    out: list[str] = []
    for i, (_a, _b, desc) in enumerate(pairs[:2]):
        line = f"{green_fg()}♦{RESET} {white_fg()}{desc}{RESET}"
        if visible_len(line) > max_w:
            # Cell-aware trim that never splits a wide glyph or an escape.
            line = ansi_truncate(desc, max_w - 2) + ".."
        out.append(move(row + i, 2) + line + "\n")
    if len(pairs) > 2:
        extra = f"{DIM}+{len(pairs) - 2} more synergies{RESET}"
        out.append(move(row + 2, 2) + extra + "\n")
    return "".join(out)


def render_synergy_tooltip(jokers: Sequence[object], term_w: int, row: int = 5) -> None:
    """Standalone writer for callers/tests that paint the tooltip directly.

    BelAtroHUD's main render path embeds `build_synergy_tooltip` output in
    its single batched write (4.7.3); use this only for direct callers.
    """
    out = build_synergy_tooltip(jokers, term_w, row=row)
    if not out:
        return
    sys.stdout.write(out)
    sys.stdout.flush()
    from belote.ui.render import invalidate_diff
    invalidate_diff()
