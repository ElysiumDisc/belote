# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
