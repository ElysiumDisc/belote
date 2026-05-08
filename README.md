# Belote – 4-Player Terminal Card Game

Complete implementation of the French card game Belote for the terminal, with a full-screen green felt table and full card graphics at compass positions (N/W/E/S).

## What's new in 3.1.0

- **Bug fixes** — HUD running-total no longer drifts under multi-boss combos (`Les Clubs Bannis + Le Roi Mort` style: pre-3.1.0 the rank-zero recompute silently overwrote the `ban_clubs` zeroing). `Shop.buy_item` no longer charges money when consumable slots are full — the "Slots full — sell first" banner now fires before any spend.
- **TierceForge wired up** — the voucher shipped in 3.0.0 with a working backend but no UI caller; the feature was unreachable. The shop now shows a "Forge ×N/3" tile when the voucher is owned, opens a numbered planet picker on Enter, and confirms the level-up via a banner.
- **Performance** — `score_round` and `apply_round_score` no longer re-walk the trick list (~16 fewer `trick_winner_seat` calls per round). The per-event `copy.deepcopy` in `ScoreAccumulator.update_state` is gone (~20 deepcopies/round saved); replaced with a shallow `dict(...)` plus a scalar-only invariant test that locks the contract. Hard-AI's `_score_card_play` precomputes hand suit counts and trump tallies once per turn instead of per candidate.
- **Cleanup** — the `modifier_patch` underscore-prefix shim is gone (23 boss `apply()` methods rewritten to use unprefixed field names; the `getattr(state, "_X", False)` anti-pattern is now locked against by a regression test). `slots=True` added to `Statistics`, `SessionStats`, `ScoreAccumulator`. Bare `except Exception:` in key-press parsing narrowed; `print → logging` in stats.
- **Test coverage** — 525 tests (up from 510). Strict gates still clean: pytest 525/525, mypy 0 errors, ruff 0 violations.

## What's new in 3.0.3

- **Full-codebase audit** — three-agent pass over the classic engine, BelAtro content wiring, and perf / code-quality hotspots (~7,100 LOC). Headline: engine is rule-correct against canonical French Belote; BelAtro content matrix is **93/93 wired** (21 bosses, 8 planets, 36 jokers, 4 editions, 12 vouchers, 12 tarots). Prioritized findings list (1 P0 functional, 2 P0 perf, 5 P1, 7 P2) tracked for follow-up cuts; implementation landed in 3.1.0.
- **Doc accuracy** — README boss-count corrected (18 → 21; 3.0.0 added Le Sauvage / L'Iconoclaste / Le Mime), and two stale `(435 tests)` references bumped to 510 to match the figure already present elsewhere in the file.

## What's new in 3.0.2

- **Replay analyzer + Ghost run wired up** — both shipped in 3.0.0 as code modules but were never called from the running game. Now opt-in behind `BELOTE_REPLAY=1` (post-round Hard-AI comparison) and `BELOTE_GHOST=1` (per-run JSON dump to `~/.local/share/belote/ghosts/`). See DEVELOPMENT.md › Optional Runtime Flags.
- **Performance** — `score_round()` now caches per-trick winners once instead of recomputing them in each boss-modifier helper (2-3× walks → 1× walk per round). `register_all_items()` is now idempotent so test setup no longer re-walks every items module per `BelAtroRun`. Bidding's special-bid path (TA / SA) hoists `_suit_lengths` out of the per-difficulty branches.
- **Defensive pin** — every entry in `ALL_BOSS_MODIFIERS` is now asserted to actually toggle a `BossModifiers` field via `.flags()`. Catches typo'd `state.patch("_misspelled", True)` keys at test time rather than letting the boss silently no-op.
- **Test coverage** — 525 tests (up from 509).

## What's new in 3.0.1

- **Bug fixes** — `play_card()` running total now honours `aces_zero` / `jacks_zero` (Le Sauvage / L'Iconoclaste); the screen-reader trick-winner pts are now boss-aware; the HUD synergy registry no longer references nonexistent joker IDs; the AI void-cache key is now reset across rounds.
- **Test coverage** — 509 tests (up from 489): HOLO/POLYCHROME editions, multi-boss composition (`separate_scoring × zero-flag`), a11y boss-aware pts, synergy registry self-check.

## What's new in 3.0.0

- **Endless mode** — beat Ante 8 in BelAtro and the run offers a continuation: targets scale ×2.2 per ante and a furthest-ante leaderboard tracks how deep you go.
- **Joker editions** — Foil (+50 chips), Holo (+10 mult), Polychrome (×1.5 mult), Negative (extra slot) randomly stamp shop jokers.
- **Three new boss blinds** — Le Sauvage (Aces = 0), L'Iconoclaste (Jacks = 0, even trump-J), Le Mime (Declarations = 0).
- **Achievements** — six classic-mode milestones tracked across sessions.
- **Colorblind palette** + **screen-reader hints** (`BELOTE_A11Y=1`) for accessibility.
- **Replay analyzer** — module added (post-round Hard-AI comparison). User-facing wiring landed in 3.0.2 behind `BELOTE_REPLAY=1`.
- **Ghost run recording** + **run summary log** — modules added (serialize a run / append per-run JSON). Run-summary fires automatically; ghost-run user-facing wiring landed in 3.0.2 behind `BELOTE_GHOST=1`.
- **Bug fixes** — Capot under Sans Atout / Tout Atout now uses the correct base (220 / 348, not 252); The Sun and Libra planets actually do something now; AI void inference no longer mis-flags voids under Le Républicain wild 7/8.

## BelAtro Expansion

**BelAtro** is a major roguelite expansion inspired by *Balatro*. Play through 8 Antes of escalating difficulty, build a deck of powerful Jokers, and use Tarot cards and Planets to break the game! 

**BelAtro is now fully integrated into the main menu!** Just launch `belote` and select it from the top of the list.

### BelAtro Quick Start
```bash
# Play using the integrated launcher (recommended)
belote

# Or play the new Roguelite mode directly
belatro
```

### Starting Decks (All Fully Implemented)
| Deck | Special Rule |
|---|---|
| Le Classique | Standard 32-card baseline |
| **Le Républicain** | 7s & 8s are wild — play them on any trick. +5 chips per 7/8 your team captures |
| L'Aristocrate | All four Aces start Gold Sealed (+cash) |
| Le Joueur | Start $14 — Boss Blind every 2 antes |
| **L'Ermite** | Starts with **La Sentinelle** Joker (×3 Mult if Trump Jack never leaves hand) |
| **Le Vétéran** | Start with a random **Planet** card pre-applied to level up a contract |
| **Le Flambeur** | Starts with **L'Aventurier** Partner Joker (×2 Mult if both win ≥3 tricks) |
| L'Anarchiste | Start $19 — Corrupted pool visible |

### Notable Vouchers
| Voucher | Effect |
|---|---|
| **Le Carnet** | See partner's full hand every round. +1 Mult each time South wins a trick |
| La Voûte | Earn $1 interest per $5 held, up to $5/round |
| La Double Donne | +1 Joker slot |
| **La Télescope** | +$1 flat bonus after every round |
| **Le Grimoire** | Shop always stocks at least one Tarot card |
| **Les Cartes Dorées** | +1 interest rate and +5 interest cap permanently |
| **La Balance** | Your team wins automatically on a card-point tie |
| La Surcoinche | Unlocks the Surcoinche contract *(unlockable)* |

## Showcase

### Main Menu
```text
  ⢠⣴⣶⣶⣶⣄
  ⣿⣿⣿⣿⣿⣿⣦
 ⢰⣿⣿⣿⣿⡿⠟⠁⣠⣴⣶⣦⠄
 ⢸⣿⣿⠟⠉⣠⣴⣿⣿⣿⠟⠁⣠⣾⣿⣦⡀
  ⠉⣀⣴⣾⣿⣿⣿⠟⢁⣤⣾⣿⣿⣿⣿⣿⡆
⢀⣤⣾⣿⣿⣿⡿⠛⢁⣴⣿⣿⣿⣿⣿⣿⣿⠟⠁⡀
⢼⣿⣿⣿⡿⠋⣀⣴⣿⣿⣿⣿⣿⣿⣿⡿⠉⣠⣾⣿⡆
⠘⢿⡿⠋⣠⣾⣿⣿⣿⣿⣿⣿⣿⡿⠋⢀⣾⣿⣿⠟⢁⣀
  ⣠⣾⣿⣿⣿⣿⣿⣿⣿⣿⠏⢀⣴⣿⣿⣿⠋⢠⣾⣿⣷⣦⡀
  ⢻⣿⣿⣿⣿⣿⣿⣿⠟⢁⣴⣿⣿⣿⡿⠁⣰⣿⣿⣿⣿⣿⣿
   ⠹⢿⣿⣿⣿⡿⠋⣠⣾⣿⣿⣿⠟⢀⣼⣿⣿⣿⣿⣿⣿⡟
     ⠉⠉⠉ ⢾⣿⣿⣿⣿⠋ ⠚⠛⠛⠛⠛⠛⠛⠁
          ⠉⠉⠉

                       (
                        )     (
                 ___...(-------)-....___
             .-''       )    (          ''-.
       .-'``'|-._             )         _.-|
      /  .--.|   `''---...........---''`   |
     /  /    |           BelAtro           |
     |  |    |       > Start Game <        |
     |  |    |      AI:     < Hard >       |
     |  |    |      Target: < 1000 >       |
     |  |    |     Speed:  < Normal >      |
     |  |    |  Theme:  < Classic Green >  |
     |  |    |       Rules & History       |
      \  \   |         Statistics          |
       `\ `\ |            Quit             |
         `\ `|                             |
         _/ /\                             /
        (__/  \                           /
     _..---''` \                         /`''---.._
  .-'           \                       /          '-.
 :               `-.__             __.-'              :
 :                  ) ''---...---'' (                 :
  '._               `''...___...--''`              _.'
 jgs \''--..__                              __..--''/
     '._     '''----.....______.....----'''     _.'
        `''--..,,_____            _____,,..--''`
                      `'''----'''`
```

### Card Graphics
```text
┌────┐  ┌────┐  ┌────┐  ┌────┐
│J ♠ │  │Q ♦ │  │K ♥ │  │A ♣ │
│ ⚔  │  │ ♕  │  │ ♔  │  │ ★  │
│ J ♠│  │ Q ♦│  │ K ♥│  │ A ♣│
└────┘  └────┘  └────┘  └────┘
```

## Requirements

- Python >= 3.10
- No third-party dependencies (stdlib only)
- Terminal with >= **80 columns × 32 rows** (compact preset). Recommended: 96×38 (standard) or 120×48 (spacious) for the full Art Nouveau card art and verbose HUD. The game auto-selects the best fit and adapts on resize.
- UTF-8 support (for card symbols: ♠♥♦♣)

## Quick Start

```bash
# Install in editable mode (recommended for development)
pip install -e .

# Or install from PyPI (once uploaded)
pip install belote-cli

# Play using the belote command
belote

# Play the new Roguelite expansion
belatro

# Custom settings
belote --difficulty hard --target 500 --seed 123 --speed fast
```


## Controls

**General:**
- `?`: Show keyboard shortcut help
- `M`: Toggle sound effects on/off
- `I` or `V`: Toggle BelAtro score overlay (per-trick breakdown popup)
- `Q`: Quit to main menu or exit
- `H`: View Game History (round-by-round, with contract / taker / tricks / declarations)
- `T`: Cycle UI Theme

**Classic Belote:**
- `↑` `↓`: Navigate options
- `←` `→`: Quick-change settings (Difficulty, Target, Speed)
- `Enter`: Select option / Enter submenu

**BelAtro (Roguelite):**
- `1`-`5`: Inspect specific Jokers in the Shop
- `U`: Use a consumable (Tarot/Planet) during gameplay

**Gameplay:**
- `←` `→` or `↑` `↓`: Move selection
- `Enter`: Confirm card/bid
- `1`-`8`: Direct card selection (or `1`-`4` for bids)
- `O`: Sort hand by suit and rank
- `Z`: Undo last move
- `Space` or `Esc`: Skip animations
- During bidding round 2: `P` = Pass, `A` = Tout Atout, `S` = Sans Atout

## Features

- **BelAtro Roguelite Mode:** A massive expansion featuring 36 Jokers, 12 Tarot cards, 8 Planets, 12 Vouchers, and permanent upgrades.
- **Collection (Almanac):** Persistent tracker to browse every Joker, Planet, and Voucher you've discovered across your runs.
- **Full Boss Blind Suite:** All 21 unique bosses implemented, including complex mechanics like *L'Anarchie* (dynamic trump) and *La Rupture* (no consecutive wins).
- **Multiplier Scoring:** Use items to stack Multipliers and reach scores in the millions.
- **Partner Trust:** Build a relationship with your AI partner to unlock synergies.
- **Rich Terminal UI:** Full-screen green felt table with detailed card graphics and "You" vs "Partner" terminology.
- **Enhanced Hard AI**: Advanced void inference and 2-ply lookahead for critical tricks (Dix de Der).
- **Customizable Themes:** Switch between six color palettes (Classic Green, Dark Mode, Blue Velvet, Red Casino, Sepia Vintage, High Contrast) using the `T` key during gameplay.
- **Incremental Rendering:** High-performance cursor-based updates for zero-flicker gameplay even at high speeds.
- **Hand Sorting:** Strategic "play value" organization (honors grouped together) for better tactical awareness.
- **Main Menu:** Simple single-player entry point with configurable AI difficulty, Target Score, and Speed.
- **Undo/Redo:** Press `Z` to undo your last move during bidding or play.
- **Statistics:** unified global tracking of games played, win rates, best rounds, and BelAtro expansion milestones.
- **Responsive Layout (3 tiers):** Three preset layouts — **compact** (80×32, fits 1366×768), **standard** (96×38), **spacious** (120×48+). The game picks the largest preset that fits your terminal on every render, so resizing mid-game adapts automatically; cards, side columns, and HUD verbosity all scale with the preset. Vertical centering pads tall terminals so the game never clings to the top.
- **Alternate Screen Buffer:** Both classic Belote and BelAtro run in a dedicated terminal buffer for a clean, non-overlapping interface — your shell scrollback stays untouched after you quit.
- **Sound Effects:** Enhanced auditory feedback for trick wins, Belote, and Capot, with a built-in mute toggle.
- **Declarations:** Automatic detection and announcement of sequences (Tierce, Quarte, etc.) and Carrés after the first trick.
- **Live HUD:** Real-time round scoring displays points won during the current round, with a smooth "rolling" numerical animation for total scores.
- **High Fidelity:** Implementation of French Belote rules according to the [official rules of the Fédération Française de Belote](https://www.ffbelote.org/regles-officielle-belote/), including a two-round bidding system, "Dix de Der", "Capot" (252 pts), and "Litige" (tie-break). All six contracts are bidable in round 2: the four card suits, **Tout Atout** (every suit acts as trump within its own led-suit group; press `a`), and **Sans Atout** (no trump, lead-suit highest wins; press `s`).
- **Rules & History Viewer:** A scrollable, bilingual (English/French) in-game reference for the game's heritage and mechanics.

## AI

Three difficulty levels:
- **Easy**: Random legal moves, bids on 2+ honors.
- **Medium**: Heuristic suit scoring, void tracking to force trumps, and smart covering/ducking.
- **Hard**: Advanced void inference, 2-ply lookahead for critical tricks, and randomized "personality" bidding thresholds.

## Project Structure

```
belote/
├── src/belote/
│   ├── main.py        # Classic entry point
│   ├── belatro/       # Roguelite Expansion package
│   │   ├── main.py    # BelAtro entry point
│   │   ├── core/      # Run state, scoring, economy
│   │   ├── engine/    # Event bus, round driver
│   │   ├── items/     # Jokers, Tarots, Planets, Vouchers
│   │   ├── partner/   # Trust system and partner AI
│   │   └── ui/        # Shop, HUD, and item visualization
│   ├── gameflow.py    # Main game loop and phase transitions
│   ├── deck.py        # Card, Suit, Rank, deck operations, points
│   ├── game.py        # GameState, phases, pure transitions, legal moves, bidding
│   ├── scoring.py     # Declarations, round scoring, capot
│   ├── ai.py          # Three-tier AI (easy/medium/hard)
│   ├── config.py      # Global configuration and timings
│   ├── context.py     # Global managers (Audio, Terminal)
│   ├── themes.py      # Color theme management
│   ├── ui/            # Modular UI package
│   ├── ansi.py        # ANSI escape helpers (colors, cursor)
│   ├── input.py       # Platform-dispatched key reader and interruptible sleep
│   ├── stats.py       # Global and session statistics tracking
│   └── rules.py       # Game rules content
├── tests/             # Comprehensive test suite (525 tests)
├── scripts/           # Performance benchmarks
├── pyproject.toml      # Build system and dev dependencies (ruff/mypy)
├── LICENSE             # MIT License
├── CHANGELOG.md        # History of changes
├── DEVELOPMENT.md      # Detailed setup and dev guide
└── GRIMAUD Standard Playing-Cards-1898.png # Reference art for card faces
```

## Running Tests

```bash
# Run all tests (Classic + BelAtro)
PYTHONPATH=src pytest
```

Currently **525 tests** passing with 100% coverage on game-logic modules.

## Technical Integrity

The codebase is strictly validated with the following tools:
- **mypy**: 0 errors (strict type safety)
- **ruff**: 0 violations (linting & formatting)
- **pytest**: 525/525 passed
- **Functional Architecture**: Purely immutable state transitions using `dataclasses.replace`
- **Performance**: High-efficiency rendering and sub-millisecond AI decision times (see `scripts/benchmark.py`)

## Statistics & Progression

**Belote-CLI** tracks your long-term performance across both game modes.

- **Global Statistics:** View your win rates, best round scores, and trump usage from the "Statistics" menu.
- **BelAtro Unlocks:** Progression in the roguelite mode is saved automatically. You can track your Ante 8 wins and total items found in the expansion.

### Resetting Progress
If you want to start fresh and clear your history/collection, manually delete the data files:
- **Linux**: `rm ~/.local/share/belote/*.json`
- **Windows**: `del %APPDATA%\belote\*.json`

This will wipe all global statistics and reset your discovered item Almanac in BelAtro.

## Terminal Hygiene

Signal handlers (SIGINT, SIGTERM) and atexit hooks ensure the terminal is always restored — cursor visible, colors reset, alt-screen off — even after Ctrl+C or crashes.

Every rendered row ends with `\x1b[K` (clear-to-end-of-line) and every interactive prompt (bid selector, card selector, full-screen overlays) repaints in a single in-frame pass — no `\r\n`-bracketed writes outside the render. This keeps the game free of stale-cell artifacts on strict ANSI emulators like Konsole (KDE), in addition to the more lenient VTE-based terminals (GNOME Terminal, LXTerminal, xterm).
