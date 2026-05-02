# Belote – 4-Player Terminal Card Game

Complete implementation of the French card game Belote for the terminal, with a full-screen green felt table and full card graphics at compass positions (N/W/E/S).

## Now Featuring: BelAtro Expansion

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
    ⠘⢿⡿⠋⣠⣾⣿⣿⣿⠟⠁⣿⣿⣿⣿⣿⠟⢁⣀
      ⣠⣾⣿⣿⣿⣿⣿⣿⣿⣿⠏⢀⣴⣿⣿⣿⠋⢠⣾⣿⣷⣦⡀
      ⢻⣿⣿⣿⣿⣿⣿⣿⠟⢁⣴⣿⣿⣿⡿⠁⣰⣿⣿⣿⣿⣿⣿
       ⠹⢿⣿⣿⣿⡿⠋⣠⣾⣿⣿⣿⠟⢀⣼⣿⣿⣿⣿⣿⣿⡟
         ⠉⠉⠉⠀⢾⣿⣿⣿⣿⠋⠀⠚⠛⠛⠛⠛⠛⠛⠁

                       (
                        )     (
                 ___...(-------)-....___
             .-''       )    (          ''-.
       .-'``'|-._             )         _.-|
      /  .--.|   `''---...........---''`   |
     /  /    |       > Start Game <        |
     |  |    |     Difficulty: Medium      |
      \  \   |    Target Score: 1000       |
       `\ `\ |       Speed: Normal         |
         `\ `|      Rules & History        |
         _/ /\           Quit              /
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
- Terminal with >= 90 columns x 32 rows
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
- `?` or `H`: Show keyboard shortcut help
- `M`: Toggle sound effects on/off
- `I`: Toggle BelAtro score overlay (per-trick breakdown popup)
- `Q`: Quit to main menu or exit
- `t`: View Game History (Round-by-round)
- `T`: Switch UI Theme

**Classic Belote:**
- `↑` `↓`: Navigate options
- `←` `→`: Quick-change settings (Difficulty, Target, Speed, Mode)
- `Enter`: Select option / Enter submenu

**BelAtro (Roguelite):**
- `S`: View current Run State and Jokers
- `1`-`5`: Inspect specific Jokers in the Shop
- `U`: Use a consumable (Tarot/Planet) during gameplay

**Gameplay:**
- `←` `→` or `↑` `↓`: Move selection
- `Enter`: Confirm card/bid
- `1`-`8`: Direct card selection (or `1`-`4` for bids)
- `O`: Sort hand by suit and rank
- `Z`: Undo last move
- `Space` or `Esc`: Skip animations

## Features

- **BelAtro Roguelite Mode:** A massive expansion featuring 50+ Jokers, 15+ Tarot cards, and permanent upgrades.
- **Multiplier Scoring:** Use items to stack Multipliers and reach scores in the millions.
- **Partner Trust:** Build a relationship with your AI partner to unlock synergies.
- **Boss Blinds:** Face unique challenges like "The Hook" or "The Eye" that change the rules of the game.
- **Rich Terminal UI:** Full-screen green felt table with detailed card graphics, face card art, and distinct color palettes. Graceful fallback to text-only mode for non-UTF-8 terminals.
- **Customizable Themes:** Switch between different color palettes (e.g., Classic Green, Dark Blue, Royal Purple) using the `T` key during gameplay.
- **Incremental Rendering:** High-performance cursor-based updates for zero-flicker gameplay even at high speeds.
- **Hand Sorting:** Strategic "play value" organization (honors grouped together) for better tactical awareness.
- **Pre-game Preview:** Review your hand and estimated declaration points before the bidding starts.
- **Main Menu:** Independent AI difficulty per seat, configurable Target Score and Speed.
- **Undo/Redo:** Press `Z` to undo your last move during bidding or play.
- **Statistics:** Global tracking of games played/won, win rate (per difficulty), capots, best/worst rounds, and longest games.
- **Dynamic Adaptive UI:** Menu art and text automatically center based on terminal width.
- **Alternate Screen Buffer:** BelAtro uses a dedicated terminal buffer for a clean, non-overlapping interface.
- **Sound Effects:** Enhanced auditory feedback for trick wins, Belote, and Capot, with a built-in mute toggle.
- **Declarations:** Automatic detection and announcement of sequences (Tierce, Quarte, etc.) and Carrés after the first trick.
- **Live HUD:** Real-time round scoring displays points won during the current round, with a smooth "rolling" numerical animation for total scores.
- **High Fidelity:** Full implementation of French Belote rules according to the [official rules of the Fédération Française de Belote](https://www.ffbelote.org/regles-officielle-belote/), including a two-round bidding system, "Dix de Der", "Capot" (252 pts), and "Litige" (tie-break). Full support for **Sans Atout** (No Trump) and **Tout Atout** (All Trump) contracts with accurate card values and rankings. Total round points sum to 162 in normal play, 120 in Sans Atout, and 248 in Tout Atout.
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
├── tests/             # Comprehensive test suite (250+ tests)
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

Currently **276 tests** passing with 100% coverage on core logic.

## Technical Integrity

The codebase is strictly validated with the following tools:
- **mypy**: 0 errors (strict type safety)
- **ruff**: 0 violations (linting & formatting)
- **pytest**: 276/276 passed

## Statistics & Progression

**Belote-CLI** tracks your long-term performance across both game modes.

- **Global Statistics:** View your win rates, best round scores, and trump usage from the "Statistics" menu.
- **BelAtro Unlocks:** Progression in the roguelite mode is saved automatically. You can track your Ante 8 wins and total items found in the expansion.

### Resetting Progress
If you want to start fresh:
1.  Select **"Reset Statistics"** from the main menu. This will clear both your classic Belote records and your BelAtro expansion unlocks.
2.  Alternatively, you can manually delete the data files:
    - **Linux**: `rm ~/.local/share/belote/*.json`
    - **Windows**: `del %APPDATA%\belote\*.json`
