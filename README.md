# Belote – 4-Player Terminal Card Game

Complete implementation of the French card game Belote for the terminal, with a full-screen green felt table and full card graphics at compass positions (N/W/E/S).

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
- Terminal with >= 100 columns x 40 rows
- UTF-8 support (for card symbols: ♠♥♦♣)

## Quick Start

```bash
# Install in editable mode (recommended for development)
pip install -e .

# Or install from PyPI (once uploaded)
pip install belote-cli

# Play using the belote command
belote

# Custom settings
belote --difficulty hard --target 500 --seed 123 --speed fast
```


## Controls

**General:**
- `?` or `H`: Show keyboard shortcut help
- `M`: Toggle sound effects on/off
- `Q`: Quit to main menu or exit
- `T`: View Game History (Round-by-round)

**Main Menu:**
- `↑` `↓`: Navigate options
- `←` `→`: Quick-change settings (Difficulty, Target, Speed, Mode)
- `Enter`: Select option / Enter submenu

**Gameplay:**
- `←` `→` or `↑` `↓`: Move selection
- `Enter`: Confirm card/bid
- `1`-`8`: Direct card selection (or `1`-`4` for bids)
- `O`: Sort hand by suit and rank
- `Z`: Undo last move
- `Space` or `Esc`: Skip animations

## Features

- **Rich Terminal UI:** Full-screen green felt table with detailed card graphics, face card art, and distinct color palettes. Graceful fallback to text-only mode for non-UTF-8 terminals.
- **Incremental Rendering:** High-performance cursor-based updates for zero-flicker gameplay even at high speeds.
- **Hand Sorting:** One-touch organization of your hand by suit and rank for better strategic overview.
- **Main Menu:** Configure Mode, Difficulty, Target Score, and Game Speed, and access **Rules & History** (EN/FR) without restarting the app.
- **Undo/Redo:** Press `Z` to undo your last move during bidding or play.
- **Statistics:** Global tracking of games played/won, win rate (per difficulty), capots, best/worst rounds, and longest games. Includes a **Session Stats** dashboard.
- **Sound Effects:** Enhanced auditory feedback for trick wins, Belote, and Capot, with a built-in mute toggle.
- **Declarations:** Automatic detection and announcement of sequences (Tierce, Quarte, etc.) and Carrés after the first trick.
- **Live HUD:** Real-time round scoring displays points won during the current round, with a smooth "rolling" numerical animation for total scores.
- **High Fidelity:** Full implementation of French Belote rules including a two-round bidding system, "Dix de Der", and "Capot" (250 pts).
- **Rules & History Viewer:** A scrollable, bilingual (English/French) in-game reference for the game's heritage and mechanics.

## AI

Three difficulty levels:
- **Easy**: Random legal moves, bids on 2+ honors.
- **Medium**: Heuristic suit scoring, strategic lead (longest suit), and smart covering/ducking.
- **Hard**: Void inference, 2-ply lookahead for critical tricks, and randomized "personality" bidding thresholds.

## Project Structure

```
belote/
├── src/belote/
│   ├── main.py        # Entry point, CLI parsing, terminal setup
│   ├── gameflow.py    # Main game loop and phase transitions
│   ├── deck.py        # Card, Suit, Rank, deck operations, points
│   ├── game.py        # GameState, phases, pure transitions, legal moves
│   ├── bidding.py     # Bidding phase state machine
│   ├── scoring.py     # Declarations, round scoring, capot
│   ├── ai.py          # Three-tier AI (easy/medium/hard)
│   ├── ui/            # Modular UI package
│   │   ├── render.py  # ANSI table and card rendering
│   │   ├── prompts.py # Keyboard input and menu navigation
│   │   ├── menu.py    # Main menu and settings
│   │   └── announce.py# Sound and score animations
│   ├── ansi.py        # ANSI escape helpers (colors, cursor)
│   ├── input.py       # Platform-dispatched key reader
│   ├── stats.py       # Global and session statistics tracking
│   └── rules.py       # Game rules content
├── tests/             # Comprehensive test suite (50+ tests)
├── pyproject.toml      # Build system and dev dependencies (ruff/mypy)
├── LICENSE             # MIT License
└── DEVELOPMENT.md      # Detailed setup and dev guide
```

## Running Tests

```bash
PYTHONPATH=src pytest
```

## Terminal Hygiene

Signal handlers (SIGINT, SIGTERM) and atexit hooks ensure the terminal is always restored — cursor visible, colors reset, alt-screen off — even after Ctrl+C or crashes.
