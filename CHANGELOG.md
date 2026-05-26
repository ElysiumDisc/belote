# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

## [4.5.1] - 2026-05-16

Audit-and-hardening pass over the fresh 4.5.0 baseline. Three parallel Explore agents reviewed the classic engine + uncommitted hot spots, the BelAtro 4.5 mechanics (L'Infiltré / L'Architecte + the six Conditional Engine jokers), and performance/caching paths. **No critical bugs found** — the 4.5.0 release ships clean. This release lands three convention-consistency fixes, a tiny allocation cleanup, two clarifying comments, and the missing prompt-bid integration test. **+2 regression tests** (790 → 792). All baselines green: `ruff` 0 violations, `mypy --strict` 0 errors, `pytest` 792/792.

### Fixed

- **`LeCollectionneur.on_trick_won` now short-circuits on the `re_emit` convention** (`src/belote/belatro/items/jokers/annonces.py:108-138`). Every other state-mutating `on_*` handler in the codebase guards on `getattr(event, "re_emit", False)` — see `annonces.py:62, 96`, `coinche.py:26, 55`, `economy.py:21` — so a re-emitted event can't double-credit money or mult. `TrickWonEvent` doesn't carry the field today (only `BidMadeEvent` does, see 4.1.0 notes), so the guard is a no-op at runtime; the value is forward-compat — if a future event type starts re-emitting, the joker is already armoured. This was a 4.5.0 omission, not a live bug.
- **L'Architecte deck description updated to spell out the "NS-won" qualifier** (`src/belote/belatro/run/decks.py:170`). Previous: `"Tricks containing a declared Annonce pay +$2."` Now: `"NS-won tricks containing a declared Annonce pay +$2."` The scoring code at `src/belote/belatro/core/scoring.py:298-307` only credits NS-team wins; the README at line 34 already said "NS-won tricks" so this aligns the in-game deck-pick screen with the README and the actual code.
- **`_record_belote_announcement` now returns `tuple[bool, bool]` directly** (`src/belote/game.py:878-925`). Pre-4.5.1 the helper returned a mutable `list[bool]` and each of the three `play_card` continuation branches re-packed it as `belote_tracker=(belote_tracker[0], belote_tracker[1])` to satisfy the frozen `GameState.belote_tracker: tuple[bool, bool]` field. Now the helper does the pack once at its return statement, and the three call sites (mid-trick / round-complete / next-trick at `game.py:1063, 1089, 1109`) pass the tuple through as `belote_tracker=belote_tracker`. Three tuple allocations per card play collapse to one; the type signature now matches what the dataclass field actually wants.

### Changed

- **Clarifying comment on the L'Infiltré ghost-lead TOUT_ATOUT branch** (`src/belote/belatro/core/scoring.py` around line 278). Under TOUT_ATOUT every card is a trump, so no play can be "void of the led suit" — `is_trump_lead` resolves to `True` and the +2 Mult / +$1 bonus is correctly gated off. The branch was already correct; the comment now spells out why.
- **LePrêteur docstring spells out the snapshot semantics** (`src/belote/belatro/items/jokers/economy.py`). The `current_money` value is read from a *pre-round* snapshot stamped by `belatro/main.py` into `round_flags`. That snapshot is intentional: it means this joker's own +$15 / -$5 swing can't loop back to defeat its own threshold check, *and* another joker's on-round-start payout in the same round won't shift this joker's gates. The docstring now says so out loud.

### Internal

- **Tests**: 790 → 792. Two new `prompt_bid` integration tests appended to `tests/test_input_wasd.py`:
  - `test_prompt_bid_x_returns_tout_atout_in_round_2` — pins the round-2 routing of `Key.CHAR(char='x')` to `Suit.TOUT_ATOUT`.
  - `test_prompt_bid_n_returns_sans_atout_in_round_2` — pins the round-2 routing of `Key.CHAR(char='n')` to `SANS_ATOUT_BID`.
  The pre-4.5.1 suite covered the reader-layer aliasing but had no test exercising the `prompt_bid` consumer's `char == "x"` / `char == "n"` branches. A capitalised typo (`char == "X"`) would have passed every test in the suite.
- **Test fixture updates**: two `_record_belote_announcement` assertions in `tests/test_belote.py` changed from `tracker == [True, True]` to `tracker == (True, True)` to match the new tuple return type. No behaviour change.
- **Version markers bumped**: `pyproject.toml`, `src/belote/__init__.py`.
- **Audit verified healthy** (no change required): L'Infiltré "void of lead" inference (relies on the Belote rule that you cannot trump while holding the led suit — `legal_cards` enforces it), L'Architecte $10 deduction (only fires after a non-None contract pick; Esc/EOF/Q cancel paths return None and skip deduction), WASD migration (zero remaining `char == "a"` or `char == "s"` consumers across `src/` and `tests/` — shop, consumables, rules, fit-guard use disjoint letters), render diff layer, theme palette caching, AI memo keys (`last_voids_key` / `last_partner_hand_key`), planet stacking, voucher idempotency (base-class `_apply_once`), zero-rank boss flag propagation, belote/rebelote under L'Anarchie. Performance: turn-based card game, no measurable hotspots beyond the now-removed `belote_tracker` repack.
- **Plan file**: `/home/mrrobot/.claude/plans/bug-hunt-code-performance-hidden-meerkat.md`.


## [4.5.0] - 2026-05-16

Feature release: WASD nav across every selection screen, two new BelAtro starting decks (L'Infiltré, L'Architecte) and six new "Conditional Engine" jokers that hook into the existing event bus. **+39 regression tests** (751 → 790). All baselines green: `pytest` 790/790.

### Added

- **WASD navigation** (`src/belote/input.py` — both `_UnixKeyReader.read` and `_WindowsKeyReader.read`). `W`/`A`/`S`/`D` (lower or upper case) alias to `Key.UP`/`Key.LEFT`/`Key.DOWN`/`Key.RIGHT` at the reader source. Every selection consumer already pattern-matches `case Key.LEFT | Key.UP:` so the alias propagates to every screen — card picker, bidding, menus, shop, collection, history, rules — without per-consumer edits. Pinned by 7 tests in `tests/test_input_wasd.py`.
- **L'Infiltré starting deck** ("Void Specialist"). Sets the `ghost_lead` flag in `card_enhancements`; consumed in `belatro/core/scoring.py`'s `TrickWonEvent` branch — when NS wins a trick by playing a Trump on a non-trump lead, the winner must have been void of the lead suit (Belote's strict suit-follow rule forbids trumping while holding lead), so +2 Mult and +$1 are paid. Pinned by 5 tests in `tests/belatro/test_decks_4_5.py`.
- **L'Architecte starting deck** ("Contract Architect"). Two flags: `buy_contract` lets the player pay $10 in bidding to force the contract (UI hook in `belatro/main.py::UICallbacks.prompt_bid` → new `BelAtroAnnounce.buy_contract_picker` helper); `annonce_cash_x2` pays +$2 on every NS-won trick that contains a card from a declared NS Annonce (consumed in scoring on the `TrickWonEvent` path, with the NS-annonce card-set harvested from `state.declarations` in the `DeclarationScoredEvent` branch). Pinned by 7 tests in `tests/belatro/test_decks_4_5.py` (including 4 tests for the buy-contract picker UI).
- **Six Conditional Engine jokers** (auto-registered via the existing module scanner):
  - **`LeCavalierNoir`** (trick_timing.py) — win a Hearts-led trick with a Spade: ×3 Mult.
  - **`LArcEnCiel`** (trick_timing.py) — each NS trick where winning suit ≠ lead suit: +2 Mult (stacks per trick across the round).
  - **`LeCollectionneur`** (annonces.py) — each NS Annonce card played in trick 2+: +$2 and +5 Mult per card. Reads the shared `_ns_annonce_cards` frozenset.
  - **`LeMathematicien`** (annonces.py) — each NS Annonce whose score is a multiple of 5: ×2 Mult.
  - **`LEclat`** (annonces.py) — win a trick that contains the trump K or Q (the Belote cards): triple that trick's chips (`add_chips = 2 × event.card_points`, since the base trick chips were already added).
  - **`LePreteur`** (economy.py) — at round start: $0 → +$15 (catch-up); $50+ → spend $5 for ×1.2 Mult (scale-up). Reads `current_money` from `joker_state` (injected via `card_enhancements` in `belatro/main.py`).
- 17 jokers tests in `tests/belatro/test_jokers_4_5.py` plus a registry pin.

### Changed

- **Bid quick-keys remapped: `A` → `X` (Tout Atout), `S` → `N` (Sans Atout)** (`src/belote/ui/prompts.py::prompt_bid`). The 2.9.0 affordance bound `a`/`s` to the new contracts; with WASD landing in 4.5.0 those letters are now nav aliases, so the contract quick-keys moved to mnemonic `X` (e**X**tra trump) and `N` (**N**o trump). Round-2 only as before; arrow-key navigation + digit shortcuts still work. Help text and docstring updated.
- **`ScoreAccumulator.trigger_round_start` now honors `JokerResult` returns from `on_round_start`** (`src/belote/belatro/core/scoring.py`). Pre-4.5.0 the return was silently discarded — existing jokers (LePremierSang, LeSergent, LaSentinelle, ...) all returned `None` from `on_round_start` so this is backward-compatible. LePrêteur is the first consumer; without this change its $15 / $5 swings would never reach the wallet.
- **Annonce card-set harvested into `joker_state["_ns_annonce_cards"]`** on every `DeclarationScoredEvent` (was: gated behind L'Architecte's `annonce_cash_x2` flag). Now shared by L'Architecte AND LeCollectionneur. Frozenset of `(suit.name, rank.name)` tuples for hashability + scalar-only `joker_state` invariant. Cleared on `trigger_round_start` alongside the existing L'Architecte key.

### Internal

- **Tests**: 751 → 790 (+39: 7 input-WASD, 15 decks-4.5, 17 jokers-4.5).
- **Version markers bumped**: `pyproject.toml`, `src/belote/__init__.py`.
- **Joker count**: 36 → 42; deck count: 10 → 12. Planets / Tarots / Vouchers unchanged (8 / 12 / 12).
- **Plan file**: `/home/mrrobot/.claude/plans/i-want-to-add-joyful-melody.md`.


## [4.1.1] - 2026-05-16

Second audit pass over the 4.1.0 baseline. Three parallel Explore agents (classic engine, BelAtro layer, UI/render) — the BelAtro layer came back clean, the classic engine + UI surfaced two real bugs plus one P2 architectural fragility. **+9 regression tests** (742 → 751). All baselines green: `ruff` 0 violations, `mypy --strict` 0 errors, `pytest` 751/751, `tests/test_perf_regression.py` 5/5 within tolerance.

### Fixed

- **Hard / Medium AI play heuristics now honor every zero-rank boss flag** (`src/belote/ai.py`). 4.1.0 migrated the AI's *bid* path to `card_points_with_modifiers` but the *play* path was still calling raw `card_points_fn` in four sites: `_medium_play:418` (no-trumps discard after trump led), `_medium_play:441` (final fallback discard when void in lead and trump), `_score_card_play:640` (`points = card_points_fn(...)` propagates into `_score_discarding_strategy` and `_score_winning_strategy`), and `_score_leading_strategy:668` (probe-waste 0-point check). Under `aces_zero` / `kings_zero` / `jacks_zero` / `tens_zero` / `declarations_zero` / `ban_clubs` the AI was evaluating a card at its full nominal point value while scoring zeros it — leading to provably suboptimal discards (e.g. "saving" a J-trump under *Le Mime* / `jacks_zero` as if it were worth 20pts when it actually scored 0). The fix routes every play-time card valuation through `scoring.card_points_with_modifiers` (the same helper the bid path uses) and drops the raw `card_points_fn` alias import entirely. Pinned by 4 new tests in `tests/test_ai.py` (`test_ai_no_raw_card_points_import`, `test_hard_ai_play_score_uses_jacks_zero` — discarding-penalty delta 14.0, `test_hard_ai_play_score_uses_ban_clubs` — delta 7.7, `test_medium_ai_discard_consults_boss_modifier_helper`).
- **`fit_guard.require_minimum` now invalidates the render-diff baseline before returning** (`src/belote/ui/fit_guard.py`). The "Terminal too small" overlay paints `clear_screen() + hide_cursor() + move(...) + ansi_center(...)` directly to stdout in its polling loop, then returns when the terminal grows past the floor. Pre-4.1.1 it never called `render.invalidate_diff()`, so the diff baseline went out of sync with terminal state — the next `display()` would diff against the (now stale) pre-overlay frame and emit incomplete updates, potentially leaving overlay residue visible behind the game. Same architectural rule as the 4.0.1 BelAtro-overlay fix. The new path wraps the loop body in `try/finally` and invalidates on every exit (success or `FitAbortedError`) *only if* the overlay actually painted (a fast-path return on the first poll doesn't touch the baseline). Pinned by 3 tests in `tests/test_alt_screen_scroll.py`: `test_require_minimum_invalidates_diff_on_return`, `test_require_minimum_does_not_invalidate_if_never_paints`, and the new `test_classic_ui_overlays_invalidate_diff` static check covering the fit-guard source.
- **`show_stats` modal now invalidates the diff baseline on exit** (`src/belote/ui/announce.py`). Same architectural rule. Called only from the main menu today (`belote/main.py:164`), so the visible-residue blast radius is smaller than `fit_guard`, but the rule is now consistently enforced across every classic-UI overlay. Pinned by `tests/test_announce_stats.py::test_show_stats_invalidates_diff`.

### Changed

- **`show_stats` builds its line list once outside the read loop** (`src/belote/ui/announce.py`). The stats numbers are immutable for the lifetime of the modal — pre-4.1.1 every keystroke (or terminal-size change while the modal was open) rebuilt the full 30+ line list AND re-walked the difficulty / trump dicts AND re-formatted every f-string. The 4.1.1 path builds the lines once and caches the centered rendering per terminal width; only a SIGWINCH-driven width change rebuilds the rendered string. Same hoist pattern as `_build_history_lines` (4.1.0). Pinned by `tests/test_announce_stats.py::test_show_stats_builds_lines_once_across_keystrokes` (asserts `load_stats()` is called exactly once per `show_stats` invocation).

### Internal

- **Tests**: 742 → 751 (+9: 4 in `tests/test_ai.py`, 3 in `tests/test_alt_screen_scroll.py`, 2 in `tests/test_announce_stats.py`).
- **Version markers bumped**: `pyproject.toml`, `src/belote/__init__.py`.
- **BelAtro layer audit — clean**. Every previously-suspected hot spot held up under fresh review: joker re-emit guards (5 added in 4.1.0), zero-rank boss-flag propagation (`kings_zero` / `tens_zero` / `aces_zero` / `jacks_zero` / `declarations_zero` / `ban_clubs` all flow through `_card_points_with_zero_ranks` → `trick_card_points` / `card_points_with_modifiers` / `_calculate_base_points` / `_compute_declaration_points` / live HUD), voucher idempotency (base-class `_apply_once` guard), planet stacking (Mercury/Venus/Jupiter/Saturn at trick-won time; Sun/Moon/Pluto/Libra at round-end with Libra scaling by `event.coinche_level`), endless mode (ante stays at 8, `endless_ante_offset` increments, boss variety guard rerolls up to 8 against the recent-2 window), and registry validation (`validate_synergy_ids()` at startup, no duplicate IDs, no stale synergy refs).
- **Mechanics audit — clean**. Bidding (regular suit / Tout Atout / Sans Atout / coinche / surcoinche / all-pass / pass-out), belote/rebelote under L'Anarchie (captured `belote_trump` survives mid-round rotation), declarations (tierce/quarte/quinte/brelan/carré + `strict=True` zips), capot bases (252/220/348), Dix-de-der (gated by `no_dix_de_der`), Republicain wild, Litige carry-over — all verified.
- **Plan file**: `/home/mrrobot/.claude/plans/foamy-plotting-wand.md`.


## [4.1.0] - 2026-05-15

Audit pass: bug-hunt, performance, and mechanics verification across the whole codebase (three parallel Explore agents: classic engine, BelAtro layer, UI/render). Three real bugs fixed, six concrete perf wins landed, five defensive re-emit guards added to state-mutating jokers, and one false-alarm category (litige carry-over, partner-hand memo, sequence reconstruction) documented as by-design after re-verification. **+19 regression tests** (723 → 742). All previous baselines green: `ruff` 0 violations, `mypy --strict` 0 errors, `pytest` 742/742, `tests/test_perf_regression.py` 5/5 within tolerance.

### Fixed

- **`LeDémon` now fires on every team-NS trick win** (`src/belote/belatro/items/jokers/corrupted.py:32-50`). The description has always said "+3 Mult unconditionally" but the pre-4.1.0 code only fired on `event.winner == Seat.SOUTH` — wins by the North partner silently dropped the mult, contradicting the description and breaking the joker's value proposition. The fix gates on `team_of(event.winner) == 0` (matching the team-aware cohort like L'Accumulateur / Le Patriote). `LeTraître` and `LAgentDouble` retain their seat-themed (South-only) gating because their descriptions tie the mult to *you* surviving partner sabotage — their docstrings were tightened to spell this out. `LEgoiste` was verified correct (both seat branches present and aligned with the description).
- **Hard AI no longer bids Clubs under *Les Clubs Bannis*** (`src/belote/ai.py::_hard_bid`). `card_points_with_modifiers` correctly zeros all club cards under `ban_clubs`, but the bid heuristic's honor count (J/9/A = +3 each) and cross-suit short-suit bonuses still pushed club-heavy hands above the bid threshold. The fix excludes Clubs from the candidate list when `bm.ban_clubs` is True. Pre-4.1.0 a club-J/9/A hand confidently called Clubs as trump and scored 0 across the round.
- **`AIPlayer.decide_card` raises on empty `legal_cards`** (`src/belote/ai.py:313-322`). The pre-4.1.0 fallback `legal = hand` masked any dealing or legal-cards regression by silently playing an illegal card. The 4.1.0 code raises `AssertionError("AI {seat}: legal_cards empty during PLAYING ...")` so any regression surfaces at the offending decision rather than as a downstream scoring mystery.
- **Diff-emit rows now append `clear_to_eol()`** (`src/belote/ui/render.py` diff-emit path). The full-render path always emitted `clear_to_eol()` per row, but the diff-emit path did not — when a row shrunk mid-game (e.g. terminal narrowed, contract changed from `tout_atout` to `normal` reducing the HUD width), stale chars past the new line's end would persist. Pinned by `test_diff_emit_appends_clear_to_eol_on_row_shrink`.

### Changed

- **`render.py` caches `theme_manager.current_name`** in a new `_cached_theme_name` module global, refreshed by a registered callback (mirroring the `ansi.py::_active_palette` pattern from 3.9.5). Each felt-row call previously queried `theme_manager.current_name` (a property dispatch) and the result was passed to `_felt_segment_cached` as a cache key. On a wide terminal that's 40+ property reads per frame, none of which can change without firing the callback. The cache also resets `_last_emitted_lines = None` on refresh, so theme switches still force a full redraw.
- **`_pip_at(row_id, col)` gained `@lru_cache(maxsize=1024)`** (`src/belote/ui/render.py:380-391`). Pure deterministic function of (row, col); `TERMINAL.has_utf8` is process-constant. The cache eliminates redundant modular-arithmetic work on the cache-miss path of `_felt_segment_cached` for the first frame after eviction.
- **`_pending_rendered_lines` and `_last_emitted_lines` are tuples** (was `list[str] | None`). The side-channel was rebuilt as a fresh list on every frame; tuples are immutable, hashable, and avoid the per-frame allocation. `_pending_rendered_lines` is now pre-cleared at the top of `display()` so an exception escaping `render()` can't leave a stale tuple for a later `display()` call.
- **`show_history` overlay caches its line list across scroll iterations** (`src/belote/ui/prompts.py::_build_history_lines`). Pre-4.1.0 every `↑`/`↓` rebuilt the full lines list — for a 60-round game with the wide-layout 8-column table that was the dominant per-keystroke cost in the modal. The cache key is `(term_w, len(state.score_history))`; state is immutable during the modal so the invariant holds.
- **`gameflow.py` reuses the 8th-trick projected list** between the Dix-de-Der and Capot announcement paths (`src/belote/gameflow.py:214-229`). Previously the same `list(current.completed_tricks) + [display_state.current_trick]` was built twice in succession.
- **Corrupted-joker docstrings tightened** (`LeTraître`, `LAgentDouble`) to spell out "+X Mult when **you** win a trick" — the seat-themed gating is intentional but pre-4.1.0 the docstring was ambiguous and the 4.1.0 audit initially flagged them as bugs before re-reading.

### Added

- **Five defensive `re_emit` short-circuit guards** on state-mutating jokers: `LeBanquier.on_round_end`, `CoincheStack.on_round_end`, `ToutStreak.on_round_end`, `QuinteRoyale.on_round_end`, `RebeloteEcho.on_belote`. Pattern mirrors the `re_emit=True` gating that `BidMadeEvent` already uses (`src/belote/belatro/engine/event_bus.py:79`). No current code path re-emits these events, but future replay / UI-driven re-emit work won't accidentally double-pay or double-advance state counters. `QuinteRoyale` is the most consequential: pre-4.1.0 a re-emit would have `state.pop(...)` the armed flag and *then* return None on the second pass, silently disarming the joker without paying out.
- **`tests/test_history_overlay_cache.py`** — 4 new tests pinning the `_build_history_lines` helper (empty / wide / narrow layouts) and the scroll-loop cache invariant (`_build_history_lines` called exactly once across multiple scroll keystrokes).
- **8 new tests in `tests/belatro/test_phase2_content.py`**: corrupted-joker description/code alignment (LeDémon team gate, LeTraître & LAgentDouble seat-themed pinning) and 5 re-emit pins. Re-emit pins use `object.__setattr__` to stamp `re_emit=True` on a frozen RoundEndEvent / BeloteAnnouncedEvent, mirroring how a future replay layer would extend the dataclass.
- **2 new tests in `tests/test_ai.py`**: `test_hard_ai_avoids_clubs_bid_under_ban_clubs` (boss-pipeline pin) and `test_ai_legal_cards_empty_raises` (monkey-patches `legal_cards` to `()` and pins the new AssertionError).
- **5 new tests in `tests/test_render_diff.py`**: `test_pip_at_is_cached` (lru-cache hit-counter pin), `test_theme_name_cache_invalidated_on_theme_change` (callback wiring pin via real `theme_manager.set_current`), `test_diff_emit_appends_clear_to_eol_on_row_shrink` (regression pin for the diff-emit `clear_to_eol` fix), `test_pending_rendered_lines_pre_cleared_in_display` and `test_pending_rendered_lines_is_tuple` (C3/C6 pins).

### Internal

- **Tests**: 723 → 742 (+19).
- **Version markers bumped**: `pyproject.toml`, `src/belote/__init__.py`.
- **Verified-false / by-design audit claims** (documented so future audits don't re-investigate):
  - `litige_points` not in `reset_round_fields` → **by design**: it's an across-round accumulator reset in `scoring.py::apply_round_score` only when `is_litige=False`. Verified by tracing `scoring.py:1146-1155`.
  - `AIMemory.last_partner_hand_key` memo collision on undo → **already handled**: the undo branch at `ai.py:85-99` resets `last_partner_hand_key = None`.
  - `show_rules` missing `invalidate_diff()` → **already present** at `prompts.py:303`. The exit-on-quit/enter/esc/EOF branch covers all return paths.
  - Sequence-reconstruction fence-post error in `scoring.py:147-166` → agent retracted in-paragraph; verified correct.
  - Capot base under L'Anarchie trump rotation → contract-dependent, not trump-dependent (documented in 3.0.0 wiring notes; verified by re-reading `scoring.py:769-788`).
  - `TierceCharger` and partner-joker seat keying → **partner jokers ARE seat-keyed by design** (per 3.7.1 wiring notes).
  - `LEgoiste` seat branches → both seats handled correctly; description matches code.
- **`_trick_winner_seat_impl.cache_clear()` already wired** into `clear_legal_cards_cache()` (`game.py:496-499`) — the audit's "speculative" cleanup turned out to already be in place. No change needed.
- **`belote.ui.render` module-shadowing trap** persists in 4.1.0 (the `belote/ui/__init__.py` re-exports `render` as a function); new tests follow the `sys.modules["belote.ui.render"]` pattern documented in the 4.0.0 wiring notes.
- **Plan file**: `/home/mrrobot/.claude/plans/bug-hunt-code-performance-immutable-treehouse.md`.


## [4.0.1] - 2026-05-15

Four bug fixes in the same family: writes that bypass `render.display()` were leaving the render-diff baseline out of sync with terminal state. **+7 regression tests** (716 → 723).

### Fixed

- **Two stacked `Partner ▓▓▓ (N cards)` rows and two `╔═══◆═══` mat-tops after the bid→play transition** (user-reported via `/home/mrrobot/belote/screen-2026-05-15-21-47-41.jpg`). Root cause: `src/belote/gameflow.py` wrote `f"\\r\\n  {bidder.name} takes it as {bid}!\\r\\n"` (and similar for play and round-end messages) directly to stdout, bypassing `render.display()`. When the cursor was at the bottom of the alt-screen, the trailing `\\n` forced strict terminals (Konsole) to scroll the entire frame up by one row. The render-diff layer in `render.display()` never learned about the scroll, so the next `display()` diffed the new frame against the cached `_last_emitted_lines` baseline, saw most rows as "unchanged", and emitted zero updates — leaving the scrolled-up old partner row visible above the new one. Documented at length in `src/belote/ui/announce.py:32-35` long before the fix, but the gameflow writes had never adopted the `announce()` primitive that comment was warning about.
- **Leftover card fragment at non-lead seats between tricks** (user-reported via the first take of `/home/mrrobot/belote/screen-2026-05-15-22-13-41.jpg`). Root cause: `render.patch_trick_card()` writes a single card directly to the terminal during a trick (called 3× per trick, for cards 2-4). It did not update `_last_emitted_lines`, so when the next trick began and `display()` ran to redraw the empty mat, the diff layer compared the new "empty mat" frame against the cached "empty mat" baseline (which reflected the *pre-patch* frame, when only the lead card was on the mat). Rows matched → diff emitted nothing → the 3 patched cards from the previous trick stayed visible behind the new trick's placeholders. Fix: `patch_trick_card()` now calls `invalidate_diff()` at the end, forcing the next `display()` to emit a full frame. Same architectural rule as the 4.0.0 popup fix.
- **BelAtro main menu, shop, rules, history, collection, and consumables overlays leaking into the next game frame** (user-reported via the second take of `screen-2026-05-15-22-13-41.jpg`, where the BELATRO ascii-art title + "Start Run / Select Deck / Collection / Rules / Quit" options were visible underneath the trick mat during an active round). Same architectural root cause: every BelAtro overlay paints directly to stdout (`clear_screen()` + content + flush) without updating `_last_emitted_lines`. When the overlay exited and the game's `display()` ran, the diff compared against a baseline that pre-dated the overlay; rows where the baseline happened to match the new frame (typically blank felt rows in the middle of the mat) skipped emit, leaving the overlay's content visible on the terminal. Fix: `invalidate_diff()` added to the end of each render path in `belatro/ui/menu.py`, `shop.py`, `rules.py`, `history.py`, `collection.py`, `consumables.py`.
- **BelAtro `I`-key score popup stuck on screen "the whole time"** (user-reported during 4.0.1 dev). Pressing `I` during BelAtro play calls `_show_overlay` which paints the score breakdown via `BelAtroAnnounce.score_popup()`, waits 1.5s, then expects the next `display()` call (line below in main.py) to redraw the game frame and overwrite the popup. The popup's `print(move(...) + lines)` writes bypassed `_last_emitted_lines`, so the post-popup `display()` diffed the unchanged game state against the cached pre-popup baseline, saw "no changes", and emitted nothing — popup pixels stayed visible until something else forced a full redraw. Same fix in all four `BelAtroAnnounce` methods (`boss_reveal`, `banner`, `yes_no`, `score_popup`): each now calls `invalidate_diff()` on exit. `yes_no` wraps its return paths in a `try/finally` to guarantee the invalidation fires regardless of which branch is taken.

### Changed

- **`src/belote/gameflow.py:131-145`** — AI bid-result writes now go through `announce()` instead of raw `sys.stdout.write(f"\\r\\n  {bidder.name} takes it as ...\\r\\n")`. The `skip_anims` flag still propagates: `announce()` now returns the dismiss `KeyEvent` from `interruptible_sleep` (was always `None` pre-4.0.1).
- **`src/belote/gameflow.py:199-200`** — Deleted the redundant `f"\\r\\n  {player.name} plays {card}\\r\\n"` write after every AI card play. The card is already drawn on the mat by the immediately-preceding `display()` / `patch_trick_card()` call, so the text was visually redundant and was the highest-frequency scroll source (24× per round). The TTS path in `src/belote/a11y.py:87` still announces plays independently for screen-reader users.
- **`src/belote/gameflow.py:407-431`** — Replaced the ~10-line raw `\\r\\n`-dump round-end summary with a call to the new `show_round_summary()` modal.
- **`src/belote/ui/announce.py::announce`** — return type is now `KeyEvent | None` (was `None`). Existing callers that ignored the return are unaffected.

### Added

- **`src/belote/ui/announce.py::show_round_summary`** — new end-of-round modal. Mirrors the `show_help` / `show_stats` pattern: title, taker info, breakdown messages (gold), team totals (NS/EW), optional replay summary, dismiss-on-any-key (or timeout). Painted with absolute cursor positioning so it cannot scroll, and calls `render.invalidate_diff()` on exit so the next `display()` does a full redraw. Returns `bool` indicating whether the user pressed a key to skip the pause.
- **`tests/test_alt_screen_scroll.py`** — 7 new regression tests:
  - `test_announce_never_writes_crlf` — `announce()` output contains no literal `\\r\\n`.
  - `test_announce_returns_keyevent_when_skipped` — pins the new return-value contract via `interruptible_sleep` monkey-patching.
  - `test_announce_returns_none_when_no_reader` — backward-compatible no-reader path returns `None`.
  - `test_show_round_summary_no_crlf_and_invalidates_diff` — the new modal emits no `\\r\\n`, includes the expected text, and resets `_last_emitted_lines`.
  - `test_belatro_overlays_invalidate_diff` — **static check**: each BelAtro overlay source file (`menu.py`, `shop.py`, `rules.py`, `history.py`, `collection.py`, `consumables.py`, and the four `BelAtroAnnounce` methods in `announce.py`) must call `invalidate_diff()` at least as many times as it has render-paint sites. Pins the architectural rule against future BelAtro overlays.
  - `test_patch_trick_card_invalidates_diff_baseline` — pins the trick-residue fix: after `patch_trick_card`, `_last_emitted_lines` must be `None`.
  - `test_gameflow_no_crlf_writes` — **architectural rule pin**: no `sys.stdout.write(...\\r\\n...)` may appear anywhere in `src/belote/gameflow.py` ever again. Any new scrolling write fails this test.

### Removed

- Unused imports cleaned from `src/belote/gameflow.py` after the deletions: `import sys`, `BOLD`, `RESET`, `gold_fg`.

### Internal

- **Tests**: 716 → 723 (+7).
- **Version markers bumped**: `pyproject.toml`, `src/belote/__init__.py`.
- **Design note — the `belote.ui` package shadow.** The `belote/ui/__init__.py` re-exports `render` (the function) and `announce` (the function), which means `from belote.ui import render` and `from belote.ui import announce` return the *functions*, not the modules. Tests that need to mutate module globals (e.g. patch `interruptible_sleep` or invalidate `_last_emitted_lines`) must use `sys.modules["belote.ui.render"]` / `sys.modules["belote.ui.announce"]`. Documented in `project_belatro_architecture.md`'s 4.0.0 wiring notes; the new tests added in 4.0.1 follow the same workaround.


## [4.0.0] - 2026-05-15

Major version bump for the **Grimaud Card Detail** feature — pressing `F` during play or bidding opens a full-screen zoomed view of the selected card with hand-drawn half-block illustrations for every face card (12 unique J/Q/K × suit combinations) loosely inspired by the *Grimaud Standard 1898* plate. Also fixes a long-latent diff-render bug where modal overlays could leave visible remnants after dismissal ("two stacks of cards"). **+5 regression tests** (711 → 716).

### Added

- **`src/belote/ui/card_detail.py`** — new module. Public entry `show_card_detail(card, reader)` paints a centered popup over a `felt_bg()` backdrop. The 18×24 pixel-art interior compiles to 12 cell rows via half-blocks (`▀` with independent fg/bg per cell — 2× vertical density). All 32 cards have a detail view: face cards use one of three silhouette templates (king / queen / jack) plus per-(rank, suit) palette + held-object overlay (sword, scepter, flower, fan, axe, bow, orb, halberd, leaf, scroll, feather fan); non-face cards (7-A) get a procedural pip layout scaled to the same canvas.
- **`Key.CARD_DETAIL` enum value + `f` binding** in `src/belote/input.py` (both Unix `_UnixKeyReader.read()` at the printable-character switch and Windows `_WindowsKeyReader.read()` for parity).
- **Hooks in `src/belote/ui/prompts.py`**: `prompt_card` opens the popup on the currently-selected card; `prompt_bid` opens it on `state.up_card`. `show_help`'s gameplay section lists the new key.
- **`render.invalidate_diff()`** public helper (`src/belote/ui/render.py`) — resets `_last_emitted_lines` to `None` so the next `display()` emits a full frame. Used by `show_card_detail` on dismiss, and defensively by `show_help` / `show_history` / `show_rules` to fix the same latent diff-skip bug.
- **`tests/test_card_detail.py`** — 5 new tests:
  - `test_every_card_renders_correct_shape` — every card in `make_deck()` renders exactly `CARD_H × CARD_W` cells (visible-width strip of ANSI).
  - `test_face_card_designs_complete_and_distinct` — all 12 face-card art outputs are pairwise unequal.
  - `test_card_detail_key_enum_exists` — `Key.CARD_DETAIL` is present.
  - `test_show_card_detail_dismisses_on_any_key` — popup writes title + body + footer to stdout and returns after a single `reader.read()`.
  - `test_show_card_detail_invalidates_diff_baseline` — **regression pin** for the "two stacks of cards" bug; uses `sys.modules['belote.ui.render']` to bypass the `belote.ui` package-init function shadowing.

### Fixed

- **Diff-render baseline invalidation on overlay dismissal.** `show_card_detail`, `show_help`, `show_history`, and `show_rules` all write directly to `sys.stdout`, bypassing `render.display()`. Before 4.0.0, the next `display()` call would diff the new game frame against the pre-overlay `_last_emitted_lines` cache, see "no rows changed", and write zero bytes — leaving the overlay visible on screen behind a partial redraw (the popup card frozen mid-screen while the hand redrew at the bottom). All four call sites now call `invalidate_diff()` before returning. Pinned by `test_show_card_detail_invalidates_diff_baseline`.

### Internal

- **Tests**: 711 → 716 (+5: `tests/test_card_detail.py`).
- **Version markers bumped**: `pyproject.toml`, `src/belote/__init__.py`.
- **Plan file**: `/home/mrrobot/.claude/plans/home-mrrobot-belote-grimaud-standard-pl-twinkling-waffle.md`.
- **Design note — face card art style.** The in-hand 3-row × 7-cell face cards (`render.py:184-203`) intentionally keep their generic box-drawing icon style; the popup is the dedicated "zoomed art view" with raster half-blocks. Two visual idioms serving different scales is fine — the in-hand cards must stay readable bracketed by 7 other cards on a felt mat at 9×7 cells, the popup gets 18×24 pixels of figure budget.


## [3.9.5] - 2026-05-15

Audit pass: bug-hunt, performance, dead-code, and logic-quality review across the whole codebase (five parallel Explore agents). **No critical bugs found** — rules, scoring, declarations, and target-score logic all match French Belote. Most "scattered if-check" / "deep cascade" findings turned out to be stale reads of the actual code, and the boss-modifier and legal-cards refactors the audit suggested were *deferred* after re-verification showed the existing structure was already correct. The remaining wins are real but small. **+9 regression tests** (702 → 711).

### Changed

- **`src/belote/ansi.py` — palette accessor fast path.** Theme palette functions (`felt_bg()`, `red_fg()`, `card_face_bg()`, …, 17 total) previously did a `_t().field` lookup + tuple unpack + `_bg_seq/_fg_seq` lru_cache hit per call. They now read a precomputed escape string from a `_Palette` dataclass cached at module level. The cache is rebuilt by `_refresh_theme_cache()` via `theme_manager.register_callback()` so theme switches still take effect immediately. ~10x fewer ops per palette call; cumulative ~50µs/render saving on wide terminals.
- **`src/belote/ansi.py::visible_len` — ASCII fast path.** Strings without an `\x1b` escape skip the regex entirely and return `len(s)`. The function already had `lru_cache(maxsize=4096)`, but seat labels and separator dividers vary per-frame because they're rebuilt with different color codes, so the cache often misses. The fast path eliminates the regex pass for plain-ASCII fragments.
- **`src/belote/scoring.py::is_capot` — accepts pre-computed winners.** `score_round` already pre-computes `compute_trick_winners()` once and threads it through `_calculate_base_points` and `_apply_scoring_modifiers`; `is_capot` was the lone scoring-phase caller still re-walking the 8 tricks. New optional `winners=` parameter avoids the redundant walk when the caller has already resolved them.
- **`src/belote/input.py::interruptible_sleep` — tunable polling granularity.** New `granularity` parameter (default 0.05s — unchanged, preserves ESC vs. arrow-key disambiguation). Animation callers may pass a tighter value for snappier interruptibility without affecting the keyboard-decoding path. Backwards-compatible signature.

### Removed

- **Dead helpers in `src/belote/ui/render.py`** — `_get_card_back()`, `_get_felt_blank()`, `_felt_pad()`, and the `_TRICK_ROW_OFFSETS` "legacy constant retained for any caller still importing it (none in-tree now)" sentinel. Grep across `src/` and `tests/` confirmed zero callers; `_felt_pad_ns()` (the active variant) handled the remaining use cases.

### Added

- **`tests/test_invariants.py`** — 4 new property tests:
  - **`test_boss_modifier_pairs_complete_round`** — drives a full round under every pair of suppression / zero-rank flags from a 9-flag pool (36 combinations). Asserts no crash, all hands drained, scoring returns. Cross-product safety net for future modifier additions.
  - **`test_la_rupture_makes_capot_unreachable`** — under `no_consecutive_team_wins`, the same team cannot win two consecutive tricks, so capot (all 8) is mathematically impossible. 25 seeds × Spades contract.
  - **`test_anarchie_plus_no_belote_suppresses_belote_across_rotations`** — `dynamic_trump` + `no_belote` together must keep `belote_tracker == (False, False)` even with mid-round trump rotation.
  - **`test_zero_rank_flags_never_increase_table_total`** — zero-rank flags can only subtract points; table total must stay ≤ 162 baseline.
- **`tests/test_perf_regression.py`** + **`tests/perf_baselines.json`** — 5 perf regression guards on `render`, `legal_cards` (cold + warm), `score_round`, `trick_card_points`. Compares median timings against committed baselines; fails on >2.5x regression (hardware-tolerant). Print warnings at 1.2x. Set `BELOTE_SKIP_PERF=1` to skip on weak runners.

### Audit notes

Reviewed but **deferred** after re-verification — code was cleaner than the audit's initial reading:

- **Boss-modifier consolidation (proposed).** 23 `state.boss_modifiers.X` references across `game.py` / `scoring.py` / `ai.py`. Counter-evidence: zero-rank flags are already consolidated in `scoring.py::_card_points_with_zero_ranks`; every other flag has exactly one logical integration point (e.g. `no_belote` at `_record_belote_announcement`; `no_dix_de_der` at the +10 site; `no_consecutive_team_wins` at `compute_trick_winners`). Forcing a registry would add indirection without reducing real touch-points.
- **`_calculate_legal_cards_impl` flattening (proposed).** Max nesting is ~4 levels; `partner_winning` is consulted in one branch only (`game.py:623`). Audit's "5-6 levels" figure was a misread. Refactor risk on rule-critical code outweighs marginal clarity gain.
- **`_medium_play` / `_medium_lead` merge (proposed).** `_medium_play` already delegates to `_medium_lead` when the trick is empty. The two methods address genuinely different decision contexts. Already structured correctly.
- **Skip full re-render after non-South card (proposed).** `gameflow.py:192-195` already gates `display()` vs. `patch_trick_card()` via `if len(current_trick) == 1 else …`. No code change needed.
- **Cache terminal size per render frame (proposed).** `TerminalContext.get_size()` already caches at module level and invalidates on SIGWINCH. Threading args adds complexity for zero gain.
- **Hoist felt color calls out of cell loop (proposed).** `_felt_segment_cached` (`render.py:390-392`) already calls `felt_bg()` / `felt_edge_bg()` / `felt_placeholder_fg()` once before its per-cell loop.

### Internal

- **Tests**: 702 → 711 (+9: 4 invariants + 5 perf guards).
- **Plan file**: `/home/mrrobot/.claude/plans/bug-hunt-code-performance-distributed-harp.md`.
- **Version markers bumped**: `pyproject.toml`, `src/belote/__init__.py`.


## [3.9.4] - 2026-05-15

UI polish pass: four new themes, decorated felt mat (vignette + braille pip texture + corner-ornamented frame), reworked hand selection display, auto-sort, and a stats-screen accuracy fix. **+10 regression tests** (691 → 702).

### Added

- **Four new themes** in `src/belote/themes.py`: **Forest Night** (mossy green with copper accents), **Moonlit Tavern** (cool slate-blue with candle amber and parchment cards), **Royal Purple** (regal violet with ivory + gold), **Emerald Isle** (jewel emerald with cream cards and brass trim). All eleven themes selectable via the `T`-key cycle or the Theme submenu (`src/belote/ui/menu.py`).
- **`Theme.felt_edge_bg` field** (`src/belote/themes.py`) + matching `felt_edge_bg()` accessor in `src/belote/ansi.py`. Populated for all 11 themes (~70% luminance of `felt_bg`). Drives the new vignette band on the trick mat. The required-fields validation test (`tests/test_ansi_helpers.py:114-119`) is updated to enforce the new key on every theme.
- **Felt-mat polish (`src/belote/ui/render.py`):**
  - **Vignette band** — leftmost / rightmost 2 cells of each row and the top + bottom rows now paint in `felt_edge_bg`, giving the mat a spotlit look that pops the playing area away from the edges.
  - **Braille pip texture overlay** — sparse single-dot braille glyphs (U+2800–U+28FF, the `_BRAILLE_DOTS = "⠁⠂⠄⡀⠈⠐⠠⢀"` constant) stamped on ~9% of blank felt cells via the pure `_pip_at(row, col)` function. Pure-deterministic on `(row, col)` so the Phase-6 diff renderer at `display()` line ~1146 still skips unchanged rows. Color is `felt_placeholder_fg()` so the texture reads as fabric weave, not pattern. Skipped on non-UTF-8 terminals via the existing `TERMINAL.has_utf8` guard.
  - **Decorative outer frame (`_render_trick_mat_framed`)** — wraps the trick mat with `╔═══◆═══...═══◆═══╗ / ║ ... ║ / ╚═══◆═══...═══◆═══╝` border + corner ornaments at ⅓ / ⅔ positions, in `felt_placeholder_fg()` on `felt_edge_bg()`. Auto-gated: only fires when `term_h >= layout.min_rows + 2` so the bottom of the south hand never gets pushed off-screen at COMPACT (80×32) or at STANDARD's minimum (96×38).
  - All blank-felt helpers (`_slot_frame_row`, `_felt_pad_ns`, `_we_row`, `_slot_label_ns`) now take `row_id` and route blank cells through the new `_felt_segment` helper. `clear_card_cache()` also clears `_felt_segment_cached` / `_felt_blank_internal` on theme change.
- **Hand-UI rework (`_render_hand_horizontal`):**
  - Bare `▲` cursor replaced with a `card_w`-wide highlight bar in `highlight_bg()` directly under the selected card — clearer on the now-busier felt.
  - Centered card-name readout `► A♠ — Trump ◄` below the bar, color-coded: `gold_fg()` if trump, suit color otherwise, `light_gray_fg()` if illegal. Tagged with `— Trump` / `— Illegal` where applicable. New `trump: Suit | None` and `show_readout: bool` parameters; the caller in `render()` gates `show_readout` at `term_h > layout.min_rows` so the readout disappears at min terminal sizes rather than pushing the south hand off-screen.
- **Auto-sort south hand on entry to `prompt_card`** (`src/belote/ui/prompts.py`). One call to the existing `sort_south_hand(state)` at the top of the function — same helper the manual `S` key already used. Returned state propagates per the existing docstring contract. The `Key.SORT` handler stays in place as a harmless re-sort (preserves muscle memory + documented controls).

### Fixed

- **Stats menu `Unlocks` line misleading on fresh profiles (`src/belote/ui/announce.py:91`).** The line `Unlocks: {len(profile.unlocked_ids)} items found` showed "3 items found" on a brand-new profile, but the BelAtro collection screen showed nothing unlocked — because `Profile.unlocked_ids` defaults to `["le_classique", "le_courageux", "l_econome"]` (3 starter items) while `Profile.discovered_items` defaults to `[]`, and the collection screen filters on `discovered_items` (`src/belote/belatro/ui/collection.py:77`). The two lists were never synced, but the stats line implied they were. Fix replaces the single line with two: `Discovered: N items seen` and `Unlocked: N items earned`. Both counts are now visible and the discrepancy is intelligible. Regression: `tests/test_announce_stats.py::test_stats_shows_discovered_and_unlocked_separately`.

### Internal

- **Tests**: 691 → 702 (+11; +10 new + 1 in `test_ansi_helpers.py`). New files: `tests/test_render_felt_polish.py` (8: pip determinism, braille presence, vignette, frame gating at COMPACT/STANDARD-min/STANDARD-with-slack, readout gating at slack/at-minimum), `tests/test_hand_auto_sort.py` (1: `prompt_card` propagates sorted hand), `tests/test_announce_stats.py` (1: stats screen shows both `Discovered:` and `Unlocked:` with correct counts). Existing `test_ansi_helpers.py::test_themes_have_required_palette_keys` updated for `felt_edge_bg` + new `test_felt_edge_bg_returns_csi_sequence`.
- **Strict gates**: pytest 702/702 green.
- **Version markers bumped**: `pyproject.toml`, `src/belote/__init__.py`.
- **Plan file**: `/home/mrrobot/.claude/plans/i-want-to-add-inherited-wilkes.md`.

### Design notes

- **Perkins integration path.** The braille-texture and corner-ornament approach was chosen partly so future visual polish can be designed in [Perkins](https://github.com/Mr-Robot-err-404/perkins) (an ASCII pixel-art editor that uses braille glyphs natively) and pasted in as ANSI-string constants. The current `╔═══◆` corner is a placeholder — a Perkins-designed fleur-de-lis / compass-rose / themed crest could replace it without touching the framing logic.
- **Diff-renderer compatibility.** Pip placement must remain a pure function of `(row, col)`. Tested by `tests/test_render_felt_polish.py::test_pip_overlay_is_deterministic` which re-renders the same state and asserts byte-identical output. Any future change introducing `random` or `time` into the felt pattern will break this test.


## [3.9.3] - 2026-05-15

Multi-agent audit pass (six Explore agents — three broad-sweep + three targeted deep-dives on AI, scoring edge cases, per-joker mechanics, endless mode, meta-progression). Every load-bearing finding verified against the live code before patching; **8 false positives** caught and documented (corrupted-joker seat semantics being intentional, ToutStreak persistence working correctly via `card_enhancements`, `_card_back` LRU cache being theme-keyed, etc.). **Six real fixes (R1–R7)** landed plus three larger phases: render-diff layer, endless-mode boss-variety guard, and a Quinte Royale unlock that had been marked `is_unlockable` for releases without a trigger. **Rematch entirely removed** at user request — game-over screen keeps only `[Enter/Q] Menu` and `[H] History`; players who want to play again use the menu. **+30 regression tests** (661 → 691).

### Fixed

- **`src/belote/ai.py::_hard_special` + `_hard_bid` (R1, MED) — AI bidding now honors zero-rank boss flags.** Pre-3.9.3 the heuristic summed raw `card_points` even when `jacks_zero` / `aces_zero` / `kings_zero` / `tens_zero` / `ban_clubs` were active, so the AI overbid Tout Atout on a jack-heavy hand under Le Sauvage even though those jacks would score 0. The fix routes evaluation through the new public `scoring.card_points_with_modifiers(card, trump, bm)` helper (a thin wrapper over the existing `_card_points_with_zero_ranks` — same canonical zero-rank logic the live HUD and final scoring use). Honor-counting in the regular-suit branch also drops a rank if its boss flag is active. Regression: `tests/test_ai.py::test_hard_ai_does_not_bid_ta_when_jacks_zero_suppresses_jacks`.
- **`src/belote/game.py::_record_belote_announcement` + new `GameState.belote_trump` field (R2, LOW) — L'Anarchie preserves rebelote across mid-belote trump rotation.** When trump rotates after trick 2/4/6 (`dynamic_trump`), a K-trump played in trick 2 and Q-of-original-trump in trick 3 would silently drop the rebelote because the K/Q match used `card.suit == current_trump`. The fix captures the trump at first-belote into a new `belote_trump: Suit | None` GameState field (mirrors the existing `belote_announcer` pattern) and matches the rebelote K/Q against the captured suit. Regression: `tests/test_belote.py::test_anarchie_rebelote_survives_cross_rotation_play` + non-rotation sanity test.
- **`src/belote/belatro/ui/hud.py::BelAtroHUD.render` + `_render_compact` (R3, LOW) — HUD score line gated under La Compétition boss.** The live running total (sequential trick-point sum) diverges from the final score under `separate_scoring` (which picks per-seat max). The HUD now shows a "Compétition: score par siège — total final caché" disclaimer instead of a misleading running total when this boss is active.
- **`src/belote/belatro/items/jokers/economy.py::LeBanquier` (R4, LOW) — bonus cash now suppressed on failed rounds and on EW-taker rounds.** Description says "Earn $1 for every 10 card points you score above the Blind target"; that framing presumes NS held a successful contract. Pre-3.9.3 the joker paid out unconditionally — even on chute, even when EW was taker. Now gates on `not breakdown.is_failed and taker_seat in (SOUTH, NORTH)`. Other on-round-end jokers (LAvare, LeFantome, LaSentinelle, LAccumulateur, LaSentinelleP) were audited and intentionally remain ungated — their descriptions are state-based (cards in hand, jack never used to win, etc.), not win-conditional.

### Changed

- **`src/belote/belatro/items/base.py::Voucher` + `belatro/items/vouchers.py` + `belatro/run/shop.py` (R5) — voucher idempotency guard relocated from `Shop._apply_item` into the `Voucher` base class.** Subclasses now implement `_apply_once(run)`; the base's `apply(run)` consults `run._applied_voucher_ids` and short-circuits a second invocation. Any future caller (replay reconstruction, deck-builder preview, hypothetical save/load) inherits the same protection automatically — pre-3.9.3 the guard only fired when the shop was the call site, so a different caller would silently double-stack `+=` vouchers (LaTelescope, LaDoubleDonne, LesCartesDorees, LeCouteau). Regression: `tests/belatro/test_voucher_idempotency.py::test_direct_voucher_apply_is_idempotent_without_shop`.
- **`src/belote/belatro/ui/hud.py` (R7) — every bare `print()` call batched into one `sys.stdout.write` + `flush`** per render entry point (`render`, `_render_compact`, `render_joker_pip_strip`, `render_synergy_tooltip`). ~9 fewer syscalls per BelAtro HUD frame. Mirrors the canonical `render.py:1002` pattern.
- **`src/belote/ai.py:627` (R6) — comment fix.** Said "prefer keeping high value cards if not winning" but the code adds points to the play-score (i.e. biases toward *playing* high cards). Rewritten as "Small per-card tiebreaker: when win/loss heuristics are otherwise equal, slightly bias toward playing the higher-value card."

### Added

- **`src/belote/ui/render.py` (Phase 6) — diff-based render emit.** `display()` now compares each frame's per-row line list against the previously committed frame and writes only the rows that actually changed. Idle re-renders (polling input between keystrokes, hovering on a card without moving) collapse from ~28 row writes to zero. New module-level `_last_emitted_lines` baseline; reset on layout change (via the existing `_last_render_key` invalidation), theme change (via the existing `theme_manager.register_callback(clear_card_cache)` callback — `clear_card_cache` now also clears `_card_back` LRU + the diff baseline), and explicit `display(state, force=True)`. Escape hatch: `BELOTE_NO_DIFF=1`. The full `render()` string contract is unchanged — tests calling `render(state)` directly still get the complete frame. Regression: `tests/test_render_diff.py` (6 tests).
- **`src/belote/scoring.py::card_points_with_modifiers` (public)** — thin wrapper exposing the existing `_card_points_with_zero_ranks` for callers outside `scoring.py` (notably `ai.py` for R1).
- **`src/belote/game.py::GameState.belote_trump: Suit | None`** — new field set when `belote_tracker[0]` first flips True, read by the rebelote check (R2).
- **`src/belote/belatro/core/run_state.py::BelAtroRun._recent_boss_ids: list[str]` (Phase 5) — endless-mode boss variety guard.** The boss selector in `belatro/main.py` now suppresses immediate boss repeats in endless by rerolling against the last-2 window (capped at 8 reroll attempts to never loop on degenerate pools / monkeypatched single-boss tests). Normal-run boss selection is unchanged — variety is only enforced when `run.endless` is True. Regression: `tests/belatro/test_endless.py::test_recent_boss_window_is_bounded_to_two`.
- **`src/belote/belatro/progression/unlocks.py::UnlockTracker._handle_declaration` (Phase 8) — Quinte Royale now unlocks on a Quinte announcement.** The Legendary joker was marked `is_unlockable = True` in `annonces.py:71` for several releases but had no path to actually unlock — `_handle_round_end` never set the flag, so the joker was filtered out of every shop pool. `UnlockTracker.on_event` now also dispatches `DeclarationScoredEvent`; when NS announces a sequence ≥ 100 pts, `quinte_royale` unlocks and the pending-announcement banner fires. Regression: `tests/belatro/test_progression.py::test_quinte_declaration_unlocks_quinte_royale` + negative tests (short sequence / opponent quinte).
- **`src/belote/gameflow.py::_undo_pop_to_south` + visible undo banner (Phase 7b user request).** Pressing `Z` previously popped one history-stack entry — but the stack records *every* play including AI moves, so a Z after the AI finished a trick landed on an AI mid-trick state, and the AI re-played deterministically with no visible effect. The new helper pops until the restored state has `turn == SOUTH` (the user's actual prior decision point), bounded by `stack_base` so undo can't cross round boundaries. After each successful pop, `announce("↶ Undo", duration=0.8, reader=reader)` paints a 0.8 s banner before the rolled-back position is redrawn so the player sees the undo take effect. Same UX applied to the bidding-undo path. Regression: `tests/test_undo.py::test_undo_pop_to_south_skips_intermediate_ai_states` + 2 boundary tests.

### Removed

- **Rematch feature (user request).** `src/belote/main.py` no longer offers `[R] Rematch` on the game-over screen; the only post-game choices are `[Enter/Q] Menu` and `[H] History`. The `rematch` variable, the conditional-menu-skip flag, and the dedicated reset path are all gone. `src/belote/ui/prompts.py::show_help` line `"[R] Rematch (Game Over)"` deleted.

### Audit verdict — verified clean, false positives caught

Six Explore agents flagged a number of "critical" issues that were verified against the actual code and rejected:

1. **Corrupted jokers (Le Traître / Le Démon / L'Égoïste / L'Agent Double) using `event.winner == Seat.SOUTH` instead of team scope** — intentional design. The class names and descriptions ("partner is irrelevant", "partner plays for opponents", "partner throws one trick per round") explicitly mark these as themed sabotage jokers. South-only is the design contract.
2. **Tout Streak streak persistence at `main.py:367-369` being "dead code"** — false. Verified at `round_driver.py:121-123`: `card_enhancements` is merged into `state._joker_state` at the start of every round, so the persisted `tout_streak_streak` flows back in. The persistence works.
3. **`_card_back` LRU cache going stale on theme change** — false. The cache is keyed by `theme_name` so a new theme produces a new key and a fresh render; old entries are LRU-evicted naturally. (3.9.3 still adds `_card_back.cache_clear()` to `clear_card_cache()` for memory hygiene since the diff-layer change now invalidates the frame baseline on theme change too — but the original "stale render" concern was wrong.)
4. **Negative-edition jokers "bypassing" the slot check** — intentional. `_can_accept` at `shop.py:152-154` returns True for Negative jokers by design; that's the whole point of the Negative edition.
5. **The Sun (Tout Atout) planet firing regardless of taker** — false. The parent block at `belatro/core/scoring.py:198+` gates on `event.winner in _NS_TEAM` already.
6. **BelAtro HUD `print()` calls causing "torn frames"** — theoretical only. Python stdout is single-threaded line-buffered; a bare `print()` is atomic per call in a TTY. We batched anyway (R7) as a micro-perf win, but there was no visual bug.
7. **L'Anarchie rebelote always broken** — partially false. Within the standard sequence (K then Q in the same trick or in trick 1+2 before the first rotation), rebelote already worked. Only the cross-rotation case was real (fixed as R2).
8. **`clear_card_cache()` being "incomplete"** — cosmetic at worst. Both LRU caches are theme-keyed, so staleness is impossible.

The "fake risky" agent finding (jokers in `risky.py` / `shaper.py` needing `is_failed` gates) cited files that don't exist — the real joker files are `annonces` / `coinche` / `contract` / `corrupted` / `economy` / `hand_comp` / `trick_timing` + `partner_jokers/{passive,shaper}`. Audit re-done against the actual files; only LeBanquier needed gating (R4).

### Performance verdict

- Benchmark smoke: 203–235 rounds/sec end-to-end (was 235 pre-3.9.3; well within budget, variance is system load).
- New render diff layer: idle re-render byte count drops to < 25% of the first frame (regression test pins this).
- No measured hotspot in scoring, AI decision, or trick-play paths. The 3.6 / 3.7.1 / 3.8.0 audits already covered the obvious cost centers.

### Internal

- **Tests**: 661 → 691 (+30). R1 (×1), R2 (×2), R4 (×3), R5 (×2), Phase 6 (×6), Phase 5 (×6), Phase 7b (×3), Phase 8 (×7).
- **Strict gates**: pytest 691/691 green; benchmark smoke green.
- **Version markers bumped**: `pyproject.toml`, `src/belote/__init__.py`.
- **Plan file**: `/home/mrrobot/.claude/plans/bug-hunt-code-performance-mutable-blanket.md`.


## [3.9.0] - 2026-05-14

Comprehensive bug-hunt, logic, and performance audit pass. Three parallel Explore agents covered the classic engine (`game.py` / `scoring.py` / `ai.py` / `gameflow.py` / `deck.py`), the BelAtro engine (`round_driver.py` / `modifier_patch.py` / `event_bus.py` / `belatro/core/scoring.py` / `boss.py` / `run_state.py` / `shop.py` / `belatro/main.py`), and the items catalogue + UI hot paths (`registry.py` + every joker / planet / tarot / voucher + `render.py` / `hud.py` / shop UI). Every load-bearing claim was spot-checked against the current code. **One real bug** (LOW), **one feature gap** filled, and a defensive cosmetic cleanup. Performance verdict: no measured hotspot — prior 3.6 / 3.7.1 / 3.8.0 audits already addressed the obvious paths. All 21 boss modifiers, 36 jokers, 8 planets, 12 tarots, 12 vouchers verified wired end-to-end. **+6 regression tests** (655 → 661). Plan file at `/home/mrrobot/.claude/plans/bug-hunt-code-performance-wise-puzzle.md`.

### Fixed

- **`src/belote/belatro/ui/announce.py:98` (LOW) — `BelAtroAnnounce.yes_no()` no longer hangs on `Key.EOF`.** Pre-3.9.0 the prompt loop exited on `Key.ENTER`, `Key.ESC`, `Key.QUIT`, or character `y`/`n`/`o`, but had no `Key.EOF` return path. Two call sites in `belatro/main.py` (the post-Ante-8 endless prompt at line 137 and the player-side surcoinche prompt at line 267) would hang the process on Ctrl-D / piped-empty stdin / closed terminal. Established inconsistency: sibling `banner()` (line 75) and `score_popup()` (line 126) in the same file already handled EOF. Regression test in `tests/test_input_eof.py::test_announce_yes_no_returns_false_on_eof`.

### Added

- **`src/belote/ansi.py` — `NO_COLOR` env-var support** per the [no-color.org](https://no-color.org/) spec. When `NO_COLOR` is set to any non-empty value, `fg()` / `bg()` return the empty string. SGR formatting (`BOLD`, `DIM`, `REVERSE`, `UNDERLINE`, `STRIKETHROUGH`, `RESET`) and cursor/clear sequences are unchanged — they aren't color. Read once at import (mirrors `a11y._ENABLED`); `_refresh_no_color_from_env()` exported for tests. 4 new tests in `tests/test_no_color.py`.
- **`scripts/benchmark.py::benchmark_belatro_round` (new)** — end-to-end `drive_round` rounds/sec probe under a deterministic seed (mean + p95 + rounds/sec). Regression sentinel for round-driver throughput. New `--smoke` flag runs every benchmark at iterations=2 for a fast CI-friendly check; pinned by `tests/test_benchmark_smoke.py`.

### Changed

- **`src/belote/scoring.py::resolve_declarations` (cosmetic)** — the 4-seat announce-order tuple (clockwise from taker) is now built once in the enclosing function and shared by `_resolve_tie_carre` and `_resolve_tie_seq` via closure. Pre-3.9.0 each helper rebuilt the same tuple inline. Behavior-preserving; the regression guard is the existing `tests/test_declaration_tiebreak.py` suite.
- **`scripts/benchmark.py` cleanup** — auto-fixed 17 long-standing ruff issues (W293/W291/I001/F401) in the file as part of the enhancement-pass scope.

### Audit verdict — verified clean, no fix needed

- **Classic engine** (game.py / scoring.py / ai.py / gameflow.py / deck.py): all 19 game mechanics wired end-to-end (bidding pass/normal/TA/SA/coinche/surcoinche, trump-play follow/trump/overtrump/partner-master exception, declarations + tie-break, belote/rebelote, contract-aware Capot 220/348/252, Dix-de-der, litige, taker-failed redistribution). AI memoization (`processed_tricks_count` / `last_voids_key` / `last_partner_hand_key`) resets correctly on both new-round and undo paths.
- **BelAtro engine**: all 21 boss modifiers patch → state → read end-to-end; no `boss.id == "…"` string branching anywhere; event bus correctly round-scoped; `ScoreAccumulator.update_state` already coalesces into one `replace()` per event; voucher idempotency guard live; endless mode (×2.2) scaling correct.
- **Items + UI**: all 36 jokers' `on_event` signatures match bus dispatch; team-not-seat convention applied correctly (jokers checking "did our team win" use `team_of(event.winner) == 0`, partner jokers deliberately key on `Seat.NORTH`). Theme cache invalidates on theme change; `_card_face` and `visible_len` both `lru_cache(4096)` with proper invalidation; HUD opt-in rebuild via `force_hud=False` since 3.8.0. Shop layout: card frame 16 cells, gap 2→1→0 degradation works.

### Performance verdict

No measured hotspot. `dataclasses.replace()` on the frozen `GameState` runs ~256 calls/round at sub-µs each — well under the 1 ms/round budget. Joker triggers linear-scan over ≤ 5 jokers (max slots). The "enhancement plan" here is the regression sentinel (`benchmark_belatro_round`), not a speculative rewrite.

### Internal

- **Tests**: 655 → 661 (+6). yes_no EOF ×1, NO_COLOR ×4, benchmark smoke ×1.
- **Strict gates**: pytest 661/661 green, mypy `--strict` 0 errors (77 files), ruff 0 violations.
- **Version markers bumped**: `pyproject.toml`, `src/belote/__init__.py`.

## [3.8.2] - 2026-05-14

Final logic audit and performance hardening. This release addresses the remaining edge cases identified during the deep-dive audit, focusing on BelAtro joker persistence, declaration scoring correctness, and test suite optimization. All 655 tests passing.

### Fixed

- **`src/belote/belatro/main.py` (HIGH) — Tout Atout streak now persists between rounds.** Fixed a bug where `ToutStreak` state was lost on every round transition because it wasn't being "drained" into the run-level state. It now correctly persists in `BelAtroRun.card_enhancements`.
- **`src/belote/belatro/items/jokers/annonces.py::QuinteRoyale` (MEDIUM) — Fixed trigger logic.** The joker previously armed on any declaration >= 100 points, including high-rank Carrés. It now correctly only arms on sequences of 5+ cards (Quintes).
- **`src/belote/belatro/items/jokers/economy.py::LeNotaire` and `contract.py::LeRebelle` (MEDIUM) — Refined belote-pair timing.** These jokers now trigger on the `rebelote` (second card played) instead of the first. This ensures they only subtract the 20-point bonus once it has actually been awarded to the team.
- **`src/belote/scoring.py::score_round` (MEDIUM) — Sequence scoring correctness.** Fixed a bug where sequences longer than 5 cards (e.g., 6 or 7 cards) were worth 0 points. They now correctly cap at 100 points (Quinte).
- **`src/belote/scoring.py::get_declaration_points` (MEDIUM) — Carré scoring fix.** Fixed a logic bug where Carrés were always worth 0 points due to a rank-lookup type mismatch.
- **`src/belote/scoring.py::_score_capot_outcome` (MEDIUM) — Capot/Zero-Final consistency.** Fixed a bug where the Capot reward did not respect the `no_dix_de_der` boss modifier. It now correctly drops the base reward by 10 points when the last-trick bonus is suppressed.
- **`tests/test_gameflow.py` (PERF) — Mocked `interruptible_sleep` in tests.** Resolved a 4-second delay in the test suite by ensuring UI-centric sleeps are bypassed during unit testing.

## [3.8.1] - 2026-05-14

Bug-hunt + logic audit pass. Five parallel audit agents (BelAtro core, classic engine, BelAtro items/run/partner, UI layer, performance) ran across the codebase; verification turned 8 raw findings into **3 confirmed critical bugs**, **3 medium correctness fixes**, and **1 documentation typo**. Two agent claims (`_card_beats` under Tout Atout, `_compute_belote_points` 20-when-only-K-played) were refuted on re-trace and not changed — both are working as designed. **+5 regression tests** (650 → 655).

### Fixed

- **`src/belote/game.py::_resolve_trick_winner` (CRITICAL) — La Rupture no longer drifts between play_card and score_round.** Pre-3.8.1 `_resolve_trick_winner` derived the previous trick's winner via `trick_winner_seat(state.completed_tricks[-1], …)` — the RAW result. Meanwhile `compute_trick_winners` (the final-scoring authority) threads the *resolved* previous winner through the chain. On trick 3+, whenever Rupture flipped trick N-1, the two paths disagreed: `state.last_trick_winner` (and downstream HUD running totals, dix-de-der attribution) reported a winner that did NOT match the final scoring tally. Fixed by reading `state.last_trick_winner` (already stored as the resolved value). Regression test in `tests/belatro/test_boss_modifiers_integration.py::test_rupture_play_card_resolves_consistently_with_scoring`.
- **`src/belote/belatro/engine/round_driver.py:135-148` (CRITICAL) — boss modifiers are now applied BEFORE `acc.trigger_round_start`.** Pre-3.8.1 the call order was `trigger_round_start` (which snapshots `state.boss_modifiers.no_dix_de_der` into `joker_state["no_dix_de_der"]`) → `boss.apply` (which patches the flag onto the live state). Any joker reading `state.get("no_dix_de_der", …)` (e.g. `trick_timing.py` last-trick scoring) saw the BossModifiers default `False` rather than the live boss flag — so the boss-aware joker code paths silently no-op'd on Le Zéro Final blinds. Fixed by reordering. Regression test in `tests/belatro/test_round_driver.py::test_boss_flags_applied_before_trigger_round_start`.
- **`src/belote/belatro/engine/round_driver.py:393-401` (CRITICAL, La Rupture follow-on) — `TrickWonEvent.winner` now carries the resolved (Rupture-aware) seat.** Pre-3.8.1 the event was emitted with `winner = trick_winner_seat(last_trick, …)` (raw); under La Rupture every joker keyed on `team_of(event.winner) == 0` would credit the team that did NOT actually receive the trick in `score_round`. Fixed by emitting `winner = state.last_trick_winner`; `trick_winner_seat` import removed from the round driver.
- **`src/belote/belatro/items/jokers/contract.py::LeRebelle` and `economy.py::LeNotaire` (HIGH) — belote-pair jokers no longer double-fire on `BeloteAnnouncedEvent`.** `round_driver.py` emits `BeloteAnnouncedEvent` twice per round (once when belote flips, once when rebelote flips). Pre-3.8.1 LeRebelle returned `times_mult=3.0` on both, yielding ×9 net Mult instead of ×3. LeNotaire awarded $10 instead of $5. Both now gate on `not event.is_rebelote` so the bonus fires once on the belote announce; the description ("Belote/Rebelote is worth …") matches the intent. Regression tests in `tests/belatro/test_phase2_content.py::test_le_rebelle_fires_once_per_belote_pair` and `…::test_le_notaire_pays_once_per_belote_pair`.
- **`src/belote/belatro/items/jokers/corrupted.py::LAgentDouble` (HIGH) — partner-sabotage half of the joker now actually triggers.** Pre-3.8.1 the joker tracked `_sabotage_remaining` in joker_state, but the AI sabotage path (`ai.py:283`) keys on `state.boss_modifiers.agent_double_active`, which the joker never set. Result: the +4 Mult half worked but "Partner plays optimally for the opponents for 2 tricks" was a no-op. Fixed by mirroring `LeTraitre`'s wiring: `on_purchase` flags `run.agent_double_joker`; `round_driver` picks it up, flips `agent_double_active=True`, and populates `agent_double_tricks` with 2 random tricks (same precedence rule — boss agent_double takes priority). New field `BelAtroRun.agent_double_joker: bool`. Regression test in `tests/belatro/test_phase2_content.py::test_lagent_double_purchase_flags_run`.
- **`src/belote/belatro/core/scoring.py:219,231,270` (MEDIUM, typing hardening) — `reward.get(…, 0)` defaults widened to `0.0` for the float-typed contract reward fields.** `honor_bonus` (Moon / Sans Atout), `bonus_mult_per_trick` (Sun / Tout Atout), and `coinche_multiplier` (Libra / Coinche) are declared `float` in `ContractReward` (3.7.1 BA-L1). The int-zero default propagated `int` through type inference at the consumer site, defeating part of the BA-L1 fix. Cosmetic at runtime, real for `mypy --strict` line of defense.
- **`src/belote/ui/layout.py:39` and `render.py:637` (DOC TYPO) — "press T for full history" → "press H for full history".** The key was renamed from T to H prior to 3.8.0; the layout comment and the last-trick-sidebar comment in render still pointed at the stale binding. T now binds to Cycle Theme; H is the canonical history key (see `input.py:163-165`, `prompts.py:217`). Visible behavior change versus pre-May-2026 builds: if you reach for T expecting history, you'll cycle the theme instead.

### Verified clean — audit findings rejected after source verification

- **`game.py::_card_beats` under Tout Atout (HIGH claim)** — agent claimed off-suit cards could beat lead-suit under TA (e.g. J♦ beating lead 7♠). Re-traced: `is_trump_card` evaluates `card.suit == trump` where `trump == Suit.TOUT_ATOUT`. Since no actual card carries `suit=TOUT_ATOUT` (the enum's `is_card_suit()` returns `False` for it), the check yields `False` for both candidates and the function correctly falls through to `return card.suit == lead_suit`. Different-suit cards never win under TA. No change.
- **`scoring.py::_compute_belote_points` 20-when-only-K-played (MEDIUM claim)** — agent flagged that `BELOTE_POINTS=20` is awarded when `belote_tracker[1]` is False. Reading `config.py`: `BELOTE_POINTS=20`, `REBELOTE_POINTS=40` — the design models the rebelote tier as a strict upgrade (40 total when both K and Q play, 20 partial credit when only one plays). Working as configured.

### Internal

- **Tests**: 650 → 655 (+5). Regression coverage for every CRITICAL/HIGH fix above.
- **Strict gates**: pytest 655/655 green, mypy `--strict` 0 errors (78 files), ruff 0 violations.
- **Version markers bumped**: `pyproject.toml`, `src/belote/__init__.py`.

## [3.8.0] - 2026-05-13

UI-cutoff pass, audit polish, and minor perf wins. The session began with a user-reported bug — the main-menu croissant art clipped at the top on certain terminal heights — and broadened into a full UI-fit overhaul (live "terminal too small" overlay, BelAtro screens rebuilt around vertical centering, shop action buttons relocated below the cards). A second three-Explore-agent audit ran across the classic engine, BelAtro mode, and render/AI hot paths: **no critical findings**, but three minor hardening items (zip-strict, voucher idempotency, all-pass-bidding test gap) and three modest perf wins shipped. **+15 regression tests** (635 → 650). Plan file at `/home/mrrobot/.claude/plans/i-want-to-fix-swirling-pelican.md`.

### Fixed

- **`src/belote/ui/menu.py:116` — classic main-menu croissant no longer clips at the top.** Pre-3.8.0 the guard read `if term_h < 42: return final_cup`, but the full content needs 41 art + 2 footer = 43 rows. At `term_h == 42` the croissant was rendered and the top row scrolled off the alt-screen; at 43 it sat flush against the top with zero margin. New threshold is derived from `len(get_cards_art()) + 1 + len(CUP_TEMPLATE) + 2 + 1` (= 44), so the croissant only shows when there is genuine room for it plus one row of breathing space.
- **`src/belote/ui/main.py:115-123` — startup "terminal too small" hard-fail replaced with a live overlay.** Pre-3.8.0 a sub-80×32 terminal got `print()` + `sys.exit(1)` before the alt-screen was entered, polluting scrollback and offering no recovery. New `src/belote/ui/fit_guard.py::require_minimum` paints a centered "Resize to 80×32 (currently NN×MM) — Press Q to quit" inside the alt-screen, refreshes on SIGWINCH (the existing handler at `render.py:99` invalidates the size cache), and returns the moment the terminal is large enough. `FitAbortedError` raised on Q/EOF.
- **BelAtro screens converted to a list-build + vcenter pattern; absolute-row writes removed.** `belatro/ui/{shop,menu,announce,collection,consumables}.py` previously pinned content to hardcoded `move(N, …)` rows (e.g. shop description at row 18, BelAtro art at rows 3-9, boss reveal at rows 10/13/15). New `src/belote/ui/layout.py::vcenter_lines(lines, term_h)` — extracted from `render.py:899-903` — pads top + bottom so every BelAtro screen centers vertically and never clips. `history.py` and `rules.py` (already responsive) only gain a `require_minimum` call at loop entry.
- **`belatro/ui/shop.py::_render` — reroll / forge buttons moved BELOW the card row.** Pre-3.8.0 the bracket-text labels (`[ Reroll $5 ]`, `[ Forge x3/3 ]`) rendered at `card_start_row + 3` — mid-frame across the card art — and `_card_col`'s 18-cell spacing × 5+ columns overflowed at 80 cols when the forge slot was visible. New layout places the action strip on its own row directly below the cards, centered. No card frame width change, no inventory cap. `_card_col` now centers the card strip and tightens inter-card gap (down to 0) before any card would extend past `term_w - 2`.
- **`src/belote/belatro/run/shop.py::_apply_item` — voucher idempotency guard (B1 audit finding, MINOR hardening).** `LaTelescope`, `LaDoubleDonne`, `LesCartesDorees`, `LeCouteau` use `+=` against `BelAtroRun` state in their `apply()`. The only call site is `Shop.buy_item`, which fires apply() exactly once per purchase — so the existing code was safe in practice. But a future save/load round-trip that re-invokes apply() on a voucher already in `run.vouchers` would silently double the bonus. New `BelAtroRun._applied_voucher_ids: set[str]` field; the shop checks-and-marks before each apply(). LaVoute's `max()` floor pattern is its own idempotency mechanism and is unchanged. 6 regression tests in `tests/belatro/test_voucher_idempotency.py`.

### Changed

- **`src/belote/ui/render.py::patch_trick_card` — HUD rebuild is now opt-in via `force_hud: bool = False` (P1).** Pre-3.8.0 every of the 32 card-play patches per round rebuilt the entire HUD bar at row 1, even though `_build_hud` reads `state.current_round_points` / `state.team_scores`, neither of which advance until `play_card` commits the completed trick (which the caller then re-renders via `display()`). New default skips the rebuild; pass `force_hud=True` when a caller knows HUD-affecting state has changed externally. Saves ~300 µs per round plus a chunk of ANSI bytes; preserves correctness because the next `display()` call refreshes the HUD anyway.
- **`src/belote/ai.py::AIMemory` — partner_hand rebuild memoised on the same trick-progress key as void inference (P2).** Pre-3.8.0 every `decide_card()` call (32 × per round) cleared and rebuilt `partner_hand` from `state.hand_of(partner(self.seat))`, even though the partner's hand only changes when they play a card. New `last_partner_hand_key: tuple[int, int]` mirrors the existing `last_voids_key` pattern (`(completed_count, current_trick_len)`); skip rebuild on a no-op repeat call. Saves ~200 µs per round; reset properly on new round and mid-round undo (mirrors the existing void-cache reset paths).
- **`src/belote/ai.py::_hard_bid` — pre-compute suit-bucketed hand in one pass (P4).** Pre-3.8.0 each of the four suit iterations re-filtered `hand` (twice for trump/honour counts, plus inner cross-suit counts) — 12 hand walks per bid evaluation. New `suit_cards: dict[Suit, list[Card]]` is built with a single `for c in hand` pass and reused. Readability win is bigger than the µs perf win on 8-card hands; pattern matches what `_special_bid` already does.
- **`src/belote/scoring.py:298,301,313,316` — declaration tie-break zips upgraded to `strict=True` (C1).** Walks `ns_carres` / `ns_carre_seats` (and `ns_seqs` / `ns_seq_seats`) in lockstep with the parallel lists built at `scoring.py:274`. Today the invariant holds; `strict=True` defends against a future edit that breaks it silently.

### Added

- **`src/belote/ui/fit_guard.py` (new) — `require_minimum(reader, min_cols, min_rows)` + `FitAbortedError`.** Live overlay used by `main.py` (once at startup) and every BelAtro screen loop. Refreshes on SIGWINCH, dismisses automatically once the user resizes past the floor, raises `FitAbortedError` on Q / EOF for clean caller cleanup.
- **`src/belote/ui/layout.py::vcenter_lines(lines, term_h)`** — pure helper extracted from `render.py:899-903`. Pads top + bottom so a list of lines sits centered in `term_h`; truncates if oversized. Used by every BelAtro screen and by classic `render()`.
- **`tests/test_bidding_all_pass.py` (new, 5 tests)** — pins all-pass redeal edge cases beyond the basic `test_new_coverage.py::test_all_pass_redeal` smoke. Covers full state reset (bids / bidder_index / bidding_round / trump / taker), multi-redeal dealer rotation, the "round 2 + all pass" path that must redeal (not advance to a phantom round 3), and successful post-redeal bidding.
- **`tests/belatro/test_voucher_idempotency.py` (new, 6 tests)** — pins the B1 guard contract.
- **`tests/belatro/test_shop_empty_pools.py` (new, 4 tests)** — B2 audit gap: regression test for empty registry pools (degenerate Profile / full-unlock state). `_empty_pools` helper monkeypatches and bumps the registry generation so cached `get_available_*` views miss.

### Verified clean — audit findings rejected after source verification

Documented so the next cycle doesn't re-investigate:

- **`render.py:807-809` "unconditional `legal_cards` call" (P3 candidate)** — the call IS inside `if state.phase == Phase.PLAYING and state.turn == Seat.SOUTH`; the perf agent misread the guard. No change needed.
- **Tout Atout void-in-lead-suit discard logic (`game.py:560-578`, initial agent CRITICAL claim)** — verified correct per official rules: off-suit cards may be played when void but never win tricks. Comments and code agree.
- **Memory-documented 3.6.0 / 3.7.1 fixes** (L'Accumulateur team check, Libra reachability via NS-taker coinche, synergy validation under `python -O`, event-bus handler isolation, `PatchedGameState` underscore narrowing) — all still in place; grep for `boss.id ==` returns zero hits in production paths.

### Internal

- **Tests**: 635 → 650 (+15). Three new test files (`test_bidding_all_pass.py` ×5, `test_voucher_idempotency.py` ×6, `test_shop_empty_pools.py` ×4).
- **Strict gates**: pytest 650/650 green, mypy `--strict` 0 errors (78 files), ruff 0 violations.
- **Version markers bumped**: `pyproject.toml`, `src/belote/__init__.py`.

## [3.7.1] - 2026-05-13

Bug-hunt, performance, and logic audit pass plus the three items 3.6.0 deferred to 3.7.0. Three Explore agents ran in parallel against the documented false-positive catalogue. The classic-engine sweep returned **no novel findings** — the 3.4.x → 3.6.0 audits have absorbed the available correctness surface. The BelAtro layer produced **2 confirmed bugs** (one HIGH, one MEDIUM) and **1 polish item**. The deferred 3.7.0 items — `score_round` / `play_card` refactor, partner-joker test coverage, player-facing NS-taker surcoinche — all land here. **+36 regression tests** (599 → 635). Plan file at `/home/mrrobot/.claude/plans/bug-hunt-code-performance-sequential-map.md`.

### Fixed

- **`src/belote/belatro/items/jokers/hand_comp.py:88` (BA-L2, HIGH) — L'Accumulateur now credits team trick wins, not just South.** Pre-3.7.1 the joker gated on `event.winner == Seat.SOUTH`, silently dropping +5 chips per 7/8 whenever the partner (NORTH) won the trick. The description says *"For every 7 or 8 **you** win in a trick"* and in BelAtro "you" = team (NS) — same convention applied to Le Patriote / Le Premier Sang / Le Sergent in 3.5.0. L'Accumulateur was missed in that pass. Fixed: `if team_of(event.winner) == 0:`. 6 regression tests in `tests/belatro/test_belatro.py::TestLAccumulateurTeamCredit` covering NORTH credit, EAST/WEST non-credit, mixed-round accumulation, and rank-8 parity with rank-7.
- **`src/belote/belatro/core/scoring.py:43,48,54` (BA-L1, MEDIUM) — `ContractReward` TypedDict now correctly annotates float fields as `float`.** `add_mult`, `bonus_mult_per_trick`, and `coinche_multiplier` were annotated `int` but populated with `0.3` / `1.0` / `1.0` by `planets.py`. Python's numeric coercion masked this at runtime, but the TypedDict was introduced explicitly to catch planet-reward key typos at type-check time — broken annotations defeated the purpose. Fixed; `mypy --strict` stays green (after pinning `libra_bonus: float` on the consumer side to keep the inference path explicit).

### Changed

- **`src/belote/scoring.py:599-878` (D1) — `score_round` extracted behind `_ScoringContext`.** ~280-LOC / ~30-branch monolith split into `_compute_belote_points`, `_compute_declaration_points`, `_score_capot_outcome`, `_score_normal_outcome`, with a `_ScoringContext` frozen+slotted dataclass threading pre-computed values (trump, taker, winners, tricks_ns/ew) into the helpers. Behaviour unchanged: zero test edits required. 3.6.0 deferred this because the natural extraction passed 15+ parameters between siblings; the context dataclass collapses that to one.
- **`src/belote/game.py:857-1018` (D1) — `play_card` extracted behind `_PlayContext`.** ~163-LOC / ~18-branch function split into `_record_belote_announcement`, `_resolve_trick_winner`, `_compute_live_round_points`, `_rotate_dynamic_trump`. The mid-trick early-return is now visually adjacent to the trick-complete branch instead of the trick-complete branch swallowing the entire function body. Zero test edits.
- **`src/belote/achievements.py` (P1-1) — achievement lookup via dict; `Achievement` gets `slots=True`.** Two `for a in ACHIEVEMENTS: if a.id == aid:` loops collapse to `_ACHIEVEMENT_BY_ID[aid]`. Catalog is 6 items so the perf win is microscopic; the readability win is real. `slots=True` brings the dataclass in line with every other frozen dataclass in the codebase.

### Added

- **`tests/belatro/test_partner_jokers.py` (D2) — focused matrix for 9 partner jokers.** Pre-3.7.1 the partner-joker modules (`passive` / `risky` / `shaper`) carried shallow smoke-tests in `test_belatro.py`. New file covers happy-path / non-trigger / round-boundary-reset for `LeMiroir`, `LaSymbiose`, `LeRelais`, `LAventurier`, `LeMartyr`, `LeParasite`, `LeGenereux`, `LaSentinelleP`, `LeCalculateur` — 26 tests, **100% line coverage** for the three modules (was effectively 0% direct coverage despite import-time references). Audit note pinned in the docstring: partner jokers correctly key on seat (NORTH), not team — they are the deliberate complement of L'Accumulateur, NOT subject to the BA-L2 fix.
- **`src/belote/belatro/engine/round_driver.py:89-98` + `belatro/main.py` (D3) — `prompt_surcoinche` callback on `RoundUICallbacks`; NS-taker player surcoinche.** Pre-3.7.1 the NS-taker branch only consulted the EW-AI heuristic; when EW coinched the player had no way to surcoinche back. New optional callback (default returns False, preserves backward compatibility for any third-party `RoundUICallbacks` impl), wired into `round_driver.py:268-279` so the player gets first refusal before the existing 30% AI surcoinche fallback fires. `BelAtroMain`'s `UICallbacks` implements it via `BelAtroAnnounce.yes_no`. 4 regression tests in `test_round_driver.py` (accept / decline-AI-skips / decline-AI-takes / default-no-op).

### Verified clean — audit findings rejected after source verification

Documented so the next cycle doesn't re-investigate:

- **Classic engine** (`game.py`, `scoring.py`, `deck.py`, `ai.py`, `gameflow.py`) — three-Explore-agent pass returned no novel findings. The 3.4.x → 3.6.0 audits absorbed the correctness surface.
- **`visible_len()` "duplicated" in `_build_hud()`** (`ui/render.py:669-670, 705-706`) — calls are on different strings in different layout branches; not redundant.
- **`detect_synergies()` recomputed per HUD render** (`belatro/ui/hud.py:67-82`) — O(joker_count × 6 pairs), microseconds per render; caching adds invalidation surface for no user-visible win.
- **`_slot_anchors()` called 3× per trick-mat render** (`ui/render.py:379/409/446`) — pure arithmetic, sub-microsecond.
- **`announce()` / `BelAtroAnnounce.banner()` duplication** — modal off-the-critical-path code with intentionally different positioning semantics.
- **Two history-overlay code paths (wide vs narrow term)** — intentional split for narrow-terminal readability.
- **Round-2 bid prompt ANSI redundancy** (`ui/render.py:751-753`) — visually correct (REVERSE wraps the segment); cosmetic only.

### Deferred to 3.7.2

- **Player surcoinche when EW is taker** — the symmetric mirror of D3. Today the EW-taker branch lets the player coinche but cannot surcoinche when partner-AI surcoinches the bid. Out of scope for the current pass; the `prompt_surcoinche` callback added in D3 can be reused.

### Internal

- **Tests**: 599 → 635 (+36). Two new test files: `tests/belatro/test_partner_jokers.py` (26), 4 new D3 tests in `tests/belatro/test_round_driver.py`, 6 new BA-L2 tests in `tests/belatro/test_belatro.py`.
- **Strict gates**: pytest 635/635 green, mypy --strict 0 errors (77 files), ruff 0 violations.
- **Version markers bumped**: `pyproject.toml`, `src/belote/__init__.py`.

## [3.6.0] - 2026-05-12

Verified bug-hunt and refactor pass over both the classic Belote engine and the BelAtro roguelite layer. A three-Explore-agent audit produced ~50 candidate findings; verification against current source rejected several as **false positives** (notably "dix-de-der double counting" — independent counters; "underscore-boss-attr anti-pattern" — already pinned; "M5 `last_voids_key` cross-round bleed" — already fixed). The items below are the ones confirmed against current code and shipped. **+4 regression tests** (595 → 599). Plan file at `/home/mrrobot/.claude/plans/bug-hunt-code-performance-functional-naur.md`.

### Fixed

- **`src/belote/belatro/engine/round_driver.py:210-289` (H1) — EW AI can now coinche an NS taker; Libra planet is reachable in natural play.** Pre-3.6.0 the coinche flow only branched on `state.taker in (Seat.EAST, Seat.WEST)`. When NS was taker there was no path that set `coinche_level > 0` outside of L'Avocat's `auto_coinche` or Le Coincheur's `start_coinched`. The `Libra` planet at `belatro/core/scoring.py:237-250` is gated on `event.coinche_level > 0 AND event.taker_seat in _NS_TEAM AND not failed`, so its content was effectively unreachable. New `_ew_should_coinche(state, rng)` heuristic (baseline 20 %, +15 % if either defender holds 2+ honour cards) gives the EW AI defenders a seeded chance; AI surcoinche from NS follows the existing 30 % pattern gated by `surcoinche_unlocked`. The branch also collapses the previous duplicated `auto_coinche` re-emit so the boss path lives in one site. 2 regression tests in `tests/belatro/test_round_driver.py` (one for the heuristic in isolation, one end-to-end via `ScoreAccumulator` joker capture).
- **`src/belote/belatro/items/registry.py:184-194` (H2) — synergy-ID validation now survives `python -O`.** The 3.0.1 check used `assert not missing, ...`. Under `PYTHONOPTIMIZE=1` (the default for packaged installs and `python -O`) the assertion is stripped and a typo in `belatro/ui/hud.py::_SYNERGY_PAIRS` would silently break every HUD synergy badge for that pair. Replaced with `if missing: raise RuntimeError(...)`. Verified by importing the registry in a subprocess under `-O`.
- **`src/belote/belatro/engine/event_bus.py:emit` (H3) — handler exceptions no longer halt remaining subscribers.** `emit()` now wraps each handler call in `try/except Exception`, logs via `logging.exception`, and continues iterating. `BaseException` (KeyboardInterrupt etc.) still propagates so a user Ctrl-C tears down the round cleanly. Pre-3.6.0 a single raising joker `on_event` would skip every subsequent subscriber for the rest of the round. 1 regression test in `tests/belatro/test_event_bus.py::test_raising_subscriber_does_not_skip_siblings`.
- **`src/belote/belatro/engine/modifier_patch.py:patch` (M3) — `PatchedGameState` no longer rejects legitimate `_`-prefixed sets.** The 3.1.0 anti-shim raised on **any** leading-underscore patch key, but `GameState` has legitimate `_chips`, `_mult`, `_joker_state`, `_rng` fields. Narrowed the guard to reject only `_X` where `X` IS a `BossModifiers` field — the precise 3.0.x anti-pattern target. A future joker / boss effect that needs to adjust accumulator scalars no longer hits a confusing "3.0.x shim was removed" error. 1 regression test in `tests/belatro/test_boss_modifiers_integration.py::test_patched_state_rejects_only_underscore_boss_attrs`.

### Changed

- **`src/belote/scoring.py` (M1+M2) — zero-rank / `ban_clubs` flag logic extracted to module-level helpers.** Three sites previously inlined the same `kings_zero` / `tens_zero` / `aces_zero` / `jacks_zero` / `ban_clubs` table (`trick_card_points`, `_calculate_base_points`, `_apply_scoring_modifiers`). New `_card_points_with_zero_ranks(card, trump, bm)`, `_trick_zeroed_by_ban_clubs(trick, bm)`, and `_trick_points_with_modifiers(trick, trump, bm)` are the single source of truth. Adding a new zero-rank boss flag is now one edit instead of three (the audit's drift-risk concern). No behaviour change; full suite green.
- **`src/belote/deck.py:Contract` (M4/R1) — added `class Contract(str, Enum)`** with values `NORMAL` / `SANS_ATOUT` / `TOUT_ATOUT` / `COINCHE` / `SURCOINCHE`. Inherits from `str` so values ARE plain strings — existing comparisons (`state.contract == "sans_atout"`) and JSON serialisation are unaffected. Migrated the dense comparison sites in `scoring.py`, `game.py`, `ai.py`, `gameflow.py`, and `belatro/engine/round_driver.py` to `state.contract == Contract.SANS_ATOUT`. UI label strings and joker / planet registry keys left as plain strings — `StrEnum`-style equality means they're interchangeable.
- **`src/belote/game.py:sort_hand` (P4) — now `@lru_cache(maxsize=512)`.** Bench: ~34 % wall-clock win on the UI render-loop access pattern (same `(hand, trump)` requested across consecutive frames). P2 (`deck.card_points` caching) was tested with the same harness and **rejected** — the function is too small for `lru_cache` overhead to amortise (1.86× slower with cache).
- **`src/belote/belatro/core/scoring.py:ContractReward` (R4) — TypedDict for `contract_levels` entries.** Documents the known keys (`add_chips`, `add_mult`, `jack_9_bonus`, `honor_bonus`, `bonus_mult_per_trick`, `add_money`, `capot_bonus`, `coinche_multiplier`) so mypy catches planet-reward key typos at type-check time. `BelAtroRun.contract_levels` stays as the wider `dict[str, dict[str, Any]]` to avoid an import cycle; the cast happens at the consumer boundary in `belatro/main.py`.
- **`src/belote/game.py` belote detection (L1)** — single-pass per hand. Previously rebuilt a `(rank, suit)` set and looped 4 suits per seat; now tracks two `set[Suit]` (kings, queens) in one pass and intersects.
- **`src/belote/deck.py` (L2)** — `card_points` and `trick_rank` type annotations widened to `trump: Suit | None` to match the SA call sites at `scoring.py` and elsewhere. Runtime behaviour was already correct.
- **`src/belote/scoring.py:_carre_points` (L3)** — uses `.get(..., 0)` for symmetry with `get_declaration_points` and `_sequence_points`. The dict is currently complete so this is fail-soft only; protects against a future `Rank` extension crashing scoring mid-round.

### Added

- **`tests/test_properties.py` (T1) — three new invariants.**
  - `test_chute_and_capot_are_mutually_exclusive`: under capot, credited points always live on exactly one side.
  - `test_dynamic_trump_never_overrides_sans_atout`: La Anarchie's per-2-trick trump rotation never fires under SA (`state.trump` stays None for the whole round).
  - `test_no_consecutive_team_wins_invariant_when_rupture_active`: under La Rupture, no team sweeps all 8 tricks (30 seeded rounds).
- **`tests/belatro/test_round_driver.py` (H1 backfill)** — `test_ew_should_coinche_baseline_rate` and `test_ew_ai_can_coinche_ns_taker_under_seed`.
- **`tests/belatro/test_event_bus.py` (H3 backfill)** — `test_raising_subscriber_does_not_skip_siblings`.
- **`tests/belatro/test_boss_modifiers_integration.py` (M3 backfill)** — `test_patched_state_rejects_only_underscore_boss_attrs`.

### Verified clean (audit false positives — do not re-investigate)

- **Dix-de-der is NOT double-counted.** `game.py:play_card` writes the live HUD's `current_round_points` on the 8th trick; `score_round` derives from `state.completed_tricks` independently. The two counters are independent — verified by reading both code paths.
- **The `getattr(state, "_X", False)` boss-flag anti-pattern is already pinned.** `tests/belatro/test_boss_modifiers_integration.py::test_invariant_no_underscore_boss_attrs` covers it. No leading-underscore boss attribute resolves on a vanilla GameState.
- **`AIMemory.last_voids_key` cross-round reset is already in place.** `ai.py:78` clears the cache key in the new-round branch alongside `played` / `known_voids` / `processed_tricks_count`. Covered by `tests/test_ai.py::test_void_cache_invalidates_across_rounds`.
- **Negative-edition joker slot growth is intentionally irreversible.** No sell mechanism exists today; the asymmetry is by design and documented at the increment site (`belatro/run/shop.py:166-168`).

### Deferred to 3.7.0

- Full `score_round()` and `play_card()` helper splits (L4/L5/R2/R3). Both functions are long (~280 LOC / ~30 branches; ~130 LOC / ~18 branches respectively) but the natural extraction passes 15+ parameters between siblings; a clean split needs an intermediate `ScoringContext` / `PlayContext` dataclass, which is its own refactor.
- Partner-jokers test coverage (T5) — `belatro/items/partner_jokers/{passive,risky,shaper}.py` are at ~0 % coverage per the perf audit. Out of scope for a single audit pass.
- Player-facing coinche / surcoinche prompts when NS is taker. Today only the AI surcoinches NS-taker rounds; the `RoundUICallbacks` layer doesn't expose a `prompt_surcoinche` callback yet.

## [3.5.0] - 2026-05-12

Comprehensive bug-hunt, game-mechanic audit, and performance pass over both the classic Belote engine and the BelAtro roguelite layer. A three-Explore-agent audit produced ~30 candidate findings; verification against the source rejected several as false positives (documented below) and confirmed **15 actionable items** plus **1 latent bug surfaced during implementation**. **24 new regression tests** land here (592 total, up from 568). Plan file at `/home/mrrobot/.claude/plans/bug-hunt-code-performance-tidy-meerkat.md`.

### Fixed

- **`src/belote/belatro/core/run_state.py:90-117` + new `src/belote/belatro/ui/consumables.py` (C1) — BelAtro consumables can now be activated.** Pre-3.5.0 `BelAtroRun.consume()` was defined but never called from any UI: every Tarot bought from the shop and every directly-purchased Planet accumulated in `run.consumables` with no way to use them. Only the voucher-gated Forge-Tierce path could level a planet. New `ConsumablesOverlay` is reachable from the shop via the `C` key, listing the tray and dispatching to `run.consume(item, context=run)` on a digit press. Hint line in the shop now shows `C: Consumables (N)`. **Also fixes a latent Le Fou bug**: `consume()` was advancing `last_consumable_id` to the *current* item BEFORE calling `item.use()`, so Le Fou's `use()` read its own id and fell through to the fallback path. Reordered to call `item.use()` first; Le Fou is special-cased as transparent so a second Le Fou keeps copying the same source rather than itself. 7 regression tests in `tests/belatro/test_consumables_ui.py`.
- **`src/belote/belatro/run_summary.py:67-74` (H1) — JSONL appends are now durable.** Added `f.flush() + os.fsync(f.fileno())` inside the `with` block, mirroring the atomic-save pattern in `progression/save.py:81-82`. A crash or power-loss mid-write no longer leaves a truncated final line that breaks downstream `jq` processing. 3 regression tests in `tests/belatro/test_run_summary.py`.
- **`src/belote/input.py:31-37,74` + ~20 consumer sites (H2) — EOF on stdin is distinct from ESC.** `KeyReader.read()` returned `KeyEvent(Key.ESC)` when `os.read()` returned empty bytes. A closed stdin (broken pipe, headless harness, Ctrl-D) made every prompt loop spin: ESC popped one menu level, the loop fell through and re-read stdin, got another "ESC", popped again — burning CPU until the outermost loop happened to exit. New `Key.EOF` enum value is returned on empty-read. Every `Key.ESC` consumer was updated to also accept `Key.EOF` (semantically equivalent: "back / cancel"); `prompt_card` and `prompt_bid` exit cleanly on EOF instead of spinning. 5 regression tests in `tests/test_input_eof.py`.
- **`src/belote/belatro/engine/event_bus.py` (H3) — `EventBus` round-scope invariant documented + `clear()` added.** The bus is created fresh per round in `round_driver.drive_round` and subscribers are released with it; no explicit unsubscribe was needed. The invariant was silent — if anyone moved the bus to a longer scope, every subscription would double-fire on round 2. Module docstring now spells out the round-scope contract; a new `clear()` method exists for the future where a longer-lived bus might be desirable. 3 regression tests in `tests/belatro/test_event_bus.py`.
- **`src/belote/scoring.py:228-330` (M1) — tied carrés / sequences go to the first announcer.** Standard Belote-Coinché awards a tied declaration to the team whose seat declared first (announcement order: taker → clockwise). Pre-3.5.0 the resolver returned `scoring_team=None` (cancel), which was defensive but non-standard. `resolve_declarations` gains an optional `taker: Seat | None = None` parameter; when supplied, tied carrés/sequences are awarded by walking the announce order. Legacy "cancel" behaviour preserved when `taker` is not provided. Both call sites updated to pass `state.taker`. 6 regression tests in `tests/test_declaration_tiebreak.py`.
- **`src/belote/belatro/engine/event_bus.py` + ~10 consumer sites (M3) — `RoundEndEvent.breakdown` is properly typed.** Pre-3.5.0 the field was `breakdown: Any` and every consumer wrote `getattr(event.breakdown, "is_failed", False)` — defensive noise that hid field-rename regressions until runtime. Now typed as `ScoringBreakdown` (TYPE_CHECKING forward-ref to avoid import cycle); all 9 `getattr` patterns replaced with direct attribute access. `taker_seat` correctly annotated `Seat | None` (was `Seat`, but the all-pass emitter at `round_driver.py:298` actually passes None).
- **`src/belote/scoring.py:750-763` (M5) — SA belote invariant pinned at contract level.** The `assert taker_belote == 0 and defender_belote == 0` for Sans Atout rounds was only inside the capot branch — a non-capot SA round with stray belote points would silently mis-score instead of surfacing the bug. Hoisted to a contract-level post-condition that covers both capot and non-capot paths.

### Changed

- **`src/belote/belatro/core/scoring.py:125-142` (M4) — `partner_jokers_double` legacy flag is now deprecated.** When both the tier scaling and the legacy boolean flag are set, a one-shot `DeprecationWarning` fires. Behaviour unchanged (`max()` of the two still wins); the flag is slated for removal in 4.0.
- **`src/belote/ui/render.py:988-997` (L1) — `patch_trick_card` batches its writes.** Pre-3.5.0 each card-face line + the HUD update were separate `sys.stdout.write` calls; signal-interruptible terminals could paint half the card before the HUD landed. Now one `write()` per repaint, mirroring the pattern at `render.py:923,933`.
- **`src/belote/a11y.py:1-20` (L2) — module docstring spells out the env-var invariant.** `BELOTE_A11Y` is read once at import; toggling mid-session has no effect on production code. Tests use `_refresh_enabled_from_env()`. No behaviour change, just documentation.
- **`src/belote/belatro/core/run_state.py:30-41` (L3) — `consumables` / `jokers` / `vouchers` mutation contract documented.** These lists are intentionally mutable; any future replay / ghost-run snapshot path must deep-copy at the snapshot boundary. No behaviour change.

### Performance

- **`scripts/benchmark.py` (M2) — three new micro-benchmarks for real hot paths.** `benchmark_legal_cards_cached` (warm-cache path; production gameplay reuses across 8 tricks), `benchmark_trick_scoring` (`trick_card_points`, called 16× per round), `benchmark_ai_legality_filter` (the legal-move filter step inside `AIPlayer.decide_card`). The pre-existing `benchmark_legal_cards` was clarified as the cache-cleared cold path.
- **`src/belote/scoring.py:439-477` (P1) — `trick_card_points` hoists boss-flag reads.** Same pattern `_calculate_base_points` (lines 489-493) uses. Saves 4 dataclass-attr lookups per card per trick. Sub-microsecond gain; the function was already micro-optimized at ~2μs per call. **Memoization rejected**: at 2μs × 16 calls = 32μs per round, the cache-key overhead would exceed the gain.
- **`src/belote/game.py:490-512` (P2) — `legal_cards` cache-key analysis documented.** Benchmark shows cold ~9μs / warm ~6μs; the 33% gap is dominated by key-build cost in `legal_cards()`, not lru_cache lookup. The key already uses small-int IDs (not Card objects) which is the minimal hashable surface. Slimming further would require caching `hand_ids` on the hand tuple itself, which isn't reachable without changing the hand representation. **Documented "no actionable optimization without larger refactor"** in the cache-impl docstring so a future audit doesn't re-investigate the same dead end.
- **`src/belote/belatro/core/scoring.py:70-89` (P3) — `ScoreAccumulator.update_state` profiling note.** cProfile of 10k calls shows `dataclasses.replace` is 65% of the cost — frozen-GameState invariant is load-bearing, so the replace cost stays. At ~19μs per event × ~25 events per round = ~0.5ms per round, the accumulator is well under the budget.

### Verified clean — agent claims that did NOT survive source verification

Catalogued so they aren't re-investigated next cycle.

- **"Belote/Rebelote not announced when partner holds K+Q"** (`game.py:863-876`) — The condition `state.belote_holders.get(trump) == state.turn` fires when the holder *plays* the K/Q, which is exactly when the announcement should fire. `state.turn` equals the holder at the moment of play regardless of partnership. **Correct as-is.**
- **"Capot false-positive under La Rupture on the 8th-trick announcement"** (`gameflow.py:215`) — `is_capot()` already routes through `compute_trick_winners()`, which honours Rupture for both the live-announce path and the final scoring path. The docstring at `scoring.py:317-326` explicitly calls this out. **Correct as-is.**
- **"AI `partner_hand` not cleared on undo path"** (`ai.py:79-92`) — `update_memory()` always clears `partner_hand` at line 104 and re-fills it from the current state, regardless of which earlier branch ran (new-round / undo / normal). **Correct as-is.**
- **"Negative-edition slot rollback on purchase failure"** (`run/shop.py:166-168`) — `_can_accept()` returns True unconditionally for Negative jokers, and `_apply_item` runs only after `spend_money()` succeeded. No failure path exists. **Correct as-is.**
- **"`boss.id == \"…\"` string-branching in pre-round setup"** — `grep -rn 'boss\.id\s*==' src/belote/belatro/` returns zero results. Cleaned up in the May 2026 audit. **Correct as-is.**

### Internal

- **Tests**: 568 → 592 (+24). Six new test files: `tests/belatro/test_consumables_ui.py` (7), `tests/belatro/test_run_summary.py` (3), `tests/test_input_eof.py` (5), `tests/belatro/test_event_bus.py` (3), `tests/test_declaration_tiebreak.py` (6). 0 existing tests modified.
- **Strict gates**: pytest 592/592 green.
- **Version markers bumped**: `pyproject.toml`, `src/belote/__init__.py`.
- **Docs bumped**: `CHANGELOG.md` (this entry), `README.md` "What's new in 3.5.0".

## [3.4.2] - 2026-05-11

Implements the deferred bug roadmap from 3.4.1's verification pass. **9 fixes land here** — 3 Critical (C1/C3/C4), 4 High (H1/H4/H5/H7), 1 architectural cleanup (H10), 1 dead-code deletion (M4). Adds 17 regression tests (551 → 568). The 3.4.1 entry catalogued these against the source; this entry implements them. Plan file at `/home/mrrobot/.claude/plans/wtf-these-were-verified-shiny-flute.md`.

### Fixed

- **`src/belote/ai.py:104-108` (C1) — AI no longer sees partner's hand under `hide_partner_hand`.** `AIMemory.update_memory()` now gates the `partner_hand` population on `not state.boss_modifiers.hide_partner_hand`. Under Le Fantôme Partenaire the human was blinded but the AI continued to play with perfect partner information — the boss's visibility cost was paid by one team only. The fix removes the perfect-information cheat; the AI still infers partner cards via `known_voids` and `played` like any real player. Regression test in `tests/belatro/test_dead_flag_fixes.py::test_ai_memory_respects_hide_partner_hand`.
- **`src/belote/gameflow.py:200-203` (C3) — Dix de Der announcement now uses the Rupture-aware winner.** Pre-3.4.2 the 8th-trick "Dix de Der (Team X)" line called raw `trick_winner_seat()` on `display_state.current_trick`, which ignores `boss_modifiers.no_consecutive_team_wins`. Under La Rupture the announcement could name a team that was *not* credited the +10 in scoring. Fix swaps to `compute_trick_winners(state, trump, is_sa, tricks=projected)[-1]` (same helper `scoring.py` uses), feeding `projected = completed_tricks + [display_state.current_trick]` since the 8th trick isn't yet pushed to `completed_tricks` when the announcement fires. Removes the now-unused `trick_winner_seat` import. Regression test in `tests/belatro/test_boss_modifiers_integration.py::test_dix_de_der_announcement_honors_rupture`.
- **`src/belote/ai.py:540-549` (C4) — `opp_trumps` no longer over-counts; TA total fixed.** The pre-3.4.2 formula `8 - sum(played trumps)` conflated "remaining trump anywhere" with "opponent trump", treating South's own hand and partner's visible cards as still in opponents' hands. The fix subtracts `my_trumps`, `played_trumps`, and `partner_trumps` from the total. Under Tout Atout every card is a trump and the total is `32`, not `8` — pre-3.4.2 the formula degraded to `8 - 0 = 8` always under TA because no card's `.suit` equals `Suit.TOUT_ATOUT`. Both regimes are now handled. Has the side effect of also fixing `my_trumps` under TA (used by `_score_leading_strategy` downstream). Regression tests in `tests/test_ai.py::test_opp_trumps_excludes_own_and_partner_hand` and `::test_opp_trumps_under_tout_atout_uses_32_total`.
- **`src/belote/belatro/items/jokers/contract.py` + `trick_timing.py` (H1) — 8 jokers now gate on team, not seat.** `LIdeologue`, `LeFanatique`, `LeDiplomate`, `LePatriote`, `LIllusionniste`, `LePremierSang` (both checks), `LeSergent`, `LExecuteur` were checking `event.winner == Seat.SOUTH` instead of `team_of(event.winner) == 0`. They silently no-opped when partner (North) took the relevant trick. Now consistent with the 3.2.0 fix that landed `LaSentinelle` and `LeDernierMot` on the same pattern. Five existing tests that asserted the broken behavior (`test_north_*_returns_none`) were rewritten to verify the new correct behavior — partner wins now fire the joker; opposing-team wins (EAST) are added as the new negative case. `LeSergent`'s "streak reset" semantics also shifted: an opposing-team trick now breaks the streak, not a partner-won one. Regression backstop in `tests/belatro/test_phase0_coverage.py::test_h1_team_aware_jokers_fire_on_north_partner_win`. **`LeRebelle` is intentionally not included** — the 3.4.1 catalogue flagged it as a probable audit hallucination; it is an `on_belote` joker, not on `on_trick_won`, and the seat-vs-team distinction there is a separate spec call deferred to a future cycle.
- **`src/belote/belatro/run/ante_themes.py` + `belatro/main.py:413-414` (H4) — TournoiAnte pays a real 50% of round payout.** `AnteTheme.on_blind_won` gains a `blind_payout: int` parameter (forwarded to base class and both subclasses). The call site at `belatro/main.py:412` snapshots `run.economy.money` immediately before `process_round_end` and computes `blind_payout = money_after - money_before` after all bonus paths (L'Avocat, `_bonus_money`, Le Puriste, L'Aristocrate) have run. TournoiAnte now does `add_money(max(1, blind_payout // 2))` — actually 50% of payout, with a $1 floor so blind payouts of 0 still pay something. Comment rewritten to match. Updated tests in `tests/belatro/test_phase3_meta.py` (CafeAnte test threads the new arg; TournoiAnte tests verify exact `payout // 2` math + the floor).
- **`src/belote/belatro/progression/save.py:97-101` (H5) — `load_profile` no longer loses starter unlocks.** Pre-3.4.2 the happy path read `data.get("unlocked_ids", [])`, defaulting to an empty list when the key was absent — wiping the Profile dataclass's `["le_classique", "le_courageux", "l_econome"]` starter unlocks for any save missing the key (legacy saves, manual edits, partial writes). The fix falls back to `Profile().unlocked_ids` when the key is missing; an explicitly empty `unlocked_ids: []` is honored unchanged (a player who has reset their unlocks stays reset). Two regression tests in `tests/belatro/test_collection_logic.py` lock both behaviors.
- **`src/belote/main.py:230-231` (H7) — stats line agrees with menu summary on ties.** Changed `won=(ns >= target and ns >= ew)` to `won=(ns >= target and ns > ew)` so the `update_stats_game` `won` flag aligns with `ui/menu.py:344`'s `winner = "NS" if ns > ew else "EW"`. On an exact tie at target, pre-3.4.2 the stats recorded a NS win while the visible summary said EW. Both regression tests in `tests/test_new_coverage.py` — one source-grep anti-pattern lock against `>=`, one semantic check on the formula.

### Internal

- **`src/belote/belatro/partner/partner_state.py:38-49` (H10, architectural)** — `equip_joker` signature widened to `equip_joker(self, joker: Joker, run: BelAtroRun | None = None) -> bool`. When `run` is provided, `joker.on_purchase(run)` fires after the slot append. No current partner joker defines `on_purchase`, so no behaviour changes today — this is forward-looking infrastructure. The catalogue called this "latent"; equipping through this path will now invoke purchase-time effects consistently with the main joker slot equip path. Note: `equip_joker` has zero callers in the current codebase (the shop path equips through a different surface), so this fix is doubly forward-looking. Three regression tests in `tests/belatro/test_partner_trust.py::TestEquipJokerOnPurchase`.
- **`src/belote/game.py::advance_turn` (M4) — dead code deleted.** Zero callers across `src/` and `tests/`. The function was a one-line `replace(state, turn=state.turn.next_seat())` helper that no live code used.
- **Tests**: 551 → 568 (+17). Five existing `test_north_*_returns_none` tests in `test_belatro.py` were flipped to assert the new team-aware behavior (these tests had encoded the H1 bug as a contract — they are not test regressions but contract updates).
- **Strict gates**: pytest 568/568, mypy 0 errors (76 source files), ruff 0 violations.
- **Version markers bumped**: `pyproject.toml`, `src/belote/__init__.py`.
- **Docs bumped**: `CHANGELOG.md` (this entry), `README.md` "What's new in 3.4.2", `DEVELOPMENT.md` baseline.
- **Still deferred**: **H2** (`LEgoiste` partner-trick nullification) was flagged as needing a spec decision in 3.4.1 and was not in any tier the user picked for 3.4.2 — the comment says "Partner's points are nullified" which reads as intent, so a fix would invert documented behavior. Stays on the deferred list pending a spec call. `LeRebelle` `on_belote` seat/team gating (noted above) is similarly deferred.

## [3.4.1] - 2026-05-11

Audit-verification-only release — **no code changes**. A fresh external LLM audit ("Comprehensive Audit Report — Belote CLI v3.4.0") produced 26 prioritized findings (4 Critical, 10 High, 12 Medium) plus a test-coverage section and a performance section. Direct verification against the source confirmed **7 real bugs** (3 Critical, 4 High), **1 architectural latent issue** (no current consumer but fragile for future work), and **1 disputed claim** that needs a spec call before any fix. **8 claims were false positives** under verification (intent inversion, defense-in-depth confused for bugs, or stale call-graph reading). Mediums spot-checked: 1 real (dead code), 4 false. The point of cutting a release for verification-only work is to (a) lock the false-positive catalogue against re-investigation next cycle and (b) record the confirmed-bug roadmap before any fixes land. Plan/verification file at `/home/mrrobot/.claude/plans/check-on-this-audit-polished-kite.md`. Test count, mypy, ruff results unchanged from 3.4.0 (no source code touched).

### Confirmed bugs — deferred to 3.4.2+

These were verified against current code and are real. None are fixed in 3.4.1; they are catalogued here so the next session has a vetted target list.

**Critical**
- **`src/belote/ai.py:104-108` (C1) — AI sees partner's full hand regardless of `hide_partner_hand`.** `AIMemory.update_memory()` unconditionally populates `self.memory.partner_hand` from `state.hand_of(partner)`. The boss flag `hide_partner_hand` (declared at `game.py:177`, set by Le Fantôme Partenaire at `belatro/run/boss.py:171`) is only read by display code at `belatro/main.py:291`, never by the AI memory path. Net effect: under Le Fantôme Partenaire the human is blinded to partner's hand but the AI continues to play with perfect partner information.
- **`src/belote/gameflow.py:196-198` (C3) — Dix de Der announcement uses non-Rupture-aware winner.** The announcement calls `trick_winner_seat()` directly; the La Rupture-aware helper `compute_trick_winners()` (defined at `game.py:756`, used by `scoring.py`) is the one that honours `boss_modifiers.no_consecutive_team_wins`. Under La Rupture the announced "Dix de Der goes to TEAM X" line can name a team that is not actually credited the +10 in scoring.
- **`src/belote/ai.py:533` (C4) — `opp_trumps` formula conflates "remaining trump" with "opponent trump".** Current line is `opp_trumps = 8 - sum(1 for c in self.memory.played if c.suit == trump)`. This counts trump still anywhere in unrevealed hands — including South's own hand (already computed as `my_trumps` on line 532) and partner's hand (visible at `self.memory.partner_hand`). The variable is then compared against `my_trumps` in `_score_leading_strategy`, so the over-count biases Hard AI's trump-coverage decisions when the AI itself is holding trump.

**High**
- **`src/belote/belatro/items/jokers/contract.py` + `trick_timing.py` (H1, partial) — 8 jokers still gate on `event.winner == Seat.SOUTH`.** 3.2.0 fixed La Sentinelle and Le Dernier Mot to use `team_of(event.winner) == 0`. The same anti-pattern survives in: `LIdeologue` (contract.py:21), `LeFanatique` (contract.py:45), `LeDiplomate` (contract.py:62), `LePatriote` (contract.py:81), `LIllusionniste` (contract.py:128), `LePremierSang` (trick_timing.py:26/30), `LeSergent` (trick_timing.py:46), `LExecuteur` (trick_timing.py:82). All silently no-op when North takes the relevant trick. (The audit also named `LeRebelle` but I could not find it among the South-only checks — likely a hallucinated joker name; verify before touching.)
- **`src/belote/belatro/run/ante_themes.py:73-76` (H4) — TournoiAnte bonus is not the advertised 50%.** Effect uses `run.economy.add_money(max(1, run.economy.bonus_per_round // 2 + 2))`. The comment claims "+50% bonus on top of whatever payout the round produced", but the formula is a flat function of `bonus_per_round` (the per-round flat-bonus economy field), not 50% of actual round payout. Either compute true 50% of the round delta or rewrite the comment.
- **`src/belote/belatro/progression/save.py:94` (H5) — `load_profile` loses default unlocks.** Line reads `unlocked_ids=data.get("unlocked_ids", [])`. The `Profile` dataclass default is `["le_classique", "le_courageux", "l_econome"]`. A saved profile missing the key (older saves, manual edits, partial writes) reloads with no unlocks. The exception branch correctly returns `Profile()` with defaults; only the happy path corrupts.
- **`src/belote/main.py:230-231` (H7) — Win operator mismatch on ties.** Main loop uses `won=(ns >= target and ns >= ew)`; menu summary at `ui/menu.py:344` uses `winner = "NS" if ns > ew else "EW"`. On an exact tie at target, main records a NS win while the visible summary attributes the round to EW.

### Architectural / latent

- **`src/belote/belatro/partner/partner_state.py:34-38` (H10) — `equip_joker` skips `on_purchase`.** The method simply appends to `self.jokers`; no `on_purchase()` hook is invoked. No current partner joker defines `on_purchase()`, so this is latent today — but any future partner joker with a purchase-time effect (a la `LeTraitre` in `corrupted.py`) will silently fail to fire when equipped through this path. Document or wire the hook before adding such a joker.
- **`src/belote/game.py:1007` (M4) — `advance_turn()` is dead code.** Defined, never called. Safe to delete.

### Needs spec decision before fixing

- **`src/belote/belatro/items/jokers/corrupted.py:56-62` (H2) — `LEgoiste` nullifies the entire partner trick.** On `event.winner == Seat.NORTH` the joker returns `JokerResult(add_chips=-event.card_points)`, where `event.card_points` is the FULL trick's card points (South's contribution included). The audit reads this as a bug (only partner's own contribution should be subtracted); the code comment reads "Partner's points are nullified", implying *intentional* full-trick nullification. Resolve which is canonical before changing the formula — and either way add a test that pins the intended behaviour.

### Verified clean — agent claims that did NOT survive source verification

Catalogued so they aren't re-investigated next cycle.

- **(C2) "No round-2 bid validation in `place_bid`"** — `place_bid` itself does not validate, but the human-input path filters the up-card suit out of the options menu at `ui/prompts.py:132-135`, and the AI path uses `exclude=forbidden` at `ai.py:137`. Defense-in-depth gap (a programmatic caller could pass a bad bid), not a live bug.
- **(H3) "`LeFou` fallback is dead code"** — `tarots.py:119` checks `if last_id and last_id != self.id`. `last_consumable_id` defaults to `None` and `getattr(item, "id", None)` can also set it to `None`, so the fallback fires on the first consumable of a run and on self-copy attempts. Live code.
- **(H6) "Signal handlers skip `finally` and lose stats"** — `main.py:127-129` handler does call `sys.exit(0)`, which bypasses the `finally`. But `flush_stats()` is also invoked at `main.py:160` (quit path) and `main.py:235` (game-over). The data-loss window is narrow (SIGINT before any flush in the same session). Cosmetic at best.
- **(H8) "`zip(..., strict=False)` causes silent data loss in scoring"** — `winners` at `scoring.py:461,498` is produced by `compute_trick_winners(state, ...)`, which is exactly one entry per completed trick by construction. The length invariant holds; `strict=False` is defensive noise, not a live bug.
- **(H9) "`_CARD_TO_ID[c]` will KeyError on BelAtro jokers"** — `_CARD_TO_ID` is built from `make_deck()` (32 standard cards). BelAtro jokers are `Joker` objects living in `state._joker_state`, never inserted into `hand`. No reachable code path produces the KeyError.
- **(M2) "Frozen `GameState` contains mutable `_rng`"** — `_rng` is declared with `field(default_factory=random.Random, compare=False, repr=False)` — the same documented pattern used for `_joker_state` (see comment at `game.py:214-217`). Intentional; the contract is "always rebuild via `dataclasses.replace`".
- **(M8) "`card in self.memory.partner_hand` is always False"** — `partner_hand` is populated at `ai.py:107-108` during PLAYING/SCORING phase. The check at line 660 is live and prevents double-scoring visible partner cards.
- **(M12) "`mult == float(int(mult))` float precision bug"** — Intentional optimisation in `belatro/core/scoring.py:254`: when the multiplier is exactly integral, take the lossless integer-multiplication path; else accept float multiplication. Correct logic.

### Audit calibration notes (for the next pass)

The audit's overall scaffolding (file:line citations, severity tiers, action plan) was well-presented but had a recurring failure mode: **flagging "suspicious-looking" patterns without verifying behaviour in context**. Concrete recurring misses worth feeding back to the auditing model:

1. **Defense-in-depth confused with bugs** (C2, H8, H9). When the audited line lacks an obvious check, the audit should trace one hop up the call graph before declaring "no validation". In all three cases the invariant is enforced at the caller.
2. **Intent inversion** (H2, M2, M12). When code is paired with a comment that describes the exact behaviour the audit flags as wrong, that's evidence of intent, not a bug. Reading the adjacent comment before flagging would have caught these.
3. **Self-cancelling dead-code claims** (H3). The audit claimed "`last_consumable_id` is always set before `use()` is called". True — but it can be set to `None`, and the consumer's guard is `if last_id and ...`. Surface-level static reasoning without tracing the guard.
4. **Headline metrics with no numbers**. The "Current Health" table lists Tests / Lint / Types / Version rows with no values. The version row is checkable; the others were left blank, which makes the table cosmetic.
5. **Joker name drift** (H1). `LeRebelle` appeared in the South-only list but is not among the actual offenders. Probable hallucination.

### Internal

- **No source code touched.** Test count, mypy strictness, ruff cleanliness all unchanged from 3.4.0: pytest 551/551, mypy 0 errors (76 files), ruff 0 violations.
- **Version markers bumped**: `pyproject.toml`, `src/belote/__init__.py`.
- **Docs bumped**: `README.md` "What's new in 3.4.1" section, `DEVELOPMENT.md` baseline.
- **Roadmap for 3.4.2**: the 7 confirmed bugs above (C1, C3, C4, H1×8, H4, H5, H7) plus the H10/M4 cleanups. Tier 1 (C1/C3/C4) closes the AI-fairness gap; Tier 2 (H1/H4/H5/H7) closes the remaining verified issues.

## [3.4.0] - 2026-05-10

Audit + endless-mode reliability + HUD polish release. A fresh three-agent codebase pass (classic engine / BelAtro layer / UI + I/O) produced ~80 candidate findings. Direct verification against the source rejected ~95% as false positives or by-design patterns. The five surviving issues plus two **new** bugs uncovered during follow-up verification of endless mode and classic game flow are fixed here. Two HUD features land alongside (joker pip strip with edition glow, synergy tooltip, polished trust bar). 551 tests passing (up from 549), ruff and mypy strict still clean. Plan file at `/home/mrrobot/.claude/plans/bug-hunt-code-performance-fizzy-summit.md`.

### Fixed

- **`src/belote/belatro/engine/round_driver.py` (A1, HIGH)** — `BidMadeEvent` was emitted twice for the winning bid on every coinche path (player coinche → AI surcoinche, AI partner coinche, boss `auto_coinche` for EW *and* NS takers, and the `start_coinched` deck mod). Both emits ran `on_bid` joker handlers — once with `coinche_level=0`, then again with the resolved level — so any `on_bid` joker that accumulates per event was silently invoked twice for the same bid (Le Passeur and the contract-injection path were both vulnerable, future on_bid jokers more so). The fix adds a `re_emit: bool = False` field to `BidMadeEvent`; the post-coinche refreshes pass `re_emit=True`, and `ScoreAccumulator.update_state` skips `_fire_jokers("on_bid", ...)` for re-emits while still updating `joker_state["contract"]` so the HUD and contract-aware logic stay in sync. Regression test in `tests/belatro/test_round_driver.py::test_bid_made_event_does_not_double_fire_on_bid_under_auto_coinche` (registers a counting `on_bid` joker under L'Avocat and asserts no fire carries `coinche_level > 0`).
- **`src/belote/belatro/core/run_state.py::enter_endless` (E1, HIGH)** — Pre-3.4.0, accepting the "Continue into Endless Mode? (Ante 9+ scales ×2.2)" prompt left the run at `(ante=8, blind_index=2, endless_ante_offset=0, endless=True)`. The next `_play_blind` therefore *replayed* the Ante 8 Boss Blind at the SAME base target before the ×2.2 scaling kicked in on the second cycle — the prompt's promise of "Ante 9+ scales" was violated for one full round. The fix bumps `endless_ante_offset` to `max(offset, 1)` and resets `blind_index = 0` inside `enter_endless`, so the first endless round is Ante 8 Small Blind × 2.2 as advertised. Regression test in `tests/belatro/test_phase3_meta.py::test_enter_endless_advances_into_first_scaled_cycle`.
- **`src/belote/main.py` classic game-over branch (E2, HIGH)** — `apply_round_score` (scoring.py:952-953) intentionally keeps `phase=Phase.DEAL` when both teams reach `target` AND the round ended in a tie — Belote's tie-breaker rule. The classic main loop then re-checked `ns >= target or ew >= target` and unconditionally forced `phase=Phase.GAME_OVER`, overriding the scoring layer's intent: tie-breakers never played, the game just ended on the first round any team crossed target even if the score was exactly even. Fixed by replacing the redundant re-check with `if state.phase == Phase.GAME_OVER:` — the scoring layer is the single source of truth, and the unused `dataclasses.replace` import is removed.
- **`src/belote/input.py::_UnixKeyReader.restore` (A2, MED)** — `termios.tcsetattr` ran without exception handling. On a dropped SSH session, broken pipe, or a permission glitch it raised and left the host shell in raw/no-echo mode (the parent terminal would no longer echo keystrokes after the game crashed out). The call is now wrapped in `contextlib.suppress(termios.error, OSError)` and `_restored` is set regardless, so a follow-up restore call from `__exit__` after a prior raise is a no-op.
- **`src/belote/belatro/ui/shop.py` selection clamp (A3, MED)** — After reroll the index clamp was `min(self.selected, len(self.shop.inventory))`, which allows `selected == len(inventory)` — out-of-bounds for the very next render's `inventory[self.selected]`. The buy-path guard at the same site already used the correct `max(0, len(...) - 1)` form. Fixed to match.
- **`src/belote/ui/prompts.py::prompt_card` dead code (A5, LOW)** — The trailing `return None, state` after the `while True:` loop was unreachable (every match arm either continues or returns inside the loop). Replaced with an explicit `raise AssertionError("…")` so a future change that lets the loop fall through fails loud rather than silently returning a sentinel.

### Added — UI/HUD polish

- **`src/belote/belatro/ui/hud.py::render_joker_pip_strip` (B.3)** — Row-1 strip of 5 joker slots, each rendered as a 4-cell pip `[Xx ]` (or `[Xx*]` when the joker is in an active synergy pair). Empty slots paint as dotted `[··]` so the player sees their capacity at a glance. Edition support: `F` Foil → bright cyan, `H` Holo → magenta, `P` Polychrome → pink-violet, `N` Negative → reverse-video. The shortcode is `Joker.shortcode` — a new class property that returns the joker's manual `_shortcode_override` if set, else the first two letters of `name` upper-cased. New jokers inherit a sensible default with no extra plumbing. Hidden under Le Brouillard's `hide_hud` like the rest of the BelAtro HUD.
- **`src/belote/belatro/ui/hud.py::render_synergy_tooltip` (B.4)** — When at least one synergy pair is active, prints a green-pip line below the score line describing the synergy (e.g. *"♦ Coinched Tout-Atout wins ramp the streak multiplier"*). Up to two synergies render on consecutive rows; further matches collapse to a `+N more synergies` line. `_SYNERGY_PAIRS` widened from `tuple[id_a, id_b]` to `tuple[id_a, id_b, description]`; existing `detect_synergies()` callers stay compatible via a 2-tuple shim, and the new `detect_synergies_full()` returns the description too. `validate_synergy_ids()` was updated to walk the new 3-tuple format.
- **`src/belote/belatro/ui/trust_bar.py` polish (B.5)** — Four-tier colour ramp (cramoisi ≤2 / orange 3–4 / gold 5–7 / emeraude 8–10) replacing the previous three-tier red/gold/green. Leading tier glyph rendered from `_TIER_GLYPHS` (`✗ ♡ ♥ ♦ ★`) — Loyal/Mécène (tier ≥3) glyphs are bolded so the top tiers stand out. All four-tier transitions reuse `TrustTrack.tier`'s existing bucketing — no trust-math change.
- **`src/belote/belatro/items/base.py::Joker.shortcode`** — New class property used by the pip strip. Subclasses can set `_shortcode_override = "Cs"` for a custom 2-char tag; otherwise the property derives one from `name`/`id`. No subclass changes required for the existing roster — defaults are good enough.

### Verified clean — agent claims that did NOT survive source verification

These were flagged by the audit agents but verification against the current code showed they are either correct behaviour, by-design patterns, or already-handled invariants. Catalogued so they aren't re-investigated next cycle.

- **`game.py:562` "Tout Atout legal_cards downgrade" claim** — The `risers or tuple(my_suit_cards)` fallback is correct Belote: if you cannot rise within the lead suit, you may play any card *of that suit*. `my_suit_cards` is your hand filtered by lead suit, not played cards. **Not a bug.**
- **`game.py:947-955` "L'Anarchie unseeded `_rng`"** — The default `_rng = field(default_factory=random.Random)` IS unseeded, BUT `start_round()` at `game.py:302` always sets `_rng=rng` from the driver's seeded RNG before any round logic runs. By the time L'Anarchie consumes it at line 955 the seeded instance is in place. **Clean.**
- **`ai.py:73-92` "AI memory `last_voids_key` reset coverage"** — Both reset branches (new-round at line 73-78 and regression-detected at line 88-92) reset `last_voids_key` alongside the other three fields. **Clean per documented invariant.**
- **`run/shop.py:166-168` "Negative-edition double-fits a full inventory"** — The `joker_slots += 1; jokers.append()` sequence is the documented Negative design (see `_can_accept` docstring at line 145-147). Net effect: slot pool grows with the joker. **Not a bug.**
- **`round_driver.py:95-99` "Le Traître sabotage flag duplication"** — The guard `not state.boss_modifiers.agent_double_active` at line 95 and the population check `not state._joker_state.get("agent_double_tricks")` at line 120 prevent the double-population the agent feared. **Clean.**
- **`run_state.py:66` "`contract_levels` not reset per run"** — `BelAtroRun.contract_levels` is `field(default_factory=dict)`; each new run instance starts fresh. Within a run it intentionally accumulates so planet rewards persist. **By design.**
- **`registry.py:128-135` "`register_all_items` idempotency hole"** — The double-guard `_registered and registry.jokers` is *deliberate* per the docstring at line 130-133, to support test-suite registry resets. **Working as intended.**

### Internal

- **Tests**: 549 → 551 (+2 — A1 regression + E1 regression). Ruff and mypy strict still clean across all 76 source files.
- **Strict gates**: pytest 551/551, mypy 0 errors (76 files), ruff 0 violations.
- **`BidMadeEvent`** gained a `re_emit: bool = False` field. Existing call sites unchanged; only the three post-coinche refresh sites in `round_driver.py` opt into `re_emit=True`. Backward-compatible.
- **`_SYNERGY_PAIRS`** widened to 3-tuples. `detect_synergies()` keeps the historic `list[tuple[str, str]]` return; `detect_synergies_full()` exposes the description.
- **Deferred to a future release**: the larger render-pipeline features from the plan — score gutter (B.2) and trick-lane compass animation (B.1) — were scoped out because they touch `ui/render.py`'s line-assembly and vertical-centering logic, where a regression risks the classic and BelAtro display flows. They remain on the roadmap but want a dedicated session.

## [3.3.4] - 2026-05-10

Portability release — removes all terminal-bell / sound code, which was triggering SIGSYS ("Bad system call") on Alpine 23 (musl libc) the moment the first trick completed in classic Belote mode. BelAtro mode was unaffected on the same Alpine box (it never imported `play_sound`), and Kubuntu / Lubuntu 24.10 / 25.10 (glibc) were unaffected in either mode. Rather than guard the BEL writes behind a libc-detection flag, the entire sound subsystem is removed: classic Belote and BelAtro now share the same "no bells" baseline. 549 tests still passing, ruff and mypy strict still clean.

### Removed

- **`src/belote/ui/announce.py::play_sound`** — terminal-bell helper (writes `\a` bytes for `trick` / `belote` / `declaration` / `chute` / `capot` events). Was called from five sites in `gameflow.py` (post-trick, capot, first-trick declarations, Belote announcement, chute on failed contract); all five call sites are deleted along with the function. BelAtro's `engine/round_driver.py` never imported it, so no BelAtro behaviour changes.
- **`src/belote/ui/announce.py::is_muted` / `toggle_mute`** — wrappers around `AUDIO.is_muted()` / `AUDIO.toggle_mute()`. Re-exports dropped from `src/belote/ui/__init__.py::__all__`.
- **`src/belote/context.py::AudioManager` + the `AUDIO` singleton** — process-wide mute state holder. `TerminalContext` and the `TERMINAL` singleton are kept (they back the terminal-size cache used elsewhere).
- **`src/belote/input.py::Key.MUTE` + the `m` / `b"m"` key bindings** — `M` no longer triggers a special key event in either `_UnixKeyReader` or `_WindowsKeyReader`; it now falls through to `Key.CHAR` like any other letter (Belote has no other meaning for `M`).
- **Three `case Key.MUTE: toggle_mute()` branches in `src/belote/ui/prompts.py`** (card prompt, bid prompt, rules viewer) — deleted along with the `from .announce import is_muted, toggle_mute` import.
- **Two `case Key.MUTE: toggle_mute()` branches in `src/belote/ui/menu.py`** (AI config submenu, main menu) — deleted along with the `from .announce import toggle_mute` import.
- **`[M] Toggle Sound Effects` line from the in-game help screen** (`src/belote/ui/prompts.py::show_help`) — plus the live `(Currently: ON/OFF)` status line that reflected `is_muted()`.
- **`tests/test_gameflow.py`** — the obsolete `unittest.mock.patch("belote.gameflow.play_sound")` mock inside `test_run_play_8_tricks`'s `ExitStack` is gone; the test still passes (the underlying `display` / `patch_trick_card` / `announce` / `prompt_card` mocks remain).

### Internal

- **Tests**: still 549 passing.
- **Strict gates**: pytest 549/549, mypy 0 errors (75 files — `context.py` lost one class but kept the module), ruff 0 violations.
- **Unused-import sweep**: `green_fg` dropped from `src/belote/ui/prompts.py` imports (only the deleted `sound_status` line used it).

### Why drop the bell instead of guarding it on musl

`play_sound` only writes BEL (`\a`) bytes to stdout; writing those bytes is just `write(2)` and doesn't itself trigger SIGSYS on any sane libc. Whatever the precise mechanism on Alpine 23 (terminal-driver quirk, blocked downstream ioctl, or musl-specific signal-frame interaction with the existing `signal.signal(SIGINT/SIGTERM)` registration in `main.py:132-133`), the simplest and most robust answer is to stop writing the bell at all. Modern terminal emulators on every tested distro either ignored or visually-flashed the bell — no user-meaningful audio was being produced. The mute toggle exists only to suppress those flashes; with the bell gone, the toggle is dead weight.

## [3.3.3] - 2026-05-10

Audit-of-audit release — a fresh three-agent codebase pass (classic engine / BelAtro mode / tests + UI) produced ~50 candidate findings. Verification cut that to **3 real fixes** plus **3 net-new invariant test suites** for properties the prior 3.3.x cycles silently relied on. ~14 rejected claims are catalogued at the bottom of this entry so they aren't re-investigated next cycle. 549 tests passing (up from 537), ruff and mypy strict still clean. Plan file at `/home/mrrobot/.claude/plans/bug-hunt-code-performance-tingly-barto.md`.

### Fixed

- **`src/belote/game.py::sort_hand` (F1)** — Under the Tout Atout contract every card should sort by the trump rank ladder (`J > 9 > A > 10 > K > Q > 8 > 7`). Pre-3.3.3 the sort key gated `_TRUMP_RANK_IDX` on `c.suit == trump`, which is *always* false when `trump is Suit.TOUT_ATOUT` because `Card.suit` is one of `SPADES/HEARTS/DIAMONDS/CLUBS` (TA is a contract-level marker, not a card suit). Result: the South hand displayed in the non-trump order whenever the player bid or held TA. Fix: explicit `all_trump = trump is Suit.TOUT_ATOUT` branch in `sort_key`. Also extends `_SUIT_IDX_CACHE` to pre-build the TA entry so the hot path stays cache-resident. UI-only — no scoring impact. Regression test in `tests/test_game_logic.py::test_sort_hand_uses_trump_ladder_under_tout_atout`.
- **`src/belote/belatro/main.py::_play_blind` (F2)** — Boss assignment on the boss blind now draws from `self.run._get_rng().choice(ALL_BOSS_MODIFIERS)`. Pre-3.3.3 the function imported `random` inline and called `random.choice()` on the module-level RNG — the same class of bug the 3.2.0 release fixed for shop generation and the three RNG-using tarots (`LeJugement` / `LaPretresse` / `LeFou`). Boss assignment was the last unseeded RNG site in the BelAtro round flow; ghost-run reproducibility now observes the same boss for the same seed regardless of prior process-wide RNG state. Regression tests in `tests/belatro/test_belatro.py::TestBossSelectionDeterminism` (behaviour + source-grep against the anti-pattern).
- **`src/belote/belatro/items/tarots.py::LeJugement` (F3)** — The tarot's description promises *"a random Common Joker"* but the implementation drew from `registry.get_available_jokers(run.profile)` — the full unlocked pool across all rarities. Late-run players with Rare/Legendary jokers unlocked could roll Legendary off this tarot, which is strictly stronger than advertised and mis-prices the consumable. Fix: filter the pool to `getattr(v, "rarity", Rarity.COMMON) == Rarity.COMMON` before the choice; existing empty-pool guard handles the (rare) case where no Commons are available. Regression tests in `tests/belatro/test_belatro.py::TestLeJugementRarity`.

### Added — invariant tests

These are the three test suites the 3.3.x bug cycle has been silently asking for. Each one would have caught at least one prior bug from below.

- **`tests/test_properties.py` — scoring conservation per contract (T1)** — Three new tests drive seeded full rounds and assert `table_taker_pts + table_defender_pts == 162` (normal) / `258` (Tout Atout) / `130` (Sans Atout). Plus a card-consumption invariant: after a full round every hand is empty and exactly 8 tricks were recorded. Would have caught the L'Anarchie belote-zero (3.3.1) and the La Rupture HUD divergence (3.3.1/3.3.2) years earlier had it existed at the time. Also includes a small `_drive_full_round` helper for future scoring-pin tests (handles the round-2-only TA/SA bidding flow).
- **`tests/test_replay.py` — replay round-trip + seeded determinism (T2)** — Two new tests: (a) record each played card from a seeded run, replay them into a fresh `GameState` built from the same seed, assert identical final state across `team_scores` / `completed_tricks` / `belote_tracker` / `belote_announcer` / `last_trick_winner`; (b) drive the same seed twice and assert identical 32-card sequences. Pins the determinism promise the 3.3.1 AI-RNG fix and the 3.3.2 replay-RNG fix established.
- **`tests/belatro/test_hud_synergy.py` — solo-half pair test (T3)** — The existing file already exercises the "both halves present → badge fires" direction. The new test adds the negative direction: for each pair in `_SYNERGY_PAIRS`, feed a single half into `detect_synergies` and assert no badge fires. Trip-wire for any change to the synergy matcher that accidentally promotes lone jokers to a pair badge.

### Internal

- **Tests**: 537 → 549 (+12 — 3 F-regressions + 4 T1 + 2 T2 + 1 T3 + extra cross-suit / TA sanity assertions).
- **Strict gates**: pytest 549/549, mypy 0 errors (76 files), ruff 0 violations.
- **`_SUIT_IDX_CACHE` widened**: now pre-builds for `(None, Suit.TOUT_ATOUT, *_SUITS_ORDER)` instead of just `(None, *_SUITS_ORDER)`. Removes a per-render cache miss under TA but is otherwise a no-op.

### Rejected — claims catalogued (so they aren't re-investigated)

The three Explore agents that drove this audit surfaced many plausible-sounding findings; the ones below fell apart on direct read of the current code and are documented here to save the next cycle from re-investigating them.

**Already fixed in 3.3.1/3.3.2 (agents read against stale priors):**
- "`_hard_play` returns `legal[0]` under Sans Atout" — fixed in 3.3.1.
- "`AIPlayer.__init__` constructs unseeded `Random()`" — fixed in 3.3.1; `analyze_round` followed in 3.3.2.
- "`AIMemory.last_voids_key` not reset on mid-round undo" — fixed in 3.3.1.
- "Live HUD diverges from final score under La Rupture" — fixed in 3.3.1 (`compute_trick_winners`) + 3.3.2 (`is_capot(tricks=…)`).
- "Belote/Rebelote silently zeroed under L'Anarchie when trump rotates" — fixed in 3.3.1 via `GameState.belote_announcer`.

**Interpretive, not bugs:**
- "`ScoreAccumulator` applies edition before partner-tier scaling, so Holo isn't tier-scaled" — by design. Editions ride along once per joker trigger; tier extras re-apply the *base* joker result. Otherwise an elite-tier Polychrome partner joker would compound geometrically.
- "Libra's `coinche_multiplier=1.0 × event.coinche_level` makes coinche pay ×5, not ×4" — description is ambiguous; the math matches the Phase 3 design doc (`+1 Mult per coinche level on success`).
- "Pluto `capot_bonus = 48` is additive to 252 = 300" — that *is* the advertised behaviour.
- "`_TIERCE_LIKE` has title-case dead entries (`Tierce`/`Quarte`/`Quinte`)" — `decl.kind` is always lowercase (`sequence`/`carre`/`belote`/`rebelote`), so only `"sequence"` ever matches. The joker fires correctly on every Tierce/Quarte/Quinte; the title-case entries are dead but harmless.
- "QuinteRoyale arms on `event.points >= 100` instead of declaration length" — Quinte = 100 pts in classic Belote and `event.points` is the unmodified `get_declaration_points([...])` computed inline at emit time; the proxy is sound.
- "`EventBus.emit` has no try/except around handlers" — broad-except would mask real bugs in joker/accumulator code. Current handlers are internal; an exception should surface in dev/test rather than be swallowed.
- "Negative-edition jokers still pay the 1.5× shop markup" — design: Negative is the rarest edition and grants a permanent +1 joker slot.
- "Boss `random.choice` doesn't respect profile unlocks" — there is no boss-unlock system in the data model; all bosses are always available by design.
- "ToutStreak / LeSergent reset semantics don't match flavour text" — joker authoring judgment call. Behaviour matches the registry definition.

**Already addressed by existing code:**
- "`ScoreAccumulator.update_state` clones `_joker_state` per event" — intentional shallow copy; `test_joker_state_only_contains_scalar_values` pins the scalar invariant.
- "Registry duplicate-ID overwrites silently" — fixed in 3.2.0; all four `register_*` methods assert same-class re-registration.
- "`_SUIT_IDX_CACHE` missing TOUT_ATOUT" — addressed as part of F1 (now in the cache).

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
