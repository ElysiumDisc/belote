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
belote --difficulty hard --target 500
```

## Controls

**Main Menu:**
- `↑` `↓`: Navigate options
- `Enter`: Select option
- `Q`: Quit application

**Gameplay:**
- `←` `→` or `↑` `↓`: Move selection
- `Enter`: Confirm action
- `1`-`8`: Direct card/bid selection
- `Q`: Return to main menu during gameplay

## Features

- **Rich Terminal UI:** Full-screen green felt table with detailed card graphics, face card art (Roi ♔, Dame ♕, Valet ⚔), and distinct color palettes.
- **Main Menu:** Configure Difficulty, Target Score, and Game Speed, and access **Rules & History** (EN/FR) without restarting the app.
- **Live HUD:** Real-time round scoring displays points won during the current round, with a smooth "rolling" numerical animation for total scores.
- **Trick History:** Visual "Last Trick" panel helps track the flow of the game.
- **High Fidelity:** Full implementation of French Belote rules including a two-round bidding system, "Dix de Der", and "Capot" (250 pts) announcements.
- **Rules & History Viewer:** A scrollable, bilingual (English/French) in-game reference for the game's heritage and mechanics.
- **Robust Input:** High-performance unbuffered key reading for responsive navigation and 'q' to quit functionality.

## AI

Three difficulty levels:
- **Easy**: Random legal moves, bids on 2+ honors
- **Medium**: Heuristic suit scoring, strategic play (cover/duck/duck)
- **Hard**: Void inference, 1-ply lookahead, Monte-Carlo bidding

## Project Structure

```
belote/
├── src/belote/
│   ├── main.py        # Entry point, game loop, CLI args
│   ├── deck.py        # Card, Suit, Rank, deck operations, points
│   ├── game.py        # GameState, phases, pure transitions, legal moves
│   ├── bidding.py     # Bidding phase state machine
│   ├── scoring.py     # Declarations, round scoring, capot
│   ├── ai.py          # Three-tier AI (easy/medium/hard)
│   ├── ansi.py        # ANSI escape helpers (colors, cursor)
│   ├── input.py       # Platform-dispatched key reader
│   ├── ui.py          # Render, prompts, full-screen layout
│   └── rules.py       # Game rules content
├── tests/
│   └── test_belote.py  # 36 pytest tests
├── pyproject.toml      # Build system configuration
├── LICENSE             # MIT License
└── DEVELOPMENT.md      # Detailed setup and dev guide
```

## Running Tests

```bash
PYTHONPATH=src pytest
```

## Terminal Hygiene

Signal handlers (SIGINT, SIGTERM) and atexit hooks ensure the terminal is always restored — cursor visible, colors reset, alt-screen off — even after Ctrl+C or crashes.
