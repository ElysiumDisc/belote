# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
