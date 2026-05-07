# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
