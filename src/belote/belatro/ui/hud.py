from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from belote.ansi import BOLD, DIM, RESET, gold_fg, green_fg, move, red_fg, visible_len, white_fg
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

        term_w, term_h = get_term_size()
        layout = choose_layout(term_w, term_h)
        run = self.run

        # 3.4.0: joker pip strip on row 1 (above the existing HUD lines), shown
        # in every layout including compact. Cheap — empty inventory still
        # paints the dotted-slot capacity so the player learns the slot count.
        if not state.boss_modifiers.hide_hud:
            render_joker_pip_strip(run, term_w, row=1)
            # Synergy tooltip below the score line; only fires when at least
            # one pair is active. Compact layouts get one line; verbose two.
            tooltip_row = 4 if layout.hud_style == "compact" else 5
            render_synergy_tooltip(list(run.jokers), term_w, row=tooltip_row)

        if layout.hud_style == "compact":
            self._render_compact(acc, state, term_w)
            return

        # Standard / verbose path (current behaviour, with a small mood glyph
        # appended to the row-2 left).
        target_str = str(run.target_score)
        mood = _MOOD_GLYPH.get(run.partner_mood, "○")
        print(
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
        )

        # Row 3: Score (hidden by Le Brouillard boss)
        if not state.boss_modifiers.hide_hud:
            score_str = f"{state._chips} x {state._mult:.1f} = {acc.get_total(state)}"
            score_col = max(2, term_w - len(score_str) - 2)
            print(move(3, score_col) + red_fg() + BOLD + score_str + RESET)

        # Show jokers on row 2 right side as compact list (full names at standard,
        # truncated names at compact widths).
        if run.jokers:
            names = "  ".join(j.name for j in run.jokers)
            print(move(2, max(2, term_w // 2)) + gold_fg() + names[: term_w // 2 - 2] + RESET)
            # 3.0.0: synergy badge — render below the joker line if any pair
            # matches. Cheap O(N) per render; the table is short.
            synergies = detect_synergies(list(run.jokers))
            if synergies:
                badge = f"{gold_fg()}{BOLD}★ SYN×{len(synergies)}{RESET}"
                print(move(4, max(2, term_w // 2)) + badge)

    def _render_compact(self, acc: ScoreAccumulator, state: GameState, term_w: int) -> None:
        """Compact HUD: single-line summary, joker count instead of names.

        Press J for the full joker list (handled by the gameplay loop, not here).
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

        # Compose both halves on row 2
        print(move(2, 2) + left)
        right_col = max(2, term_w - visible_len(joker_label) - 1)
        print(move(2, right_col) + joker_label)

        # Row 3: chips × mult on the right (hidden by Le Brouillard)
        if not state.boss_modifiers.hide_hud:
            score_str = f"{state._chips}×{state._mult:.1f}={acc.get_total(state)}"
            score_col = max(2, term_w - len(score_str) - 2)
            print(move(3, score_col) + red_fg() + BOLD + score_str + RESET)


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


def render_joker_pip_strip(run: BelAtroRun, term_w: int, row: int = 1) -> None:
    """Render a compact one-row strip of joker slots at `row` (default top).

    Layout: `J: [Co][To*][..][..][..]` — 4 chars per slot, leading "J: " label,
    `*` marker on slots involved in an active synergy pair. Empty slots are
    rendered with `··` so the player sees their capacity at a glance.

    No-ops when `term_w < 24` (not enough room for a 5-slot strip).
    """
    if term_w < 24:
        return
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
    strip = "".join(parts)
    # Center is overkill; anchor at col 2 so it doesn't fight the score line
    # on the right of row 2.
    print(move(row, 2) + strip)


def render_synergy_tooltip(jokers: Sequence[object], term_w: int, row: int = 5) -> None:
    """Render one-line synergy descriptions at `row` if any pair is active.

    No-ops when there are no active synergies. Truncates each line to the
    available width so we never wrap.
    """
    pairs = detect_synergies_full(list(jokers))
    if not pairs:
        return
    # Show up to two synergies; further ones are summarised as "+N more".
    max_w = max(20, term_w - 4)
    for i, (_a, _b, desc) in enumerate(pairs[:2]):
        line = f"{green_fg()}♦{RESET} {white_fg()}{desc}{RESET}"
        if visible_len(line) > max_w:
            # crude trim — fall back to plain ASCII to make ansi-stripping
            # unnecessary (we never split mid-escape).
            line = desc[: max_w - 2] + ".."
        print(move(row + i, 2) + line)
    if len(pairs) > 2:
        extra = f"{DIM}+{len(pairs) - 2} more synergies{RESET}"
        print(move(row + 2, 2) + extra)
