# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.3.2] - 2026-05-10

Residual-audit release — a fresh full-codebase pass after 3.3.1 turned up three real findings (a HIGH live-HUD divergence under La Rupture, a MEDIUM determinism leak in `replay.analyze_round`, and a LOW cosmetic chips display). The same pass flagged ~5 plausible-sounding "performance wins" and other claims that fell apart on verification — catalogued in the plan file at `/home/mrrobot/.claude/plans/bug-hunt-code-performance-cheeky-globe.md` so they aren't re-investigated. 537 tests passing (up from 535), ruff and mypy strict still clean.

### Fixed

- **`src/belote/scoring.py::is_capot` + `src/belote/game.py::compute_trick_winners` (F1)** — `is_capot(state, tricks=[…])` now honors La Rupture (`no_consecutive_team_wins`) in the explicit-tricks branch, matching the default-branch behaviour the 3.3.1 La Rupture fix established. The 8th-trick live-HUD CAPOT announcement (`gameflow.py:211-217`) passes an explicit list (`completed_tricks + [current_trick]`) and previously re-derived winners with raw `trick_winner_seat`, falsely shouting "CAPOT!" under La Rupture even though the final score correctly resolved as non-capot. Fix: `compute_trick_winners` now accepts an optional `tricks` override and `is_capot` delegates both branches through it — single source of truth for Rupture-aware winner resolution. Regression test in `tests/belatro/test_boss_modifiers_integration.py::test_is_capot_honors_rupture_in_explicit_tricks_branch`.
- **`src/belote/replay.py::analyze_round` + `src/belote/gameflow.py` (F2)** — The 3.3.1 fix made `AIPlayer.__init__` accept a seeded `rng` parameter; the round driver threaded it through, but `replay.analyze_round` kept the legacy unseeded fallback. Post-round replay analysis on the 'R' key thus ran the Hard AI with an unseeded `random.Random()`, so "Optimal plays: 6/8 (75%)" could become "5/8 (62%)" between consecutive runs on the same data — most visibly under Sans Atout, where `_hard_play` falls through to `_easy_play` and `rng.choice(legal)` is the sole arbiter. Fix: `analyze_round` takes an optional `rng`, and the gameflow caller passes `current._rng` from the final round state. Regression test in `tests/test_replay.py::test_analyze_round_deterministic_under_seeded_rng`.
- **`src/belote/belatro/core/scoring.py::get_popup_lines` (F3)** — Score popup now displays clamped chips (`max(0, state._chips)`) to match `get_total()`'s clamp boundary. Pre-3.3.2 L'Égoïste partner-win-heavy rounds rendered "Chips -12 × Mult 2.0 = 0" — internally consistent but visually a bug. Cosmetic only; no logic change.

### Internal

- **Tests**: 535 → 537 (+2 regressions for F1 and F2).
- **Strict gates**: pytest 537/537, mypy 0 errors (76 files), ruff 0 violations.
- **`compute_trick_winners` signature widened**: optional `tricks` parameter (default `None` preserves the existing behaviour). Single source of truth for La Rupture-aware winner resolution across both live-HUD and final-scoring paths.

### Rejected — performance "wins" catalogued (so they aren't re-investigated)

- **"`_hard_play` recomputes `Counter` per candidate card"** — falsified. `hand_suit_counts` is hoisted at `ai.py:531` *before* the `for card in legal:` loop and threaded into `_score_card_play` as a parameter.
- **"`score_round` walks tricks 4×"** — falsified post-3.2.0. `winners` is computed once at `scoring.py:600` and threaded into `_calculate_base_points` and `_apply_scoring_modifiers`. Remaining trick-count passes are two cheap `sum(1 for …)` walks of an 8-element list.
- **"`play_card` does a wholesale `replace()`"** — true but irreducible. Frozen+slotted GameState is a deliberate design choice; the "fix" would re-introduce the mutation class of bugs the 2.x rewrites eliminated.
- **"`stats.py` per-round full-rewrite is a regression"** — falsified. It's the B2 (3.3.1) fix for crash-safety, intentional.
- **"Event-bus `list(self._handlers)` per emit is wasteful"** — defensive copy enabling sub/unsub during emit. Handler counts are static and tiny.

## [3.3.1] - 2026-05-10

Audit-of-audit release — an inbound LLM audit produced a 18-bug list with mixed accuracy (B1/B2/B7/B8/B9/B10/B14/B16/B17 real; B3/B5/B12/B18 and the ruff-violation claim either self-refuted or hallucinated). The verified subset was fixed, then a fresh independent pass turned up seven additional high-confidence bugs the original audit missed — chiefly La Rupture and L'Anarchie scoring divergences, an unseeded AI RNG that broke ghost-run determinism, and a stale-void inference leak across mid-round undo. All 17 fixes ship in this release. 535 tests passing, ruff and mypy strict still clean.

### Fixed — audit findings

- **`src/belote/scoring.py::trick_card_points` (B1)** — `ban_clubs` zero rule now matches `_calculate_base_points`: the whole trick zeros when *any* card is a club, not just when the lead is. Pre-3.3.1 the live HUD running total diverged from the final round score whenever a non-lead card was a club under the `LesClubsBannis` boss.
- **`src/belote/stats.py::StatisticsManager.update_stats_round` (B2)** — Now calls `flush_stats()` after every round, not just at end-of-game. A crash between rounds no longer silently loses round-level stats and achievement unlocks.
- **`src/belote/belatro/items/base.py::fuse_jokers` (B7)** — Fused joker now carries over the better edition of the two inputs (POLY > HOLO > FOIL > NONE; NEGATIVE collapses to NONE since its slot bonus was already granted at purchase) and inherits `is_corrupted` if either input was corrupted. Pre-3.3.1 `type(a)()` returned a class-default instance, silently erasing any Foil/Holo/Polychrome the player had paid for.
- **`src/belote/belatro/ui/rules.py` (B8)** — Reroll cost doc text now reads `$5` to match `Shop.reroll_cost = 5` in code.
- **`src/belote/belatro/engine/modifier_patch.py::patch` (B9)** — Replaced `assert not attr.startswith("_")` with an explicit `if … raise ValueError(...)`. The `assert` was strippable with `python -O`.
- **`src/belote/belatro/progression/unlocks.py` + `src/belote/belatro/main.py::BelAtroGame._drain_unlock_announcements` (B10)** — Unlock notifications no longer `print()` raw to stdout (which scrolled and corrupted the alt-screen). Notices are queued on `UnlockTracker.pending_announcements` and drained by the host loop through `BelAtroAnnounce.banner`.
- **`src/belote/belatro/run/ante_themes.py` + `src/belote/belatro/main.py::_play_blind` + `src/belote/belatro/core/run_state.py::target_score` (B14)** — The Phase 3.1 ante-themes module is now wired into the live game loop: `roll_theme(rng_value)` fires at the start of each ante (`blind_index == 0`) using the run's seeded RNG, `target_score` applies the theme's `target_multiplier(blind_index)`, and `on_blind_won` runs after each successful blind. Tests already covered the module in isolation; production code never invoked it.
- **`src/belote/belatro/ui/trust_bar.py` (B16)** — Three-tier color: ≤3 red, 4–6 gold (neutral), ≥7 green. Default trust value 5 used to render red under the old `> 5` threshold, falsely signalling distrust at the start of every run.
- **`src/belote/belatro/partner/personality.py::should_coinche` (B17 + wiring gap)** — Signature now takes a `Random` parameter; `LeFlambeur` consumes the round-driver's seeded RNG instead of the bare module-level `random.random()`. The round driver (`engine/round_driver.py:215-235`) also now calls `partner.personality.should_coinche(state, rng)` when the human player declines a coinche on an EW taker, giving the AI partner a chance to act on its own initiative (gated by `partner.trust.ai_degraded`). Pre-3.3.1 `should_coinche` had no production caller at all.

### Fixed — independent bug-hunt pass (not in original audit)

- **`src/belote/scoring.py::compute_trick_winners` (new helper in `game.py`) — La Rupture scoring divergence** — `play_card` reassigned the trick winner for the live HUD whenever `no_consecutive_team_wins` (La Rupture boss) would flip the win, but `score_round`, `_calculate_base_points`, `_apply_scoring_modifiers`, and `is_capot` all re-derived winners via raw `trick_winner_seat` calls — silently restoring the un-flipped winner and producing impossible capots / double-credited rounds. A new `compute_trick_winners(state, trump, is_sa)` helper in `game.py` carries the Rupture rule once and is used by every scoring path. Live HUD and final score now agree under La Rupture.
- **`src/belote/game.py::GameState.belote_announcer` + `src/belote/scoring.py::score_round` — L'Anarchie + Belote/Rebelote** — Under L'Anarchie (dynamic trump), `state.trump` rotates mid-round. Scoring's `belote_holders.get(state.trump)` lookup then keyed on the *post-rotation* trump and missed any Belote announced on the original trump, silently zeroing the 20/40 bonus. New `belote_announcer: Seat | None` field on `GameState` captures the announcing seat at the moment `belote_tracker[0]` flips True; scoring reads it directly instead of going through the rotated-trump lookup.
- **`src/belote/scoring.py::score_round` chute branch — `no_dix_de_der` ignored on chute** — The chute formula at line ~774 unconditionally added `LAST_TRICK_BONUS` (+10) to the defender total, even when the `Le Zéro Final` boss was active. The in-round path at line ~606 already gated the bonus on `no_dix_de_der`; the chute branch is now gated symmetrically.
- **`src/belote/scoring.py::_apply_scoring_modifiers` — La Compétition (`separate_scoring`) parity** — Two parallel bugs to B1 / the chute fix above: (a) the separate-scoring branch zeroed only the *lead-clubs* trick under `ban_clubs` (same divergence we fixed in `trick_card_points`); (b) it unconditionally added +10 de der to the individual last-trick winner, ignoring `no_dix_de_der`. Both now mirror the main scoring path.
- **`src/belote/ai.py::AIPlayer.__init__` + `src/belote/belatro/engine/round_driver.py` — AI RNG was unseeded** — `AIPlayer.__init__` constructed `random.Random()` (no seed) regardless of the round's seed. Easy-AI random plays, personality jitter, and any other stochastic AI decision randomised per process even at a fixed run seed — silently breaking ghost-run reproducibility, replay determinism, and seeded benchmarks. The round driver now passes its seeded `rng` into every AIPlayer it constructs; the constructor accepts an optional `rng` arg with the old unseeded `Random()` as fallback for legacy callers.
- **`src/belote/ai.py::AIPlayer.update_memory` — stale void inference across undo** — `known_voids` and `processed_tricks_count` were monotonic; a mid-round undo (which reverts `state` from `gameflow.history`) left voids inferred from now-rolled-back tricks in place, causing the AI to misplay based on cards that no longer existed in the game. `update_memory` now detects regression (current `(completed_count, current_trick_len)` strictly less than `last_voids_key`) and rebuilds the inference set from the live state.
- **`src/belote/ai.py::_hard_play` — first-legal-card under Sans Atout** — `_hard_play` bailed to `return legal[0]` when `state.trump is None` (the legitimate SA contract), making hard AI strictly worse than medium under SA — `_medium_play` falls through to `_easy_play` (uniform random) in the same case. Hard now does the same; the deterministic-worst-case path is gone.

### Internal

- **Tests**: 535 / 535 still passing.
- **Strict gates**: mypy 0 errors (75 files), ruff 0 violations.
- **One new GameState field**: `belote_announcer: Seat | None = None`, threaded through `play_card` and `reset_round_fields`. Default-None matches pre-3.3.1 serialisation for the legacy non-Anarchie path.
- **One new public helper**: `belote.game.compute_trick_winners(state, trump, is_sans_atout) -> list[Seat | None]` — the single source of truth for La Rupture-aware winner resolution. `play_card`'s own Rupture branch is retained for the live HUD; the helper is what scoring now uses.

## [3.3.0] - 2026-05-10

BelAtro history overlay release — the [H] key in BelAtro mode now opens a populated, run-aware overlay instead of always showing "No rounds completed yet." Classic Belote's H-key path is unchanged. 535 tests passing (up from 528), ruff and mypy strict still clean.

### Fixed

- **`src/belote/belatro/ui/history.py` (new) + `src/belote/belatro/core/run_state.py::BelAtroRun.history` + `src/belote/belatro/main.py::BelAtroGame._record_history_entry`** — Pressing **H** in BelAtro now shows a per-blind ledger (ante, blind label, target, boss, taker, contract, score, status, money Δ, declarations) instead of an empty "No rounds completed yet." screen. Root cause: the classic [H] overlay (`belote.ui.prompts.show_history`) reads `state.score_history`, but the BelAtro round driver (`belatro.engine.round_driver.drive_round`) never invokes `apply_round_score` — the sole writer of `score_history` — and the existing BelAtro `on_round_end` callback was just `pass`. Fix: `BelAtroRun` now carries a parallel `history: list[BelAtroHistoryEntry]`, populated after each round in `_play_blind` from the score breakdown + run snapshot, and rendered by the new `show_belatro_history` overlay (wide table on ≥90-col terminals, three-line-per-row compact layout below).

### Added

- **`src/belote/ui/prompts.py::set_history_override`** — Module-level hook the BelAtro launcher installs in `BelAtroGame.start` (closure over `self.run.history`) and clears in its `finally` block. `show_history` short-circuits to the override when set, otherwise falls through to the classic `state.score_history` renderer. This is the seam that lets BelAtro own its overlay without forking `prompt_card` or threading a renderer through every UI call site.
- **`tests/belatro/test_history_overlay.py`** — 7 new tests covering `BelAtroRun.history` default-empty, the four status branches (WON / FAILED / CAPOT / SURVIVED), and the override hook's routing + cleanup contract. An autouse fixture clears `_history_override` between tests so leaks across the test session are impossible.

### Internal

- **Tests**: 528 → 535 (+7).
- **Strict gates**: pytest 535/535, mypy 0 errors, ruff 0 violations across `src/` and `tests/`.

## [3.2.0] - 2026-05-10

Two-audit reconciliation release — the prioritized fix list distilled from Qwen 3.6 27B + Ring 1T audits (~30 raw claims, ~half held up under verification). Twelve real bugs fixed across joker logic, registry hygiene, RNG determinism, and UI offsets; one new finding (Tarot RNG was also unseeded) caught by the fresh-hunt pass. Eleven audit claims rejected as false positives are catalogued in the plan file so they aren't re-investigated. 528 tests passing (up from 525), ruff and mypy strict still clean.

### Fixed

- **`src/belote/belatro/items/jokers/hand_comp.py::LaSentinelle`** — Detection of the trump Jack now keys on the NS *team* via `team_of(seat) == 0` instead of `seat == Seat.SOUTH`. Pre-3.2 the joker was silently no-op when North (the partner) was dealt the trump Jack, even though Belote's "you" is team-level. Trick-win detection follows the same team rule. Regressions: `tests/belatro/test_dead_flag_fixes.py::test_la_sentinelle_arms_when_partner_plays_trump_jack`, `test_la_sentinelle_does_not_arm_for_opponent_jack`.
- **`src/belote/belatro/items/jokers/trick_timing.py::LeDernierMot`** — Dix de Der replacement now fires whenever the NS team wins the last trick (`team_of(event.winner) == 0`), not only when South personally takes it. Pre-3.2 the joker silently did nothing when partner won the closing trick. Regressions: `tests/belatro/test_belatro.py::TestLeDernierMot::test_north_last_trick_returns_result`, `test_east_last_trick_returns_none`.
- **`src/belote/belatro/items/jokers/corrupted.py::LEgoiste` → `src/belote/belatro/core/scoring.py::ScoreAccumulator.get_total`** — Final chip total is now `max(0, state._chips)`. L'Égoïste subtracts `event.card_points` for every partner-won trick; with enough partner wins the running total could cross zero, producing a negative final round score. Clamping at the scoring boundary preserves the intermediate accounting log while guaranteeing the visible score is never negative.
- **`src/belote/belatro/engine/round_driver.py:236-249`** — NS-taker `auto_coinche` path now re-emits `BidMadeEvent` with the new `coinche_level` so jokers/HUD subscribed to `on_bid` see the bump. The EW-taker branch above always emitted; this NS-side branch silently set `coinche_level = 1` without notifying subscribers.
- **`src/belote/belatro/core/run_state.py::BelAtroRun.advance_blind`** — Victory now sets both `run_won = True` and `run_over = True`, so downstream callers can rely on `run_over` alone as the terminal-state signal. `enter_endless()` resets both, re-opening the run for endless mode. Pre-3.2 the main loop only terminated via a `break` after a `run_won` check — semantically correct but fragile under refactors.
- **`src/belote/belatro/items/registry.py::ItemRegistry.register_*`** — All four register methods (`joker` / `planet` / `tarot` / `voucher`) now assert that an existing entry under the same `id` is the *same class*. Pre-3.2 a typo'd duplicate ID would silently overwrite the prior class, and the override would never surface until the original behaviour visibly broke. Idempotent re-registration of the same class still works for the test-suite swap pattern.
- **`src/belote/belatro/engine/modifier_patch.py`** — `boss_fields` is now derived from `BossModifiers`' dataclass fields via `dataclasses.fields(BossModifiers)` instead of a hardcoded set. Pre-3.2 a new boss flag added to `BossModifiers` would be silently no-op'd until someone remembered to add it to the hardcoded allowlist in lock-step.

### Determinism

- **`src/belote/belatro/run/shop.py::Shop.generate_inventory`** — All RNG calls (`random.random` / `random.choice` / `random.sample` across edition rolls, joker pick, tarot/planet pick, voucher pick) now use `self.run._get_rng()` instead of the module-level `random`. Pre-3.2 shop contents were non-deterministic even with a seeded run, which broke ghost-run reproducibility. `Shop._roll_edition` signature changed to accept an explicit `rng` argument; the `test_shop_edition_weights_match_distribution` test was updated to pass the seeded RNG directly instead of monkey-patching `shop_mod.random.random`.
- **`src/belote/belatro/items/tarots.py`** — `LeJugement`, `LaPretresse`, and `LeFou` all now draw from `run._get_rng()` instead of the module-level `random`. Module-level `import random` removed.

### Improved

- **`LaPretresse` planet picks now deduplicate** — switched from two independent `random.choice(planets)` calls to `rng.sample(planets, k=2)`, so the tarot can no longer pick the same planet twice. Falls back to a single pick when the planet pool has fewer than 2 entries.
- **`LeJugement` slot-full notification** — new `BelAtroRun.last_tarot_message: str | None` field carries a non-fatal failure reason ("joker slots are full — no joker granted") when the tarot can't complete. Pre-3.2 the joker was silently dropped with no UI signal. Cleared whenever a tarot is used.
- **`src/belote/ui/render.py::patch_trick_card`** — Now reads `_last_rendered_unpadded_h` (set by `render()`) and threads it into `_calculate_base_row`, so single-card patches re-apply the same vertical-centering offset `render()` used. Pre-3.2 it passed the "I don't know" sentinel (0) and skipped the offset entirely, drawing cards too high on tall terminals (>40 rows).
- **`src/belote/ui/layout.py`** — `hud_style` docstring corrected. Pre-3.2 it claimed `"verbose" / "standard" / "compact"`, but no preset used `"standard"` and no consumer recognized it — only `"verbose"` and `"compact"` are real.

### Rejected (catalogued so they aren't re-investigated)

Eleven claims from the input audits were rejected after verification against the actual code:

- LaBalance voucher (`tie_breaks_for_taker`) and LaCompetition (`separate_scoring`) flags — **both consumed** in `src/belote/scoring.py` and `src/belote/belatro/main.py`. Qwen flagged both as P0 dead-flag bugs; verification falsified both.
- LeFou tarot "chain broken" — `run_state.py::consume` sets `last_consumable_id` *before* `item.use()` runs, so chaining works as intended.
- `no_belote_rebelote` deck-mod flag — consumed at `src/belote/scoring.py:630`.
- `_pending_tierce_charge` cross-round leak — each blind constructs a fresh `ScoreAccumulator` (main.py:126) and `drive_round` builds a fresh `GameState` via `new_game()` (round_driver.py:84), so `_joker_state` is empty at every round start. No cross-round persistence path exists.
- `fuse_jokers` "loses `on_purchase` effects" — `on_purchase` mutates `run` state (which survives fusion); re-applying on the fused instance would *double-apply* cumulative effects (LeDemon's trust drop). Pre-3.2 behaviour is correct.
- IllegalMoveError in `round_driver.py:291` — reachable only via test MockCallbacks; production `prompt_card` has a guard.
- `_card_beats` defensive `assert trump is not None` — unreachable under current contract invariants.
- `display_hud` no clear-to-EOL — HUD is rebuilt fresh per call; the claim was wrong.
- Libra planet description — "×4 instead of ×3" matches the payout; mechanism is additive per coinche level but the description references the result.
- `get_total()` float precision — explicit `int()` guard at scoring.py:248-249.
- KeyboardInterrupt save — profile is saved *before* the loop starts; only intra-run delta is lost.

### Internal

- **Tests**: 525 → 528 (+3 net: −1 test renamed/repurposed for LeDernierMot team check, +2 new for La Sentinelle partner-detection and EW opponent rejection).
- **Strict gates**: pytest 528/528, mypy 0 errors, ruff 0 violations across `src/` and `tests/`.
- **Audit plan**: `~/.claude/plans/between-these-two-plans-graceful-puppy.md` — captures the two source audits, the verification pass that filtered them, the implementation order, and the catalogue of rejected claims.

## [3.1.0] - 2026-05-08

Audit-action release — implements the prioritized fix list from 3.0.3. One real correctness bug fixed, one unreachable feature wired up, one money-leak path closed, three measurable perf wins, and the long-standing `modifier_patch` underscore shim retired. 525 tests passing (up from 510), ruff and mypy strict still clean across 75 source files.

### Fixed

- **`src/belote/game.py:843-855` (HUD multi-boss running total)** — Under `Les Clubs Bannis + Le Roi Mort` (or any combo of `ban_clubs` with a rank-zero boss), the live HUD running total in `play_card` over-credited a clubs-led trick: the `ban_clubs → trick_pts = 0` branch was immediately overwritten by the rank-zero recompute. The eventual round score was already correct (different code path through `scoring.py`). Now `play_card` delegates to `scoring.trick_card_points`, the canonical helper that composes every boss zero-rank flag, `ban_clubs`, and the SE-trump scale in a single pass — the HUD cannot drift from the round score under any boss combo. Regression: `tests/test_official_rules.py::test_hud_running_total_under_multi_boss_ban_clubs_plus_kings_zero`.
- **`src/belote/belatro/run/shop.py::buy_item` (consumable money-leak)** — Slot-capacity check is now hoisted *above* `Economy.spend_money`. Pre-3.1.0 the player's money was charged for a Tarot/Planet purchase even when consumable slots were full, and the item was silently dropped. New `Shop.last_buy_failure: str | None` carries the reason ("slots_full" / "no_money") so the shop UI surfaces a `BelAtroAnnounce.banner("Slots full — sell first")` banner. Regressions: `tests/belatro/test_belatro.py::TestShop::test_buy_consumable_with_full_slots_does_not_charge_money`, `test_buy_joker_with_full_slots_does_not_charge_money`, `test_buy_item_no_money_records_no_money_failure`.

### Added

- **TierceForge UI integration** (`src/belote/belatro/ui/shop.py`) — The `TierceForge` voucher shipped in 3.0.0 with a working `forge_tierce(run, planet_id)` backend (`src/belote/belatro/items/vouchers.py:129`) but no UI caller; the feature was unreachable. The shop now shows a "Forge ×N/3" tile when the voucher is owned, opens a numbered planet picker on Enter, and surfaces a confirmation banner on success. Regressions: `tests/belatro/test_phase2_content.py::test_forge_tierce_voucher_spends_charges_and_levels_planet`, `test_forge_tierce_blocked_when_charges_below_three`.
- **Block-policy regressions for Tarot overflow** — `LeJugement` and `LaPretresse` are now pinned to no-op when joker/consumable slots are at capacity (rather than partial-grant). Tests: `test_le_jugement_no_op_when_joker_slots_full`, `test_la_pretresse_no_op_when_consumable_slots_full`.
- **`tests/belatro/test_phase1_plumbing.py::test_joker_state_only_contains_scalar_values`** — Walks every registered joker through `on_round_start` + four event hooks and asserts no mutable container leaks into `_joker_state`. Locks the contract that lets the per-event copy stay shallow (3.1.0 dropped the deepcopy).
- **`tests/belatro/test_phase1_plumbing.py::test_shop_edition_weights_match_distribution`** — 10 000-roll empirical check on `Shop._roll_edition()`, ±1% per bucket. Catches accidental edits to the `_EDITION_WEIGHTS` table.
- **`tests/belatro/test_phase3_meta.py::test_endless_ante_target_scaling`** + `test_endless_ante_offset_zero_matches_base_table` — pin the `100 × 1.5^(ante-1) × blind × 2.2^offset` formula and the static-table parity invariant.
- **`tests/belatro/test_phase2_content.py::test_le_fou_no_prior_consumable_falls_back_to_random_tarot`** — covers the `last_id == self.id` defensive branch in `tarots.py::LeFou.use`.
- **`tests/belatro/test_boss_modifiers_integration.py::test_invariant_no_underscore_boss_attrs`** — anti-pattern lock for the architecture-pinned rule that boss flags must be reached via `state.boss_modifiers.X`, never `getattr(state, "_X", False)`.

### Improved

- **`src/belote/scoring.py` (winners-threading)** — `score_round` already pre-computed the per-trick winner list (3.0.2); the residual `trick_winner_seat` recomputations in the Malédiction branch (lines 776-793) and `apply_round_score` (lines 843-855) are now eliminated. Per-team trick counts ride on the new `ScoringBreakdown.tricks_ns` / `tricks_ew` fields (default 0; `apply_round_score` falls back to walking when a hand-constructed breakdown leaves them at default). Net: ~16 fewer `trick_winner_seat` calls per round.
- **`src/belote/belatro/core/scoring.py::ScoreAccumulator.update_state` (deepcopy → shallow)** — Replaced the per-event `copy.deepcopy(state._joker_state)` with `dict(state._joker_state)`. All current `_joker_state` writers store scalars (bool/int/str), so the deep-copy was over-defensive — and ran ~20×/round. Module-level `import copy` and `from dataclasses import replace` removed (they were also reimported inside two methods). Contract is locked by the new scalar-invariant test.
- **`src/belote/ai.py` (Hard AI hot-loop allocations)** — `_hard_play` precomputes `hand_suit_counts: Counter[Suit]`, `my_trumps`, `opp_trumps` once per turn and threads them into `_score_card_play` / `_score_leading_strategy` / `_score_discarding_strategy`. Pre-3.1.0 these counters were rebuilt for every candidate card — a four-card legal set walked the hand and `memory.played` four times each.
- **`@dataclass(slots=True)` on `Statistics`, `SessionStats`, `ScoreAccumulator`** (`src/belote/stats.py`, `src/belote/belatro/core/scoring.py`). Frequently-instantiated containers; ~40 bytes saved per instance. `BelAtroRun` deliberately stays non-slotted (its `__post_init__` lazy-init pattern fights `slots=True`).
- **`src/belote/stats.py:97-98`** — `print(..., file=sys.stderr)` on save failure swapped for `logging.getLogger(__name__).warning`. Removed unused `import sys`.
- **`src/belote/input.py:138, 160`** — bare `except Exception:` in key-press parsing narrowed to `(UnicodeDecodeError,)` and `(ValueError, UnicodeDecodeError)`. Genuine bugs surface; key-press robustness preserved.
- **`src/belote/replay.py:46`** — explanatory comment added above the `# noqa: BLE001` so the broad-except rationale is visible at the call site.
- **`src/belote/game.py:213-217, 220-224`** — docstring on `belote_holders` and `_joker_state` documenting the "always replace, never mutate-in-place" contract for mutable dicts inside the frozen `GameState`.

### Removed

- **`modifier_patch.py` underscore shim** — The `state.patch("_X", True)` → `state.patch("X", True)` migration is complete. All 23 boss `apply()` methods in `src/belote/belatro/run/boss.py` were rewritten in lock-step. The leading-underscore strip in `PatchedGameState.patch()` and the `__getattr__` fallback to `boss_modifiers.X` are gone; `patch()` now asserts loud on a leading-underscore key. The `getattr(state, "_X", False)` reading anti-pattern is locked against in `test_invariant_no_underscore_boss_attrs`.

### Internal

- **Tests**: 510 → 525 (+15).
- **Strict gates**: pytest 525/525, mypy 0 errors, ruff 0 violations across `src/` and `tests/`.
- **Audit plan**: `~/.claude/plans/bug-hunt-code-performance-sleepy-ritchie.md`.

## [3.0.3] - 2026-05-08

Full-codebase audit pass + documentation accuracy. No behaviour changes; the audit produced a prioritized findings list and corrected three stale README counts. Planned fixes (one P0 functional, two P0 perf/quality, five P1, seven P2) are tracked for follow-up cuts and not yet implemented.

### Fixed (documentation)

- **`README.md`** — "Full Boss Blind Suite: All 18 unique bosses" → "All 21 unique bosses". 3.0.0 added Le Sauvage / L'Iconoclaste / Le Mime to bring `ALL_BOSS_MODIFIERS` (in `src/belote/belatro/run/boss.py`) to 21; the showcase line was never bumped.
- **`README.md`** — two stale "(435 tests)" / "pytest: 435/435 passed" references corrected to 510, matching `pytest --collect-only` and the figure already present at `README.md:250` ("Currently 510 tests passing").

### Audit findings (planning only — implementation deferred)

A three-agent audit covered the classic engine vs. canonical Belote rules, BelAtro content wiring (jokers / bosses / planets / vouchers / tarots / editions / unlocks), and performance / code-quality hotspots across ~7,100 LOC. Headline: engine is rule-correct; BelAtro content matrix is 93/93 wired (21 bosses, 8 planets, 36 jokers, 4 editions, 12 vouchers, 12 tarots).

Findings tracked at `~/.claude/plans/bug-hunt-code-performance-atomic-sutton.md`:
- **P0-1** — `EventBus.emit` still never called (carried over from 3.0.2). `L'Exécuteur` / `L'Idéologue` / `Le Fanatique` unlocks silently never fire.
- **P0-2** — `legal_cards()` LRU wrapper rebuilds `Card` objects on every cache hit (`src/belote/game.py:475-653`); est. 5–8% AI-turn regression vs. caching the resolved tuple.
- **P0-3** — `play_card()` is 174 LOC / cyclomatic ~20 (`src/belote/game.py:777-950`); split into `_update_belote_tracker` / `_apply_play_modifiers` / `_resolve_trick_complete`.
- **P0-4** — `_calculate_base_points()` accepts an optional pre-computed `winners` arg; cache-miss callers walk all 8 tricks twice (`src/belote/scoring.py:580-588`). Make required.
- **P1-1** — `card_points(trump: Suit)` lies about None; 8 `# type: ignore` markers across `game.py` / `scoring.py` should drop once signature becomes `Suit | None`.
- **P1-2** — Boss zero-rank logic duplicated across three sites (`game.py:856-872`, `scoring.py:390-400`, `scoring.py:429-440`); extract a single `apply_zero_rank_bosses(card, trump, bm)` helper. Highest-leverage maintenance fix.
- **P1-3..P1-5** — `_hard_bid` recomputes void counts inside the suit loop; `trick_rank()` called twice per overtrump check; missing docstrings on hot APIs.
- **P2** — carré KeyError harden, `REBELOTE_POINTS = 40` variant doc, AI memory reset hardening, `render()` 129-LOC split, `register_all_items` `__all__`, voucher / tarot integration test (24 effects to cover).

### Internal

- **Tests**: 510 (unchanged).
- **Strict gates**: pytest 510/510, mypy 0 errors, ruff 0 violations (all unchanged from 3.0.2).

### Carried forward

- `EventBus.emit` wiring fix (P0-1 above) remains deferred. Now planned for 3.0.4 alongside the perf wins.

## [3.0.2] - 2026-05-08

Audit pass — wired two previously-dead 3.0.0 modules behind opt-in env vars, removed redundant work from `score_round()`, and pinned every boss modifier's patch keys against typo regressions.

### Fixed

- **`src/belote/belatro/main.py` + `src/belote/belatro/engine/round_driver.py`** — `GhostRecorder` (`src/belote/belatro/ghost_run.py`) was imported nowhere outside its own tests since it shipped in 3.0.0; ghost recording silently never happened. Wired through `drive_round()` via a new optional `recorder` param so bids, plays, and round-end breakdowns are now captured. Gated on `BELOTE_GHOST=1` so default play is unchanged. Saves to `~/.local/share/belote/ghosts/<label>-<seed>.json` on run end.
- **`src/belote/gameflow.py`** — `replay.analyze_round()` / `summarize()` (`src/belote/replay.py`) was never called from any runtime path since it shipped in 3.0.0; the post-round Hard-AI comparison the README advertised silently never fired. `run_play()` now optionally accumulates `(state, played_card)` pairs for South; `run_round()` reads `BELOTE_REPLAY=1` once per round, runs the analyzer post-scoring, and prints a one-line `Replay: Optimal plays: N/M (P%)` summary. UNDO clears the buffer so the report matches the play that actually finished the round.

### Improved

- **`src/belote/scoring.py::score_round`** — pre-computes the per-trick winner list once at the top and threads it into `_calculate_base_points` and `_apply_scoring_modifiers`. Both helpers used to re-call `trick_winner_seat()` for every completed trick; under `separate_scoring` + `queen_spades_penalty` the 8-trick walk could run 3× per round.
- **`src/belote/belatro/items/registry.py::register_all_items`** — now idempotent. A module-level `_registered` flag short-circuits subsequent calls; second clause `and registry.jokers` re-runs when a caller has swapped the global to a fresh empty `ItemRegistry` (the test-suite pattern at `tests/belatro/test_belatro.py::TestItemRegistry.setup_method`). Saves the 4× `dir(mod)` walk on every `BelAtroRun` after the first.
- **`src/belote/ai.py::_special_bid`** — `_suit_lengths(hand)` is now computed once and threaded into `_easy_special` / `_medium_special` / `_hard_special`. The three branches each used to rebuild it from scratch.

### Added

- **`tests/belatro/test_phase0_coverage.py::test_every_boss_modifier_actually_patches_a_flag`** — pin against a typo'd `state.patch("_misspelled", True)` key silently producing a no-op boss. Iterates `ALL_BOSS_MODIFIERS`, asserts each `.flags()` differs from default `BossModifiers()`. The `boss_fields` allow-list in `engine/modifier_patch.py` is now load-bearing for correctness — this test surfaces drift.
- **`DEVELOPMENT.md`** — new "Optional Runtime Flags" section documenting `BELOTE_REPLAY` and `BELOTE_GHOST` next to the existing `BELOTE_A11Y` entry.

### Internal

- **Tests**: 509 → 510 (+1).
- **Strict gates**: pytest 510/510, mypy 0 errors, ruff 0 violations.

### Known issue (not fixed in this cut)

- `src/belote/belatro/engine/event_bus.py::EventBus.emit` is never called anywhere in the source. `unlock_tracker.subscribe_to(bus)` registers `on_event` but receives no events, so `_handle_round_end`'s unlocks for **L'Exécuteur** (first Capot), **L'Idéologue** (Sans Atout NS win), and **Le Fanatique** (Tout Atout NS win) silently never fire under normal play. Out of scope for 3.0.2 (fix would change ordering with `acc.update_state` in `round_driver._emit`); flagged for a follow-up.

## [3.0.1] - 2026-05-07

Post-3.0.0 audit pass — four player-visible / correctness bugs introduced or missed by the 3.0.0 cut, plus a batch of test-coverage and small-correctness improvements. No behaviour changes for code paths that were already correct.

### Fixed

- **`src/belote/game.py:860-873`** — `play_card()`'s per-trick running total honoured `kings_zero` and `tens_zero` but ignored the new 3.0.0 `aces_zero` and `jacks_zero` flags. Final scoring (`scoring.py::_calculate_base_points`) was correct, but the live HUD running total under Le Sauvage / L'Iconoclaste was wrong until the round ended. Mirrored the canonical `scoring.py` zero-rank pattern; `bm` aliased once for readability.
- **`src/belote/belatro/ui/hud.py::_SYNERGY_PAIRS`** — referenced four joker IDs (`le_finisseur`, `le_dix_de_der`, `le_marseillais`, `carre_aces_x2`) that don't exist in the registry. Two of the four pairs were dead code that could never fire. Removed; `validate_synergy_ids()` now exposes a self-check, and `register_all_items()` asserts every synergy ID resolves so future typos surface at import time.
- **`src/belote/gameflow.py:248-258`** — the a11y trick-winner announcement used raw `card_points()` and ignored every boss zero-rank flag, so screen-reader users heard inflated trick scores under Le Sauvage / L'Iconoclaste / Le Roi Mort / Les Dix Maudits / Les Clubs Bannis. New canonical helper `scoring.trick_card_points(state, trick)` is now the single source of truth for per-trick boss-aware totals.
- **`src/belote/ai.py::AIMemory.last_voids_key`** — the new-round reset in `update_memory()` cleared `played`, `known_voids`, and `processed_tricks_count` but not the cache key. After the prior round's final key (e.g. `(7, 4)`), a fresh-round `(0, 0)` or `(0, 1)` could coincidentally match a key seen during round 1 and cause `_update_voids` to skip processing. Added `last_voids_key = None` to the reset.

### Added

- **`src/belote/scoring.py::trick_card_points`** — public helper for "card-point sum of one trick under all active boss zero-rank flags." Used by gameflow's a11y hook.
- **`src/belote/belatro/ui/hud.py::validate_synergy_ids`** — return the synergy IDs that aren't registered as jokers. Used by `register_all_items()` for the new startup self-check.
- **Tests**: `tests/test_a11y.py` (8 cases for `trick_card_points` + a11y stderr emit), `tests/belatro/test_hud_synergy.py` (5 cases for the synergy registry), HOLO/POLYCHROME edition tests + four `separate_scoring × zero-flag` composition tests in `tests/belatro/test_dead_flag_fixes.py`, cross-round void-cache regression test in `tests/test_ai.py`. Tests grew 489 → 509 (+20).

### Improved

- **`src/belote/belatro/run_summary.py`** — resolved path is cached at module level after the first call, so `mkdir` is no longer re-attempted on every BelAtro exit.
- **`src/belote/a11y.py`** — `BELOTE_A11Y` env var resolved once at module import (`_ENABLED` module variable). Tests use `_refresh_enabled_from_env()` to re-read after `monkeypatch.setenv`. Saves ~30 environ lookups per round in the disabled path.
- **`src/belote/scoring.py:649-668`** — Sans Atout Capot branch now asserts `taker_belote == 0 and defender_belote == 0`. Belote/Rebelote requires a unique trump suit, so this invariant should always hold under SA — the assertion documents it and surfaces any future regression that leaks belote points into the SA path.
- **`src/belote/belatro/run/boss.py::LeMime`** — docstring notes the redundancy between `declarations_zero` and `separate_scoring` and points to the regression test that pins their composition.

### Internal

- **Tests**: 489 → 509 (+20). All new modules covered: a11y boss-aware pts (8), HUD synergy registry (5), HOLO/POLYCHROME editions (2), separate_scoring × zero-flag matrix (4), cross-round void cache (1).
- **Strict gates**: pytest 509/509, mypy 0 errors, ruff 0 violations.
- **Perf baseline**: unchanged from 3.0.0 (sub-millisecond throughout).

## [3.0.0] - 2026-05-07

Bug-hunt + audit pass — three player-visible features that were registered but silently no-ops are now wired, the Capot scoring under Sans Atout / Tout Atout has been corrected, mypy is once again strict-clean, and a batch of P3 features lands behind the new BelAtro Endless mode flow.

### Fixed

- **`src/belote/scoring.py::score_round`** — Capot reward used a flat `CAPOT_BASE = 252` for every contract, over-paying SA Capots (252 vs the contract-correct 220) and under-paying TA Capots (252 vs 348). New `CAPOT_BASE_SANS_ATOUT = 220` and `CAPOT_BASE_TOUT_ATOUT = 348` constants in `config.py`; scoring now branches on `state.contract`. `tests/test_belote.py::TestCapotPerContract` covers all three contracts; `tests/test_official_rules.py::test_sans_atout_score_round_baseline` updated from 252 → 220.
- **`src/belote/belatro/items/planets.py::TheSun`** — `level_up_reward()` returned `{"bonus_mult_per_trick": 1.0}` but no consumer ever read the key. Wired into `belatro/core/scoring.py::ScoreAccumulator` on `TrickWonEvent` when `event.trump == Suit.TOUT_ATOUT and event.trick_number > 4`.
- **`src/belote/belatro/items/planets.py::Libra`** — `coinche_multiplier` was set on the contract level but never read. Now consumed at `RoundEndEvent` time, scaled by `event.coinche_level`, and gated on the round being a non-failed taker win for NS.
- **`src/belote/scoring.py`** — `RoundScore` was constructed via `**common_kwargs` splat; mypy lost the per-field types and reported 8 errors. Inlined into both branches.
- **`src/belote/ui/render.py::_slot_frame_row`** — variable shadowing (`for c in range(...)` then `for c in cells`) made mypy infer `cells[i]` as `int`. Renamed the inner loop variables (`c → i`, `c → cell`).
- **`src/belote/ui/prompts.py`** — three untyped helpers (`_hist_taker_label`, `_hist_contract_label`, `_hist_status`) now annotated with `RoundScore`.
- **`src/belote/ui/prompts.py::show_history`** — N806 lint on `W_RD/W_TKR/...` constants resolved by lowercasing the locals; behaviour unchanged.
- **`src/belote/ai.py::_process_trick_voids`** — under the `republicain_wild` flag (Le Républicain deck / boss reuse), playing a 7 or 8 off-suit no longer falsely flags the player as void in the lead suit. Hard AI's void inference now skips wild ranks when the flag is active.

### Added

- **`src/belote/belatro/main.py`** — post-Ante-8 endless prompt. After winning Ante 8, the run offers `Continue into Endless Mode? (Ante 9+ scales ×2.2)`. Built on the existing `BelAtroRun.endless` / `endless_ante_offset` infrastructure plus a new `BelAtroAnnounce.yes_no` helper.
- **`src/belote/belatro/items/base.py::Edition`** — new enum (NONE/FOIL/HOLO/POLYCHROME/NEGATIVE). Shop generation rolls per-joker editions; Foil adds +50 chips per trigger, Holo +10 mult, Polychrome ×1.5 mult, Negative grants an extra joker slot at purchase. Wiring lives in `belatro/run/shop.py` and `belatro/core/scoring.py::_apply_edition`.
- **`src/belote/belatro/run/boss.py`** — three new boss blinds (Le Sauvage / L'Iconoclaste / Le Mime) and three new `BossModifiers` flags (`aces_zero`, `jacks_zero`, `declarations_zero`) read by the existing scoring path.
- **`src/belote/belatro/ui/hud.py::detect_synergies`** — small registry of known joker pair combos; renders a `★ SYN×N` badge on the HUD when any pair (or 3+ jokers) is held.
- **`src/belote/achievements.py`** + **`src/belote/stats.py::Statistics.achievements`** — six classic-mode achievements (first Capot, 3 Capots in a session, 2 Capot streak, 300+ point round, hard win, ten games played) auto-evaluated post-round / post-game.
- **`src/belote/themes.py::THEMES["colorblind"]`** — deuteranopia/protanopia-friendly palette using blue/cyan/orange instead of red/green.
- **`src/belote/a11y.py`** — screen-reader hints. Cards played, trick winners, and round results emit one-line plain-text descriptions to stderr when the env var `BELOTE_A11Y=1` is set.
- **`src/belote/replay.py`** — `analyze_round()` runs the just-played decisions through the Hard AI and reports per-decision agreement; `summarize()` produces a one-line `Optimal: N/M (X%)` string.
- **`src/belote/belatro/ghost_run.py`** — `GhostRecorder` accumulates seed + bid + play events and serializes them to JSONL under the user data dir. Foundation for a future ghost-replay viewer; the JSON format is versioned (v1).
- **`src/belote/belatro/run_summary.py`** — appends a one-line per-run summary (deck, ante, jokers, won) to `~/.local/share/belote/run_history.jsonl` on BelAtro exit. Best-effort, OSError-swallowed.
- **`src/belote/gameflow.py::show_hand_preview`** — short `Dealing…` flourish before the hand preview, gated on the existing speed setting and skippable via Space/Esc.

### Improved

- **`src/belote/ansi.py`** — 16 palette accessors (`felt_bg()`, `red_fg()`, …) previously hit `theme_manager.get_current()` per call. Cached the active `Theme` at module level and registered an invalidation callback with `theme_manager`. Lower per-render dict-lookup overhead.
- **`src/belote/themes.py::ThemeManager`** — redundant class-level `_current_theme_name` removed; new public `current_name` property; `_initialized` guard now uses `getattr` for clarity. Eight call sites in `ui/menu.py`, `ui/prompts.py`, and `ui/render.py` migrated off `_current_theme_name`.
- **`src/belote/ui/render.py`** — `_LAST_RENDER_KEY` list-of-one singleton replaced with a module-level variable + `global` declaration; same behaviour, less Python idiom drag.
- **`src/belote/ai.py::AIMemory.last_voids_key`** — caches `(completed_count, current_trick_len)` so `_update_voids` short-circuits on repeat calls within the same trick decision (lookahead exploration triggered redundant scans).

### Internal

- **Performance baseline (post-fix)**: `scripts/benchmark.py` reports render 0.271ms (±0.044), AI Easy/Med/Hard 0.015 / 0.030 / 0.026 ms, BelAtro update 0.032 ms, scoring 0.169 ms, deal 0.071 ms, legal_cards 0.012 ms.
- **Tests**: 446 → 489 (+43). New files: `tests/test_ansi_helpers.py`, `tests/test_achievements.py`, `tests/test_replay.py`, `tests/belatro/test_ghost_run.py`. Existing files extended with Capot-per-contract, Sun/Libra wiring, TA→le_fanatique unlock, republicain-void edge case, and three new boss tests.
- **Strict mode**: README's "0 mypy errors / 0 ruff violations" claim was inaccurate at 2.9.5 (18 mypy + 10 ruff at audit time). Both gates are now actually clean.

## [2.9.5] - 2026-05-07

In-game keyboard shortcuts cleaned up, the trick mat now anchors every played card inside a visible per-seat slot, the round history overlay carries the full per-round picture, and the cards have been redrawn in a GRIMAUD-1898 style with both-corner indices and patterned pip layouts.

### Fixed

- **`src/belote/input.py`** — `Key.THEME` was defined but never mapped to a keystroke; the help text falsely advertised `Shift+T` (which terminals can't generally distinguish in raw mode). Theme cycling during gameplay was unreachable. New mapping: `t/T → Key.THEME`, `h/H → Key.HIST`, `?` → `Key.HELP`, `o/O → Key.SORT`. Both the Unix and Windows readers updated.
- **`src/belote/input.py`** — `s` was previously stolen by `Key.SORT`, so pressing `S` in round-2 bidding triggered a sort instead of the **Sans Atout** quick-bid the help text promised. Sort now lives on `O` (matching what the help screen always claimed) and `s` falls through to `Key.CHAR` so SA bidding works.
- **`src/belote/gameflow.py::run_play`** — when the user had already pressed any key earlier in the round (which sets `skip_anims`), the post-trick pause was skipped entirely and the 4th card vanished before it could be read. New `MIN_TRICK_DWELL = 0.5s` non-skippable hold runs after every completed trick (even on the `instant` speed preset) so the player always sees all four cards before the mat clears.

### Added

- **`src/belote/ui/render.py`** — visible **slot frames** drawn around each compass position on the trick mat. Implemented via three new helpers (`_slot_anchors`, `_slot_frame_row`, `_felt_pad_ns`, `_we_row`) that paint thin `─`/`│` borders on the felt cells immediately surrounding each card slot, in the felt-placeholder dim colour. Total mat dimensions (`6 + 3*card_h`) are unchanged, so `_calculate_base_row` and `patch_trick_card` continue to work without any coordinate adjustments — patched cards land exactly inside the existing frame.
- **`src/belote/game.py::RoundScore`** — eight new optional fields (`contract`, `trump`, `taker_seat`, `tricks_ns`, `tricks_ew`, `last_trick_winner`, `decl_summary_ns`, `decl_summary_ew`) populated from `state` and `state.completed_tricks` at scoring time. All fields default so existing test fixtures and any historical `RoundScore` constructions remain valid.
- **`src/belote/scoring.py::apply_round_score`** — now computes per-team trick counts via `trick_winner_seat`/`team_of`, builds short declaration labels (`"100♥"`, `"Belote"`, `"Carré-J"`, …) gated on the team's `*_decl_pts > 0` so only the *scored* declarations appear, and threads everything into `RoundScore`. New helper `_decl_short_label` covers belote/rebelote/sequence/carre.
- **`src/belote/ui/prompts.py::show_history`** — rewritten as an 8-column table (`RD | TAKER | CONTRACT | TRICKS | DECLARATIONS | NS | EW | STATUS`) for terminals ≥78 cols, with a 2-line-per-round fallback for narrower terminals. Status colouring: gold `CAPOT`, red `CHUTE`, dim `LITIGE`. Existing scrolling, view-height clamp, and exit-on-any-key behaviour preserved.
- **`src/belote/ui/render.py::_card_face_internal`** — full GRIMAUD-1898-inspired redraw:
  - Both corners now carry a 3-cell `rank+suit` index (`A♠` top-left, `♠A` bottom-right). The index padding scales with `inner_w`.
  - Pip cards (7-10) at `card_h ≥ 7` get a recognisable pip arrangement instead of a single centred suit symbol.
  - Court cards J/Q/K each get a distinct multi-row motif (sword, jewelled headdress, crown).
  - Aces get a decorative `╭─◆─╮` / `╰─◆─╯` wreath around the central suit.
  - Compact 6×5 layout keeps the single inner row but still benefits from both-corner indices.
  - All variants honour the active theme (`face_card_bg`, `card_face_bg`, `highlight_bg`, `red_fg`/`black_fg`) and the `DIM` prefix for illegal cards. ASCII fallback paths preserved.
- **`tests/test_extended.py::test_round_score_history_extra_fields`** — pins the new `RoundScore` fields end-to-end through `apply_round_score`.

### Changed

- **`src/belote/ui/menu.py`** — main-menu loop now handles `Key.THEME` (cycles forward through `THEMES`), so the new in-game `T` shortcut works at the menu too.
- **`src/belote/main.py`**, **`src/belote/ui/render.py`** — game-over hint and HUD compact hint updated to advertise the new `[H] History` / `[T] Theme` shortcuts.
- **`src/belote/ui/prompts.py::show_help`** — help-screen text rewritten to match the new bindings.
- **`README.md`** — Controls section rewritten; theme section now lists all six themes by name.
- **`tests/test_layout.py::test_hud_compact_omits_help_hints_and_theme`** — assertion updated for the new compact-HUD hint substring.

### Notes

436/436 tests pass. No gameplay, scoring, or AI-decision changes — all updates are UX (keys, slot framing, dwell, history depth, card glyphs).

## [2.9.2] - 2026-05-07

Render-pipeline fix for Konsole (KDE/Kubuntu) and other strict ANSI terminals where UI elements visibly stacked on top of each other — the top HUD repeating ~6 times, "Theme: Sepia Vintage" duplicating in the right column, "Partner" doubling, the bid prompt repainting below itself, and bid history accumulating between frames. The bug existed in the code on every terminal but VTE-based emulators (LXTerminal, GNOME Terminal, xterm) auto-blanked the leaking cells, masking it. Konsole's Vt102Emulation does not, so the leakage was visible.

### Fixed

- **`src/belote/ui/render.py::render`** — the bidding selector (Round 1 inline highlighted Take/Pass; Round 2 boxed grid; optional `partner_bid_tendency_text` line) is now painted inside the main render frame via the new `bid_selection: int | None` parameter on `render()` and `display()`. Previously `prompt_bid` paid display() and then wrote 8+ extra `\r\n` lines, which scrolled the alt-screen on the bottom row and left stale rows that the next frame's blank padding never repainted.
- **`src/belote/ui/render.py::render`** — every line in the rendered frame now ends with `clear_to_eol()` (`\x1b[K`), including blank vertical-centering padding rows. The previous `line + clear_to_eol() if line else line` branch skipped the escape on padding rows, betting the previous frame's content area had already cleared them — but that bet broke whenever an external write (announcement, prompt artifact) deposited debris on a padding row. Cost is one 3-byte escape per row; benefit is correct rendering on any ANSI-compliant terminal regardless of strictness.
- **`src/belote/ui/prompts.py::prompt_bid`** — gutted of all post-`display()` `sys.stdout.write` calls. Each loop iteration is now a single `display(state, None, bid_selection=sel)` + `reader.read()`. Removed unused `REVERSE` and `black_fg` imports (the box-rendering code that consumed them moved to `render.py::_build_bid_prompt_lines`).
- **`src/belote/ui/announce.py::announce`** — replaced the `\r\n`-bracketed banner with absolute cursor positioning (`move(term_h - 1, 1) + clear_line()`) so the banner can never trigger a scroll, even when the cursor is parked on the bottom row of the alt-screen.

### Added

- **`src/belote/ui/render.py::_build_bid_prompt_lines`** — pure helper that returns the in-frame bidding selector lines. Encapsulates the Round 1 inline form, the Round 2 60-column boxed form, and the optional partner-tendency line so the main render loop reads as one coherent paint.

### Notes

No gameplay, scoring, or AI changes. 435/435 tests pass. The fix is observable when running under Konsole — start a Belote round, force a Round 2 bid (pass on the up-card), and arrow-navigate the selector: previously the box stacked between iterations; now it repaints in place.

## [2.9.1] - 2026-05-06

UI polish patch on top of 2.9.0. Two pieces of menu art had drifted; this release fixes both and tightens the menu plumbing so the cup walls hold for every label combination.

### Fixed

- **`src/belote/ui/menu.py::get_cards_art`** — the croissant Braille had a corrupted line 8 (`⠘⢿⡿⠋⣠⣾⣿⣿⣿⠟⠁⣿⣿⣿⣿⣿⠟⢁⣀`, 21 cells) that broke the right curl, and was missing the 13th-line `⠉⠉⠉` crumb under the tip entirely. Restored to the canonical 13-line, 25-cell-wide reference. Each line now uses U+2800 Braille blanks for its leading indent (uniform 25-cell width) rather than mixed ASCII spaces, so callers don't have to re-pad.
- **`src/belote/ui/menu.py::CUP_TEMPLATE`** — body inner width was 47 chars (29-char opt + 16 trailing dead space + 2 gutter), much wider than the 23-char lid and saucer. Now 29 chars flush so menu options sit between the cup walls with no padding. Steam line 2 now correctly shows the two-puff frame (`)     (`) — previously the template's leading-indent disagreement with `STEAMS[..][1]` pushed the second puff out of view.
- **`src/belote/ui/menu.py::_render_main_menu_art`** — selected-row markers tightened from ` > {label} < ` (6-char overhead) to `> {label} <` (4-char overhead) so the selected row uses the same width budget as unselected (`  {label}  `, also 4-char overhead). Without this, a selected `Theme: < Sepia Vintage >` would bust the right cup wall.
- **`src/belote/ui/menu.py::show_main_menu`** — settings labels shortened to fit the new 25-char usable label width: `AI Config:` → `AI:`, `Target Score:` → `Target:`. `Speed:` and `Theme:` keep their names with tightened spacing. All four `<` markers still column-align.

### Changed

- **`src/belote/ui/menu.py::_render_main_menu_art`** — opt-slot loop and assertion bound dropped from 12 → 9 to match the new template. The error message ("add opt slots to CUP_TEMPLATE") still points at the right fix if the menu ever grows past 9 entries.

### Notes

No gameplay or scoring changes; classic and BelAtro behavior is bit-for-bit identical. 435/435 tests pass; ruff and mypy clean on `src/`. Pre-existing lint/type debt in `tests/` and `scripts/benchmark.py` (18 ruff, 69 mypy strict-mode annotations) is untouched and tracked separately.

## [2.9.0] - 2026-05-06

Audit-driven sweep on top of 2.8.0: four engine bugs fixed and the long-deferred Tout Atout / Sans Atout bidding affordance shipped end-to-end. The README's "future work" line for those contracts is gone — both contracts are now bidable in classic Belote and BelAtro, and the two jokers / two unlock counters that had been waiting on the affordance now fire in real play. Plan: `plans/bug-hunt-code-performance-elegant-starlight.md`.

### Fixed — confirmed bugs

- **`src/belote/belatro/engine/round_driver.py`** — replaced the lingering `boss.id == "l_agent_double_boss"` string-branch with a flag-based dispatch keyed on `state.boss_modifiers.agent_double_active`. Previously, BetrayalArc and the Le Traître joker both set the active flag but only L'Agent Double populated `agent_double_tricks` — so partner sabotage silently never fired for the other two paths. New `BossModifiers.agent_double_late_only` flag lets BetrayalArc express its "from trick 4 onward" pattern without re-introducing string-branching. Regression tests pinned in `tests/belatro/test_round_driver.py`. Plan B1.
- **`src/belote/belatro/run/decks.py` + `core/run_state.py` + `belatro/main.py`** — Le Joueur's advertised "Boss Blind every 2 antes" was unimplemented (zero `boss_every_2` matches in the codebase). Now: deck modification → `card_enhancements["boss_every_2"]` → `main.py` rolls an extra boss on the Big Blind of even-numbered antes, doubling Le Joueur's boss-encounter count and matching the deck's high-variance theme. Plan B2.
- **`src/belote/game.py`** — removed the dead `bid_suits` field on `GameState`. It was initialized and reset to `()` but never written, never read for gameplay. AI bidding correctly uses `state.up_card.suit` for round-1/2 forcing/forbidding. Plan B3.
- **`src/belote/game.py::_calculate_legal_cards_impl`** — Tout Atout legal_cards branch added. Pre-fix the code dropped into the "non-trump led" branch under TA because `lead_suit != Suit.TOUT_ATOUT`, producing wrong legal moves whenever a TA round actually played. Now: must follow lead suit, must rise within suit if possible, free discard if void. Bug was unreachable until B-feature shipped, but is now exercised by the new bidding affordance. Plan B4.

### Added — Tout Atout / Sans Atout contracts

The full bidding affordance for both special contracts, end to end across classic Belote and BelAtro:

- **`src/belote/game.py`** — `BidValue = Suit | Literal["sans_atout"] | None` and `SANS_ATOUT_BID` sentinel. `place_bid` accepts the new bid value and rejects TA/SA in round 1 with `IllegalMoveError`. Post-bid mapping: TA → `trump=Suit.TOUT_ATOUT, contract="tout_atout"`; SA → `trump=None, contract="sans_atout"`; normal → `trump=<suit>, contract="normal"`. Belote pre-calc skipped for both special contracts (no unique K+Q-of-trump exists). New `is_sans_atout` flag threaded through `_calculate_legal_cards_impl`, `_card_beats`, `_current_trick_winner`, `trick_winner_seat`. Dynamic-trump boss suppressed under SA.
- **`src/belote/scoring.py`** — `score_round` gates on `state.contract` instead of `state.trump` so SA rounds (trump=None) score correctly. Chute formula uses `TOTAL_POINTS_TOUT_ATOUT=248` (TA) / `TOTAL_POINTS_SANS_ATOUT=120` (SA) from `config.py`. `_detect_all_declarations` skips belote detection under TA/SA. `card_points(c, None)` already produces the SA non-trump scale, so inner arithmetic is unchanged. Capot stays 252 for both contracts.
- **`src/belote/ai.py`** — three-tier TA/SA bid heuristics. Easy: spread-Jacks → TA, flat-Aces → SA. Medium: weighted scoring with personality jitter. Hard: card_points-based with Jack-bonus / long-suit-penalty. Round 1 still rejects TA/SA — the affordance is round-2-only per FFBelote rules.
- **`src/belote/ui/prompts.py`** — round-2 bid box widened to 60 cols and offers `[♠ ♥ ♦ ♣ TA SA Pass]` minus the up-card suit. New keyboard shortcuts `a` (Tout Atout) and `s` (Sans Atout) alongside the existing digit-select.
- **`src/belote/gameflow.py::_bid_label`** — helper produces "Tout Atout" / "Sans Atout" / suit symbol / "Pass" for the AI bid announcement line. Pre-fix `bid.symbol` would crash on the SA string sentinel.
- **`src/belote/belatro/engine/round_driver.py`** — partner's TA/SA bid is now gated on `partner.trust.duo_contracts_available`. Below the threshold, the bid falls back to "pass" rather than to a normal-suit bid, respecting the personality's choice to "go big or go home." This is the missing reader of the unread `duo_contracts_available` flag at `partner/trust.py:49`.
- **`src/belote/belatro/partner/personality.py`** — `LeCourageux` opts into TA on Jack-heavy hands; `LeStratege` opts into SA on flat Ace/10-heavy hands. Both gate on round 2 and on the trust flag.

These changes unblock two BelAtro jokers that were previously dead code:

- **`Le Fanatique`** — now reachable via `tout_atout_wins` unlock counter; ×1.5 mult past the 4th NS-won trick of a TA round actually fires.
- **`L'Idéologue`** — reachable via `sans_atout_wins`; +18 chips per Jack in SOUTH-won SA tricks actually fires.

End-to-end integration tests in `tests/belatro/test_contract_unlocks.py` pin both unlock counters incrementing on real round-end events.

### Audit findings reviewed and dismissed

Three claims from the audit pipeline turned out to be misreadings of correct code; documented here so future audits don't re-flag them:

- "AI Round 1 bidding logic is inverted" — the variable is named `forbidden` but per the comment it's the up-card suit, which is the **only** allowed bid in Round 1 per FFBelote. Code is correct.
- "Partner-overtrump exception missing on trump leads" — intentional and pinned by `tests/test_belote.py:313` ("Trump lead: partner-winning exception does NOT apply"). Per FFBelote rules.
- "Le Marseillais `announce_x2` / `no_belote_rebelote` flags never read" — both ARE read at `scoring.py:518` and `:554`, with dedicated tests in `tests/belatro/test_dead_flag_fixes.py`.

### Performance

Audit confirmed AI 0.032ms / render 0.233ms / scoring 0.197ms — well under the advertised targets. No perf changes needed.

## [2.8.0] - 2026-05-06

Two consecutive audit-driven bug-fix sweeps shipped together. The first cleaned up advertised-but-silently-dead BelAtro flags (deck modifiers and vouchers whose `apply()` set state nobody read). The second verified a 5-critical / 12-high / 14-medium / 8-incomplete / 10-perf audit — about 62% of findings were real game-affecting bugs and were fixed; the rest were misreadings of the rules or already-correct code, listed under "Audit claims explicitly rejected" at the bottom. The plan-mode verification report lives at `plans/check-these-findings-accurately-abstract-kahan.md`.

### Fixed — game-affecting correctness (sweep 2)

- **`src/belote/main.py` + `belatro/main.py`** — terminal corruption returning from BelAtro to the main menu. Both files independently entered/exited alt-screen; `BelAtroGame.start()` no longer toggles alt-screen and instead trusts the caller (classic-mode `belote.main` keeps alt-screen across menu↔BelAtro transitions, the standalone `belatro` console script keeps its own wrapper). Audit C1.
- **`src/belote/ai.py`** — every `trick_rank` / `card_points` / `_current_trick_winner` call now passes `state.boss_modifiers.seven_eight_trump`. AI was previously ranking the trump 7/8 wrong under La Déluge, picking incorrect cards. The flag is cached on `AIPlayer._se` at the top of `decide_card`/`decide_bid` so the threading is one read per decision. Audit C2.
- **`src/belote/belatro/items/tarots.py::LeFou`** — actually re-applies the last Tarot/Planet effect now. Backed by a new `BelAtroRun.last_consumable_id` field and `BelAtroRun.consume()` helper for centralised activation; falls back to the previous random-tarot behavior when no prior consumable has been recorded. Audit C4.
- **`src/belote/belatro/items/jokers/trick_timing.py::LePremierSang`** — "+2 Mult for the rest of the round" now keeps paying out on every trick after a trick-1 NS win. The `_active` flag was set but never read, so only trick 1 ever scored. Audit H4.
- **`src/belote/belatro/items/jokers/corrupted.py::LAgentDouble`** — sabotage counter ("for 2 tricks") decrements every trick instead of only on opponent wins. Previously, NS sweeping the round left the sabotage flag stuck on indefinitely. Audit H5.
- **`src/belote/belatro/items/vouchers.py::forge_tierce`** — delegates to `Planet.use()` so overlapping numeric levels are summed, matching the regular planet level-up path. Previously a `**existing` dict merge silently dropped earlier levels. Audit H6.
- **`src/belote/belatro/items/vouchers.py::LaVoute`** — uses `max()` rather than `=` so it can't wipe additive bonuses already granted by LesCartesDorees; LaVoute now defines a floor of (rate=1, cap=5). Audit H7.
- **`src/belote/belatro/main.py`** — the three bare `print()` calls in alt-screen ("YOU WON!", Capot Insurance softening, RUN OVER) routed through a new `BelAtroAnnounce.banner()` helper that writes a centred line at a fixed row, avoiding scroll. Audit H8.
- **`src/belote/belatro/main.py::prompt_card`** — UNDO no longer recurses (`return self.prompt_card(state)` → `continue` inside the existing `while True`). Repeated UNDO presses can no longer hit the recursion limit. Audit H9.
- **`src/belote/belatro/progression/save.py`** — atomic save: `tempfile.NamedTemporaryFile` + `fsync` + `Path.replace` so a crash mid-write leaves the previous `profile.json` intact. Added `SCHEMA_VERSION = 1` and a `_migrate()` hook so future schema bumps have a place to live. Audit H10 + I7.
- **`src/belote/gameflow.py::run_round`** — undo now calls `clear_legal_cards_cache()` before popping the history stack so a restored earlier `GameState` can never serve a stale legal-cards entry. Audit H11.

### Fixed — robustness / correctness

- **`src/belote/belatro/core/economy.py::spend_money`** — rejects negative `amount`. Previously `if money >= -5` passed trivially and `money -= -5` credited the player. Audit M2.
- **`src/belote/belatro/core/run_state.py`** — free-planet draw uses a per-run `random.Random` instance seeded from `BelAtroRun.seed`, not the global module RNG. Runs are seed-deterministic again. Audit M3.
- **`src/belote/belatro/engine/modifier_patch.py`** — deleted the dead `patch_card_points` method (set `_card_pt_override`, no consumer). Audit M4.
- **`src/belote/belatro/core/scoring.py`** — joker_state is `copy.deepcopy`'d, not `dict()`-shallowed, so mutable values (lists/dicts/sets) can't leak across rounds. Audit M5.
- **`src/belote/input.py`** — ESC vs. arrow-key disambiguation window is now 50ms (was 10ms), and the UTF-8 continuation-byte read is bounded by a `select.select` timeout so a partial sequence can't block the reader forever. Audit M6 + M7.
- **`src/belote/rules.py`** — French sequence labels: `Tierce / Quarte / Quinte` instead of `Tierce / Cinquante / Cent`. (English text was already correct.) Audit M8.
- **`src/belote/belatro/partner/personality.py::LeFlambeur`** — bid logic now picks the longest suit with most honors instead of `random.choice`; `should_bid` checks for any J/9/A in the strongest suit. Description "aggressive" is honored. Audit M11.
- **`src/belote/belatro/engine/round_driver.py`** — Le Fantôme partner personality grants +$1 per partner-won trick via `state._bonus_money`, matching the description. Audit I5.
- **`src/belote/belatro/partner/partner_state.py::difficulty_for`** — now respects the `seat` parameter and returns `"hard"` at trust tier ≥ 3. `round_driver.py` maps the new return value to `Difficulty.HARD`. Audit M12.
- **`src/belote/belatro/run/shop.py`** — `random.sample` instead of two `random.choice` calls so the same Joker can't appear twice in one shop. Audit M13.
- **`src/belote/themes.py::set_current`** — raises `ValueError` for unknown theme names instead of silently no-op'ing. Audit M14.
- **`src/belote/belatro/main.py`** — La Maison-Dieu's `disable_next_boss` and Le Diable's `partner_overcut_round` flags are now consumed: La Maison-Dieu skips the next boss reveal and clears the flag; Le Diable is popped after the round ends. Were one-round effects but stayed permanent. Audit I3.

### Performance

- **`src/belote/ansi.py`** — `fg()` and `bg()` are `@lru_cache`'d (maxsize=512). Previously every render allocated ~200 fresh format strings. Audit P3.
- **`src/belote/ui/render.py`** — hoisted the lazy `clear_screen` import out of `render()` (was re-resolved every call); `clear_to_eol()` is no longer emitted for blank padding lines. Audit P1 + P2.
- **`src/belote/game.py`** — pre-computed `_SUIT_IDX_CACHE` for every possible trump value; `sort_hand` no longer rebuilds the suit ordering and index dict per call. Audit P4.
- **`src/belote/belatro/items/registry.py`** — `get_available_jokers` / `get_available_vouchers` cache their filtered output keyed on a generation counter (bumped on every `register_*`) and the profile's unlock set. Re-registration invalidates automatically. Audit P8.
- **`src/belote/config.py`** — `stats_path` no longer mkdirs on every property access. Persistence sites (stats writer + profile saver) already mkdir at write time. Audit P10.

### Fixed — silently-dead BelAtro flags (sweep 1)

The pattern: a deck modifier or voucher's `apply()` set a flag on `BelAtroRun` (or patched a boss flag), but no game-logic site read it. Tests passed because they only asserted the flag existed, never the behavior.

- **`src/belote/belatro/main.py`** — boss handling now reads `boss.flags()` instead of hardcoded `boss.id == "..."` checks. Consequence: **La Trahison** (`BetrayalArc`) actually freezes partner trust at 0 (was a no-op — only `Le Divorce` worked, by id-coincidence). `hide_partner_hand` and `auto_coinche` are also flag-driven now, restoring the architecture the rest of the engine uses.
- **`src/belote/scoring.py`** — Le Marseillais deck mods now honored: `announce_x2` doubles Tierce/Quarte/Quinte/Carré points; `no_belote_rebelote` zeroes Belote/Rebelote scoring (was set on the run, ignored by scoring). La Balance voucher's `tie_breaks_for_taker` short-circuits litige and awards the contract to the taker (previously dead — every tie became a litige).
- **`src/belote/game.py`** — Le Républicain's "7s and 8s are wild — play them on any trick" rule now actually applies in `legal_cards`. Before, only the +5-chip-per-7-or-8 rider worked; the wild-play rule was deck-description fiction. Also: the `winner is None` fallback after a 4-card trick now raises `AssertionError` instead of silently picking `prev_seat()` (unreachable in practice; surfacing it catches future state corruption).
- **`src/belote/belatro/engine/round_driver.py`** — Le Coincheur's `start_coinched` enters the round at coinche level 1 (was set, never read). Le Traître joker's `partner_throws_trick` actually triggers partner sabotage on one random trick by piggy-backing on the existing `agent_double_active` AI path (only the +2.5 mult half worked before). La Surcoinche voucher gates AI surcoinche.
- **`src/belote/belatro/items/jokers/hand_comp.py`** — La Sentinelle's ×3 mult only fires when South was actually dealt the trump Jack. Previously the joker armed `had_jack=True` whenever the trump Jack appeared in any winning trick, including when partner or an opponent held it — false positives. Reconstructs per-card seat from `leader_seat + index`.
- **`src/belote/belatro/main.py`** + **`core/run_state.py`** — L'Aristocrate's `gold_seal_aces` pays $1 per Ace your team wins (was set in the deck mod dict but never copied to run state, never read). L'Anarchiste's `corrupted_pool_visible` is now surfaced on the run.
- **`src/belote/ui/prompts.py`** — L'Encyclopédie voucher (`show_partner_bid_tendency`) renders one-line partner personality hint above the bid prompt; was set, never displayed.
- **`README.md`** — count drift corrected: **36 Jokers / 12 Tarot / 18 Bosses** (were "50+ / 10 / 17"). Sans Atout claim softened to match reality (no `SANS_ATOUT` suit value or bid affordance exists; scoring engine handles `TOUT_ATOUT` but it's not currently bid-able from the UI).

### Added

- **`src/belote/belatro/run/boss.py::BossModifier.flags()`** — returns the `BossModifiers` dataclass produced by this boss's `apply()` against a stub. Lets `main.py` react to flags without driving a full round, replacing the hardcoded `boss.id ==` chain.
- **`src/belote/belatro/items/vouchers.py::forge_tierce(run, planet_id)`** — runtime helper that consumes 3 Tierce charges and applies a Planet's level-up reward to `run.contract_levels`. Promotes TierceForge from pure stub to a callable shop hook (UI integration is the remaining work).
- **`src/belote/belatro/ui/announce.py::BelAtroAnnounce.banner()`** — centred fixed-row banner that doesn't scroll the alt-screen buffer; replaces the three bare `print()` calls in `belatro/main.py`.
- **`src/belote/belatro/core/run_state.py::BelAtroRun.consume()`** — centralised consumable activation that records the item id as `last_consumable_id` for LeFou to copy.
- **`src/belote/belatro/progression/save.py::SaveManager.SCHEMA_VERSION` + `_migrate()`** — save-file schema versioning + migration hook.
- **`tests/belatro/test_dead_flag_fixes.py`** (19 tests) — integration coverage for every flag wired up above. Each test constructs a minimal `GameState` or `BelAtroRun` with the flag set and asserts the *observable* effect (e.g. "carré declarations score 200 instead of 100 with `announce_x2`", "trump 7 is legal off-suit with `republicain_wild`", "trump Jack played by NORTH does not arm South's Sentinelle").

### Audit claims explicitly rejected (do not reopen)

From sweep 2:

- C3 "AI doesn't handle TOUT_ATOUT" — `card.suit == trump` is harmless: TOUT_ATOUT is a sentinel suit, and `trick_rank` / `card_points` already special-case it.
- C5 "`JokerResult.times_mult` defaults to 0.0" — used as a truthy-skip sentinel in `core/scoring.py`'s `_apply`; `0.0` means "skip", not "zero out".
- H1 "Rebelote logic wrong" — `belote_holders[trump]` is the single seat holding both K and Q; standard Belote rule is exactly that, code is correct.
- H2 "`legal_cards` cache stale on dynamic trump" — `trump` is part of the cache key; rotating it produces a different entry.
- H3 "QuinteRoyale threshold wrong" — Quinte = 100 pts, `>= 100` triggers correctly.
- H12 "Coinche blocked when partner takes" — correct behavior; you cannot coinche your own partner's bid.
- M1 "EventBus swallows handler errors" — no `try/except`, exceptions propagate. Description is the opposite of reality.
- M9 "Worst-round 999 sentinel leaks" — `announce.py:96` already gates on `total_rounds > 0` with default `0`.
- I2 "BossModifiers flags unused" — every flag is read (`hide_hud`, `hide_partner_hand`, `agent_double_active`, `partner_forced_pass`, `lock_trust_zero`); matches the architecture documented in memory.
- I4 "LeFanatique state['contract'] never set" — written by `core/scoring.py` on `BidMadeEvent`.
- I8 "unlocks event handler stub" — implementation is complete; the `# Potentially more event handlers` comment is an extension hint, not a stub.

From sweep 1:

- "Litige pool drops on chute" — `scoring.py` correctly releases the pool to defenders on chute (line 620), to taker on success (line 625), and accumulates only on litige tie. Working as intended.
- "AI round-1 bidding logic reversed" — re-reading `ai.py:87-91`, returning the matching suit in round 1 *is* the intended behavior (round 1 only allows the up-card's suit).
- "Le Carnet partner reveal unimplemented" — fully wired: `vouchers.py` → `run_state.show_north_hand` → `main.py:113` → `display(show_north_hand=True)`. The +1 mult is wired at `belatro/core/scoring.py:129`.
- "Contract levels race in `Planet.use()`" — single-threaded shop interaction; no race.

### Test count

409 → **409** (no count change; existing tests cover every fixed path. `tests/belatro/test_belatro.py::test_spend_money_zero_always_succeeds` still passes — `spend_money(0)` remains a benign no-op).

## [2.7.1] - 2026-05-04

Audit follow-up: cleared the last `getattr(state, "_X", False)` boss-flag reads, removed the now-redundant property aliases on `GameState`, and closed three coverage gaps the v2.7 audit flagged.

### Changed

- **`src/belote/scoring.py`** — replaced 12 `getattr(state, "_kings_zero" / "_seven_eight_trump" / "_separate_scoring" / …, False)` reads with direct `state.boss_modifiers.X` access. mypy can now type-check these branches; renaming a flag will surface as an error instead of silently returning `False`. `_calculate_base_points`, `_apply_scoring_modifiers`, and the 10-de-der branch in `score_round` are all migrated.
- **`src/belote/game.py`** — deleted the 17 underscore property aliases on `GameState` (`_no_belote` … `_separate_scoring`) that previously delegated to `boss_modifiers.*`. `PatchedGameState` keeps its `__getattr__` fallback so `state.patch("_kings_zero", True)` style boss applications and the existing tests at `tests/belatro/test_belatro.py:1496+` continue to work unchanged.

### Added

- **`tests/belatro/test_phase0_coverage.py::test_boss_dynamic_trump_changes_trump_every_two_tricks`** — plays a full 8-trick round under L'Anarchie and asserts trump rotates after tricks 2/4/6 and stays put after trick 8 (`game.py:752`'s `tricks_count < 8` guard). Pairs with the existing seed-determinism test.
- **`tests/belatro/test_progression.py`** — five endless-mode tests: 2.2× per-offset target scaling (`ante.py:26`), `advance_blind` ante-8 → endless transition, `run_won` flip when not in endless, and `current_blind` dispatch to `endless_ante()` vs the static `ANTE_TABLE`.
- **`tests/test_undo.py`** (new file, 3 tests) — pins the gameflow history-stack contract: snapshot/pop equality, `stack_base` round-boundary semantics, and round-to-round isolation. Exercises the rollback logic at `src/belote/gameflow.py:264-299` without booting the interactive input layer.

### Audit claims explicitly rejected

The v2.7 audit also recommended five changes that turned out to be wrong or already done; documenting here so future reviewers don't reopen them:

- `@cached_property` on the 17 boss-flag properties — **infeasible**: `GameState` is `@dataclass(frozen=True, slots=True)`; `cached_property` requires `__dict__`, which `slots=True` removes. Verified locally (`TypeError: No '__dict__' attribute…`).
- "Stale legal-cards cache when `dynamic_trump` swaps trump mid-round" — **not a bug**: `_calculate_legal_cards_impl` (`game.py:457`) takes `trump` as a key parameter, so trump changes naturally produce a different cache entry.
- "Phantom card fallback in `ai.py:128`" — **already fixed** (the fallback is `legal = hand`).
- "Cache key uses `Seat` object directly at `game.py:461`" — **wrong**: parameter is `seat_val: int` and `legal_cards()` passes `seat.value`.
- `belatro/main.py:248` "f-string consistency" — **bogus**: that line is a literal string with no interpolation.

### Test count

381 → **390** (+9: 1 dynamic-trump, 5 endless, 3 undo).

## [2.7.0] - 2026-05-04

A responsive-layout overhaul: the game now adapts to any terminal between **80×32** (compact) and arbitrarily large (spacious), picking the largest preset that fits and re-detecting on every render so resize-during-play just works.

### Added

- **Layout system** (`src/belote/ui/layout.py` — new): `LayoutPreset` dataclass and three presets (`COMPACT` 80×32 / `STANDARD` 96×38 / `SPACIOUS` 120×48). `choose_layout(cols, rows)` picks the largest fitting preset. Each preset drives card dimensions, side-column widths, HUD verbosity, and whether the W/E "Last Trick" sidebar is shown.
- **Adaptive card art** in `render.py`: `_card_face_internal` now keys its cache on `(card_w, card_h)`. Standard / spacious render the full Art Nouveau face art; compact (5-row cards) drops to a clean rank-corners-and-suit design that fits the tighter inner area.
- **Per-tier HUD formatter**: spacious widths get the verbose form (full labels + help hints + theme name on the right). Compact and standard widths get an abbreviated single-line bar (`BELOTE  T:♥  NS:200(+50)  EW:80(+30)  5/8  Tk:S`) — fits cleanly in 80 cols. The previous unconditional ~132-char HUD was already overflowing at 96 cols pre-2.7.
- **BelAtro HUD compact mode** (`belatro/ui/hud.py`): drops the joker-name list for `J:N/M [J]` placeholder, abbreviates Ante/Blind/Target labels, adds a partner-mood glyph (`✗ · ○ ● ★`).
- **Vertical centering**: when the terminal is taller than the rendered content, `render()` pads top + bottom equally so the game centres vertically instead of clinging to the top.
- **Tests** (`tests/test_layout.py`, 20 tests): preset-selection boundaries, fits-minimum gate, card-cache layout separation, HUD verbosity per tier, vertical centering math, trick-mat dimension consistency, KeyReader factory regression.

### Changed

- **Minimum terminal size**: 90×32 → **80×32**. A 1366×768 monitor at default font (~150×40) now uses the compact preset comfortably; the previous 90-col floor cut off the bottom rows on many practical setups.
- **Layout-aware redraw**: `render()` clears the screen on layout flavour change (`compact` → `standard`, etc.) so a mid-game resize doesn't leak stale artifacts from the previous layout.
- **`patch_trick_card` and trick-mat row offsets** are now computed from the active layout (`_trick_row_offsets(layout)` returns the seat→row map), instead of being baked-in at standard-preset dimensions.
- **Alt-screen mode is entered before the menu loop**, not when "Start Game" is picked. Without this, every menu redraw frame wrote to the regular terminal scrollback; on exit the user saw a wall of cup-template frames in their shell history. Game-start and BelAtro-mode entry points now stay in alt-screen and just clear when transitioning.

### Fixed

- **`KeyReader()` constructor regression** introduced in 2.6.0's `input.py` refactor. The `__new__`-based factory returned a `_UnixKeyReader` instance via `cls.__new__(cls)`, which Python treats as "not a `KeyReader` subclass" and therefore skips `__init__`. Result: `_stdin_fd` was never set and `__enter__` crashed with `AttributeError`. Factory now calls the concrete reader as a normal constructor (`_UnixKeyReader()`), so its `__init__` always runs.
- **"Infinite main menu" cosmetic bug**: the menu's animation loop was redrawing 3× per second outside of alt-screen mode, so each `clear_screen() + redraw` cycle pushed the previous frame into the terminal scrollback. By the time the user quit the menu, their shell history was filled with overlapping cup templates. Fixed by entering alt-screen mode at the start of the `KeyReader` context, not at game-start.

### Migration notes

- Code that imported `CARD_W`, `CARD_H`, `CARD_GAP`, or `SIDE_COL_W` directly from `belote.ui.render` still works — those constants are now derived from the `STANDARD` preset for back-compat. New code should call `belote.ui.layout.choose_layout(cols, rows)` and read dimensions from the returned `LayoutPreset`.
- The legacy `partner_jokers_double` flag still forces +1 apply for back-compat with tests setting it directly. New partner-joker scaling reads `ScoreAccumulator.partner_tier` (set from `TrustTrack.tier`).

## [2.6.0] - 2026-05-04

A large BelAtro expansion landed in one release: a Phase 0 audit pass plus six feature areas (see `plans/let-do-all-of-radiant-pizza.md`).

### Fixed

**Critical bugs (audit Phase 0.1)**

- `game.py:750` — `random.choice(possible)` for L'Anarchie's `dynamic_trump` boss used the global RNG, ignoring `--seed`. `GameState` now carries a private `_rng: random.Random` field that `start_round` populates from the seeded RNG, and the dynamic-trump branch reads from it. L'Anarchie rounds are now seed-deterministic.
- `gameflow.py:125–126` — `if not isinstance(card, Card): return "UNDO"` silently coerced every non-Card return value (including `"OVERLAY"` from the info-toggle key) into UNDO, restarting the round when the user pressed `I`. `run_play` now handles `"OVERLAY"` explicitly (re-prompts; classic mode has no overlay UI). Same bug existed in `run_bidding` — pressing `I` during bidding hit `if isinstance(res, str): return None` and quit the game; now also handled explicitly.
- `scoring.py:616` — chute scoring hardcoded `162` instead of using `GLOBAL_CONFIG.TOTAL_POINTS + GLOBAL_CONFIG.LAST_TRICK_BONUS`. Replaced; tweaks to either config constant now propagate.
- `scoring.py:319, 326, 628` — `getattr(state, "_seven_eight_trump", False)` silently returned False if the property got renamed. All three sites now read `state.boss_modifiers.seven_eight_trump` directly (matches the boss-flag pattern).
- `ai.py:110–112` — `current_trick in sabotage_tricks` operated on an `object`-typed value pulled from `_joker_state` (mypy errored), and `trick_rank(c, state.trump)` could be called with `trump=None`. Now reads `state.boss_modifiers.agent_double_active` (consistent with the rest), narrows `sabotage_tricks` to `frozenset[int]`, and guards on `trump is not None`.
- `input.py:106–109` — UTF-8 multi-byte handler used `n` for the count of *continuation* bytes, then read `n + 1` bytes. Behaviour was correct but naming was misleading; renamed to `continuation_bytes` / `total_bytes`.

**Test suite hygiene (audit Phase 0.2)**

- `tests/test_official_rules.py::test_chute_declaration_transfer` — first scenario's `breakdown` was overwritten before any assertion, making it dead code. Split into two real tests (one for capot+declaration-transfer, one for defender-belote on taker success).
- `tests/belatro/test_boss_modifiers_integration.py::test_boss_invert_scoring` — body was just `pass`. Now actually tests La Malédiction zeroing the taker's total when NS wins more tricks.
- Same file — `(TrickCard(...),) * 4` patterns built four-identical-cards tricks (invalid). Helper `_trick_won_by_south` builds proper four-seat tricks instead.
- `tests/test_belote.py::test_must_trump_when_void_partner_not_winning` actually tested the partner-winning *exception*. Renamed to `test_void_can_discard_when_partner_winning`.
- `tests/test_belote.py::test_card_points_sum_152` was a duplicate of `test_total_points_consistency`. Dropped.
- `tests/test_new_coverage.py::test_sort_south_hand_persists_across_plays` never called `play_card`. Renamed to `test_sort_south_hand_orders_trump_first_and_is_idempotent`.
- `tests/test_properties.py::test_legal_moves_never_empty` silently `break`-ed on empty hands instead of failing. Now asserts the invariant explicitly.

**Lint/types (audit Phase 0.3)**

- `ruff check`: 72 → 0 errors.
- `mypy --strict`: 15 → 0 errors. Notably refactored `input.py::KeyReader` from a stub-class with runtime `KeyReader = _UnixKeyReader` reassignment to a polymorphic `__new__`-dispatching base, eliminating attribute-error and type-assignment errors and exposing `_restored` / `restore()` cleanly to callers.

### Added

**Phase 0.4 — Coverage backstop** (`tests/belatro/test_phase0_coverage.py`, 13 tests)

Happy-path tests for jokers, partner personalities, and boss modifiers that subsequent Phase 1+ refactors touch: `LeFanatique`, `LeDiplomate`, `LEconome`, `LeFlambeur`, `LeSacrifie`, `LeFantome`, `LeStratege`, `seven_eight_trump`, `dynamic_trump` seed determinism, `no_dix_de_der`, `agent_double_active`, plus a regression guard on `RoundEndEvent` payload.

**Phase 1 — Plumbing foundations** (`tests/belatro/test_phase1_plumbing.py`, 10 tests)

- `Suit.TOUT_ATOUT` is now a real enum value alongside the four card suits, with an `is_card_suit` property and a `CARD_SUITS` tuple. Every `for suit in Suit:` iteration in `game.py`, `ai.py`, and `belatro/partner/personality.py` is gated on `is_card_suit` so cards/decks are never built with TOUT_ATOUT. Under TOUT_ATOUT every card is treated as trump (`card_points` and `trick_rank` updated). `_SUIT_TO_CONTRACT` includes the new suit. `LeFanatique`'s unlock path is re-enabled in `unlocks.py` (was deferred in 2.5.6).
- Player-facing **coinche / surcoinche**. After bidding, if the taker is on the EW team, `RoundUICallbacks.prompt_coinche` is called; the AI rolls a seeded 30% surcoinche on top. `BidMadeEvent` and `RoundEndEvent` now carry `coinche_level: int` and `contract: str`; jokers and the economy can react to it.
- `BeloteAnnouncedEvent` is now actually *emitted* in `round_driver` whenever `state.belote_tracker` flips, with `is_rebelote` set correctly. The event class existed since 2.5.x but was never fired.
- `Rarity` enum on item base (`COMMON / UNCOMMON / RARE / LEGENDARY`); `Joker` gains `fusable: bool = True` for Phase 3 fusion gating. All existing items default to `Rarity.COMMON`.
- New `BelAtroRun` fields: `tierce_charges`, `legendary_unlocked`, `endless`, `endless_ante_offset`, `ante_theme`, `capot_insurance`, `partner_mood`.

**Phase 2 — Content** (`tests/belatro/test_phase2_content.py`, 20 tests)

- *Contract jokers* (`items/jokers/coinche.py`): `CoincheStack` (+4 Mult/coinche level on win), `ToutStreak` (consecutive Tout-Atout wins ramp Mult by ×0.5/streak; resets on Tout failure).
- *Annonce jokers* (`items/jokers/annonces.py`): `TierceCharger` (+5 chips and +1 charge per sequence announced), `RebeloteEcho` (×3 Mult on Rebelote play), `QuinteRoyale` (Legendary — quinte arms a ×4 round multiplier).
- *Vouchers* (`items/vouchers.py`): `CapotInsurance` (one-shot — chute next round survived without run-over), `TierceForge` (placeholder for shop-side charge spending).
- *Tarots* (`items/tarots.py`): `LaMaisonDieu` (sets `disable_next_boss` flag), `LeDiable` (sets `partner_overcut_round` flag).
- *Decks* (`run/decks.py`): `marseille` (annonces ×2, no Belote/Rebelote), `coinche` (+50 starting chips, pre-coinched rounds).
- *Trust as a real second axis* (`partner/trust.py`): `TrustTrack.tier` (0–4 buckets), `TrustTrack.mood()` returning HUD strings. `ScoreAccumulator.partner_tier` replaces the binary `partner_jokers_double` for partner-joker effect scaling — extra applies follow `(0,0,1,1,2)[tier]`. Legacy `partner_jokers_double` still forces +1 apply for back-compat.
- *Betrayal Arc boss* (`run/boss.py::BetrayalArc`): forces `lock_trust_zero` and `agent_double_active` for the round, registered in `ALL_BOSS_MODIFIERS`.
- `_play_blind` (`belatro/main.py`) wires Capot Insurance consumption (one-shot halve on chute) and drains pending Tierce charges into `run.tierce_charges`. `run.partner_mood` is refreshed each blind from `trust.mood()`.

**Phase 3 — Meta** (`tests/belatro/test_phase3_meta.py`, 15 tests)

- *Ante themes* (`run/ante_themes.py`): `AnteTheme` base + `CafeAnte` (+25 chips at ante start, +1 trust on blind-1 win, target 5% softer on boss blind) and `TournoiAnte` (always offers coinche, +money per blind win). `roll_theme(rng_value)` picks one with 30% probability.
- *Endless mode (La Belote Infinie)*: `BelAtroRun.advance_blind` no longer terminates at ante 8 / blind 2 when `run.endless` is True — instead increments `endless_ante_offset` and restarts the blind cycle. `BelAtroRun.enter_endless()` toggles the flag and clears `run_won`. `calculate_target` accepts `endless_offset` for ×2.2-per-loop super-exponential scaling. `BelAtroRun.current_blind` returns dynamically-built `endless_ante` instances when offset > 0.
- *Joker fusion* (`items/base.py::fuse_jokers`): two jokers → one with rarity bumped one tier (clamped at RARE — never auto-promotes to LEGENDARY), `fusable=False` on the result so fused jokers can't be re-fused, names concatenated. Rejects legendary inputs and `fusable=False` inputs with `FusionError`.

### Changed

- `GameState` gains a private `_rng: random.Random` field (`compare=False, repr=False`) so seeded randomness is reachable mid-play. Existing call sites that don't pass an RNG continue to work — the field defaults to a fresh `random.Random()`.
- `BidMadeEvent` and `RoundEndEvent` payload extensions (`coinche_level`, `contract`, `trump`).
- `make_deck()` builds from `CARD_SUITS` instead of `list(Suit)`; `deck.py` exposes `CARD_SUITS` for clean iteration in BelAtro code.
- Test count: 303 → 361 (+58 across Phase 0.4, Phase 1, Phase 2, and Phase 3 suites).

## [2.5.6] - 2026-05-03

### Fixed

**Critical crashes (BelAtro module)**
- `belatro/items/tarots.py`: `random` was never imported — `NameError` on any use of `LeJugement`, `LaPretresse`, or `LeFou`.
- `belatro/core/run_state.py`: `BelAtroRun` had no `consumables` list — `AttributeError` whenever tarots or the shop tried to add a Planet or Tarot to the player's inventory.
- `belatro/run/shop.py`: `run.consumables` crash removed; the double-append fallback in the overflow branch also removed.
- `belatro/items/registry.py`: `get_available_jokers(None)` and `get_available_vouchers(None)` crashed with `AttributeError` — both now accept `Profile | None` and treat `None` as "show all non-unlockable items".
- `belatro/engine/round_driver.py`: `Suit` was referenced in type annotations but never imported — `NameError` on module load.
- `belatro/progression/save.py`: `stats=data.get("stats", {})` returned an empty dict on profiles missing any stat key, causing `KeyError` when `unlocks.py` accessed `stats["total_capots"]`. Load now merges against the full default dict.
- `belatro/engine/event_bus.py`: `EventBus.unsubscribe` called `list.remove` unconditionally — `ValueError` if the handler was never subscribed. Now uses `contextlib.suppress(ValueError)`.

**Logic bugs (jokers / progression)**
- `LaSentinelle` (`hand_comp.py`): detection loop read `state.get("trump")` which is never written to the joker state dict, so it was always `None` and the joker never fired. Fixed to use `event.trump`.
- `LeFanatique` (`contract.py`): checked `state.get("contract") != "tout"` but `"contract"` was never injected into joker state, so the joker never activated. `ScoreAccumulator` now injects `event.contract` into joker state on every `BidMadeEvent`. Key corrected to `"tout_atout"` to match actual contract identifiers.
- `sans_atout_wins` stat (`unlocks.py`): incremented on every Sans Atout round regardless of outcome. Now only counts rounds where the NS team declared Sans Atout and succeeded.
- `LePuriste` (`contract.py`): `getattr(event.breakdown, "is_failed", True)` — wrong default (`True` = assume failed) silently blocked the joker from ever triggering. Default changed to `False`.
- `LaSentinelleP` (`shaper.py`): fired `trump_led = True` whenever North won any trick containing trump, including when North was *following* suit. `TrickWonEvent` now carries `leader_seat: Seat` (default `Seat.SOUTH` for backwards compatibility); the joker correctly sets the flag only when `leader_seat == Seat.NORTH` and the lead card was trump.
- `LeBanquier` (`economy.py`): `state.get("target_score", 80)` hardcoded to 80 because the key was never injected. `ScoreAccumulator.trigger_round_start` now writes `target_score` into the joker state dict.
- `LeDernierMot` (`trick_timing.py`): hard-coded `add_chips=-10` to cancel the Dix de Der bonus regardless of whether the `no_dix_de_der` boss modifier was active. Now reads `state.get("no_dix_de_der", False)` (injected at round start) and only subtracts when the bonus was actually applied.

**Boss modifier enforcement gaps**
- `LAvocat` (`l_avocat`): `auto_coinche` flag was set on `BossModifiers` but never read. `_play_blind` now doubles `acc.target_score` before the round; if the player wins, the base payout is tripled (2× added on top of `economy.process_round_end`).
- `LeDivorce` (`le_divorce`): `lock_trust_zero` flag was set but `TrustTrack` was never frozen. Trust is now temporarily set to 0 before `drive_round` (suppressing partner joker doubling and AI difficulty bonuses), restored to its original value after, and all post-round trust updates (`blind_beaten`, `big_margin_win`, `blind_failed`, `chute`, `capot_together`) are skipped.
- `LAgentDoubleBoss` (`l_agent_double_boss`): `_agent_double_active` caused North to sabotage for all 8 tricks despite the description stating "a random 3 tricks". `round_driver.drive_round` now picks 3 random trick numbers via the round RNG and stores them in `_joker_state["agent_double_tricks"]`; `ai.py` gates the sabotage behavior on the current trick number.
- `LeBrouillard` (`le_brouillard`): `hide_hud` flag was set but `BelAtroHUD.render` always drew the chips×mult score line. The score row is now skipped when `state.boss_modifiers.hide_hud` is True.
- `LeFantomePartenaire` (`le_fantome_partenaire`): `hide_partner_hand` flag was set but `show_north` in `_play_blind` was computed only from `run.show_north_hand` and `trust.shares_void_info`. `show_north` is now forced to `False` when this boss is active, overriding both.

**Joker accuracy**
- `LePuriste` (`contract.py`): `on_round_end` returned a hard-coded `add_money=10` regardless of the actual round payout. It now sets `joker_state["puriste_triggered"] = True` instead; `_play_blind` reads the flag after `economy.process_round_end` and adds an equal extra amount, correctly doubling the base payout.

### Added

**Incomplete features now implemented**
- `BelAtroRun` new fields: `permanent_chips`, `permanent_mult`, `guarantee_tarot_in_shop`, `show_partner_bid_tendency`, `tie_breaks_for_taker`, `partner_throws_trick`.
- `Economy.bonus_per_round`: flat per-round cash bonus, incremented by vouchers.
- `Joker.on_purchase(run)`: lifecycle hook called once at buy time for permanent run-level effects. `Shop._apply_item` now calls it after adding a joker.
- `Planet.use(run)`: applies `level_up_reward()` into `run.contract_levels`, stacking numerically on repeated use.
- **Tarot cards**: `LaRoue` (`+1.0 permanent Mult`) and `LaForce` (`+20 permanent chips`) fully implemented.
- **Vouchers**: `LaTelescope` (`+$1/round via bonus_per_round`), `LeGrimoire` (sets `guarantee_tarot_in_shop`), `LEncyclopedie` (sets `show_partner_bid_tendency`), `LesCartesDorees` (`+1 interest rate, +5 interest cap`), and `LaBalance` (sets `tie_breaks_for_taker`) all implemented.
- **Corrupted joker negative effects**: `LeTraitre.on_purchase` sets `run.partner_throws_trick = True`; `LeDemon.on_purchase` reduces partner trust by 3; `LAgentDouble` tracks a per-round sabotage window in joker state.
- **Planet contract bonuses consumed**: `ScoreAccumulator` now applies `contract_levels` rewards during play — per-trick chip bonuses (Saturn), per-trick Mult bonuses (Venus), Jack/9 capture bonuses (Jupiter), honor bonuses in Sans Atout (The Moon), capot chip bonus (Pluto), and round-win money bonus (Mercury).
- **Permanent Tarot bonuses applied**: `ScoreAccumulator.trigger_round_start` applies `permanent_chips` and `permanent_mult` from the run to the initial `GameState` before the round begins.
- `ScoreAccumulator` wired in `BelAtroGame._play_blind`: `target_score`, `contract_levels`, `permanent_chips`, and `permanent_mult` are now set from the active run before each blind.

### Changed
- `TrickWonEvent` gains `leader_seat: Seat = Seat.SOUTH` field. `round_driver.drive_round` populates it from `last_trick[0].seat`. All existing event construction and tests remain compatible via the keyword-argument default.
- `round_driver.py` import cleanup: removed unused `Rank`, `card_points`, `clear_announced`, and `BeloteAnnouncedEvent`; added the missing `Suit`.
- `Shop.generate_inventory` respects the `guarantee_tarot_in_shop` flag set by `LeGrimoire`.
- `LeFou` (tarot) no longer adds a copy of itself to consumables; also respects the consumable slot limit.

## [2.5.5] - 2026-05-03

### Fixed
- **BelAtro Run Loop**: Fixed multiple critical crashes, including a `TypeError` in `drive_round` due to signature mismatch and an `IndexError` when tricks were accessed prematurely.
- **Event Bus Integrity**: Fixed `TrickWonEvent` instantiation error by providing missing `trick_number` and `trump` context.
- **Run State Consistency**: Added missing `consumable_slots` to `BelAtroRun` to prevent crashes when applying certain Vouchers (e.g., Le Couteau).
- **Cache Clear Bug**: Fixed an `AttributeError` when clearing the legal cards cache by ensuring the implementation function is properly decorated with `@lru_cache`.
- **Input & HUD**: Fixed the `[I]` key mapping for the score overlay HUD and synchronized the Windows `KeyReader` to support all game-specific keys.

## [2.5.4] - 2026-05-03

### Fixed
- **Missing read_timeout**: Fixed an `AttributeError` in the main menu by implementing the `read_timeout` method in the `KeyReader` class.
- **IndentationError in trick_timing.py**: Fixed a critical syntax error in the BelAtro items module.
- **LePremierSang Logic**: Fixed `LePremierSang` joker to correctly apply +2 Mult (additive) and track its active state.

## [2.5.3] - 2026-05-03

### Fixed
- **IndentationError in game.py**: Fixed a critical syntax error that prevented the game from starting.

## [2.5.2] - 2026-05-02

### Fixed
- **Critical Winner Detection Bug**: Resolved an issue in `game.py` where trick wins were assigned to the wrong player.
- **Scoring Engine Desync**: Fixed a major bug in `round_driver.py` where trick points were being calculated manually, leading to desyncs with boss modifiers. Now uses a direct state differential from the core engine.
- **Declaration Scoring**: Realized actual point values for sequences and carrés in `round_driver.py` using the official scoring utilities.

### Added
- **Partner Trust Integration**: Fully wired the trust system into the BelAtro run loop. Trust now increases on blind beats and big wins, and decreases on failures or chutes.
- **AI Personalities in Bidding**: The partner AI now uses its assigned personality (e.g., *Le Courageux*, *L'Économe*) to make bidding decisions, respecting trust levels.
- **Dynamic Partner Hand Visibility**: The partner's hand now automatically becomes visible to the player once the "shares void info" trust threshold is met.
- **Performance Cache Invalidation**: Added targeted cache clearing after boss modifier application to ensure game logic remains accurate and performant.

## [2.5.1] - 2026-05-02

### Added
- **BelAtro Collection Discovery**: Items are now only revealed in the collection when actually encountered in-game, rather than immediately upon unlocking.
- **Auto-Save Persistence**: Added automatic profile saving after run initialization and shop encounters to ensure discovered items are never lost.

### Fixed
- **BelAtro Shop Crash**: Resolved a `NameError` in the shop UI by adding the missing `sys` import.
- **Trick Visibility Timing**: Fixed a race condition in `round_driver.py` where the 4th card of a trick was cleared before it could be rendered. The UI now correctly displays all 4 cards on the table before the trick-win popup appears.

## [2.5.0] - 2026-05-02

### Added
- **Functional State Architecture**: Completed the transition to a pure functional engine. Joker state is now stored immutably in `GameState`, ensuring absolute "frozen-safety" and preventing state leakage between rounds.
- **Comprehensive BelAtro Test Suite**: Added a massive collection of 50+ new integration and regression tests covering all 57 critical edge cases identified in the audit. Total test count reached 276.
- **Performance Benchmarking Suite**: Added a new benchmark tool in `scripts/benchmark.py` to measure scoring, dealing, and legal card calculation performance.

### Changed
- **Scoring Engine Refactor**: Decoupled boss modifier scoring logic into specialized helper functions, significantly improving maintainability and reducing risk of regression in complex Boss Blinds.
- **AI Strategy Decomposition**: Refactored the Hard AI decision-making into a clean strategy pattern, allowing for more granular tactical tuning.
- **EventBus Reliability**: Overhauled `EventBus.emit` to safely handle handler unsubscription during event dispatch, fixing a potential runtime crash.
- **Immutable Score Accumulation**: `ScoreAccumulator` now returns a new `GameState` instead of mutating internal fields, aligning BelAtro with the core engine's architectural principles.

### Fixed
- **Animation Skip Reset (M6)**: Animation fast-forwarding now correctly resets on every human turn, preventing the game from accidentally staying in high-speed mode.
- **Score Overflow Precision**: Fixed a floating-point precision issue in `ScoreAccumulator` when dealing with extremely large chip counts (billions+).
- **Boss Blind Core Bugs**: Fixed all remaining audit bugs (B1-B8), including boss modifier application, scoring accumulation disconnects, and deck-specific bonus triggers.

## [2.4.1] - 2026-05-02

### Fixed
- **BelAtro Rules UI**: Fixed a major rendering bug where the rules screen would not clear correctly, leading to overlapping text.
- **Dynamic Formatting**: Rules screen now correctly handles terminal resizing and dynamic centering.

## [2.4.0] - 2026-05-02

### Added
- **BelAtro Collection (Almanac)**: A persistent gallery in the expansion menu to track discovered Jokers, Tarots, Planets, and Vouchers.
- **Full Boss Blind Suite**: All 17 unique bosses implemented, including complex mechanics like *L'Anarchie* (dynamic trump) and *La Rupture* (no consecutive wins).
- **Hard AI Overhaul**: Improved endgame awareness (Dix de Der), strategic discarding, and 2-ply void inference.
- **Enhanced UI Terminology**: Transitioned to "You" and "Partner" labels for a more immersive single-player experience.

### Changed
- **Single-Player Focus**: Removed Hotseat (2P) mode and simplified the game engine and UI menus accordingly.
- **Consolidated Save Paths**: All local data (stats and profile) now live in a unified `belote` directory.
- **Menu Streamlining**: Removed "Mode" and "Reset Statistics" options for a cleaner main menu.

### Fixed
- **Gameflow Reliability**: Fixed a regression that caused certain tests to hang by properly mocking UI prompts.
- **Technical Integrity**: Achieved 100% type-safety (0 mypy errors) across all source and test modules.

## [2.3.3] - 2026-05-02

### Added
- **BelAtro Mode Integration**: Fully integrated the BelAtro roguelite mode into the main menu.
- **WIP Deck Completion**: Fully implemented all starting decks (L'Ermite, Le Vétéran, Le Flambeur) with their unique starting items and modifiers.
- **Advanced Joker Logic**: Completed implementation for all 50+ Jokers, including complex round-end and bidding-phase triggers.
- **Dynamic UI Rendering**: Refactored menu systems to dynamically center art and text based on terminal width.
- **Alternate Screen Support**: Implemented alternate screen switching for BelAtro to provide a clean, isolated terminal buffer.

### Fixed
- **BelAtro Startup**: Resolved a `TypeError` and `ImportError` that prevented BelAtro from launching correctly.
- **UI Centering**: Fixed an issue where menu art assumed a fixed 80-column width, causing misaligned headers on different terminal sizes.
- **Game Loop Continuity**: Fixed a bug where BelAtro would exit immediately back to the main menu instead of starting a run.
- **Event Bus Robustness**: Overhauled the `RoundEndEvent` to provide complete game state snapshots to Jokers, fixing several uninitialized logic paths.

## [2.3.1] - 2026-05-01

### Fixed
- **Contract Engine Logic**: Fixed a critical bug where trick winner detection failed during "Sans Atout" (No Trump) contracts. The engine now correctly handles `trump=None` scenarios.
- **Tout Atout / Sans Atout support**: Fully implemented correct card values and rankings for special contracts.
  - *Tout Atout*: All Jacks (20 pts), all 9s (14 pts), and all suits follow trump ranking.
  - *Sans Atout*: All Aces (11 pts), all 10s (10 pts), and all 9s (0 pts).
- **Coinche Multipliers**: Fixed a bug where Coinche (×2) and Surcoinche (×4) multipliers were not being applied to the final score in the core engine.
- **Sequence Detection**: Refactored sequence detection logic to be more maintainable and fixed a potential `NameError` in the detection loop.
- **Project-wide Type Safety**: Resolved over 250 `mypy` errors across the `tests/` and `src/` directories, achieving 100% strict type compliance.
- **Linting & Code Cleanup**: Eliminated all `ruff` violations and improved idiomatic Python usage throughout the codebase.
- **API Consistency**: Updated `trick_winner_seat`, `card_points`, and `trick_rank` to explicitly accept the `contract` type, ensuring accurate scoring and AI decisions across all game modes.

## [2.3.0] - 2026-05-01

### Added
- **Full Tarot System**: All 10 Tarot cards are now fully functional. Use `[U]` during your turn to open the consumable menu.
  - *Le Chariot*: Steal the current trick (wired `force_next_trick_win`).
  - *La Roue*: Change trump mid-round.
  - *Le Jugement*: Resurrect sold Jokers.
  - *Le Monde*: Double declaration points.
  - *La Tempérance* & *Le Fou*: Permanent deck editing (random removal/duplication).
- **Complete Voucher Set**: All 9 vouchers are implemented with unique hooks.
  - *La Télescope*: Preview the talon during bidding.
  - *L'Encyclopédie*: Reveal partner personality during bidding.
  - *Les Cartes Dorées*: Increased Gold Seal value (+$5).
  - *Le Couteau*: Unlock card destruction in the Shop for $2 refunds.
  - *La Balance*: Automatic win on close losses (within 10 points of target).
  - *La Surcoinche*: Unlocks the massive ×4.0 Mult contract.
- **Dynamic Deck-Building**: The game engine now supports modified decks, allowing for permanent card additions and removals across a run.
- **Corrupted Joker Mechanics**: Implemented `Le Démon` (trust penalty on purchase).
- **Expanded Test Suite**: Added 52 new tests (total 165), significantly increasing coverage for `round_driver.py`, `shop.py`, `tarots.py`, and `vouchers.py`.

### Changed
- **Bidding Overhaul**: Opponents can now Coinche your bids (×2.0 Mult), and you can counter with Surcoinche (×4.0 Mult) if the voucher is owned.
- **Input Map**: Added `[U]` key for using consumables and removed `Tab` -> `Enter` mapping.
- **Performance**: Increased render cache size to 2048 and moved suit/ID mappings to module level for faster scoring.
- **Code Quality**: Extracted `_undo_or_restart` helper in `gameflow.py` and improved `EventBus` error logging.

### Fixed
- **Critical Bug Fixes**:
  - *La Sentinelle*: Now correctly requires both Jack AND trump suit.
  - *Le Rebelle*: Multiplier no longer stacks exponentially on Belote+Rebelote.
  - *Le Stratège*: Strategic bidding logic (requires high-value cards instead of just any hand).
  - *Recursive UI*: Fixed stack overflow risk in `prompt_card` on UNDO.
  - *Shop Duplicates*: Replaced random choice with sampling to prevent identical jokers in shop.
  - *UI Truncation*: Card destruction UI no longer truncates at 20 cards.
- **Boss Modifier Engine**: Fully wired 17 boss modifiers (forced pass, zero-point kings/tens, no Dix de Der, etc.) into the game engine.
- **Declaration scoring crash** (`round_driver.py`): replaced nonexistent `belote.deck.declaration_points` import with `belote.scoring.get_declaration_points`.
- **JokerResult multiplier zeroing** (`items/base.py`): `times_mult` default changed from `0.0` to `1.0`.
- **BelAtro standalone crash** (`belatro/main.py`): fixed missing `KeyReader` context.
- **Bid prompt null-dereference** (`ui/prompts.py`): added guards for `up_card`.
- **Type safety**: Resolved all 32 mypy errors and improved overall project type integrity.
- **Starting Decks**: All bonuses for *Le Joueur*, *L'Aristocrate*, *L'Ermite*, *Le Flambeur*, *Le Vétéran*, and *L'Anarchiste* are now correctly applied.
- **Scoring Hooks**: Wired missing `on_bid`, `on_round_start`, and `on_round_end` triggers for all Jokers.

## [2.2.0] - 2026-04-30

### Added
- **BelAtro Score Overlay Toggle**: Press `[I]` during any Belote/BelAtro game to toggle the per-trick score breakdown popup on or off. Useful when you want an unobstructed view of the table between tricks.

### Fixed
- **BelAtro trick display**: The 4th card played in a trick (the trick-completing card) was never shown on the table — the table went blank before the score popup appeared. All 4 cards now remain visible on the mat until the next trick begins.
- **BelAtro 4th-card visibility**: `on_card_played` now reconstructs the display state from `completed_tricks[-1]` when `current_trick` has been cleared by `play_card`, mirroring the classic mode's pre-play display state pattern.

## [2.0.1] - 2026-04-30

### Added
- **Le Républicain deck** is now fully playable: 7s and 8s are wild cards that can be played on any trick regardless of suit constraints. Your team earns +5 chips for every 7 or 8 you capture.
- **Le Carnet voucher** is now fully implemented: your partner's full hand is visible to you throughout every round. You earn +1 Mult each time South personally wins a trick.
- Both mechanics documented in the in-game Belatro Rules screen (EN and FR), under new "Starting Decks" and "Vouchers — Le Carnet" sections.

### Fixed
- Card-count invariant assertion added to `_handle_trick` to catch any future hand-size corruption early.
- Cards on the trick mat now render immediately after each card is played (previously only updated after the trick was complete).

## [2.0.0] - 2026-04-30

### Added
- **BelAtro Expansion**: A massive roguelite expansion inspired by Balatro, integrated into the Belote core.
  - **The Run**: Progress through 8 'Antes' with increasing target scores. Each Ante consists of Small, Big, and Boss Blinds.
  - **Scoring Engine**: New Multiplier-based scoring system: `Score = (Chips + Declarations) × Multiplier`.
  - **Joker System**: 50+ unique Jokers (Contract, Corrupted, Economy, Hand Comp, Trick Timing) that provide passive buffs and scoring modifiers.
  - **Consumables**: Planet cards to level up contracts, Tarot cards for one-shot effects, and permanent Vouchers.
  - **Partner Trust**: Dynamic relationship with your AI partner. High trust reveals their hand/voids and boosts their specific "Partner Jokers."
  - **Boss Blinds**: 10+ unique bosses with rule-breaking modifiers (e.g., hidden scores, suit debuffs, mid-round trump changes).
- **Event-Driven Architecture**: Introduced a centralized `EventBus` to handle complex item interactions and state updates.
- **Save/Load System**: Persistence for run progress, unlocks, and global statistics.
- **New UI Package**: Dedicated BelAtro HUD with Multiplier animations, Shop interface, and Trust bar visualization.

### Changed
- **Entry Points**: Added `belatro` as a secondary CLI command for direct access to the roguelite mode.
- **Core Refactor**: Decoupled the game loop from the rendering engine to support multiple game modes (Classic vs. BelAtro).
- **Test Suite**: Expanded tests to cover economy, ante scaling, item registry, and boss modifiers.

### Fixed
- **State Leakage**: Fixed an issue where items from previous runs could occasionally persist in the registry.
- **Trust Calculation**: Resolved a rounding error in trust gains during high-multiplier rounds.

## [1.1.0] - 2026-04-30

### Added
- **Incremental AI Void Inference**: Optimized AI memory to process tricks incrementally, significantly reducing CPU usage during late-game decision making.
- **Windows Input Support**: Added full `read_timeout` support for the Windows `KeyReader`, enabling animation skipping (Space/Esc) on Windows machines.
- **Enhanced Test Suite**: Added 4 new test cases covering Belote-to-defender scenarios, East-West taker variants, and trump sequence comparison logic.

### Changed
- **Scoring Breakdown Refactor**: Refactored the internal `ScoringBreakdown` structure to use clearer terminology (`table_pts` vs `credit_pts`), improving maintainability of the scoring engine.
- **Cache Optimization**: Replaced mutable object keys in the `trick_winner_seat` cache with primitive IDs, increasing the LRU cache hit rate to nearly 100%.
- **UI Layout Safety**: Migrated hardcoded terminal offsets to a centralized constant `_TRICK_ROW_OFFSETS` to ensure layout stability across different terminal heights.

### Fixed
- **Ineffective LRU Caching**: Fixed a major performance issue where the trick winner cache was effectively bypassed on every call due to object identity mismatches.
- **Scoring Comparison Bug**: Fixed a logic error in `scoring.py` where contract fulfillment (Litige/Chute) was comparing raw card points instead of total round points (including 10 de der and declarations).
- **Flawed Chute Test**: Corrected `test_chute_declaration_transfer` which was incorrectly triggering the capot code path instead of the intended chute path.
- **Circular Imports**: Resolved a brittle circular dependency between `themes.py` and `ui/render.py` using a new observer-based callback system.
- **No-op Tests**: Fully implemented `test_litige_detection` and `test_current_round_points_update` which were previously empty stubs.

## [1.0.0] - 2026-04-30

### Added
- **Official Rules Compliance**: Significant overhaul of game logic to align with the [Fédération Française de Belote](https://www.ffbelote.org/regles-officielle-belote/).
- **Litige (Tie-break)**: Implemented standard tie-break rules. On a card-point tie (e.g., 81-81), the taker's points and declarations are held in escrow and awarded to the winner of the next round.
- **Improved Capot Scoring**: Winning all 8 tricks now awards exactly 252 points (152 cards + 100 bonus) and includes all declarations from both teams.
- **Correct Chute Scoring**: On a failed bid (chute), the defenders now correctly receive 162 points plus all declarations from both teams.
- **Tie-breaker Rounds**: Games ending in a perfect tie beyond the target score now trigger an additional round instead of selecting a winner arbitrarily.

### Changed
- **Default Capot Points**: Updated `CAPOT_BASE` from 250 to 252.
- **Bilingual Rules Text**: Updated the English and French rules viewer to reflect the new official scoring mechanics.
- **Project Version**: Officially promoted to version 1.0.0.

### Fixed
- **Capot Announcement Bug**: Fixed a regression where Capot was not announced for the NS team due to a truthiness check on team index `0`.

## [0.9.9] - 2026-04-28

### Fixed
- **Critical: Failed bid (chute) scoring**: Taker's declarations were incorrectly added to the defender total on failure. In standard French Belote, the taker's declarations are annulled on chute — not transferred. Defender total is now `162 + defender_declarations + defender_belote` only.
- **Critical: Belote announcement fires on every subsequent card**: `state.announced` was preserved across plays, causing the Belote!/Rebelote! popup to re-trigger on each card played after the announcement. Announcement now resets to `None` at the start of each play and is cleared in `gameflow.py` after display.
- **Critical: Hand sort not persisted**: Pressing [O] to sort South's hand updated only the local variable in `prompt_card`; the sorted state was never propagated back to `run_play`, reverting on the next turn. `prompt_card` now returns `(Card | str | None, GameState)` so callers receive the potentially-sorted state.
- **Multi-byte UTF-8 input**: `os.read(fd, 1)` reads one byte at a time — multi-byte characters (accented letters, symbols, emoji) were split across reads producing garbled output. Input reader now accumulates the correct number of continuation bytes based on the leading byte's UTF-8 prefix bits.
- **AI hard-mode magic number**: Trump rank threshold `rank < 14` hardcoded the numeric rank of the 9 of trump. Now computed as `trick_rank(Card(trump, Rank.NINE), trump)` so it remains correct if the ranking table changes.
- **`TrickCard` NameError**: `TrickCard` was referenced in `scoring.py` and `ai.py` without being imported, causing a runtime crash during trick scoring.
- **`ScoringBreakdown` missing fields**: Early-return path in `score_round` omitted `taker_rebelote` and `defender_rebelote` keyword arguments, causing a `TypeError` on all-pass rounds.
- **`resolve_declarations` type mismatch**: Parameter type corrected from `dict[Seat, dict[str, object]]` to the proper `SeatDeclarations` TypedDict, eliminating unsafe `.get()` calls with stale fallbacks.
- **`is_capot` walrus operator**: Fixed malformed walrus expression that prevented capot detection from evaluating correctly.
- **`belote_tracker` tuple type**: Three call sites in `game.py` passed `tuple(list)` producing `tuple[bool, ...]` where `tuple[bool, bool]` was required; fixed to explicit two-element construction.
- **`deal()` return type**: Third element annotation corrected from `tuple[tuple[Card, ...], ...]` to `tuple[Card, ...]` to match the actual talon structure.
- **Trump `None` guard in `ai.py`**: Medium AI `_medium_play` now returns early via `_easy_play` when trump is `None`, preventing a `Suit | None` vs `Suit` type error.
- **Trump `None` guard in `game.py`**: `play_card` extracts `trump` as a local variable and guards `card_points` summation with `if trump is not None else 0`.

### Changed
- **`trick_winner_seat` cache cleared between rounds**: `clear_legal_cards_cache()` now also clears the `trick_winner_seat` LRU cache to prevent unbounded memory accumulation across long games.
- **Theme change invalidates card render cache**: `ThemeManager.set_current()` now calls `clear_card_cache()` so new theme colors apply immediately without stale card face renders.
- **`announced` field decoupled from HUD badge**: The HUD Belote!/Rebelote! badge is now derived from `belote_tracker` (persistent) rather than `state.announced` (one-shot trigger), giving correct behaviour in both the popup and the persistent status bar.
- **AI void tracking incremental**: `_update_voids` now processes only new cards in the current trick on each call rather than re-scanning all cards from index 1 every time.
- **`initial_hands` comment**: Added clarifying comment that `initial_hands` stores 8-card hands at start of play (not the 5-card deal), used for declaration detection during scoring.
- **Removed dead fields**: `GameState.declarations_resolved` (set but never read) and `GameState.round_scores` (superseded by `current_round_points`) removed to eliminate confusion.
- **`themes` import moved to top of `ansi.py`**: The `from .themes import theme_manager` import was placed mid-file with a `# noqa: E402` suppressor; moved to the standard top-of-file position.
- **Type safety**: Resolved all 70 mypy strict-mode errors across 12 source files — `game.py`, `scoring.py`, `ai.py`, `gameflow.py`, `deck.py`, `input.py`, `stats.py`, `rules.py`, `themes.py`, `config.py`, `ui/prompts.py`, `ui/render.py`.
- **Code quality**: Resolved all 243 ruff lint violations (188 auto-fixed, 55 manual) across the entire codebase — covering unused imports (F401), bare `except` (B), shadowed builtins (A), redundant conditionals (SIM), pathlib migration (PTH), return simplification (RET), and more.
- **`rules.py` typed content**: Introduced `RulesSection` and `RulesPage` TypedDicts for the rules content dictionary, replacing untyped `dict[str, object]`.
- **`input.py` raw-mode guard**: `_old_termios` type changed from `termios.termios` to `list[Any]` to match the actual return type of `termios.tcgetattr`.
- **`ui/prompts.py` render cache**: Cache key type corrected from `str` to `tuple[str, int]` to include terminal width, preventing stale renders on resize.

### Tests
- Added test: failed bid taker declarations are annulled (not transferred to defenders).
- Added test: multi-byte UTF-8 input (`♠` = 3 bytes) read as a single `CHAR` event.
- Added test: `sort_south_hand` is idempotent and produces a stable ordering.
- Added test: declarations stored at bid time match those recalculated at scoring.

### Performance
- **`visible_len` ANSI cache**: Increased LRU cache size from 1 024 to 4 096 slots to reduce cache evictions during rapid re-renders.

## [0.9.8] - 2026-04-28

### Added
- **Overtrump Rule Enforcement**: Added strict validation and tests for the overtrump rule when a trump suit is led.
- **Improved AI Void Inference**: AI now infers opponent voids in real-time from the current trick, making it more tactically aware during play.
- **Consistency Tests**: Added new tests to verify point conservation and rule integrity across all trump suits.

### Changed
- **Scoring Integrity**: 
    - Corrected `TOTAL_POINTS` to 152 to match the actual sum of card points (A=11, 10=10, K=4, Q=3, J=2/20, 9=0/14).
    - Refactored "failed bid" (chute) logic to explicitly account for card points (152) and last trick bonus (10), totaling 162.
- **Performance Optimizations**:
    - **Dictionary Rebuilds**: Eliminated redundant mapping rebuilds in `legal_cards` by precomputing card-to-ID lookups.
    - **Batch Stats I/O**: Reduced disk pressure by batching statistics flushes to the end of each game.
- **UI & Controls**:
    - **Interruptible Announcements**: Players can now skip banner announcements (Dix de Der, Capot) using Space or Esc.
    - **Adaptive Layout**: Fixed coordinate offsets in `patch_trick_card` to ensure perfect card placement on all terminal sizes.
    - **Input Consistency**: Resolved 't'/'T' conflict; 't' is now dedicated to History and 'T' to Theme switching.
- **Architectural Improvements**:
    - **Clean Exports**: Standardized `replace` usage by importing directly from `dataclasses`.

### Fixed
- **Worst Score Display**: Fixed a bug where round scores ≥ 200 were hidden in the statistics screen.
- **Off-suit Comparison**: Fixed a redundancy in `_card_beats` to correctly handle same-suit rank comparisons for off-suit cards.

## [0.9.7] - 2026-04-27

### Added
- **Pre-game Hand Preview**: Shows your hand and estimated declaration points before the bidding phase starts.
- **Strategic Hand Sorting**: "Play value" sort mode that groups honors (J, 9, A, 10...) and separates trump strategically.
- **Improved Medium AI**: Now tracks inferred voids to force trumps or discards, making it significantly more challenging.
- **Configurable AI Seats**: Fully independent AI difficulty selection for each seat in the main menu.
- **Illegal Move Protection**: Play loop now strictly enforces rules and raises `IllegalMoveError` for invalid card plays, preventing state corruption.
- **Centralized Configuration**: All game rules, timings, and UI dimensions consolidated into a global `Config` system.

### Changed
- **Performance Optimization**: 
    - HUD updates are now targeted (1-line refresh) instead of full-screen re-renders during animations.
    - Memoized `trick_winner_seat` calculation to avoid redundant scoring logic.
    - Switched to a manual per-round cache for legal card lookups.
- **XDG Compliance**: Statistics are now stored in standard locations (`~/.local/share/belote/stats.json`) with automatic fallback.
- **Refactored Architecture**: Eliminated module-level global state in favor of dedicated `StatisticsManager`, `AudioManager`, and `TerminalContext` managers.

### Fixed
- **Sentinel Correction**: Fixed `worst_round_score` initialization and added support for recording 0-point rounds (capot against you).
- **Type Safety**: Fixed potential crashes in declaration processing by adding safe detail access for Carré/Belote types.
- **Deterministic RNG**: Round deals are now deterministic when using the `--seed` CLI flag.
- **Import Errors**: Fixed missing `GameState` import in entry point.
- **Test Integrity**: Fixed numerous test suite regressions related to generator types and mocked dependencies.

## [0.9.6] - 2026-04-27

### Added
- **Enhanced Statistics**: Added tracking for best/worst round scores, longest game length, and win rate broken down by AI difficulty level.
- **Session Stats**: New "This Session" panel in the statistics screen for real-time session tracking.
- **Improved AI Strategy**: 
    - Medium AI now prioritizes leading from its longest suit and avoids leading into opponent strength.
    - Hard AI features an improved 2-ply lookahead for critical tricks and better void inference.
    - Added "AI personality" variance for less predictable bidding.
- **Non-UTF-8 Support**: Added graceful degradation for terminals without UTF-8 support (text-only card representation).
- **Expanded Test Suite**: Increased coverage with new AI logic, gameflow integration, and property-based tests.

### Changed
- **UI Refactoring**: Major modularization of `ui.py` into `belote.ui` package (`render`, `prompts`, `menu`, `announce`).
- **Game Flow Separation**: Extracted game loop logic from `main.py` into `gameflow.py`.
- **Keyboard Shortcuts**: Changed History shortcut to 'T' (previously 'H') to resolve conflicts with Help.
- **Language Toggle**: Changed language toggle in rules screen to 'L' to avoid conflict with History.

### Fixed
- **Initial Hands Bug**: Fixed a bug where `initial_hands` was incorrectly reset to empty tuples at the start of a round.
- **Input Validation**: Added defensive checks to ensure chosen cards are always in the player's hand and legal.
- **Redeal Loop**: Ensured dealer rotation works correctly during repeated "all-pass" bidding rounds.

## [0.9.5] - 2026-04-26

### Added
- **Hand Sorting**: Press 'O' to sort your hand by suit and rank.
- **Keyboard Shortcut Help**: Press '?' for a quick reference of all key bindings.
- **Mute Toggle**: Press 'M' to toggle sound effects on/off.
- **Declaration Announcements**: Automatic display of sequences (Tierce, Quarte, etc.) and Carrés after the first trick.
- **CLI --version**: Added standard version flag.

### Improved
- **Terminal Performance**: Switched to incremental rendering (cursor move + EOL clear) for zero-flicker UI.
- **AI Performance**: Optimized void inference and added LRU caching for legal card lookups.
- **Memory Efficiency**: Optimized GameState cache keys and pre-calculated Belote eligibility.
- **Reliability**: Declarations now use pre-calculated initial hands to prevent reconstruction errors.
- **Sound Effects**: Better timing and distinct sounds for different game events.

### Fixed
- Fixed infinite loop in `show_stats()`.
- Fixed early return bug in `show_history()`.
- Fixed missing `Key` import causing crash on animation skip.

## [0.9.4] - 2026-04-26

### Added
- Detailed Round Score History pop-up (accessible via 'H').
- Global Statistics screen in main menu.
- Hotseat (2P) Mode for local multiplayer.
- Undo Support (accessible via 'Z' during play).
- Terminal Sound Effects for key events.
- Seat-specific AI Difficulty configuration.
- Support for skipping animations (Space/Esc).

### Improved
- Significant performance optimization for real-time HUD scoring.
- UI rendering speed and smooth ASCII art animations.
- O(1) rank lookup performance.

### Fixed
- Indentation and template errors in `main.py` and `ui.py`.

## [0.9.2] - 2026-04-26

### Fixed
- Fixed `ValueError: max() iterable argument is empty` in `legal_cards` when trump is led.

## [0.9.1] - 2026-04-26

### Fixed
- Fixed `ModuleNotFoundError` during gameplay caused by absolute imports in `game.py`.

## [0.9.0] - 2026-04-26

### Added
- Initial release as a standard Python package.
- Full-screen terminal UI for French Belote.
- AI difficulty levels: Easy, Medium, Hard.
- Bidding and scoring systems.
- Multilingual (EN/FR) rules and history viewer.
- Standard project structure with `src` layout.
- Git repository initialization and GitHub sync.
