# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.9.4] - 2026-05-26

Audit + maintenance pass. Three parallel Explore agents reviewed game-logic
correctness (classic Belote + BelAtro), performance hot paths, and
end-to-end feature-implementation coverage across every joker / deck / voucher /
planet / tarot / boss. **One real bug** surfaced (AI surcoinche dead code,
fixed below); performance is already well-optimised — the 4.6.x / 4.7.x
audit passes that drove the per-round baseline from 4.21ms → 3.67ms left
no quick wins on the table; feature wiring is complete with **zero
broken wirings and zero doc-drift** on item counts.

### Fixed

- **AI surcoinche dead code** (`src/belote/ai.py::decide_coinche`). The
  same method serves both initial coinche (defenders respond to the
  taker's bid) and surcoinche (taker team redoubles after a coinche),
  but the early-return guard `if team_of(self.seat) ==
  team_of(state.taker): return False` fired in both phases — so every
  taker-team AI polled by `gameflow.py:217` returned False, and AI
  could never reach the ×4 surcoinche multiplier. The method is now
  polymorphic on `state.coinche_level`: level 0 → defenders only,
  level 1 → taker team only, level 2+ → nobody redoubles further.
  Existing `test_taker_team_member_never_coinches_own_bid` rewired to
  explicitly pin the level-0 path; three new tests in
  `tests/test_g1_coinche_classic.py` pin the level-1 taker surcoinche,
  the level-1 defender no-op, and the level-2 universal no-op.

### Internal

- **CHANGELOG condensed through 4.5.x.** The 4.0.0 → 4.5.1 verbose
  entries are collapsed into a new `## Pre-4.6.0 Releases — Condensed
  History` section, mirroring the existing pre-4.0.0 block. Six bullets
  (one per release), -~190 lines, no historical info lost — full
  implementation context remains in `git log` and the per-release plan
  files referenced in the original entries.
- **`DEVELOPMENT.md` gains a "Performance measurement" runbook**: the
  `tests/test_perf_regression.py` guard's role, the
  `scripts/benchmark.py` re-baseline path, and a pointer to the two
  canonical hot paths (`render()`, `_calculate_legal_cards_impl`) for
  live profiling. So the next perf sweep starts with a known recipe
  instead of guesswork.
- **Doc-accuracy sweep.** README test count: 1066 → 1069 (two call
  sites updated); README version bump 4.9.3 → 4.9.4 in the same
  paragraph. Feature counts (42 jokers / 12 tarots / 8 planets / 12
  vouchers / 12 decks / 21 bosses) re-verified against the registry —
  unchanged.
- **Verified-OK (do not re-litigate)**: zero-rank boss flags applied at
  all three sites (`_calculate_base_points`, `game.py::play_card` HUD
  running total, `ai.py::card_points_with_modifiers`); `coinche_level`
  reset between rounds; declaration tie-break order; AIMemory cache
  invalidation on undo and new round; SA belote assertion; overlay
  `invalidate_diff()` discipline; the three 4.9.0 pinned-feature tests
  (`test_g1_coinche_classic`, `test_g2_ai_signals`,
  `test_render_hand_lift`) match their code-under-test exactly; no
  silent `except Exception: pass` beyond three intentional containment
  sites (input.py UTF-8 decode, replay.py legacy state, event_bus
  joker isolation); no `assert` reachable from user input. Performance:
  RoundLedger transactional snapshot, register_all_items module-walk
  guard, run-history I/O batching, AIMemory memo keys, render diff layer
  — all already in their optimised state.

### Test count baseline

**1069** (4.9.3 had 1066; +3 surcoinche regressions in
`tests/test_g1_coinche_classic.py`).

## [4.9.3] - 2026-05-26

User-feedback patch over 4.9.2. Both AI-delay decorations introduced
in the 4.9.x line read as glitchy in practice; both removed. The
post-trick visual is now carried entirely by `pulse_winner_glow`
(the "★ Direction wins the trick ★" banner from 4.8.0 / C4), which
already fires immediately after the deleted animation.

### Removed

- **(G4) AI thinking spinner** — `interruptible_sleep_with_spinner`
  in `src/belote/ui/anim.py` (along with the `_SPINNER_GLYPHS`
  braille table) is gone. The call site in
  `src/belote/gameflow.py::run_play` now uses plain
  `interruptible_sleep(ai_delay, reader)`, so AI pacing between
  cards is preserved and a keypress still collapses remaining
  animations (`skip_anims = True`) exactly as before — only the
  top-right braille glyph is dropped.
- **(U3) Trick-collection animation** — `collect_trick_to_winner` in
  `src/belote/ui/render.py` is gone (function + closures), along
  with its re-export in `src/belote/ui/__init__.py`. The call in
  `gameflow.py` is deleted; `pulse_winner_glow(w, reader)` on the
  following line still fires and remains the post-trick visual.
  4.9.0's sparkle-glyph version and 4.9.1's hybrid card-frame
  convergence are both retired by this removal.

### Internal

- `BELOTE_NO_ANIM=1` docs in `DEVELOPMENT.md` updated to drop the
  4.9.0 additions bullet (the symbols it referenced no longer exist).
- `README.md`'s 4.8.0 / 4.9.0 / 4.9.1 animation polish paragraph
  rewritten to drop the G4 and U3 clauses; U1 card-lift remains.

### Test count baseline

**1066** (unchanged from 4.9.2 — no tests referenced either removed
symbol, verified by repo grep).

## [4.9.2] - 2026-05-26

Defensive patch release. A targeted multi-model audit flagged ~45
candidate issues across the classic engine, BelAtro roguelite, and
the rendering layer; spot-verification against the source filtered
that down to one real correctness bug, a handful of cache-sizing
wins, and a deprecation comment refresh. The rest were false
positives (see `~/.claude/plans/bug-hunt-code-performance-magical-pixel.md`
"Phase D" for the catalogue so future audits don't relitigate them).

### Fixed

- **`animate_score_update` now honors `BELOTE_NO_ANIM=1` and is
  skippable** (`src/belote/ui/announce.py`). The 20-frame score-roll
  used raw `time.sleep`, violating the architectural rule documented
  in `src/belote/ui/anim.py` ("route delays through
  `reader.read_timeout()`"). The function now accepts an optional
  `reader=` kwarg: with a reader supplied, each step waits via
  `reader.read_timeout(delay)` and a keypress collapses the
  animation to its final frame — same idiom as `slot_machine_tally`
  / `belete_stinger`. With `BELOTE_NO_ANIM=1` set, the loop is
  short-circuited entirely and one final HUD frame is painted.
  Call site in `src/belote/gameflow.py::run_game` updated to pass
  the reader through.

### Performance

- **`_pip_at` LRU cache raised 1024 → 4096**
  (`src/belote/ui/render.py`). On 80×48 terminals the (row_id, col)
  key space exceeded the previous maxsize, causing eviction
  mid-frame on resize. Function is pure (depends only on row_id,
  col, and the process-constant `TERMINAL.has_utf8`); larger cache
  is a free warm-path win.
- **`_felt_segment_cached` LRU cache raised 2048 → 4096**
  (`src/belote/ui/render.py`). Terminal resize creates fresh
  `(width, mat_w)` axes without evicting old entries; the larger
  cache absorbs typical resize churn without thrashing. Theme-change
  invalidation already wired via `clear_card_cache`.
- **`_card_face_internal` LRU cache raised 2048 → 8192**
  (`src/belote/ui/render.py`). The key space across 52 cards ×
  selected/legal/layout/theme/utf8 axes was ~7488; the previous
  2048 cap evicted working-set cards on theme flip. New cap covers
  the full matrix with ~600KB worst-case memory — negligible for
  a desktop TUI.

### Internal

- `partner_jokers_double` deprecation comment refreshed
  (`src/belote/belatro/core/scoring.py`) — the "removal in 4.0"
  target was missed; comment now notes the flag is kept for
  back-compat with external test fixtures, scheduled for removal at
  the next major bump.
- Pre-existing ruff (C420 dict comprehension, I001 import sort,
  F401 unused import) and mypy strict-mode type-shadow errors in
  the working tree's modified files cleared. `ruff check src/
  tests/` and `mypy --strict src/belote/` are now both clean.

### Verified false (catalogued for posterity)

Audit candidates that were flagged but verified against the code as
non-issues — re-investigate at your peril:

- "All-pass redeal leaks `coinche_level` / `declarations` /
  `belote_holders`." False. `start_round()` is called via the
  `phase == DEAL` branch in `gameflow.py` and resets all of them
  via `reset_round_fields`.
- "L'Anarchie trump rotation loses rebelote." False.
  `_compute_belote_points` prefers `state.belote_announcer` (the
  captured seat at first-belote time) over the
  `belote_holders.get(ctx.trump)` dict lookup.
- "Endless `_recent_boss_ids` grows unbounded." False. Explicitly
  trimmed to the last 2 ids in `belatro/main.py::start`.
- "Joker dispatch double-rolls back log state." False. Two
  distinct logs — accumulator's `self._log` (outer handler) and
  `ledger.log` (inner `transactional()` context).
- "Free-planet reward re-applies on `BelAtroRun` reconstruction."
  Misdirected. Only the `Profile` is persisted, not the live run
  state; `__post_init__` runs once per session.

### Test count baseline

**1066** (4.9.1 had 1064; +2 in 4.9.2 — both regression tests for
the `animate_score_update` short-circuit / skip paths added to
`tests/test_render_diff.py`).

## [4.9.1] - 2026-05-25

User-feedback patch over 4.9.0. The casino theme didn't land and the U3
trick-collection sparkle animation cluttered the felt. Both addressed:

### Changed

- **(U6 → user feedback) Theme swap: Monte Carlo Casino Night → Provence
  Lavande** (`src/belote/themes.py`). The casino-dark-felt direction was
  swapped for a sun-soaked Provençal countryside palette: soft lavender
  felt, sun-parchment cards, terracotta backs + highlights, poppy red
  ♥/♦, olive-noir ♠/♣, faded-indigo banners. Evokes outdoor table
  Belote in a Provence summer — closer to Belote's French parlour-card
  heritage. Theme count stays at 13.
- **(U3 → user feedback) Trick-collection animation rewritten: sparkle
  glyphs → hybrid card convergence**
  (`src/belote/ui/render.py::collect_trick_to_winner`). 4.9.0 painted
  scattered `✦/✧/·` glyphs along straight paths from compass slots to
  the winner; against the felt vignette this read as visually noisy
  grey/gold flecks. 4.9.1 replaces it with a three-phase animation:
  1. **Faces converge to center** (3 frames, `ease_out_quad`): each of
     the four trick cards slides from its compass slot inward.
  2. **Fade to a stack of backs at center** (1 frame): face cards
     replaced by a small fan of `card_back_bg`-filled rectangles.
  3. **Stack slides to winner** (3 frames): the back-stack interpolates
     from center to the winner's compass slot.

  Total ~280 ms; skippable on any key; honors `BELOTE_NO_ANIM=1`.
  Signature change: `collect_trick_to_winner(winner, trick, reader)` —
  caller in `src/belote/gameflow.py` updated to pass
  `display_state.current_trick`.

### Internal

- `src/belote/ui/render.py` gains a `TrickCard` import (was already
  imported transitively via `gameflow.py`; the new helper needs the
  symbol directly).
- Test count baseline: **1064** (unchanged from 4.9.0).

---

## [4.9.0] - 2026-05-25

Bundled UI-polish + gameplay-correctness release. Six UI / feel
improvements (U1–U6) close the deferred items from 4.8.0 and add a 13th
theme; four gameplay items (G1–G4) surface coinche in classic mode, add
hard-AI signaling, make litige carryover visible, and add a thinking
spinner during AI delays. L2 (Belote Contrée full bidding) is scoped to a
later release. **Roadmap drift caught and corrected**: a `colorblind`
theme already existed at `themes.py:157`, so U6 ships a new Monte Carlo
Casino Night theme instead; no golden-frame test existed for hand-lift,
so U1 creates one.

### Added

- **(U1) Card-lift on selection** (`src/belote/ui/render.py::_render_hand_horizontal`).
  Selecting a card in the south hand visually rises it +1 row above its
  neighbors. The renderer switches from a fixed `card_h`-row block to a
  `card_h + 1`-row layout when `selection` is set; the highlight bar
  follows the new bottom edge. Unselected hands keep the original
  `card_h` shape (no regression on the no-selection render path).
- **(U2) Card lift doubles as selection-change transition.** Terminal
  cells can't do sub-character vertical motion, so U2's "interpolated
  slide" collapses into U1's lift itself — the new card visibly rises
  on render, the old one drops. Documented in the lift code so future
  contributors don't re-attempt a broken pixel-slide.
- **(U3) Trick-collection animation** (`src/belote/ui/render.py::collect_trick_to_winner`,
  wired in `src/belote/gameflow.py:234-248`). When a trick ends, four
  sparkle trails converge from the compass slots toward the winner's
  position before `pulse_winner_glow` fires. Mirrors
  `slide_card_to_table_hint`'s rules (absolute cursor moves,
  `invalidate_diff()` in `finally`, interruptible via reader). ~150ms;
  skipped under `BELOTE_NO_ANIM=1`.
- **(U4) Live score-formula contributor inline** (`src/belote/belatro/ui/hud.py`,
  row 3). The BelAtro HUD's existing `chips × mult = total` line now
  shows the most-recent joker contributor inline as `(+25 chips from
  Le Banquier)`, sourced from `ScoreAccumulator._log[-1]`. Compact mode
  unaffected (no row budget).
- **(U5) Inventory + Consumables unified** (`src/belote/belatro/ui/inventory.py`).
  The V-key inventory screen is no longer read-only: pressing `1`–`9`
  activates the Nth consumable directly, and pressing `A` on a
  consumable's detail page does the same. The footer surfaces the
  digit-activate path. The shop's `C` key still launches the numbered
  `ConsumablesOverlay` (the two coexist: V is the unified screen, C is
  the in-shop quick path).
- **(U6) Monte Carlo Casino Night theme** (`src/belote/themes.py`). 13th
  theme — belle-époque casino: midnight purple-black felt, wine-red
  suits on champagne-cream cards, gold-leaf highlights, burgundy
  banners. Fills the glitzy-formal niche the existing 12 themes don't
  cover. Pivoted away from the original "colorblind palette" plan
  because a `colorblind` theme already ships.
- **(G1) Coinche / Surcoinche in classic mode** (`src/belote/gameflow.py::_run_coinche_flow`,
  `src/belote/ui/prompts.py::prompt_coinche` / `prompt_surcoinche`,
  `src/belote/ai.py::decide_coinche`, scoring multiplier in
  `src/belote/scoring.py::apply_round_score`). After a bid locks,
  defender side gets a `[C] coinche` prompt; if coinched, taker side
  gets `[S] surcoinche`. New `coinche_level: int` field on `GameState`
  (0/1/2) drives a `2^level` multiplier applied to the winning team's
  credit (`is_failed` decides which side wins). AI heuristic
  (HARD-only): coinche if holding the trump Jack OR 3+ trumps. Resets
  per round via `reset_round_fields`.
- **(G2) AI signaling convention (peter, HARD tier)** (`src/belote/ai.py`).
  Hard AI's forced off-suit non-trump discards may swap rank within the
  zero-point set (7/8/9) to signal partner: 9 = "lead this suit back",
  7 = "don't bother", 8 = neutral. New `AIMemory.signals: dict[Suit, int]`
  and `signals_emitted: int` (capped at 2/round so the convention
  doesn't sacrifice all rank flexibility). Signals are read in
  `_process_trick_signals` from completed tricks only (transient
  current-trick reads would update mid-decision). `_hard_lead` prefers
  a signaled suit before falling back to the existing void-based bias.
- **(G3) Litige carryover HUD chip** (`src/belote/ui/render.py::_build_hud`).
  Compact and verbose HUD modes now render `Lit:162` / `Litige: 162`
  in dim gold when `state.litige_points > 0`. Render-layer only — no
  rules change; the pool is team-neutral and accrues until the next
  fulfilled contract absorbs it (`scoring.py::_score_normal_outcome`).
- **(G4) AI thinking spinner** (`src/belote/ui/anim.py::interruptible_sleep_with_spinner`,
  wired in `src/belote/gameflow.py:220-226`). A rotating braille glyph
  paints in the top-right of HUD row 1 with the seat initial during AI
  card-play delays. Skipped if `duration < 0.15` (instant mode) or
  `BELOTE_NO_ANIM=1`. Self-cleaning + `invalidate_diff()` in `finally`.

### Tests

- New: `tests/test_render_hand_lift.py` (4 tests) — pins U1's row-count
  contract: `card_h` rows without selection, `card_h + 1` cards + bar
  with selection, `+1` more row when `show_readout=True`.
- New: `tests/test_g1_coinche_classic.py` (8 tests) — coinche multiplier
  doubles/quadruples the winning side, defender gets the multiplier on
  fail, `coinche_level` resets between rounds, HARD-AI heuristic gates.
- New: `tests/test_g2_ai_signals.py` (8 tests) — signal classification
  (9/7/8), trump discards excluded, easy AI ignores signals, lead-bias
  prefers signaled suit, emit-cap enforces 2/round.
- Test count baseline: **1064** (4.8.2 had 1044; +20 in 4.9.0).

### Internal / Doc

- New plan file `~/.claude/plans/ui-feel-squishy-moonbeam.md` documents
  the bundled design and three roadmap claims verified false during
  exploration: no golden-frame test for hand rendering, the existing
  `colorblind` theme, and the coinche int-flag vs enum discrepancy.

---

## [4.8.2] - 2026-05-25

Audit-driven correctness + perf-hygiene release. A deep multi-lane audit
(bug hunt + logic + performance + game-mechanics-implementation review)
surfaced two real Sans Atout AI bugs, a joker-registry footgun, a
joker-state alias hazard, and a handful of low-severity loose ends. All
findings landed; no rules changes; AI play is more accurate under SA.

### Fixed

- **(B1, HIGH) Hard AI no longer mis-scores off-suit cards as "winning" under
  Sans Atout** (`src/belote/ai.py::_score_winning_strategy`). Pre-4.8.2 the
  candidate's rank was `_NONTRUMP_ORDER[card.rank]` regardless of suit, while
  `highest_rank` was computed from lead-suit cards only. An off-suit Ace
  (rank 7) compared against a lead-suit Jack (rank 3) fired `win_bonus` even
  though `_card_beats` (game.py) forbids off-suit cards from winning under SA.
  The AI burned high off-suit cards when forced to discard. Fix: pin `rank=-1`
  for off-suit candidates so `rank > highest_rank` is unreachable.
- **(B2, MED) 2-ply opponent-trump-fear penalty suppressed under SA**
  (`src/belote/ai.py::_score_winning_strategy`). The penalty assumes opponents
  can trump the winner. Under SA `trump is None`, so the conditions
  `trump not in opp_voids` (always True for `None`) and
  `card.suit != trump` (always True) both passed — the AI penalized any
  winning play by -8 when the right-hand opponent was known void in lead.
  Wrapped in `if not is_sa:` so the entire block is moot under SA.
- **(B3, MED) `ScoreAccumulator._handler_index` rebuilds on `_jokers` mutation**
  (`src/belote/belatro/core/scoring.py::_fire_jokers`). Pre-4.8.2 the lazy
  gate was `not self._handler_index and self._jokers`, which is False once
  `attach_jokers([])` ran (the index has 5 truthy keys with empty lists).
  Tests that appended to `_jokers` after the empty attach were silently
  ignored. Fix: identity-set comparison (`_attached_joker_ids`) against the
  current `_jokers` list — any drift triggers `attach_jokers(self._jokers)`.
- **(B4, MED) `state._joker_state` alias preserved across post-trigger
  mutations** (`src/belote/belatro/engine/round_driver.py`). The post-
  `trigger_round_start` agent_double sabotage block used
  `replace(state, _joker_state={...})`, which broke the ledger alias and
  forced the heist block into a defensive dual-write. Replaced with in-place
  mutation; the heist dual-write is gone too. Classic-Belote reads via
  `state._joker_state.get(...)` once again see live ledger mutations for the
  rest of the round.
- **(B5, LOW) `_compute_belote_points` asserts the announcer↔tracker
  invariant** (`src/belote/scoring.py`). Hand-built states with
  `belote_announcer` set but `belote_tracker[0]=False` would silently award
  belote points; now raises AssertionError.
- **(B6, LOW) `ContractReward.honor_bonus` default switched to `int 0`**
  (`src/belote/belatro/core/scoring.py`). Default was `0.0` (float) but the
  TypedDict declared `int` — worked by numeric duck-typing but drifted from
  the contract. No behavior change.

### Performance

- **(P1) Hard AI rank lookups consolidated** (`src/belote/ai.py::_hard_play`).
  Pre-4.8.2 `_score_winning_strategy` called `trick_rank(card, trump, ...)`
  once per candidate plus once per visible partner card — O(legal ×
  partner_hand) recomputations. Now `_hard_play` builds `candidate_ranks`
  and `partner_ranks` once, threaded through `_score_card_play` and
  `_score_winning_strategy` as new kwargs. The SA off-suit `-1` short-circuit
  from B1 is baked into the cache, so the canonical comparison is a dict
  lookup.
- **(P2) Dropped redundant `from collections import Counter` local in
  `_hard_play`** — `Counter` is already imported at module top.

### Internal / Doc

- **(L1) `GameState._joker_state` docstring spells out the BelAtro
  ledger-alias contract** (`src/belote/game.py`). After
  `trigger_round_start` the dict is shared with `acc._ledger.joker_state`;
  round-driver mutates in place to preserve the alias. Classic callers
  outside that scope still use `replace()`.
- **(L2) `UnlockTracker.on_event` logs at DEBUG on unhandled event types**
  (`src/belote/belatro/progression/unlocks.py`). Silent no-op was the
  contract, but a new unlock keyed off `TrickWonEvent` or `BeloteAnnouncedEvent`
  would silently fail — the log line makes the miss visible under
  `BELOTE_LOG_LEVEL=DEBUG`.
- **(L3) `AIMemory.last_partner_hand_key` includes `hide_partner_hand`**
  (`src/belote/ai.py`). Memo invalidates if the boss flag flips mid-round.
  Defensive — no boss toggles it today, but a future voucher/joker that
  changes visibility mid-round would otherwise see stale cached partner
  cards.

### Tests

- **New file `tests/test_ai_sans_atout.py`** (3 tests) — pins B1 (off-suit
  Ace not burned), B1 unit-level (no `win_bonus` for off-suit candidate),
  B2 (2-ply penalty suppressed under SA).
- **New file `tests/test_ai_deluge_voids.py`** (4 tests) — pins void
  inference under La Déluge alone, Le Républicain alone, and both
  combined; plus the negative case (non-wild off-lead card still proves
  void under Le Républicain).
- **New file `tests/belatro/test_handler_registry.py`** (3 tests) — B3
  regression pins: `attach_jokers([])` + append, attach + replace, and the
  no-drift no-rebuild sanity check.
- **New file `tests/belatro/test_competition_malediction.py`** (3 tests)
  — documents the actual stacking behaviour of La Compétition + La
  Malédiction under `score_round`.
- **Extended `tests/test_belote.py`** with B5 assertion test.
- **Extended `tests/belatro/test_phase1_plumbing.py`** with B4 alias
  survival test.
- **Extended `tests/test_bidding_all_pass.py`** with end-to-end litige
  pool consume after two all-pass redeals (T1).
- Test count baseline: **1044** (4.8.1 had 1028; +16 in 4.8.2).

### Speculative perf (measured, not implemented)

Two speculative items from the plan (P4 `legal_cards` key-build cost; P5
`ledger.transactional` wrapper overhead) were instrumented and closed.
Measurement: legal_cards is ~3 % of round time (below the 5 % threshold to
justify a hand-id-on-tuple refactor); BelAtro round mean is 13.69 ms /
p95 18.49 ms (73 rounds/sec) — well below any user-visible jank threshold.

## [4.8.1] - 2026-05-21

Maintenance release: outcome of a thorough multi-lane audit (logic / performance / state management, then four deeper passes). Audit headline: **zero critical or high-severity bugs** survived verification. The two micro-fixes below are pure consistency / micro-optimization. No rules, scoring, AI behavior, or UI behavior changes — `belatro` and `belote` play exactly the same.

### Changed

- **`BelAtroAnnounce.boss_reveal` harmonized onto the post-4.8.0
  `reader.read_timeout(...)` pattern** (`src/belote/belatro/ui/announce.py`).
  Pre-4.8.1 used `interruptible_sleep(N, reader)` at three sites, which
  routes through a module-level `select.select` call that doesn't go
  through the `KeyReader` interface. `banner()` (just below `boss_reveal`
  in the same file) was already on the new pattern; this aligns
  `boss_reveal` so test stubs can interpose at the reader interface
  without monkey-patching `belote.input.interruptible_sleep`. Runtime
  behavior is byte-identical — any key still skips the reveal.
- **`AIPlayer._medium_play` precomputes `trick_rank` once per decision**
  (`src/belote/ai.py`). The pre-4.8.1 code recomputed `trick_rank(c,
  trump, self._se)` inside each `min(...)`/`max(...)` walk plus inside
  the void-trump "winners" filter — five+ recomputations per AI play.
  Now a single `ranks = {c: trick_rank(c, trump, self._se) for c in
  legal}` is built up-front and reused via `ranks.__getitem__` and
  `ranks[c]` lookups. Saves roughly 1200 `trick_rank` calls per round
  (~60 µs) and reads cleaner. Decision output is unchanged.

### Internal

- Audit found and documented six **verified-false** findings from agent
  passes (LeNotaire/LeRebelle `is_rebelote` gate, ToutStreak streak
  persistence, `pulse_winner_glow` banner persistence, Libra + auto_coinche
  on chute, AI `_hard_play` SA-trump condition, `boss_reveal` print()
  scrolling). All re-investigated against current code and confirmed
  correct as designed. Plan file
  `/home/mrrobot/.claude/plans/bug-hunt-code-performance-greedy-perlis.md`
  has the full list so future audits don't re-raise them.
- Test count baseline unchanged: **1028**. No new tests; the changes are
  behavior-preserving refactors and the existing suite covers them
  (`test_ai.py` for the AI path, `test_phase2_content.py` for joker
  flow; `boss_reveal` is exercised indirectly through ante setup).

## [4.8.0] - 2026-05-21

Feature release: a twelfth theme, a coordinated animation polish pass for
BelAtro, and a tactile feel pass for classic-mode Belote. All additions are
UI-only — zero rules / scoring / AI changes. Every new helper follows the
established `try / finally invalidate_diff()` architectural rule (4.6.4 /
4.0.0). New `BELOTE_NO_ANIM=1` env-var kill switch short-circuits every new
animation to its end-state for slow terminals or scripted runs.

### Added

- **Twelfth theme: Sunset Magma** (`src/belote/themes.py::sunset_magma`).
  Deep-magenta felt, coral suits, smoky-purple "blacks", amber-sunset
  highlights, magenta-on-cream banners. Fills the warm orange/magenta niche
  none of the existing 11 themes occupied. Cycles via the `T` key and
  shows up in the main-menu theme selector automatically — no other code
  changes needed because `ThemeManager.set_current` validates dynamically.
- **Shared animation toolkit** (`src/belote/ui/anim.py`). New module with
  three easing helpers (`ease_out_quad`, `ease_in_out_quad`,
  `ease_out_cubic`) and three painted-frame helpers (`pulse_text`,
  `float_text`, `tick_bar`). Every painted helper ends with
  `invalidate_diff()` in `finally`; every interruptible delay routes
  through `reader.read_timeout(...)` so test stubs (and the existing
  `slot_machine_tally` idiom) work uniformly. Env switch
  `BELOTE_NO_ANIM=1` short-circuits to the end-state, paired with
  `_refresh_animations_enabled_from_env()` for test fixtures.
- **(BelAtro / B1) Joker trigger callouts in the slot-machine tally**
  (`belatro/ui/announce.py`). Per-trick log entries added by
  `ScoreAccumulator._log` (joker firings, planet/Carnet/Architecte
  attributions) now float above the bucket row as labelled callouts
  (`⚡ Foo: +25 chips` / `✦ Bar: ×2.5 Mult` / `$ Architecte: +$2 …`).
  New module-level `_last_log_count` cursor + `_classify_callout` /
  `_emit_callouts` helpers; reset by `reset_tally_state()`. Capped at 4
  callouts per trick to keep the moment under ~600 ms.
- **(BelAtro / B2) Shop purchase and reroll feedback**
  (`belatro/ui/shop.py`). New `_animate_purchase(idx, num_items, money_before,
  money_after)` (gold pulse on the bought slot + `tick_bar` money tick-down)
  and `_animate_reroll(num_items)` (pulsed "↻ rerolling..." cue before the
  new inventory paints). Hooked from the existing `run()` loop without
  changing shop state semantics.
- **(BelAtro / B3) Target-crossing celebration**
  (`belatro/ui/announce.py::_emit_target_celebration`). Fires once per
  round on the first tally where the running total crosses
  `acc.target_score`: gold pulse on the odometer line plus a `★ TARGET ★`
  floater above it. The existing 1.2× flame row is unchanged.
- **(BelAtro / B4) Trust-bar tick-up animation**
  (`belatro/ui/trust_bar.py::TrustBar.animate_change`). After the
  round-end trust mutations in `belatro/main.py` (`blind_beaten` /
  `blind_failed` / `big_margin_win` / `chute` / `capot_together`), the bar
  animates from the pre-round value to the post-round value via `tick_bar`.
  Snapshot taken right after `trust = self.run.partner.trust`; animation
  fires only when `trust.value != pre_trust_value`.
- **(Classic / C3) Tactile play-trail on SOUTH plays**
  (`belote/ui/render.py::slide_card_to_table_hint`). A brief vertical
  sparkle trail (`✦/✧/·`) from the south hand toward the south trick
  slot, painted just before the played card lands via `patch_trick_card`.
  AI plays are unchanged. Self-cleaning trail; ~120 ms, skippable.
- **(Classic / C4) Trick-winner glow + hold**
  (`belote/ui/render.py::pulse_winner_glow`). After all four cards land
  and the MIN_TRICK_DWELL pause completes, a 3-frame gold→white→gold pulse
  on the bottom hint row announces `★ <Direction> wins the trick ★`
  before the trick sweeps. Computed via `trick_winner_seat` (Rupture
  swing takes effect at scoring, so the on-table label stays accurate).
- **(Classic / C5) Dramatic centered Belote / Rebelote stinger**
  (`belote/ui/announce.py::belote_stinger`). Replaces the modest
  one-line `announce("Belote!")` / `announce("Rebelote!")` call with a
  4-row centered banner framed in `╔═╗║╚═╝` chars, painted in the active
  theme's `banner_bg()` + `gold_fg()`. Falls back to the slim
  `announce()` path on terminals narrower than 32 columns. Routed through
  `gameflow.py`'s existing `current.announced` dispatch.

### Internal

- `belote/ui/__init__.py` now re-exports `belote_stinger`,
  `pulse_winner_glow`, and `slide_card_to_table_hint` alongside the
  existing UI surface.
- Test count baseline: **1028** (4.7.3 had 1007; +21 in 4.8.0). New files:
  `tests/test_anim_helpers.py` (8), `tests/test_belote_stinger.py` (2),
  `tests/test_winner_glow.py` (5), `tests/belatro/test_joker_callouts.py`
  (5), `tests/belatro/test_shop_animations.py` (2). All anim tests use
  `sys.modules["belote.ui.render"]` to bypass the `belote.ui` re-export
  shadow (per the 4.0.0 architectural note).
- **Deferred from this release:** the original plan included a
  "card lift on selection" (C1) and "smooth highlight slide between cards"
  (C2) for the south-hand cursor. Both require deeper changes to the
  multi-row horizontal hand renderer than fit cleanly in the same release
  as the new toolkit; tracked for a follow-up. The remaining tactile
  effects (C3 trail, C4 winner glow, C5 stinger) ship as planned.

## [4.7.3] - 2026-05-21

Patch release: targeted bug-hunt + performance + code-logic audit. Three
parallel exploration passes (classic engine, BelAtro layer, UI/render)
surfaced ~30 candidate findings; verifying each against the live code
rejected the false positives (deck.py "deluge scores 0", LePasseur "missing
re_emit guard", show_rules "missing invalidate on scroll", show_history
"missing term_h in cache key", legal_cards "missing trick_rank hoist") and
shipped only the verified-true delta. All baselines green: `ruff` 0
violations, `mypy --strict` 0 errors, `pytest` 1007/1007.

### Fixed

- **(Bug) `announce()` did not invalidate the render-diff baseline.** The
  function paints a transient banner with absolute cursor positioning,
  bypassing `display()`. Without a post-paint `invalidate_diff()` the next
  `display()` diffed against `_last_emitted_lines` (which has no record of
  the banner) and could leave the banner visible as a ghost on the bottom
  row. Same architectural rule as `show_help` / `show_history` /
  `show_rules` / `show_card_detail` / `show_round_summary` /
  `animate_score_update`. `announce()` was the last unfixed site of the
  4.0.0 / 4.6.4 finally-pattern sweep. Pinned by
  `test_announce_invalidates_diff_baseline` in `tests/test_render_diff.py`.
- **(Bug) L'Infiltré × La Déluge interaction.** The `ghost_lead` deck rule
  paid `+2 Mult / +$1` when NS won a trick by playing trump on a "non-trump
  lead". The is-trump-lead check at `belatro/core/scoring.py:414-417`
  considered only `lead_suit == event.trump` and the TOUT_ATOUT case —
  it did not honour `seven_eight_trump` (La Déluge), so a 7-led or 8-led
  trick was incorrectly treated as a non-trump lead and the bonus could
  fire even though the lead was effectively trump. Pinned by
  `test_ghost_lead_silent_when_lead_is_seven_under_deluge` in
  `tests/belatro/test_decks_4_5.py`.
- **(Defensive) `LeDemon.on_purchase` is now idempotent.** Re-running the
  hook on an already-owned joker (a future save/load round-trip or replay-
  resume tool) would have compounded the trust subtraction. New
  `_applied_purchase_ids: set[str]` field on `BelAtroRun` (mirrors
  `_applied_voucher_ids` from 3.9.3) short-circuits the second call. Pinned
  by `test_le_demon_on_purchase_is_idempotent` in
  `tests/belatro/test_joker_contracts.py`.

### Changed

- **AI comment about La Déluge corrected** (`src/belote/ai.py:293-296`).
  The pre-4.7.3 comment claimed "promotes 7s/8s of trump above the Jack" —
  but `deck.py::trick_rank` puts the 7 at rank 8 and the 8 at rank 9
  (the two LOWEST trumps, scoring 0). The boss description in
  `boss.py:95` ("become trump") matches the code, not the comment. The
  comment now states the actual behaviour so future maintainers don't
  chase a phantom bug.
- **`render_joker_pip_strip` / `render_synergy_tooltip` split into
  builders + writers** (`belatro/ui/hud.py`). Pre-4.7.3 each helper did
  its own `sys.stdout.write + flush` outside `BelAtroHUD._render`'s
  batched parts list, costing 2–3 syscalls per HUD refresh instead of
  one. New `build_joker_pip_strip` / `build_synergy_tooltip` return
  strings; the legacy `render_*` wrappers (used by direct callers and
  tests) still exist for backward compatibility. `BelAtroHUD.render`
  and `_render_compact` now embed both builders into a single batched
  write. Pinned by `test_belatro_hud_render_writes_once` in
  `tests/belatro/test_hud_toggle.py`.

### Performance

- **`_get_card_face` reads `_cached_theme_name` instead of
  `theme_manager.current_name`** (`belote/ui/render.py:314`). The module
  already caches the theme name (line 84) and refreshes it via the theme
  callback (line 95); `_get_card_face` is called ~52 times per game
  frame, so eliminating the per-call property lookup shaves a few
  microseconds off the render budget. The cache is kept in sync via the
  existing theme-change callback. `clear_card_cache` ensures the card
  face cache is reset on every theme change, so reading the cached name
  is safe.

### Internal

- New `BelAtroRun._applied_purchase_ids: set[str]` field for joker
  on_purchase idempotency (analogous to `_applied_voucher_ids`). Empty
  by default; populated lazily by corrupted jokers with non-idempotent
  on_purchase actions.
- `build_joker_pip_strip(...) -> str` / `build_synergy_tooltip(...) -> str`
  public builder API in `belatro/ui/hud.py`; `render_joker_pip_strip` /
  `render_synergy_tooltip` retained as thin wrappers around the builders.

### Test count baseline

- 1007 (4.7.2 had 1003; +4 in 4.7.3 across `test_render_diff.py`,
  `test_decks_4_5.py`, `test_joker_contracts.py`, `test_hud_toggle.py`).

## [4.7.2] - 2026-05-20

Patch release: external-model audit verification pass. A prior audit (pasted
from another LLM) flagged ~30 issues across bugs / perf / quality. Verifying
each claim against the live code rejected the false positives (including one
HIGH-severity claim — "160 event dispatches per round" — that the model
invented out of whole cloth) and shipped only the genuinely confirmed
findings. Two real correctness gaps the prior audit missed were caught via
fresh-additions review. All baselines green: `ruff` 0 violations,
`mypy --strict` 0 errors, `pytest` 1003/1003.

### Fixed

- **(Bug) Malédiction (`invert_scoring`) 4-4 trick tie.** Pre-fix the boss
  flag zeroed the team that won MORE tricks, but a 4-4 split fell through
  both branches and neither side was zeroed — both teams kept their full
  scores under the curse. Rule chosen: the taker is zeroed (the cursed
  side failed to break the tie). `scoring.py::_apply_invert_scoring` adds
  an `else` branch; pinned by
  `test_boss_invert_scoring_4_4_tie_zeros_taker` in
  `tests/belatro/test_boss_modifiers_integration.py`.

### Changed

- **`bm: object` → `bm: BossModifiers`** on `_trick_zeroed_by_ban_clubs`,
  `_card_points_with_zero_ranks`, `card_points_with_modifiers`, and
  `_trick_points_with_modifiers` (`scoring.py`). All four helpers were
  typed as `object` with `getattr(bm, "ban_clubs", False)` defensive
  lookups; the actual callsites always pass `BossModifiers`. Now type-
  safe attribute access — `mypy --strict` enforces every new field is
  spelled correctly.
- **`UICallbacks` extracted from `BelAtroGame._play_blind`** to a module-
  top class in `belatro/main.py`. The nested class spanned 189 lines and
  captured 8 closure variables (`run`, `profile`, `save_manager`, `hud`,
  `acc`, `trust_bar`, `show_north`, plus a dead-write `last_display_state`
  cell). Now an explicit constructor; `last_display_state` removed
  (write-only, never read).
- **Litige pool carry across all-pass redeals is now documented.** Added
  a `reset_round_fields` docstring entry calling out that `litige_points`
  is deliberately NOT in the reset list — the pool survives across
  rounds (including all-pass redeals) until a non-litige scoring round
  consumes it. Pinned by
  `test_litige_pool_survives_all_pass_redeal` +
  `test_litige_pool_survives_two_consecutive_all_pass_redeals` in
  `tests/test_bidding_all_pass.py`.

### Performance

- **`detect_sequences` is now `@lru_cache(128)`.** Microbench placed it
  at ~25% of `score_round` cost when `initial_hands` is populated, and
  `get_declarations` runs the same 4 hand tuples through the helper
  twice per round (once at bid-acceptance time in `game.py`, once during
  `score_round` itself). Cache hits eliminate the second pass.
  `score_round` macrobench: 300 µs → 227 µs (~24% on the full path).
  Cards are frozen dataclasses (hashable); all callers treat the
  returned list as read-only.

### Tests strengthened

- **`test_last_trick_bonus_applied`** (`tests/test_belote.py`) → split
  into `test_capot_subsumes_last_trick_bonus` (asserts the actual
  `CAPOT_BASE` total) and new `test_last_trick_bonus_applied_in_normal_round`
  (deterministic 4-NS/4-EW non-capot fixture proving the +10 dix-de-der
  actually lands on the taker side). Previously only asserted `is_capot
  is True` — the +10 mechanic the test name promised was untested.
- **`test_non_capot_points_sum_162`** (`tests/test_belote.py`) →
  conditional `if not breakdown.is_capot:` replaced with explicit
  `assert not breakdown.is_capot` plus the unconditional conservation
  check. The old form passed vacuously if `make_deck()` ordering ever
  produced a capot.

### Internal

- **Contract→word a11y mapping deduplicated** to a `_contract_word(state)`
  helper in `gameflow.py`. Two near-identical 8-line blocks collapsed
  into one helper call each (bid→play transition; round-result speak).

### Documentation

- README test count claims and CHANGELOG / DEVELOPMENT references
  updated 999 → 1003.

### Verified-false audit claims (re-investigate at your peril)

For the record so the next audit cycle doesn't relitigate items the
external model flagged but the code disagreed with:

- `partner()` if-chain vs modular arithmetic — style only, not a bug.
- `start_round` "doesn't reset belote_holders" — self-refuted (line 308
  passes `belote_holders={}`).
- Score-animation labels "confusing" — `gameflow.py:458` already labels
  by `breakdown.taker_team`.
- `_empty_breakdown` taker_team default — only returned on contract-
  inactive states; harmless.
- `BelAtroRun.consume()` "removes before use" — wrapped in
  `contextlib.suppress(ValueError)`, semantically correct.
- `_bonus_money` "race" — Le Fantôme writes to `acc._ledger.money`
  directly since 4.6.2; main.py only consumes seal_round-routed amounts.
- "160 event dispatches per round" — false. Jokers subscribe to
  `TrickWonEvent` / `BeloteAnnouncedEvent` / `DeclarationScoredEvent`
  only; per-card emit doesn't iterate jokers. Real count is ~85-100
  dispatches per round and they're already O(jokers × events).
- LeRebelle / RebeloteEcho / TierceCharger ungated under boss flags —
  verified gated. `game.py:907` short-circuits `BeloteAnnouncedEvent`
  under `no_belote`; `round_driver.py:467-473` documents
  TierceCharger's intentional un-gating; LeMathématicien / QuinteRoyale
  read `event.points` which Le Mime forces to 0.

## [4.7.1] - 2026-05-19

Patch release: post-4.7.0 audit pass that found two latent correctness
foot-guns and three concrete AI hot-path wins, then reconciled the
documentation surfaces with the actual code. Three parallel Explore-agent
audits (core engine, BelAtro mode, performance) surfaced ~20 candidate
issues; the seven false-positives were rejected against the live code
and only the verified findings shipped. All baselines green: `ruff` 0
violations, `mypy --strict` 0 errors, `pytest` 999/999.

### Fixed

- **(Major) Sans Atout partner-hand rank comparison.** `_score_winning_strategy`
  computed the local `rank` via `_NONTRUMP_ORDER[card.rank]` under SA
  (correct), but the partner-hand penalty block at the bottom of the
  function unconditionally called `trick_rank(card, trump, self._se)` with
  `trump=None` for BOTH the candidate card and every partner card.
  `trick_rank(card, None, ...)` happens to collapse to the same ordering
  as `_NONTRUMP_ORDER` today, so the bug is benign-by-coincidence — but
  any future tweak to `trick_rank`'s SA branch (e.g. honor-scaling)
  would silently break the partner-hand heuristic without any test
  catching it. Now mirrors line 728's `if is_sa` branch on both rank
  computations. Pinned by `test_winning_strategy_partner_hand_uses_nontrump_order_under_sa`
  in `tests/test_ai.py`, which poisons `trick_rank` and confirms the
  SA branch never touches it.
- **(Minor) `prompt_card` silently substituted `hand[0]` on empty
  `legal_cards`.** Belote's suit-follow / overtrump rules guarantee at
  least one legal card whenever the hand is non-empty, so the path is
  unreachable today — but the `return hand[0], state` fallback would
  let an illegal card through to `play_card` if `legal_cards` ever
  regressed. The AI path (`ai.py::decide_card`) already raises on the
  same precondition; the human-input path now matches. Pinned by
  `test_prompt_card_raises_on_empty_legal_cards`.

### Performance

- **Hoisted `highest_rank` and `opp_voids` out of the per-card scoring
  loop in `_hard_play`.** Both depend only on `(trick, trump, is_sa,
  self._se)` and the next-opp seat — all constant across the 1–8 legal
  candidates being scored. Pre-fix they were recomputed inside
  `_score_winning_strategy` per card. Now precomputed once and threaded
  through `_score_card_play` → `_score_winning_strategy` as kwargs with
  `None` defaults so standalone callers (tests, future ad-hoc
  heuristics) still work. ~8–15% on hard-AI card decisions.
- **Plumbed `points` through `_score_leading_strategy`.**
  `_score_card_play` already computes `points = card_points_with_modifiers(card, trump, bm)`,
  but the leading-strategy helper re-invoked the function to detect waste
  cards. Now the helper accepts a keyword-only `points: int` and reuses
  the caller's value. ~3–5% on lead decisions.

### Changed

- `tests/test_ai.py` test count: 22 → 24 (the two new pins above).
  Total suite: 997 → **999**.

### Documentation

- `README.md` — test-count claims updated 997 → 999 in three places
  (project-structure block, "Running Tests" section, "Technical
  Integrity" bullet list). Joker/voucher/planet/tarot/boss/deck counts
  reverified against `registry` / `ALL_BOSS_MODIFIERS` / `STARTING_DECKS`
  (42 / 12 / 8 / 12 / 21 / 12) — all already accurate at 4.7.0, no
  change.
- `DEVELOPMENT.md` — code-quality command block now mentions 999 tests.
  Release process now explicitly calls out that `pyproject.toml` AND
  `src/belote/__init__.py` must be bumped together (they had been
  drifting in older release attempts; `belote --version` /
  `belatro --version` read `__version__` while PyPI / pipx read
  `pyproject.toml`).

## [4.7.0] - 2026-05-19

Feature minor: ships the **Dix de Der Heist** (BelAtro roguelite gamble keyed off `economy.interest_rate`) and the **slot-machine score tally** that replaces the static per-trick popup with a rolling odometer animation. Includes a full 4.6.5-style multi-agent audit (six parallel Explore agents covering heist correctness, slot-machine boss safety, items integration, save/load, performance, and 21-boss crash safety) and the resulting fixes, plus a hands-on polish pass — heist-discoverability hint, persistent tally in HUD, and a new V-key inventory overlay. All baselines green: `ruff` 0 violations, `mypy --strict` 0 errors, `pytest` 997/997.

### Added

- **Dix de Der Heist (BelAtro)** — Player-only roguelite gamble declared at the start of trick phase. When SOUTH is the taker and `economy.interest_rate > 0` (gated; default rate = 0 = no reward = no prompt), the player can declare a heist that resolves on trick 8:
  - On NS win: `ledger.mult *= (1 + interest_rate)` (`×2` with La Voûte, up to `×4` stacked with interest-bumping tarots).
  - On NS loss: the card_points NS accumulated in tricks 1–7 are subtracted from `ledger.chips`. Declarations / belote / permanent / joker bonuses preserved.
  - The multiplier resolves BEFORE `_fire_jokers("on_trick_won", event)` on trick 8 so jokers like LeDernierMot (×2) and LExecuteur (×1.5) compose on top. Documented in `belatro/core/scoring.py` to lock the composition rule in for future readers.
  - State on `joker_state` as three scalar keys (`heist_declared`, `heist_ns_trick_chips`, `heist_outcome`) seeded fresh by `trigger_round_start`; per-round transient, never persisted. Sentinel `heist_outcome` guards resolution against the ~30 HUD `materialize()` re-reads per round.
  - New `RoundUICallbacks.prompt_heist(state) -> bool` hook with a default no-op (classic Belote never offers the heist). BelAtro UICallbacks overrides in `belatro/main.py`.
- **Slot-machine score tally** (`BelAtroAnnounce.slot_machine_tally`) — Per-trick odometer animation replacing the static `score_popup`. 20-frame ease-out over ~600ms; bucket bar shows trick card_points filling, mult indicator pulses, odometer ticks toward the new total with color shifts (cyan → white → gold) and a flame row (`≈ ▼ ◆ ▼ ≈`) when running total crosses 120% of target. Skippable on SPACE / ESC / ENTER / EOF. Suppressed under `hide_hud` (Le Brouillard), `separate_scoring` (La Compétition), and on terminals smaller than 6 rows. Module-level cache (`_last_tally_total`) cleared each round via `reset_tally_state()`.
- **Persistent slot-machine readout in the BelAtro HUD (follow-up).** After the animation completes, the final-frame bucket + odometer lines stay visible at the bottom of the screen until the next trick or until `I` toggles the top HUD off. Adds a 1s skippable hold after the final frame so the player can read the result, then a new `_last_tally_readout` module cache feeds `BelAtroHUD.render()` / `_render_compact()` for the repaint. Cleared via `reset_tally_state()`. Bound to `is_top_hud_visible()` so `I` hides both the HUD and the readout in one shot.
- **Inventory overlay on the V key** (`BelAtroAnnounce` peer `InventoryOverlay` in `belatro/ui/inventory.py`). Read-only detail-on-select pager that lists owned jokers (with edition tags + per-edition bonus blurb), vouchers, consumables (tarots/planets held but not yet activated), permanent chip / mult bonuses, and per-contract planet levels. List view → ↑/↓ navigate, Enter opens a per-item detail page; Esc/V/Q close. Mirrors the `C` key's `ConsumablesOverlay` paint pattern (`clear_screen` + `vcenter_lines` + `invalidate_diff()` in `finally`).
- **Discoverability hint for the Dix de Der Heist.** The first time a player takes a contract while `economy.interest_rate == 0` (i.e. they haven't bought La Voûte yet), a one-time banner explains the gating: *"Tip: buy the La Voûte voucher in the shop to unlock the Dix de Der Heist (×2+ Mult on trick 8)."* Persisted via a new `Profile.seen_heist_hint: bool` field; no SCHEMA_VERSION bump needed (dataclass default kicks in for legacy saves).

### Fixed (4.7.0 audit pass)

- **(Critical) Slot-machine cache leak on mid-animation interrupt** (`belatro/ui/announce.py`). The `_last_tally_total = new_total` update lived inside the try-block; a `KeyboardInterrupt` or render-time raise mid-animation would skip the update and leave the next round animating from a stale baseline. Moved into the `finally` block alongside `invalidate_diff()`. Pinned by `test_slot_machine_cache_updates_even_if_render_raises`.
- **(Critical) Slot-machine row collision on tiny terminals** (`belatro/ui/announce.py`). Row math (`term_h - 5..3`) collapsed when `term_h < 6`, painting the animation over the HUD row 1. Added a `term_h < 6` short-circuit that suppresses the animation while still updating the cache. Pinned by `test_slot_machine_tiny_terminal_renders_nothing`.
- **(Critical) `BelAtroAnnounce.reset_tally_state` AttributeError on round start.** `belatro/main.py::_play_blind` called `BelAtroAnnounce.reset_tally_state()` but the function was defined at module level (mirroring `reset_top_hud_state` / `reset_overlay_state`), not as a static method on the class. Crashed at the first round. Now imported as a module function. User-surfaced.
- **(Medium) Slot-machine paints misleading totals under La Compétition** (`belatro/ui/announce.py`). `acc.get_total(state)` is a running sum but `separate_scoring` uses a per-seat max at round-end; the animated total diverged from the eventual sealed total. Now gated like the HUD (`belatro/ui/hud.py:171-176`): cache update without paint. Pinned by `test_slot_machine_under_separate_scoring_renders_nothing`.
- **(Medium) Heist outcome banner leaked under Le Brouillard** (`belatro/main.py`). The post-round "HEIST SECURED / BUSTED" banner ignored `hide_hud`, defeating the boss's "hide the score" promise. Now gated on `not final_state.boss_modifiers.hide_hud`.
- **(Polish) Blank flame row consumed a screen row** (`belatro/ui/announce.py`). When `displayed < target × 1.2`, `ansi_center("")` painted a `term_w`-wide blank line, wasting vertical space. Now skip the paint when the flame line is empty.
- **Sans Atout AI type safety.** The 4.6.6 in-flight Sans Atout Hard AI work shipped with type annotations that assumed `trump: Suit`, but the SA path has `trump = None`. Widened `_hard_lead` and `_score_card_play` signatures to `Suit | None`, added an explicit `trump is None` arm to the `opp_trumps` computation in `_hard_play`, and removed a dead `is_sa = True/False` branch (overwritten three lines later by the canonical `state.contract == Contract.SANS_ATOUT` read). `mypy --strict` now clean.

### Changed

- **`BelAtroAnnounce.score_popup` no longer called at `on_trick_end`.** Replaced by `slot_machine_tally`. The method is still defined for one release; if no consumer surfaces by 4.8 it will be removed. Bumped the `belatro/ui/announce.py` `invalidate_diff` count in `tests/test_alt_screen_scroll.py::test_belatro_overlays_invalidate_diff` from 4 to 5.
- **`ScoreAccumulator` gained an `interest_rate: int = 0` field.** Snapshotted at `_play_blind` time alongside `target_score`, so a mid-round La Voûte purchase or tarot effect cannot retroactively change the resolved heist multiplier.
- **`V` key is no longer an alias of `I`.** Pre-4.7.0 both keys mapped to `Key.OVERLAY` (top-HUD toggle). The follow-up pass split `V` into a new `Key.INVENTORY` enum value that opens the read-only inventory overlay. `I` keeps its existing toggle semantics (and now also covers the persistent tally readout). Wired in `belote/input.py` (both `_UnixKeyReader` and `_WindowsKeyReader`), dispatched in `belote/ui/prompts.py::prompt_card` (`"INVENTORY"` sentinel string), and handled by `belatro/main.py::UICallbacks._show_inventory`. Classic Belote's `gameflow.py` treats the sentinel as a no-op (re-prompt).

### Internal

- **Test count baseline**: 941 → 997 (+56 in 4.7.0: 23 heist tests including 3 hint-discoverability regressions, 16 slot-machine tests including 5 HUD-readout persistence regressions, 15 inventory-overlay tests, 2 audit-driven entries).
- **Version markers bumped**: `pyproject.toml` (`4.6.6` → `4.7.0`), `src/belote/__init__.py` (`4.6.6` → `4.7.0`).
- **No `SCHEMA_VERSION` bump required**: heist state is per-round transient on `joker_state`, seeded fresh by `trigger_round_start` and never persisted. `Economy.interest_rate` was already persisted as part of `BelAtroRun.economy`; existing saves load without migration.
- **Six-agent audit highlights (all verified clean, no further action)**: per-round transient state hygiene (heist keys reset at round start, slot-machine cache reset at `_play_blind` entry); idempotency under HUD `materialize()` (sentinel-guarded, no re-application); composition with all trick-8 jokers (LeDernierMot, LExecuteur, Le Carnet, L'Infiltré); composition with planets (Pluton capot bonus, Mercure round-end money, Le Soleil Tout Atout per-trick mult); 21-boss safety smoke (La Rupture / La Compétition / L'Avocat / Le Mime / Le Zéro Final / L'Anarchie / L'Agent Double / La Solitude all verified). Performance: heist branches sub-microsecond per trick; slot-machine animation adds ~4.8s/round (designed, skippable).
- **Documentation accuracy sweep**: README and DEVELOPMENT refreshed; item counts (42 jokers, 12 tarots, 8 planets, 12 vouchers, 12 starting decks, 21 bosses) unchanged from 4.6.6 and re-verified against the registry.
- **Plan file**: `/home/mrrobot/.claude/plans/let-s-add-dix-de-steady-duckling.md`.

---

## [4.6.6] - 2026-05-19

Performance and logic audit pass. Highlights: improved Hard AI strategy for Sans Atout, unified round scoring paths to remove redundancy, and end-to-end documentation accuracy verification. All baselines green: `ruff` 0 violations, `mypy --strict` 0 errors, `pytest` 941/941.

### Fixed

- **Hard AI fallback for Sans Atout rounds.** Pre-4.6.6, the 1-ply lookahead heuristic was trump-centric and fell back to random play when no trump was set. Now uses a non-trump ranking heuristic based on `_NONTRUMP_ORDER` (A > 10 > K > Q > J > 9 > 8 > 7), making the Hard AI significantly more competitive in Sans Atout play.
- **Refactored `apply_round_score` in `scoring.py`.** Unified the NS-taker and EW-taker branches into a single path using conditional mapping, eliminating 50+ lines of duplicated code and reducing the risk of logic drift between teams.

### Internal

- **Test count baseline**: 941 (unchanged).
- **Version markers bumped**: `pyproject.toml`, `src/belote/__init__.py`, and various documentation references (4.6.5 → 4.6.6).
- **Documentation accuracy sweep**: Item counts (42 jokers, 12 tarots, 8 planets, 12 vouchers, 12 starting decks, 21 bosses) and test counts (941) verified across `README.md` and `DEVELOPMENT.md`.

## [4.6.5] - 2026-05-18

Follow-up audit pass — six parallel Explore agents covered the surface area the 4.6.4 sweep didn't reach (partner-trust + bidding state machine, shop / economy / items / ghost-run, progression / replay / a11y / input). Result: two verified critical bugs in production paths the previous audit didn't touch (the LePrêteur economy exploit and a Windows-only EOF reader bug), three performance wins, and four quality items including the dead-but-declared `announce_round_result` helper finally wired up. Mechanics audits (partner trust, bidding state machine, capot detection, belote/rebelote under L'Anarchie, voucher idempotency, ghost-run write safety, save atomic-writes, achievement unlocks) all came back clean against current code. Plan file: `/home/mrrobot/.claude/plans/bug-hunt-code-performance-sparkling-fairy.md`. All baselines green: `ruff` 0 violations, `mypy --strict` 0 errors, `pytest` 941/941.

### Fixed

- **(Critical) LePrêteur's $5 skim cost was silently dropped — free ×1.2 Mult on every $50+ round.** `belatro/main.py:453` gated the `_bonus_money` payout on `> 0`, so `JokerResult(add_money=-5, times_mult=1.2)` from LePrêteur's "$50+ → skim $5 for ×1.2 Mult" branch let the multiplier through (it routes via the accumulator's `times_mult` field, separate from `_bonus_money`) but never debited the cost. Repro: BelAtro run, buy LePrêteur, accumulate >$50, start the next round → wallet does not decrement. Fix: route negative `_bonus_money` through `Economy.spend_money(abs(amount))` — symmetric with the 4.6.4 non-negative guard on `Economy.add_money`. Pinned by `tests/belatro/test_jokers_4_5.py::test_preteur_skim_actually_debits_economy`.
- **(Critical) Windows EOF never surfaced as `Key.EOF`.** `_WindowsKeyReader.read()` (`input.py:275`) handled the `b"\x00"` / `b"\xe0"` escape prefixes from `msvcrt.getch()` and the WASD / arrow / letter aliases, but had no guard for empty bytes (`msvcrt.getch()` returning `b""` on closed stdin). Control fell through past every match, reached `ch.decode("utf-8")` (which succeeds on empty bytes → `""`), and returned `KeyEvent(Key.CHAR, "")`. Any prompt loop that ignored empty CHAR events would hot-spin until the outermost loop happened to exit. Latent in the codebase since the input layer was introduced; only the Unix reader had the EOF guard. Fix: `if not ch: return KeyEvent(Key.EOF)` immediately after `msvcrt.getch()`, mirroring `_UnixKeyReader`. Pinned by `tests/test_input_eof.py::test_windows_reader_returns_eof_on_empty_read` (mocks msvcrt on Windows; cross-platform static-shape check elsewhere).
- **`announce_round_result` had zero call sites.** Declared in `a11y.py` since 3.0.0 ("round complete. {team} taker scores ...") but nothing in `gameflow.py` actually called it; screen-reader users heard per-trick winners with no round-summary line. Fix: hooked at the score-animation site in `gameflow.py` after `animate_score_update`. Also added a new optional `contract: str | None` parameter so the spoken line is "round complete on hearts. north-south taker scores 162; defenders score 0" rather than the trump-less original.

### Added

- **A11y: `announce_contract(taker, contract_label, coinche_level)`** — spoken at the bid→play transition in `gameflow.py`. Translates the locked trump / Tout Atout / Sans Atout into a screen-reader line. Coinche level is suffixed (", coinched" / ", surcoinched").
- **A11y: `announce_declaration(seat, kind, points)`** — exposed for future hook in `round_driver.py`'s declaration-emit branch. Helper landed in 4.6.5; the round_driver hook is deferred (the existing on-screen banner is loud enough that the user can hear it via OCR-style screen readers, but pure-stderr a11y readers will need the wiring).
- **`SaveManager._migrate` forward-incompat guard.** Pre-fix, a save file with `schema_version > SCHEMA_VERSION` would silently load as the current schema with future fields ignored. 4.6.5 raises `ValueError` instead; loud failure beats silent garbage. Auto-fallback to a fresh `Profile()` is intentionally **not** added — silently dropping progress is worse than asking the player to upgrade the game build.
- **Regression test `test_preteur_skim_actually_debits_economy`** — pins the LePrêteur economy exploit fix.
- **Regression test `test_windows_reader_returns_eof_on_empty_read`** — Windows-conditional mock + cross-platform static-shape check (asserts the empty-bytes guard appears before the decode fallback in the source).

### Performance

- **`_medium_lead` (`ai.py:466-477`) collapsed from 3× hand-walks to 1× Counter pass.** Pre-fix built `non_trumps`, then computed `suit_counts = {s: sum(1 for c in non_trumps if c.suit == s) for s in Suit if ...}` (4 walks across non_trumps), then re-filtered `[c for c in non_trumps if c.suit == best_suit]`. Now: `Counter(c.suit for c in non_trumps if c.suit.is_card_suit).most_common(1)` returns the best suit + count in one pass.
- **`animate_score_update` no longer allocates a fresh frozen `GameState` per frame.** Pre-fix the 20-step score-roll animation called `dataclasses.replace(state, team_scores=(curr_ns, curr_ew))` per frame. 4.6.5 threads an optional `team_scores_override` kwarg through `display_hud` / `_build_hud`; the loop now passes the intermediate scores directly. `dataclasses.replace` is no longer imported in `ui/announce.py`. Existing `invalidate_diff()` in the `finally` block preserved (still pinned by `test_animate_score_update_invalidates_diff_baseline`).
- **Declaration tie-break (`scoring.py:300-326`) collapsed from nested-zips to a dict lookup.** Pre-fix `_resolve_tie_carre` / `_resolve_tie_seq` each did `for s in seat_order: for c, cs in zip(...): if cs == s and ...`. Now: build `{seat: team}` once, then `for s in seat_order: if s in seat_team: return seat_team[s]`. O(seats × decls) → O(seats); both factors are tiny so the speedup is microscopic but the dict form reads more clearly.

### Changed

- **`UnlockTracker.on_event` docstring** (`belatro/progression/unlocks.py`) now enumerates handled event types (`RoundEndEvent`, `DeclarationScoredEvent`). Other bus events remain no-op by design — future unlocks that key off `BidMadeEvent` / `TrickWonEvent` / `BeloteAnnouncedEvent` add an `elif` here.
- **`JokerResult.add_money` sign convention documented** on the dataclass docstring (`belatro/items/base.py:43-49`): positive = credit, negative = debit (cost), zero = no-op; negative values route through `Economy.spend_money` at the payout site, not through `Economy.add_money` (which rejects negatives since 4.6.4).
- **`_build_hud` and `display_hud`** gained an optional `team_scores_override: tuple[int, int] | None = None` kwarg. Existing callers pass nothing and get the same behaviour (read from `state.team_scores`).
- **`a11y.announce_round_result`** gained an optional `contract: str | None = None` parameter that, when set, produces "round complete on hearts. ..." instead of "round complete. ...".

### Removed

- **Dead constant `_TIER_NAMES`** in `belatro/ui/trust_bar.py:13`. Defined in 3.4.0 as `("Méfiant", "Sulking", "Neutre", "Loyal", "Mécène")` but never indexed; the BelAtro UI reads mood names from `TrustTrack.mood()` directly.

### Internal

- **Test count baseline**: 939 → 941 (+2 in 4.6.5: LePrêteur economy + Windows-EOF regressions).
- **Version markers bumped**: `pyproject.toml` (`4.6.4` → `4.6.5`), `src/belote/__init__.py` (`4.6.4` → `4.6.5`).
- **Documentation accuracy sweep**: `README.md` test-count + version markers refreshed (939 → 941; 4.6.4 → 4.6.5). `DEVELOPMENT.md` baseline section rebuilt with the 4.6.5 highlights, 4.6.4 demoted to "Previous baselines". Accessibility section in `DEVELOPMENT.md` updated to mention the new contract / declaration announcements and the hook-point convention. Item counts re-verified end-to-end: **42 jokers, 12 tarots, 8 planets, 12 vouchers, 12 starting decks, 21 bosses** — all README claims match the registry.
- **Audit scope (verified clean, no action)**: partner trust score-bounds and tier-bucketing; all 6 personality archetypes; all-pass dealer rotation; Tout Atout / Sans Atout round-2 gating (triple-defended in `game.py`, `prompts.py`, `round_driver.py`); coinche → surcoinche flow on both NS-taker and EW-taker paths; L'Avocat auto-coinche `max()` invariant; capot detection across SA / TA / normal contracts under La Rupture; belote/rebelote under L'Anarchie trump rotation; voucher idempotency through the 3.9.3 base-class `_apply_once` guard; edition roll weight distribution; endless `_recent_boss_ids` cap + 8-attempt reroll guard; LeBanquier chute / NS-taker gating; ghost-run / run-summary write safety (`OSError`-swallowed, `fsync` before rename); theme-change cache-invalidation chain (`_card_back`, `_felt_segment`, `_card_face`, `_last_emitted_lines`); save atomic-writes (tempfile + fsync + rename); WASD aliasing on the Unix reader; AI memo invalidation (`last_voids_key`, `last_partner_hand_key` reset on new-round AND undo paths); `AIPlayer.decide_card` empty-legal assertion. Each item proven against current source rather than memory.
- **Plan file**: `/home/mrrobot/.claude/plans/bug-hunt-code-performance-sparkling-fairy.md`.

---

## [4.6.4] - 2026-05-17

Multi-agent audit pass — fixes five confirmed defects surfaced by an LLM-driven codebase audit, the most serious being a silently-broken unlock pipeline. The `EventBus` parameter that `drive_round` accepted was never `emit()`-ed, so every event-driven unlock (L'Exécuteur on first Capot, L'Idéologue on Sans Atout win, Le Fanatique on Tout Atout win, Quinte Royale on a NS sequence ≥100 pts) silently never fired in real play despite the `tests/belatro/test_contract_unlocks.py` suite passing — those tests `bus.emit(...)` directly and bypass `drive_round`. Also wires the previously-defined `RoundLedger.transactional()` exception-safety guard, closes the Le Mime + L'Architecte score-leak combo, replaces a dead `card in self.memory.partner_hand` identity check in hard-AI scoring with a real "partner has stronger same-suit card" comparison, and pins `animate_score_update` against the diff-baseline-staleness pattern the BelAtro overlays already enforce. All baselines green: `ruff` 0 violations, `mypy --strict` 0 errors, `pytest` 939/939.

### Fixed

- **`drive_round` accepted an `EventBus` but never emitted to it — UnlockTracker silently broken.** `_emit()` in `src/belote/belatro/engine/round_driver.py` only called `acc.process_event(s, event)`; `bus.emit(event)` was missing. `UnlockTracker.subscribe_to(bus)` (called in `belatro/main.py:168`) added the unlock dispatcher to an empty pipeline, so every event-driven unlock condition (`progression/unlocks.py::on_event` for RoundEndEvent / DeclarationScoredEvent) was unreachable in natural play. Repro: complete a Capot in a normal run → L'Exécuteur never appears in your unlocks; declare a Quinte ≥100 pts → Quinte Royale stays locked. Fix: `_emit()` now publishes to the bus after the accumulator runs. The `bus.emit` ordering after `acc.process_event` keeps subscribers' state inspections consistent with ledger mutations made by jokers fired in the same dispatch.
- **`RoundLedger.transactional()` exception-safety guard was defined but never used.** `ScoreAccumulator.process_event` dispatched joker handlers raw — a joker raising mid-`_fire_jokers` left the ledger in a partial-mutation state AND short-circuited every sibling joker subscribed to the same event. The `transactional()` context manager (defined at `src/belote/belatro/core/round_ledger.py:74-103` with a documented "preserves the pre-4.6.2 exception-safety guarantee" docstring) wasn't called from anywhere. Fix: each per-joker invocation in `_fire_jokers` is now wrapped in `with ledger.transactional():`, plus a try/except mirroring EventBus's isolation pattern — `logger.exception(...)` and continue with siblings. The accumulator's `self._log` length is snapshotted around each call because `_apply` writes there (separate from `ledger.log` which transactional already rolls back).
- **Le Mime + L'Architecte combo leaked declaration-derived $$.** Under `declarations_zero`, `round_driver` correctly emitted `DeclarationScoredEvent` with `points=0`, but the BelAtro `core/scoring.py` handler unconditionally stamped `joker_state["_ns_annonce_cards"]` from `state.declarations`. L'Architecte's `annonce_cash_x2` deck rule then still paid +$2 per NS trick containing a declared card, defeating Le Mime's "all declaration value zeroed" promise. Fix: gate the harvest on `not state.boss_modifiers.declarations_zero` so the joker_state keys stay unset.
- **Dead `card in self.memory.partner_hand` check in hard-AI `_score_winning_strategy`.** `card` came from MY hand; `partner_hand` held partner's cards. With 32 unique deck cards and disjoint hands, the identity check was always False, so the documented "don't duplicate strength" −5 penalty never fired. Fix: walk `partner_hand` for a strictly stronger same-suit card via `trick_rank(...)` (honours L'Anarchie trump rotation via the existing `_se` flag) and apply the penalty only when partner can actually cover the trick.
- **`animate_score_update` didn't invalidate the diff baseline.** `display_hud` writes row 1 directly via `move(1,1)`, bypassing the `_last_emitted_lines` diff cache. The 20-step animation loop left the cache stale; a subsequent `display()` whose new row 1 happened to match the pre-animation cached row 1 would skip emitting it, leaving the last animation frame painted on screen. Fix: post-loop `invalidate_diff()` in a `finally` block. Mirrors the architectural rule already enforced for `show_help` / `show_history` / `show_rules` / `show_card_detail` / `show_stats` (pinned by `tests/test_alt_screen_scroll.py::test_belatro_overlays_invalidate_diff`).

### Changed

- **`Economy.add_money` now rejects negative amounts** (`src/belote/belatro/core/economy.py:15`). Symmetric with `spend_money`, which already rejects negatives. No production caller passes negative (`grep`-verified: every `add_money(...)` site is either a `process_round_end` payout, a `bonus_money > 0` gated branch in `belatro/main.py`, or a `max(0, ...)`-bounded value). The LePrêteur `JokerResult(add_money=-5)` path is unaffected — those go through `ledger.money +=` directly, not through `Economy.add_money`.
- **`_is_honor` closure hoisted out of the per-suit loop in `ai.py::_hard_bid`** (was rebuilt 4× per call for no benefit). The closure now reads `_drop_jacks` / `_drop_aces` locals captured once before the loop.

### Internal

- **New regression tests (+6)**:
  - `tests/belatro/test_round_driver.py::test_drive_round_emits_to_event_bus` — subscribes a list-appender to the bus, drives a real all-pass round, asserts at least one `BidMadeEvent` was received. Pins the bus-wiring fix.
  - `tests/belatro/test_round_driver.py::test_raising_joker_isolated_via_transactional` — attaches two jokers (one that raises, one that adds +42 chips), asserts the sibling still fires and the raise is logged via `logger.exception`. Pins the transactional guard.
  - `tests/belatro/test_decks_4_5.py::test_le_mime_suppresses_architecte_annonce_cash` — activates `declarations_zero` boss flag, declares a Tierce, plays a trick containing a declared-suit card, asserts `_bonus_money == 0`.
  - `tests/test_ai.py::test_winning_strategy_penalises_when_partner_has_stronger_same_suit` — pins the −5 score delta when partner downgrades from a stronger to weaker same-suit card.
  - `tests/test_render_diff.py::test_animate_score_update_invalidates_diff_baseline` — seeds `_last_emitted_lines` to a non-None value, calls `animate_score_update` with `display_hud` and `time.sleep` stubbed, asserts the baseline resets to None.
  - `tests/belatro/test_belatro.py::TestEconomy::test_add_money_rejects_negative` — pins the new guard.
- **Test count baseline**: 933 → 939 (+6).
- **Version markers bumped**: `pyproject.toml` (`4.6.3` → `4.6.4`), `src/belote/__init__.py` (`4.6.3` → `4.6.4`).
- **Documentation accuracy sweep**: `README.md` and `DEVELOPMENT.md` test-count markers refreshed from 933 → 939, version refs from 4.6.3 → 4.6.4. README `Controls > General` entry for `I`/`V` corrected — pre-fix it said "Toggle BelAtro score overlay (per-trick breakdown popup)", which is the pre-4.6.3 behavior (the popup flash on `I` was removed in 4.6.3). Now references the BelAtro top-HUD toggle described in the gameplay section.

---

## [4.6.3] - 2026-05-17

Targeted UX fix — pressing `I` (or `V`) now actually toggles the BelAtro top-HUD overlay so the classic `Trump: …` indicator on row 1 is reachable. Before 4.6.3 the joker pip strip at `move(1, 2)` unconditionally painted over the leading ~24 chars of the classic HUD bar produced by `_build_hud()`, hiding `T:♥` and the leading score chunk; the `I` key was wired but only flashed a transient score popup (redundant with the row-3 chips×mult display) and had no effect on what was visible at rest. All baselines green: `ruff` 0 violations, `mypy --strict` 0 errors, `pytest` 933/933.

### Fixed

- **BelAtro top HUD covered the classic Trump/Taker bar with no way to hide it.** `render_joker_pip_strip` (`src/belote/belatro/ui/hud.py:275`) anchors at row 1 col 2 — exactly where the classic HUD's `T:♥ / NS:…` lives — and was rendered unconditionally after every `display()` via `BelAtroHUD.render` + the post-write inside `_show_overlay`. The taker letter at the tail (`Tk:S`) survived, but the trump suit symbol was clobbered. Reproducer captured in `screen-2026-05-17-17-24-43.jpg` shows the top row reading `BJ: [..][..][..][..][..]W:0(+16) 2/8 Tk:N` — a single `B` from `BELOTE`, then the joker strip, then the tail of the classic HUD with the trump field gone.

### Changed

- **`I` / `V` now toggles the BelAtro top HUD visibility** (joker pip strip, ante/blind/target line, chips×mult score, trust bar, synergy tooltip). Default = visible (no behaviour change at first paint); pressing the key hides them so the classic HUD's `Trump: ♥` and `Taker: NORTH` fields render in full on row 1. Pressing again restores the BelAtro overlays. New module-level flag `_top_hud_visible` in `src/belote/belatro/ui/announce.py` is independent of the existing `_overlay_visible` (still owned by `score_popup`'s transient flip).
- **`_show_overlay()` in `src/belote/belatro/main.py:204`** rewritten: calls `toggle_top_hud()` + `invalidate_diff()` + `display()` + render passes (which become no-ops when the flag is hidden). The transient `score_popup` flash on `I` is removed — the auto-popup at `on_trick_end()` (line 283) is untouched and continues to fire after every trick.
- **`render_joker_pip_strip` / `render_synergy_tooltip` / `TrustBar.render` / `BelAtroHUD.render`** all honour `is_top_hud_visible()` at their first statement, so any third-party caller of the helpers gets the same gate.
- **Classic HUD verbose hint string** (`src/belote/ui/render.py:922`) gained `[I]HUD` next to `[H]Hist [T]Theme [Z]Undo` so the new toggle is discoverable. Compact layout left alone (already at width limit).

### Internal

- **`tests/belatro/test_hud_toggle.py` (NEW, 7 tests)** — pins default visible, toggle flips/restores, joker pip strip is silent when hidden, joker pip strip paints `J:` and a `[` slot when visible, synergy tooltip silent when hidden, trust bar silent when hidden, trust bar paints `Trust:` when visible. Uses an autouse fixture that calls `reset_top_hud_state()` around each test so module-level flag state can't leak across the suite.
- **Test count baseline**: 926 → 933 (+7 in 4.6.3).
- **Version markers bumped**: `pyproject.toml` (`4.6.2` → `4.6.3`), `src/belote/__init__.py` (`4.6.2` → `4.6.3`).
- **Documentation accuracy sweep**: `README.md` and `DEVELOPMENT.md` test-count markers refreshed from 926 → 933, version refs from 4.6.2 → 4.6.3.
- **Plan file**: `/home/mrrobot/.claude/plans/home-mrrobot-belote-screen-2026-05-17-1-witty-lemon.md`.

## [4.6.2] - 2026-05-17

Deep-audit pass — full per-joker (42) + per-boss (21) walk of the BelAtro feature surface plus a classic-engine and UI-rendering pipeline pass. Three parallel Explore agents found one **HIGH** finding (an event-emit gap that let Le Mime's "declarations score 0" promise leak through the BelAtro accumulator path) plus a small set of defensive items. Two agent findings (L'Avocat description mismatch, "AI not in benchmark") were verified false positives and recorded so future audits don't re-flag them. The release also lands a per-joker / per-boss test matrix to mechanically catch the four foot-guns (seat-vs-team keying, re-emit guards, is_failed gates on cash, boss-flag awareness) on every future joker / boss added. All baselines green: `ruff` 0 violations, `mypy --strict` 0 errors, `pytest` 926/926.

### Performance

- **`src/belote/belatro/core/scoring.py` — `ScoreAccumulator` now mutates a `RoundLedger` instead of doing `dataclasses.replace(GameState, ...)` per event** (`src/belote/belatro/core/round_ledger.py`, new file, ~100 LOC). Pre-4.6.2 every event went through a final `replace(state, _chips=..., _mult=..., _bonus_money=..., _joker_state=...)` that built a fresh frozen GameState (~19μs × ~25 events ≈ 0.48ms per round, ~11% of `drive_round_ms`). 4.6.2 keeps the frozen invariant at round boundaries only: `trigger_round_start` does one `replace()` to install `ledger.joker_state` AS `state._joker_state` (same dict object), then `process_event` mutates the ledger in-place for the rest of the round, and `seal_round` does one final `replace()` to stamp `_chips`/`_mult`/`_bonus_money` into the canonical sealed state. Classic-Belote read sites (`ai.py`, `scoring.py`, `game.py`) reading `state._joker_state.get(...)` see live mutations without further replaces because the dict is shared. The HUD reads chips/mult/money via new accumulator getters (`current_chips()` / `current_mult()` / `current_money()`) instead of `state._chips` directly, so per-render materialize cost is zero. `update_state(state, event) -> GameState` is preserved as a backward-compat wrapper for ~100 unit tests that didn't go through `trigger_round_start` (the lazy-init path on the wrapper aliases the ledger's `joker_state` onto a fresh state via a one-time `replace`, restoring the shared-dict invariant). The `transactional()` context manager on `RoundLedger` preserves the pre-4.6.2 "raising handler doesn't leak partial joker_state mutations" guarantee via snapshot-on-entry / restore-on-exception.
- **`ScoreAccumulator.attach_jokers` — pre-resolved joker handler registry** (B.2). `_fire_jokers(method_name, event)` was doing `getattr(joker, method_name, None)` per joker per event in the hot path (~125 getattr calls per round); now `attach_jokers` builds a `dict[str, list[(joker, bound_method)]]` once, skipping jokers that didn't override the base `Joker.on_X` no-op (filter by `getattr(method, "__func__", None) is base_method`). Lazy rebuild on first `_fire_jokers` call protects tests that mutate `_jokers` directly.
- **`drive_round` no longer does the per-event replace**. The `_emit` helper now calls `acc.process_event(s, event)` and returns the state unchanged; classic-Belote reads pick up live joker_state mutations via the shared dict; `seal_round` runs once at the end of the round. Net measured change on the dev machine: `drive_round_ms: 4.21 → 3.67` (**−12.9%** over an 80-round sample). The remaining ~3.7ms is dominated by AI inference (3 seats × MEDIUM difficulty × 8 tricks ≈ 24 `decide_card` calls per round); further wins would need AI optimization, not event-bus refactors.
- **Le Fantôme partner personality cash payout** (`round_driver.py` line ~452, `+$1` on partner trick wins) was previously a `replace(state, _bonus_money=state._bonus_money + 1)` side-channel that bypassed the accumulator. 4.6.2 routes it through `acc._ledger.money += 1` so the source of truth stays consistent and the HUD's `current_money()` read sees it immediately. A fallback to the old replace path remains for callers without an accumulator.
- **`tests/perf_baselines.json`** updated to `drive_round_ms: 3.67` with `_history` line documenting the change. `_captured_version` bumped to `4.6.2`. 2.5× regression tolerance retained.

### Fixed

- **`src/belote/belatro/engine/round_driver.py` — `DeclarationScoredEvent.points` now zeroed when `state.boss_modifiers.declarations_zero` (Le Mime) is set**. Pre-fix, classic scoring honored Le Mime at `scoring.py::_carre_points` / `_sequence_points` (returning `(0, 0)` for declaration totals), but the BelAtro accumulator's `DeclarationScoredEvent` branch (`belatro/core/scoring.py:324`) still did `new_chips += event.points` on the raw declaration value, AND fired on_declaration jokers (LeMathematicien — pays ×2 Mult on multiple-of-5 declarations; QuinteRoyale — arms a ×4 round-end multiplier on declarations ≥ 100 pts) on raw points. Net player-visible effect: under Le Mime, a Carré of Aces correctly scored 0 in the final breakdown but still pushed +200 chips into the BelAtro running total and could arm a ×4 round multiplier. The fix is at the emit site (cleaner than per-joker gating because it propagates to every consumer of `event.points`): under `declarations_zero`, the emitted event carries `points=0`. TierceCharger continues to credit its charge — it's gated on `declaration_type` only, per its "announce" (not "score") description.
- **`src/belote/belatro/core/scoring.py:197` — `partner_tier` defensive clamp**. The tuple indexing `(0, 0, 1, 1, 2)[self.partner_tier]` would raise `IndexError` if a corrupted save or future mutation set tier > 4 or < 0. Now clamped via `max(0, min(self.partner_tier, 4))` so out-of-band tier values degrade gracefully to the nearest documented tier. Two regression tests pinned in `tests/belatro/test_joker_contracts.py` (`test_partner_tier_clamp_oob_high` / `_oob_negative`).
- **`src/belote/ui/render.py::patch_trick_card` — kept emitting card rows WITHOUT `clear_to_eol()`** (a fix proposed and then reverted in 4.6.2 after visual regression). A `clear_to_eol()` was briefly appended per face line to harden against row-shrink debris on terminal resize, but card patches are positioned at a specific column over the felt mat — `clear_to_eol()` then wipes felt-green cells to the right of every card face with the terminal's default background, leaving grey/black bars next to every patched card. The convention from `display()` diff rows only applies when the emit covers the full row width; per-card patches do not. Row-shrink debris on resize is handled by the existing `invalidate_diff()` call at the end of `patch_trick_card` — the next full `display()` repaints the row. Inline comment added to `render.py` pinning the rule so a future audit doesn't re-propose the same change.

### Internal — Audit Matrix & Test Coverage

- **`tests/belatro/test_joker_contracts.py` (NEW, 100 tests)** — pins each of the 42 jokers' happy-path trigger and at least one non-trigger gate, plus cross-cutting parametrized tests for the four audit foot-guns: (a) re-emit guards on state-mutating handlers (LeBanquier, CoincheStack, ToutStreak, QuinteRoyale, RebeloteEcho, LeCollectionneur), (b) `on_round_start` resets, (c) team_of vs seat-keying (LeDemon and LAccumulateur explicitly pinned as team-keyed; LeTraitre / LAgentDouble / LEgoiste as seat-keyed by design), (d) registry completeness (every joker has non-empty id/name). Two findings pinned without code change: `RebeloteEcho` / `LeNotaire` / `LeRebelle` gate seat=SOUTH only on belote/rebelote (NORTH-held trump K+Q never triggers them — `test_le_notaire_seat_keyed_north_no_op` documents the contract), and `LePatriote` uses raw `card_points()` not `card_points_with_modifiers()` (`test_le_patriote_uses_raw_card_points` pins the trump-bonus behaviour under zero-rank bosses).
- **`tests/belatro/test_boss_contracts.py` (NEW, 36 tests)** — pins each of the 21 bosses' `apply() → BossModifiers` flag mapping via parametrized table; BetrayalArc's three-flag composition; the Le Mime fix above; four high-risk boss combo flag-coexistence pins (LaRupture × LAnarchie, LaCompetition × LaMalediction, three zero-rank bosses, BetrayalArc × LaSolitude); and two anti-pattern locks that grep the actual source tree: `test_no_underscore_boss_read_pattern_in_src` rejects any `getattr(state, "_kings_zero", False)`-style read site (the 3.0.x foot-gun) and `test_no_boss_id_string_branching_in_runtime` rejects `boss.id == "..."` branching in runtime files.
- **Test count baseline**: 790 → 926 (+136 in 4.6.2).
- **Save/load schema migration shim verified live** at `belatro/progression/save.py::_migrate` (110-121) — already wired pre-4.6.2, no change needed. Confirms the audit's "add migration shim" hypothesis was a false positive.
- **Verified-false / pinned-against-re-flag** (audit returned and verified clean — listed here so a future audit pass doesn't waste cycles): `L'Avocat` triple-payout math at `main.py:444-446` (math AND description both say triple; verified), benchmark `drive_round_ms` excludes real AI (verified false — `round_driver.py:188-191` uses real `AIPlayer(Difficulty.MEDIUM)` for E/W/N), event_bus `re_emit` central guard at `core/scoring.py:382-383` for on_bid jokers (LePasseur is safe without a per-handler guard), every BelAtro boss flag has at least one canonical read site at `state.boss_modifiers.X` (no string-id branching detected by `test_no_boss_id_string_branching_in_runtime`).
- **Version markers bumped**: `pyproject.toml` (`4.6.1` → `4.6.2`), `src/belote/__init__.py` (`4.6.1` → `4.6.2`).
- **Documentation accuracy sweep**: `README.md` and `DEVELOPMENT.md` test-count markers refreshed from 790 → 926, version refs from 4.6.1 → 4.6.2.
- **Plan file**: `/home/mrrobot/.claude/plans/partitioned-cooking-hennessy.md`.

## [4.6.1] - 2026-05-17

Third audit / hardening pass — this one against the freshly-trimmed 4.6.0 baseline. Three parallel Explore agents (classic engine, BelAtro roguelite layer, UI/render layer) walked the codebase looking for bugs, mechanic gaps, and perf hot paths. Most flagged items resolved as **false positives** or **already-fixed in 4.5.1** once verified against current code; this release lands the two genuine findings and bumps the test count from 787 → 790. All baselines green: `ruff` 0 violations, `mypy --strict` 0 errors, `pytest` 790/790.

### Fixed

- **`src/belote/ui/menu.py` — `invalidate_diff()` on every overlay-bypass exit path**. Four classic-menu screens (`show_theme_selector`, `show_ai_config`, `show_main_menu`, `show_final_screen`) write directly to `sys.stdout` with `clear_screen() + sys.stdout.write(...) + flush()` and were not invalidating the render diff baseline (`render._last_emitted_lines`) before returning. The same overlay-bypass diff-skip class of bug that 4.0.0 fixed for `show_help`/`show_history`/`show_rules` (and that 4.6.0 preserved when it removed `show_card_detail`). The failure mode is latent because all four paths run before/after the gameplay `display()` loop, but it surfaces on **second-game-in-session** play: game-over → menu → start-game → the first `display()` of the second game diffs against the stale post-prior-game frame and emits only changed rows → first-frame artifacts. Now consistent with the rest of the codebase; the BelAtro overlays (`belatro/ui/menu.py:123`, `shop.py:309`, `consumables.py:70`, etc) already followed this pattern.

### Performance

- **`src/belote/belatro/ui/shop.py::ShopScreen._render` now batches its full frame into a single `sys.stdout.write` + `flush`** (was ~16 bare `print()` calls per redraw, each its own syscall). `_render_planet_card` and `_render_item_card` were refactored to return `list[str]` instead of emitting directly; `_render` accumulates everything (clear-screen prefix, title, money line, every card frame, action strip, description, hint row) into one `parts: list[str]` and writes once at the end. Mirrors the single-write convention used in `belatro/ui/hud.py::_render`, `belote/ui/announce.py`, and `prompts.py::show_help`. Not user-visible at terminal speeds — this is a consistency / convention fix.

### Internal

- **Tests**: 787 → 790. Three regression tests appended to `tests/test_render_diff.py`:
  - `test_show_main_menu_invalidates_diff_on_exit` — stamps a stale baseline, drives `show_main_menu` to its `Quit` exit via a `_QuitReader` stub, asserts `render._last_emitted_lines is None` afterward.
  - `test_show_theme_selector_invalidates_diff_on_exit` — same contract pinned independently so a future refactor of one path can't silently drop the other's guard.
  - `test_shop_render_writes_once_per_frame` — instantiates `ShopScreen` over a real `Shop(BelAtroRun(seed=42))`, wraps `sys.stdout` in a write-counting `StringIO`, asserts `_render()` produces exactly one write call (pre-4.6.1 this was ~16).
- **Version markers bumped**: `pyproject.toml` (`4.5.1` → `4.6.1`), `src/belote/__init__.py` (`4.5.1` → `4.6.1`).
- **Documentation accuracy sweep**: `README.md` — removed the `GRIMAUD Standard Playing-Cards-1898.png` entry from the file-tree block (image was deleted in 4.6.0 but the doc reference lingered), updated stale `792 tests` / `(4.5.1)` markers to `790 tests` / `(4.6.1)`. `DEVELOPMENT.md` — rewrote the *Current baseline* section to lead with 4.6.1, demoted 4.5.x / 4.6.0 to a *Previous baselines* list.
- **Audit verified healthy** (no change required — pinned here so the next audit pass doesn't re-flag them):
  - `game.py:278` `reset_round_fields` resetting `boss_modifiers` to defaults — by design. BelAtro applies boss flags AFTER `start_round` via `PatchedGameState.patch()` → `dataclasses.replace`. Classic mode doesn't use boss flags.
  - `LeCollectionneur` `re_emit` guard — already added in 4.5.1 (`annonces.py:129`).
  - L'Infiltré ghost-lead seat-walking loop (`core/scoring.py:285-295`) — correct as-is. Seat is walked from `event.leader_seat.next_seat()` per card; winner-check fires only when the iterating seat equals `event.winner` and the card is trump.
  - `_architecte_ns_annonce_cards` "dead pop" — not dead. Read live at `core/scoring.py:303` by the `annonce_cash_x2` branch.
  - `_card_points_with_zero_ranks` three-site consistency — covered by 3.9.3 + 4.1.0 wiring; flags flow through `card_points_with_modifiers` / `trick_card_points` uniformly. Zero changes needed in `ai.py` when a new zero-rank flag lands.
  - Voucher idempotency, render diff layer, theme palette caching, AI memo keys (`last_voids_key` / `last_partner_hand_key`), planet stacking, belote/rebelote under L'Anarchie, WASD reader aliasing.
- **Plan file**: `/home/mrrobot/.claude/plans/bug-hunt-code-performance-synthetic-pearl.md`.

## [4.6.0] - 2026-05-16

The **Grimaud Card Detail** feature shipped in 4.0.0 has been removed. The `F` key no longer opens a full-screen zoomed card view; the hand-drawn pixel-art module is gone. Other overlays (`?` help, `H` history, rules, theme cycle, `I`/`V` overlay) are unchanged.

### Removed

- **`src/belote/ui/card_detail.py`** — entire module deleted (silhouette templates, per-(rank, suit) palettes, held-object overlays, `_FACE_DESIGNS`, `_compile_art`, `_render_card`, public `show_card_detail`).
- **`Key.CARD_DETAIL` enum value + `f` binding** in `src/belote/input.py` (both Unix and Windows readers). The `f` key now falls through as a `Key.CHAR` and is unhandled by any prompt — a no-op.
- **`Key.CARD_DETAIL` case arms** in `prompt_card` and `prompt_bid` (`src/belote/ui/prompts.py`).
- **`[F]` help-screen entry** in `show_help` (`src/belote/ui/prompts.py`).
- **`tests/test_card_detail.py`** — all 5 tests deleted (shape, distinctness, key enum, dismiss, diff-baseline regression). Test count drops by 5 from the 4.5.1 baseline.
- **README mentions** of the `F` keybind and the Grimaud feature paragraph.

### Preserved (intentionally)

- **`render.invalidate_diff()`** stays — it is still used by `show_help`, `show_history`, and `show_rules` to fix the same latent diff-skip overlay bug. Only the docstring was updated to drop the `show_card_detail` reference.

## Pre-4.6.0 Releases — Condensed History

Detailed entries for releases **4.0.0 through 4.5.1** are condensed below to keep this file scannable. Each line summarizes the headline change(s); the git log carries the full implementation context.

### 4.x Series (pre-4.6.0)

- **[4.5.1] — 2026-05-16.** Audit pass; LeCollectionneur re_emit guard, L'Architecte deck description spells out "NS-won", `_record_belote_announcement` returns tuple directly (792 tests).
- **[4.5.0] — 2026-05-16.** Feature release: WASD navigation at the reader source, 2 new BelAtro decks (L'Infiltré, L'Architecte), 6 new "Conditional Engine" jokers (LeCavalierNoir, LArcEnCiel, LeCollectionneur, LeMathematicien, LEclat, LePreteur), bid quick-keys remapped A/S → X/N (790 tests).
- **[4.1.1] — 2026-05-16.** Audit pass; AI play heuristics route through `card_points_with_modifiers` so every zero-rank boss flag is honoured at play time (not just bid time), `fit_guard.require_minimum` and `show_stats` invalidate the diff baseline on exit, `show_stats` builds its line list once across keystrokes (751 tests).
- **[4.1.0] — 2026-05-15.** Audit/perf pass; LeDémon team-keyed (was seat-keyed and silently dropped North wins), Hard AI excludes Clubs under `ban_clubs`, `decide_card` asserts on empty `legal_cards` (was silently playing illegal), diff-emit appends `clear_to_eol` on row shrink, render perf wins (cached `theme_manager.current_name`, `_pip_at` `@lru_cache`, tuple `_last_emitted_lines`/`_pending_rendered_lines`), 5 defensive `re_emit` guards on state-mutating jokers (742 tests).
- **[4.0.1] — 2026-05-15.** Four diff-baseline fixes in the same family: writes that bypass `render.display()` were leaving the render-diff baseline out of sync with terminal state. `gameflow.py` stops writing raw `\r\n` (replaced by `announce()` / new `show_round_summary` modal), `patch_trick_card` invalidates diff, every BelAtro overlay (menu, shop, rules, history, collection, consumables) and every `BelAtroAnnounce` modal exit calls `invalidate_diff()` (723 tests).
- **[4.0.0] — 2026-05-15.** Major bump for the **Grimaud Card Detail** feature: `F` key opens a centered half-block pixel-art popup with 12 unique J/Q/K × suit illustrations loosely inspired by the Grimaud Standard 1898 plate; non-face cards get a procedural pip layout on the same canvas. Introduced `render.invalidate_diff()` as the canonical overlay-cleanup hook. (Feature subsequently removed in 4.6.0; the `invalidate_diff()` helper survives.) (716 tests).

---

## Pre-4.0.0 Releases — Condensed History

Detailed entries for every release before **4.0.0** are condensed below to keep this file scannable. Each line summarizes the headline change(s); the git log carries the full implementation context.

### 3.x Series

- **[3.9.5] — 2026-05-15.** Audit pass (5 agents); palette accessor fast path, `is_capot` accepts pre-computed winners, dead-helper cleanup in `ui/render.py`, 4 new invariant tests + 5 perf regression guards (711 tests).
- **[3.9.4] — 2026-05-15.** UI polish: 4 new themes (Forest Night / Moonlit Tavern / Royal Purple / Emerald Isle), felt vignette + braille pip texture + ornamented frame, hand-readout bar, auto-sort on prompt entry, stats screen splits "Discovered" vs "Unlocked" (702 tests).
- **[3.9.3] — 2026-05-15.** Multi-agent audit; AI bidding honors zero-rank bosses (R1), L'Anarchie preserves rebelote across rotation via new `belote_trump` field (R2), HUD disclaimer under Compétition (R3), LeBanquier gated on success+NS-taker (R4), voucher idempotency moved to base class (R5), render diff-emit layer added, Quinte Royale unlock wired, undo banner + skip to SOUTH, rematch removed (691 tests).
- **[3.9.0] — 2026-05-14.** Audit pass; `BelAtroAnnounce.yes_no` EOF fix, `NO_COLOR` env-var support, end-to-end belatro-round benchmark, declaration tie-break announce-order shared (661 tests).
- **[3.8.2] — 2026-05-14.** Audit polish: Tout Atout streak persistence, QuinteRoyale only arms on Quintes (not high-rank Carrés), LeNotaire/LeRebelle trigger on rebelote not belote, sequences >5 cards cap at Quinte, Carré scoring fix, Capot honors `no_dix_de_der` (655 tests).
- **[3.8.1] — 2026-05-14.** Audit pass; La Rupture consistency between `play_card` and `score_round` (CRITICAL), boss flags applied before `acc.trigger_round_start`, `TrickWonEvent.winner` is the resolved seat, LeRebelle/LeNotaire no longer double-fire on rebelote, LAgentDouble joker partner-sabotage wired (655 tests).
- **[3.8.0] — 2026-05-13.** UI-fit overhaul: croissant clip fixed, live "terminal too small" overlay (`fit_guard.py`), BelAtro screens converted to `vcenter_lines`, shop action buttons relocated; voucher idempotency guard at shop level, declaration zip-strict; AI partner_hand memoization, `_hard_bid` single-pass suit bucketing (650 tests).
- **[3.7.1] — 2026-05-13.** Audit + 3.7.0 deferred items; L'Accumulateur team-keyed (BA-L2), `ContractReward` float fields correctly annotated (BA-L1), `score_round` / `play_card` split via `_ScoringContext` / `_PlayContext`, achievement lookup via dict, partner-jokers coverage (9 jokers, 100% line coverage), NS-taker player surcoinche callback (635 tests).
- **[3.6.0] — 2026-05-12.** Audit; EW AI can coinche NS taker (Libra reachable, H1), synergy-ID validation survives `python -O` (H2), EventBus handler isolation (H3), zero-rank/`ban_clubs` consolidated to helpers, `Contract` enum, `sort_hand` lru_cache, `ContractReward` TypedDict (599 tests).
- **[3.5.0] — 2026-05-12.** Audit; consumables overlay reachable via `C` (C1), JSONL run-summary fsync (H1), `Key.EOF` distinct from ESC (H2), EventBus round-scope documented (H3), tied declarations to first announcer (M1), `RoundEndEvent.breakdown` typed, partner-tier scaling supersedes `partner_jokers_double` (deprecation warning), SA belote assertion hoisted (592 tests).
- **[3.4.2] — 2026-05-11.** Roadmap from 3.4.1; AI respects `hide_partner_hand` (C1), Dix-de-der announcement Rupture-aware (C3), `opp_trumps` excludes own/partner hand + TA-32-trump total (C4), 8 jokers migrated to `team_of` (H1), TournoiAnte pays real 50% (H4), `load_profile` keeps starter unlocks (H5), tie-on-target stats agree with menu (H7), `equip_joker(run=)` for purchase hook (H10), `advance_turn` dead-code removed (568 tests).
- **[3.4.1] — 2026-05-11.** Verification-only release; catalogued 7 confirmed bugs + 8 verified-false claims from an external audit (no source changes; 551 tests).
- **[3.4.0] — 2026-05-10.** Audit + endless-mode reliability + HUD polish; `BidMadeEvent` no longer double-fires on coinche (re-emit flag), endless mode enters at first-scaled-cycle, tie-breaker rounds play out, terminal-restore robust to broken pipes, shop selection clamp; joker pip strip + synergy tooltip + 4-tier trust bar (551 tests).
- **[3.3.4] — 2026-05-10.** Portability: terminal-bell / sound subsystem removed entirely (SIGSYS on Alpine 23/musl). `play_sound` / `is_muted` / `toggle_mute` / `AudioManager` / `Key.MUTE` all gone (549 tests).
- **[3.3.3] — 2026-05-10.** Audit-of-audit; `sort_hand` honors TA ladder (F1), boss assignment uses seeded RNG (F2), `LeJugement` filters to Commons (F3); invariant tests for scoring conservation, replay determinism, solo-half synergy (549 tests).
- **[3.3.2] — 2026-05-10.** Residual audit; `is_capot` Rupture-aware in both branches (F1), `replay.analyze_round` uses seeded RNG (F2), score popup clamps chips ≥ 0 (F3) (537 tests).
- **[3.3.1] — 2026-05-10.** Audit-of-audit; `trick_card_points` ban_clubs whole-trick parity (B1), per-round stats flush (B2), `fuse_jokers` carries edition + corrupted (B7), modifier_patch `python -O`-safe assert→raise (B9), unlock notifications queued not printed (B10), ante-themes wired (B14), trust-bar 3-tier color, La Rupture single-source winner helper, L'Anarchie `belote_announcer` field, AI RNG seeded, void-cache undo invalidation, hard AI under SA (535 tests).
- **[3.3.0] — 2026-05-10.** BelAtro history overlay: `[H]` in BelAtro mode opens a populated per-blind ledger via `BelAtroRun.history` + `set_history_override` hook (535 tests).
- **[3.2.0] — 2026-05-10.** Two-audit reconciliation (Qwen + Ring 1T); LaSentinelle / LeDernierMot / etc. team-keyed, LEgoiste chip clamp, NS-taker auto_coinche re-emits, registry duplicate-ID assertions, modifier_patch dynamic-fields, shop + tarots seeded RNG (528 tests).
- **[3.1.0] — 2026-05-08.** Audit-action; HUD multi-boss running total delegates to `trick_card_points`, shop slot-capacity above spend_money, TierceForge UI integration, scoring winners-threading, `update_state` shallow `dict()` copy, AI hot-loop allocation hoist, `modifier_patch` underscore shim retired (525 tests).
- **[3.0.3] — 2026-05-08.** Audit + doc fixes; README boss count 18→21, test count 435→510, full planning catalogue at `~/.claude/plans/bug-hunt-code-performance-atomic-sutton.md` (510 tests; no source changes).
- **[3.0.2] — 2026-05-08.** Audit; `GhostRecorder` wired via `BELOTE_GHOST=1`, `replay.analyze_round` wired via `BELOTE_REPLAY=1`, `score_round` pre-computes winners, `register_all_items` idempotent (510 tests).
- **[3.0.1] — 2026-05-07.** Post-3.0.0 audit; `play_card` HUD honors `aces_zero`/`jacks_zero`, HUD synergies use registered IDs, a11y trick announce uses `trick_card_points`, `last_voids_key` reset on new round, SA capot belote assertion (509 tests).
- **[3.0.0] — 2026-05-07.** Capot scoring per contract (220 SA / 348 TA / 252 normal), The Sun and Libra planets wired, Edition enum (Foil/Holo/Polychrome/Negative) at shop generation, three new boss flags (`aces_zero` / `jacks_zero` / `declarations_zero`), HUD synergy badges, 6 achievements, colorblind theme, `BELOTE_A11Y` screen-reader hints, replay analyzer, `GhostRecorder`, run_summary JSONL, post-Ante-8 endless prompt (489 tests).
- **[2.9.5] — 2026-05-07.** Keyboard shortcuts: `T`/`H`/`O`/`?` mapped properly, `s` returned to SA quick-bid, min-trick-dwell 0.5s; slot frames on trick mat; expanded `RoundScore` fields drive 8-column history table; full GRIMAUD-1898-inspired card art redraw (436 tests).
- **[2.9.2] — 2026-05-07.** Konsole render-pipeline fix; bidding selector painted inside render frame via `bid_selection`, every frame line `clear_to_eol`-terminated, prompt_bid no extra stdout writes (435 tests).
- **[2.9.1] — 2026-05-06.** UI polish: croissant Braille restored, cup-template width tightened, selected-row markers symmetric (435 tests).
- **[2.9.0] — 2026-05-06.** Tout Atout + Sans Atout bidding affordance ships end-to-end (round 2 only); 4 audit bugs fixed including `BidValue` typing, scoring `state.contract`-gated, AI three-tier TA/SA heuristics, partner TA/SA gated on `duo_contracts_available`; Le Fanatique + L'Idéologue jokers reachable (test count unchanged).
- **[2.8.0] — 2026-05-06.** Two audit sweeps; alt-screen pollution fixed (C1), AI threads `seven_eight_trump` everywhere (C2), `LeFou` re-applies last consumable (C4), `LePremierSang` keeps paying (H4), `LAgentDouble` sabotage decrements every trick (H5), `forge_tierce` uses Planet.use (H6), `LaVoute` max() floor (H7), atomic save (H10), undo clears legal-cards cache (H11), 19 dead-flag fixes (announce_x2 / no_belote_rebelote / republicain_wild / start_coinched / partner_throws_trick / gold_seal_aces / show_partner_bid_tendency / etc.) (409 tests).
- **[2.7.1] — 2026-05-04.** Cleared last `getattr(state, "_X", False)` boss-flag reads; deleted 17 redundant underscore property aliases on GameState; coverage for L'Anarchie rotation, endless mode, undo stack (390 tests).
- **[2.7.0] — 2026-05-04.** Responsive layout overhaul: COMPACT (80×32) / STANDARD (96×38) / SPACIOUS (120×48) presets, adaptive card art, vertical centering, alt-screen entered before menu loop, KeyReader `__new__` factory regression fixed.
- **[2.6.0] — 2026-05-04.** BelAtro Phase 0 audit + 6 feature areas: critical fixes (seeded `_rng`, OVERLAY-key UNDO collision, chute-config), `Suit.TOUT_ATOUT` enum value, coinche/surcoinche player flow, `BeloteAnnouncedEvent` emission, `Rarity`/`fusable`/`BelAtroRun` new fields, contract jokers (CoincheStack, ToutStreak), annonce jokers (TierceCharger, RebeloteEcho, QuinteRoyale), CapotInsurance + TierceForge vouchers, La Maison-Dieu + Le Diable tarots, marseille + coinche decks, trust-tier scaling, BetrayalArc boss, ante themes (CafeAnte, TournoiAnte), endless mode, joker fusion (361 tests).
- **[2.5.6] — 2026-05-03.** Massive crash + logic fix sweep: tarot `random` import, `BelAtroRun.consumables` list, `get_available_jokers(None)` accepts None, save schema merge, EventBus.unsubscribe ValueError suppress; LaSentinelle / LeFanatique / sans_atout_wins / LePuriste / LaSentinelleP / LeBanquier / LeDernierMot logic fixes; boss flag enforcement (LAvocat auto_coinche, LeDivorce trust lock, LAgentDoubleBoss 3-trick sabotage, LeBrouillard HUD hide, LeFantomePartenaire hand hide); permanent Tarot / Planet bonuses applied; corrupted joker negative effects wired; LaTelescope / LeGrimoire / LEncyclopedie / LesCartesDorees / LaBalance vouchers implemented.
- **[2.5.5] — 2026-05-03.** BelAtro run-loop crash fixes: `drive_round` signature mismatch, TrickWonEvent context fields, `consumable_slots`, legal-cards cache decorator, `[I]` HUD key.
- **[2.5.4] — 2026-05-03.** `read_timeout` missing on KeyReader, IndentationError in trick_timing, `LePremierSang` +2 Mult additive.
- **[2.5.3] — 2026-05-03.** IndentationError in `game.py` prevented startup.
- **[2.5.2] — 2026-05-02.** Critical winner-detection bug fixed; scoring engine desync resolved (state-differential trick points); declaration scoring uses real values; partner trust wired into BelAtro loop; AI personalities in bidding; dynamic partner hand visibility.
- **[2.5.1] — 2026-05-02.** Collection discovery on-encounter (not on-unlock); auto-save after run init + shop; trick visibility timing fix.
- **[2.5.0] — 2026-05-02.** Functional state architecture (immutable joker state in GameState); 50+ new BelAtro tests (276 total); benchmark suite in `scripts/benchmark.py`; scoring engine + Hard AI refactors; EventBus reliability.
- **[2.4.1] — 2026-05-02.** BelAtro rules-UI rendering bug + dynamic formatting.
- **[2.4.0] — 2026-05-02.** BelAtro Collection (Almanac); full 17-boss suite; Hard AI overhaul (Dix de Der awareness, 2-ply void inference); "You"/"Partner" labels; hotseat removed; unified save paths; menu streamlining.
- **[2.3.3] — 2026-05-02.** BelAtro integrated into main menu; WIP decks completed (L'Ermite, Le Vétéran, Le Flambeur); 50+ jokers fully implemented; alt-screen for BelAtro; dynamic UI centering; `RoundEndEvent` complete snapshot.
- **[2.3.1] — 2026-05-01.** SA trump-None handling; full Tout Atout / Sans Atout card values; Coinche (×2) / Surcoinche (×4) multipliers; sequence detection refactor; project-wide type safety (250+ mypy errors resolved).
- **[2.3.0] — 2026-05-01.** Full Tarot system (10 cards); complete Voucher set (9 vouchers); dynamic deck-building; Corrupted Joker mechanics; +52 new tests (165 total); opponent Coinche; `[U]` consumable key; render cache size 2048.

### 2.0–2.2 Series

- **[2.2.0] — 2026-04-30.** BelAtro score-overlay toggle on `[I]`; 4th-card trick visibility fix; `on_card_played` reconstructs from `completed_tricks[-1]`.
- **[2.0.1] — 2026-04-30.** Le Républicain deck fully playable; Le Carnet voucher implemented; card-count invariant assertion; immediate trick-mat render.
- **[2.0.0] — 2026-04-30.** **BelAtro Expansion launched.** 8-Ante run structure, Chips × Multiplier scoring, 50+ Jokers, Planets / Tarots / Vouchers, Partner Trust system, 10+ Boss Blinds, `EventBus` architecture, save/load, dedicated BelAtro HUD + Shop UI; `belatro` CLI entry point.

### 1.x Series

- **[1.1.0] — 2026-04-30.** Incremental AI void inference; Windows `read_timeout` for KeyReader; `ScoringBreakdown` refactor (table vs credit pts); primitive cache keys for `trick_winner_seat`; centralized `_TRICK_ROW_OFFSETS`; chute-vs-litige comparison fix; circular import via observer callback.
- **[1.0.0] — 2026-04-30.** Official FFBelote rules compliance; **Litige** tie-break implemented; **Capot** = 252 (152 + 100 bonus) with all declarations to winners; chute scoring 162 + defender_declarations; tie-breaker rounds beyond target; `CAPOT_BASE` 250→252.

### 0.9.x Series — Pre-1.0

- **[0.9.9] — 2026-04-28.** Chute scoring fix (taker declarations annulled, not transferred); Belote announcement no longer re-fires; hand-sort persisted via `prompt_card` return; multi-byte UTF-8 input; project-wide type safety (70 mypy + 243 ruff resolved).
- **[0.9.8] — 2026-04-28.** Overtrump rule enforcement; real-time AI void inference; `TOTAL_POINTS` = 152; interruptible announcements (Space/Esc); adaptive `patch_trick_card` coordinates.
- **[0.9.7] — 2026-04-27.** Pre-game hand preview; strategic hand sorting; medium AI void tracking; configurable per-seat AI; `IllegalMoveError`; centralized `Config`; XDG-compliant stats path; module-global state replaced with managers.
- **[0.9.6] — 2026-04-27.** Per-difficulty win-rate stats; session-stats panel; medium-AI longest-suit leading; Hard AI 2-ply lookahead + void inference; non-UTF-8 graceful degradation; UI modularization into `belote.ui` package.
- **[0.9.5] — 2026-04-26.** Hand sorting on `O`; quick-help on `?`; mute toggle on `M` (later removed in 3.3.4); declaration announcements; incremental rendering (zero flicker); LRU caching for legal cards; CLI `--version`.
- **[0.9.4] — 2026-04-26.** Round-score history (`H`); global stats screen; hotseat 2P mode (later removed in 2.4.0); undo support (`Z`); terminal sound effects (later removed in 3.3.4); seat-specific AI difficulty; animation skipping.
- **[0.9.2] — 2026-04-26.** Fixed `ValueError: max() iterable argument is empty` in `legal_cards` when trump is led.
- **[0.9.1] — 2026-04-26.** Fixed `ModuleNotFoundError` from absolute imports in `game.py`.
- **[0.9.0] — 2026-04-26.** Initial release: full-screen TUI for French Belote; AI Easy/Medium/Hard; bidding + scoring; EN/FR rules; `src` layout; GitHub sync.
