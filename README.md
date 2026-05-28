# Belote – 4-Player Terminal Card Game

Complete implementation of the French card game Belote for the terminal, with a full-screen themed felt table (13 palettes), full card graphics at compass positions (N/W/E/S), vignette and braille pip-texture polish, and an optional decorative outer frame.

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
| **Le Marseillais** | Annonces (Tierce / Quarte / Quinte) score ×2. Belote / Rebelote disabled |
| **Le Coincheur** | Every round starts pre-coinched. +50 starting Chips, $8 starting cash |
| **L'Infiltré** *(4.5.0)* | Ghost Lead — winning a trick by playing Trump on a suit you have ZERO of grants +2 Mult and +$1 |
| **L'Architecte** *(4.5.0)* | Pay $10 in bidding to choose the contract yourself. NS-won tricks containing a declared Annonce card pay +$2 |

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
- `I` *(BelAtro only)*: Toggle the BelAtro top HUD overlay AND the persistent slot-machine tally readout — see the BelAtro gameplay note below for details
- `V` *(4.7.0; 4.9.0 / U5: activation merged in, BelAtro only)*: Open the **Inventory** overlay (jokers, vouchers, consumables, permanent bonuses, contract levels). ↑/↓ navigate, Enter for detail, Esc/V/Q close. **`1`–`9` activates the Nth consumable directly**; `A` on a consumable's detail page does the same. `C` in the shop still launches the standalone numbered Consumables tray for quick-pick activation.
- `Q`: Quit to main menu or exit
- `H`: View Game History (round-by-round, with contract / taker / tricks / declarations)
- `T`: Cycle UI Theme

**Classic Belote:**
- `↑` `↓`: Navigate options
- `←` `→`: Quick-change settings (Difficulty, Target, Speed)
- `Enter`: Select option / Enter submenu

**BelAtro (Roguelite):**
- `1`-`5`: Inspect specific Jokers in the Shop
- `C`: Open the Consumables tray in the Shop (use Tarots / Planets you've purchased)

**Gameplay:**
- `←` `→` or `↑` `↓` or **`W` `A` `S` `D`** *(4.5.0)*: Move selection
- `Enter`: Confirm card/bid
- `1`-`8`: Direct card selection (or `1`-`4` for bids)
- `O`: Re-sort hand by suit and rank (hand auto-sorts on every play turn since 3.9.4 — this key is now a manual re-sort, kept for muscle memory)
- `Z`: Undo last move
- `Space` or `Esc`: Skip animations
- During bidding round 2: `P` = Pass, `X` = Tout Atout, `N` = Sans Atout *(remapped from A/S in 4.5.0 to make room for WASD nav)*
- `I` *(4.6.3, BelAtro only)*: Toggle the BelAtro top HUD (joker pip strip, ante/blind/target line, chips×mult score, trust bar, synergy tooltip) AND, since 4.7.0, the persistent slot-machine tally readout at the bottom. Visible by default; press `I` to hide both and reveal the classic Belote HUD's `Trump:` / `Taker:` fields underneath. Press `I` again to bring them back.
- `V` *(4.7.0; 4.9.0 / U5: activation merged in, BelAtro only)*: Open the inventory overlay (jokers, vouchers, consumables, permanent bonuses, contract levels). Since 4.9.0 also activates consumables: `1`–`9` from the list or `A` on a detail page. Pre-4.7.0 this was an alias of `I`; it's now its own thing.

## Features

- **BelAtro Roguelite Mode:** A massive expansion featuring 42 jokers, 12 tarots, 8 planets, 12 vouchers, 12 decks, 21 bosses, and permanent upgrades.
- **Dix de Der Heist (4.7.0):** Take a contract and declare a heist before trick 1 — win trick 8 for a `×(1 + interest_rate)` Mult multiplier on your round score; lose it and forfeit your card chips from tricks 1–7. Gated on owning **La Voûte** voucher (`interest_rate > 0`). AI never declares.
- **Slot-Machine Score Tally (4.7.0):** Per-trick odometer animation replaces the static popup. Chip-bucket fills, mult pulses, total ticks toward target, and a flame row crowns the odometer when you blow past 120% of the blind. Skippable on SPACE / ESC / ENTER. Final readout persists in the HUD between tricks (toggled by `I` alongside the top HUD). Suppressed under Le Brouillard (`hide_hud`) and La Compétition (`separate_scoring`).
- **Inventory Overlay on V (4.7.0; 4.9.0 / U5):** Press `V` mid-game to inspect everything you own — jokers (with edition tags + per-edition bonus blurb), vouchers, consumables, permanent chip / mult bonuses, and per-contract planet levels. List view → ↑/↓ navigate, Enter for detail, Esc/V/Q close. Since 4.9.0 also activates consumables: `1`–`9` from the list or `A` on a detail page (the shop's standalone `C` tray remains for in-shop quick-pick).
- **Animation Polish (4.8.0, extended 4.9.0):** Per-joker callouts float above the slot-machine tally as each joker fires, target-crossing pops a `★ TARGET ★` flag, shop purchases pulse + tick the money down, rerolls fade, and the trust bar ticks up between rounds. Belote / Rebelote now get a dramatic 4-row centered stinger. Classic-mode SOUTH plays paint a tactile sparkle trail; the trick winner glows briefly before the trick clears. **4.9.0 adds U1's card-lift on selection.** (4.9.0's G4 AI-delay spinner and 4.9.1's U3 trick-collection convergence were both removed in 4.9.3 as too noisy.) All animations skip on any key press and respect `BELOTE_NO_ANIM=1` for slow terminals.
- **Collection (Almanac):** Persistent tracker to browse every Joker, Planet, and Voucher you've discovered across your runs.
- **Full Boss Blind Suite:** All 21 unique bosses implemented, including complex mechanics like *L'Anarchie* (dynamic trump) and *La Rupture* (no consecutive wins).
- **Multiplier Scoring:** Use items to stack Multipliers and reach scores in the millions.
- **Partner Trust:** Build a relationship with your AI partner to unlock synergies.
- **Rich Terminal UI:** Full-screen themed felt table with detailed card graphics and "You" vs "Partner" terminology.
- **Enhanced Hard AI**: Advanced void inference and 2-ply lookahead for critical tricks (Dix de Der).
- **Customizable Themes:** Switch between thirteen color palettes (Classic Green, Dark Mode, Blue Velvet, Red Casino, Sepia Vintage, High Contrast, Colorblind, Forest Night, Moonlit Tavern, Royal Purple, Emerald Isle, Sunset Magma, Provence Lavande) using the `T` key during gameplay.
- **Polished Felt Mat (3.9.4):** The trick mat now has a subtle vignette at its edges, a faint deterministic braille pip-dot texture (fabric-weave feel without intrusive glyphs), and — at standard/spacious terminal sizes — a decorative `╔═══◆═══...═══◆═══╗` outer frame with corner ornaments.
- **Selection HUD (3.9.4):** Selecting a card in hand now paints a highlighted bar under it AND a centered `► A♠ — Trump ◄` readout below, color-coded by suit / trump / legality.
- **Hand Sorting:** Strategic "play value" organization (honors grouped together) for better tactical awareness.
- **Main Menu:** Simple single-player entry point with configurable AI difficulty, Target Score, and Speed.
- **Undo/Redo:** Press `Z` to undo your last move during bidding or play.
- **Statistics:** unified global tracking of games played, win rates, best rounds, and BelAtro expansion milestones.
- **Responsive Layout (3 tiers):** Three preset layouts — **compact** (80×32, fits 1366×768), **standard** (96×38), **spacious** (120×48+). The game picks the largest preset that fits your terminal on every render, so resizing mid-game adapts automatically; cards, side columns, and HUD verbosity all scale with the preset. Vertical centering pads tall terminals so the game never clings to the top.
- **Alternate Screen Buffer:** Both classic Belote and BelAtro run in a dedicated terminal buffer for a clean, non-overlapping interface — your shell scrollback stays untouched after you quit.
- **Declarations:** Automatic detection and announcement of sequences (Tierce, Quarte, etc.) and Carrés after the first trick.
- **Live HUD:** Real-time round scoring displays points won during the current round, with a smooth "rolling" numerical animation for total scores.
- **High Fidelity:** Implementation of French Belote rules according to the [official rules of the Fédération Française de Belote](https://www.ffbelote.org/regles-officielle-belote/), including a two-round bidding system, "Dix de Der", contract-aware **Capot** (252 normal / 220 Sans Atout / 348 Tout Atout), and "Litige" (tie-break). All six contracts are bidable in round 2: the four card suits, **Tout Atout** (every suit acts as trump within its own led-suit group; press `x`), and **Sans Atout** (no trump, lead-suit highest wins; press `n`).
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
│   │   ├── engine/    # Event bus, round driver, modifier patch
│   │   ├── items/     # Jokers, Tarots, Planets, Vouchers
│   │   ├── partner/   # Trust system and partner AI
│   │   ├── run/       # Antes, blinds, bosses, decks, shop
│   │   ├── progression/ # Saves & unlocks
│   │   ├── run_summary.py / ghost_run.py # Run history & replays
│   │   └── ui/        # Shop, HUD, consumables tray, history
│   ├── gameflow.py    # Main game loop and phase transitions
│   ├── deck.py        # Card, Suit, Rank, deck operations, points
│   ├── game.py        # GameState, phases, pure transitions, legal moves, bidding
│   ├── scoring.py     # Declarations, round scoring, capot
│   ├── ai.py          # Three-tier AI (easy/medium/hard)
│   ├── config.py      # Global configuration and timings
│   ├── context.py     # Global managers (Terminal)
│   ├── themes.py      # Color theme management
│   ├── ui/            # Modular UI package
│   ├── ansi.py        # ANSI escape helpers (colors, cursor)
│   ├── input.py       # Platform-dispatched key reader and interruptible sleep
│   ├── stats.py       # Global and session statistics tracking
│   └── rules.py       # Game rules content
├── tests/             # Comprehensive test suite (1079 tests)
├── scripts/           # Performance benchmarks
├── pyproject.toml      # Build system and dev dependencies (ruff/mypy)
├── LICENSE             # MIT License
├── CHANGELOG.md        # History of changes
└── DEVELOPMENT.md      # Detailed setup and dev guide
```

## Running Tests

```bash
# Run all tests (Classic + BelAtro)
PYTHONPATH=src pytest
```

Currently **1079 tests** passing with 100% coverage on game-logic modules (4.9.5).

## Technical Integrity

The codebase is strictly validated with the following tools:
- **mypy**: 0 errors (strict type safety)
- **ruff**: 0 violations (linting & formatting)
- **pytest**: 1044/1044 passed
- **Functional Architecture**: Purely immutable state transitions using `dataclasses.replace`
- **Performance**: High-efficiency rendering and sub-millisecond AI decision times (see `scripts/benchmark.py`)

## Statistics & Progression

**Belote-CLI** tracks your long-term performance across both game modes.

- **Global Statistics:** View your win rates, best round scores, and trump usage from the "Statistics" menu.
- **BelAtro Unlocks:** Progression in the roguelite mode is saved automatically. The Statistics screen tracks your Ante 8 wins and shows two distinct counts (since 3.9.4): **Discovered** (items you've actually seen in a shop or starting deck — these show up in the Collection screen) and **Unlocked** (items you've earned access to via achievements; fresh profiles start with 3 unlocked starter decks).

### Resetting Progress
If you want to start fresh and clear your history/collection, manually delete the data files:
- **Linux**: `rm ~/.local/share/belote/*.json`
- **Windows**: `del %APPDATA%\belote\*.json`

This will wipe all global statistics and reset your discovered item Almanac in BelAtro.
