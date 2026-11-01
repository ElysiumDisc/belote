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
| **Le Complice** *(4.11.0, unlockable)* | Partner starts at Trust 7 (plays at Hard) with one random Partner Joker in its own slot; you start with $2. Unlocked after 5 lifetime Boss Blind wins |

### New in 4.11.0
**Jokers (42 → 54):**

| Joker | Effect |
|---|---|
| Le Contrebandier | +1 Mult per opponent honor your team captures (J/9/A of trump, A/10 elsewhere; Sans Atout: A/10; Tout Atout: J/9/A) |
| Le Maréchal | Your team wins trick 1: ×1.5 Mult |
| Le Métronome | Each trick won after the first in a row: +1, +2, then +3 Mult per beat; a lost trick resets it |
| La Commère | +$2 whenever the opponents score an annonce or complete Belote-Rebelote |
| L'Horloger | +0.5 Mult per consecutive round this run without a failed contract (max +6) |
| Le Capitaine | South takes the contract and makes it: +4 Mult |
| Le Rempart | The opponents take the contract and fail: +$3 and ×2 Mult |
| Le Joaillier | Each Carré your team declares: +$3 and ×2 Mult; any other annonce: +$1 |
| Le Maître d'Atout | Win a trick with the trump Jack: +3 Mult; with the trump 9: +2 Mult |
| La Remontée | Lose 2 of the first 3 tricks yet make the contract: ×3 Mult |
| Le Rentier | At round start, +1 Mult per $10 held (max +4) |
| ??? *(secret)* | A riddle in the Collection: "let the smallest card have the very last word." |

**Bosses (21 → 24):** *Le Contre-Attaquant* — each Belote / Rebelote the
opponents announce steals 20 chips and $2. *L'Huissier* — your leftmost Joker
is seized and doesn't trigger this round. *Le Bal Masqué* — the opponents
play their first-trick cards face-down (information you'd normally see),
revealed once the trick is won. The Collection has a new **Bosses**
tab (a boss is discovered the first time you face it).

**Tarots, planet, voucher:** *Le Juge* rerolls this ante's Boss Blind (once
per ante); *L'Amoureux* gives partner Trust +2 (or $3 at max Trust);
*Neptune* levels Dix de Der (+25 chips when your team takes the last trick);
*Le Téléphone* (voucher) — the shop sometimes stocks an extra Partner Joker.

**Boss Rush / Challenge Seed** (BelAtro menu): start from any ante (1–8),
pick a boss or Random, any unlocked deck, an optional seed, and optionally
make every blind a boss. Challenge runs don't count toward wins or unlocks.
The Statistics screen now also shows your lifetime **Boss Blinds Won**.

**Watch Ghost Run** (BelAtro menu): replay a recorded run round by round
through the real table — `+`/`-` speed, `Space`/`P` pause, `→` step while
paused, `N`/`Enter` next round, `Esc`/`Q` quit. Ghost recording (Settings)
now keeps losing runs too and records the shop, bosses and round results.

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
| **Le Téléphone** *(4.11.0)* | About half the time, the shop stocks one extra Partner Joker (it goes in your partner's own slots) |

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
     |  |    |       Daily Challenge       |
     |  |    |        > Start Game <       |
     |  |    |           Settings          |
     |  |    |       Rules & History       |
     |  |    |          Statistics         |
     |  |    |             Quit            |
      \  \   |                             |
       `\ `\ |                             |
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
- A terminal of at least **80 columns × 24 rows** for Classic Belote (a default terminal window); BelAtro's screens need **80×32**. Bigger is nicer: 96×40 gets the standard cards with Art Nouveau face art, 120×48 the spacious layout and verbose HUD. The table is fitted to your terminal on every frame and adapts when you resize.
- UTF-8 support (for card symbols: ♠♥♦♣)

## Quick Start

```bash
# Install in editable mode (recommended for development)
pip install -e .

# Or install from PyPI (recommended for playing)
pipx install belote-cli      # update later with: pipx upgrade belote-cli

# Play using the belote command
belote

# Play the new Roguelite expansion
belatro

# One-off overrides of the saved settings (not persisted)
belote --difficulty hard --target 500 --seed 123 --speed fast
```

**Settings** live in the main menu's *Settings* screen and are saved to
`settings.json` in your config directory (`$XDG_CONFIG_HOME/belote`, else
`~/.config/belote`; `%APPDATA%\belote` on Windows): AI difficulty (per seat
via Enter), target score, speed, theme, animations, fast redraw,
screen-reader hints, post-round replay analysis, BelAtro ghost-run
recording, plus *(4.11.0)* your **card back** and **table frame** (with a
live preview), **Controls** (rebind the letter keys; conflicts are refused,
"Reset to defaults" restores them) and **Theme files** (export the current
palette to `themes/<name>.json` in the config dir, or import one a friend
shared — files are validated, never trusted). The old `BELOTE_*` environment
variables still work and override the saved value while set.

**Hot-seat & Spectate** *(4.11.0, main menu)*:
- **Spectate** — watch four AIs play. Before each round, guess which team
  takes it (←/→) and build a prediction streak (best streak is saved).
  While watching: `+`/`-` speed, `Space` pause, `Q` stop.
- **Hot-seat (Pass & Play)** — 2–4 people share one terminal (partners,
  opponents, three or four players; empty seats are AI). The table is always
  drawn from the chair of whoever holds the device, so your hand is at the
  bottom and "NS" is your team; a blank *Pass the device* screen hides the
  hands between players. Undo is off in hot-seat, and neither mode touches
  your statistics.

**Daily Challenge** (main menu): one seeded BelAtro run per day, the same for
everyone (fixed deck, date-derived seed, starter shop pool, no endless).
The intro shows the day's number and a share code; your best result per day
is kept locally.

**Achievements** pop a toast the moment you unlock one and are listed on the
Statistics screen.

**Card backs & table frames** *(4.11.0)*: pick them in Settings (locked ones show
their condition); the Statistics screen shows your progress. Unlocks are
stored in `cosmetics.json` in the data dir, separate from your stats.

| Card back | How to unlock |
|---|---|
| Classique *(default)* | Free — the house lattice in your theme's colour |
| Damier | Free — café checkerboard |
| Rayures | Free — fine pinstripes |
| Tressé | **Joueur Patient** — play 25 games |
| Royal | **Le Maître** — win a game on Hard |
| Grand Chelem | **Capot Collector** — score 10 capots |
| Laurier | **Le Vainqueur** — win 10 games |
| Vague | **Marathonien** — play 250 rounds |
| Néon Joker | **L'Insider** — win a BelAtro run |
| Calendrier *(calendar foil)* | **Habitué du Jour** — play the Daily Challenge on 5 days |

| Table frame | How to unlock |
|---|---|
| Art Nouveau *(default)* | Free — double rule with ◆ ornaments |
| Minimal | Free — a single thin rule |
| Gilded | **Mécène** — earn every Classic achievement |

Every back and frame has an ASCII version and honours `NO_COLOR`.


## Controls

Every letter key below except the bidding keys can be rebound in
**Settings → Controls**; the `?` help screen always shows your current keys.

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
- `S` *(4.9.7)*: Sell a joker in the Shop for half its cost (corrupted jokers can't be sold)

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

- **BelAtro Roguelite Mode:** A massive expansion featuring 54 jokers, 14 tarots, 9 planets, 13 vouchers, 13 decks, 24 bosses, Boss Rush, ghost-run replays, and permanent upgrades.
- **Dix de Der Heist (4.7.0):** Take a contract and declare a heist before trick 1 — win trick 8 for a `×(1 + interest_rate)` Mult multiplier on your round score; lose it and forfeit your card chips from tricks 1–7. Gated on owning **La Voûte** voucher (`interest_rate > 0`). AI never declares.
- **Slot-Machine Score Tally (4.7.0):** Per-trick odometer animation replaces the static popup. Chip-bucket fills, mult pulses, total ticks toward target, and a flame row crowns the odometer when you blow past 120% of the blind. Skippable on SPACE / ESC / ENTER. Final readout persists in the HUD between tricks (toggled by `I` alongside the top HUD). Suppressed under Le Brouillard (`hide_hud`) and La Compétition (`separate_scoring`).
- **Inventory Overlay on V (4.7.0; 4.9.0 / U5):** Press `V` mid-game to inspect everything you own — jokers (with edition tags + per-edition bonus blurb), vouchers, consumables, permanent chip / mult bonuses, and per-contract planet levels. List view → ↑/↓ navigate, Enter for detail, Esc/V/Q close. Since 4.9.0 also activates consumables: `1`–`9` from the list or `A` on a detail page (the shop's standalone `C` tray remains for in-shop quick-pick).
- **Animation Polish (4.8.0, extended 4.9.0):** Per-joker callouts float above the slot-machine tally as each joker fires, target-crossing pops a `★ TARGET ★` flag, shop purchases pulse + tick the money down, rerolls fade, and the trust bar ticks up between rounds. Belote / Rebelote now get a dramatic 4-row centered stinger. Classic-mode SOUTH plays paint a tactile sparkle trail; the trick winner glows briefly before the trick clears. **4.9.0 adds U1's card-lift on selection.** (4.9.0's G4 AI-delay spinner and 4.9.1's U3 trick-collection convergence were both removed in 4.9.3 as too noisy.) All animations skip on any key press and respect `BELOTE_NO_ANIM=1` for slow terminals.
- **Collection (Almanac):** Persistent tracker to browse every Joker, Planet, and Voucher you've discovered across your runs.
- **Full Boss Blind Suite:** All 24 unique bosses implemented, including complex mechanics like *L'Anarchie* (dynamic trump) and *La Rupture* (no consecutive wins).
- **Multiplier Scoring:** Use items to stack Multipliers and reach scores in the millions.
- **Partner Trust:** Build a relationship with your AI partner to unlock synergies. At trust 3+ the trust bar shows which suits North is void in (`✦ Void: ♠♦`); seeing North's full hand requires the Le Carnet voucher.
- **Rich Terminal UI:** Full-screen themed felt table with detailed card graphics and "You" vs "Partner" terminology.
- **Enhanced Hard AI**: Advanced void inference and 2-ply lookahead for critical tricks (Dix de Der).
- **Customizable Themes:** Switch between thirteen color palettes (Classic Green, Dark Mode, Blue Velvet, Red Casino, Sepia Vintage, High Contrast, Colorblind, Forest Night, Moonlit Tavern, Royal Purple, Emerald Isle, Sunset Magma, Provence Lavande) using the `T` key during gameplay.
- **Polished Felt Mat (3.9.4):** The trick mat has a subtle vignette at its edges, a faint deterministic braille pip-dot texture (fabric-weave feel without intrusive glyphs), and — when there's room — a decorative outer frame (Art Nouveau by default; Minimal and Gilded since 4.11.0).
- **Hot-seat & Spectate (4.11.0):** pass-and-play for 2–4 people on one terminal, or watch four AIs and predict each round's winner.
- **Cosmetics (4.11.0):** ten card backs and three table frames, unlocked by milestones in Classic and BelAtro, with live previews in Settings and progress on the Statistics screen.
- **Selection HUD (3.9.4):** Selecting a card in hand now paints a highlighted bar under it AND a centered `► A♠ — Trump ◄` readout below, color-coded by suit / trump / legality.
- **Hand Sorting:** Strategic "play value" organization (honors grouped together) for better tactical awareness.
- **Main Menu:** BelAtro, Daily Challenge, Start Game, Hot-seat & Spectate, Settings, Rules & History, Statistics. On short terminals (under 30 rows) the coffee-cup art gives way to a compact menu.
- **Undo/Redo:** Press `Z` to undo your last move during bidding or play.
- **Statistics:** unified global tracking of games played, win rates, best rounds, and BelAtro expansion milestones.
- **Responsive Layout (4 tiers, 4.11.0):** **mini** (80×24, 3-row cards), **compact** (80×32), **standard** (96×40), **spacious** (120×48+). The largest card size whose essential rows fit is chosen on every frame, then optional rows (selection bar, mat labels, card readout, decorative frame, breathing space) are added only while they fit — the table is never taller than your terminal. Before 4.11.0 the bottom of the hand was cut off at most sizes.
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
│   ├── round_engine.py # Shared round phase order (classic + BelAtro)
│   ├── gameflow.py    # Classic round policy: prompts, AI, animations, undo
│   ├── table_modes.py # Solo / Spectate / Hot-seat
│   ├── deck.py        # Card, Suit, Rank, deck operations, points
│   ├── game/          # Rules: state, legal moves, bidding, play, sorting, seat views
│   ├── scoring/       # Declarations, trick points, round scoring, capot
│   ├── ai/            # AI: memory + easy / medium / hard tiers
│   ├── cosmetics.py   # Card backs, table frames, unlocks
│   ├── config.py      # Global configuration and timings
│   ├── context.py     # Global managers (Terminal)
│   ├── themes.py      # Color theme management
│   ├── ui/            # Modular UI package
│   ├── ansi.py        # ANSI escape helpers (colors, cursor)
│   ├── input.py       # Platform-dispatched key reader and interruptible sleep
│   ├── stats.py       # Global and session statistics tracking
│   └── rules.py       # Game rules content
├── tests/             # Test suite (1954 tests) + headless UI harness
├── scripts/           # benchmark, hotspots (profiler), fingerprint (refactor guard), balance (BelAtro)
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

Currently **1954 tests** passing, 95% line coverage overall (4.11.0).

## Technical Integrity

The codebase is strictly validated with the following tools:
- **mypy**: 0 errors (strict type safety)
- **ruff**: 0 violations, one `ruff format` style, McCabe complexity ≤ 15 everywhere
- **pytest**: 1954/1954 passed, on Python 3.10 → 3.14 in CI (GitHub Actions)
- **Seeded fingerprints**: refactors are verified byte-identical over 450 classic games and 800 BelAtro rounds (`scripts/fingerprint.py`)
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
