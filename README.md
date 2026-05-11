# Belote – 4-Player Terminal Card Game

Complete implementation of the French card game Belote for the terminal, with a full-screen green felt table and full card graphics at compass positions (N/W/E/S).

## What's new in 3.4.2

- **The 3.4.1 catalogue is closed.** All 7 confirmed bugs plus the H10 architectural cleanup and the M4 dead-code deletion ship here. **C1 — AI cheating under Le Fantôme Partenaire:** AI memory now respects `hide_partner_hand`; the boss flag's visibility cost is paid by both sides. **C3 — Dix de Der announcement under La Rupture:** the 8th-trick "Team X" line now uses the Rupture-aware `compute_trick_winners` helper, so the named team matches what scoring credits. **C4 — `opp_trumps` formula:** subtracts South's own trumps, played trumps, and partner-visible trumps; under Tout Atout the total switches to 32 (every card is a trump). **H1 — 8 BelAtro jokers:** `LIdeologue`, `LeFanatique`, `LeDiplomate`, `LePatriote`, `LIllusionniste`, `LePremierSang`, `LeSergent`, `LExecuteur` now gate on `team_of(event.winner) == 0` instead of `event.winner == Seat.SOUTH`, matching the 3.2.0 fix that landed `LaSentinelle` and `LeDernierMot`. **H4 — TournoiAnte:** `on_blind_won` now receives `blind_payout` and pays a true 50% (was a flat function of `bonus_per_round`). **H5 — `load_profile`:** saves missing the `unlocked_ids` key fall back to the Profile dataclass default starter unlocks. **H7 — classic win attribution on ties:** `update_stats_game` operator aligned to `ns > ew` so the stats line agrees with `menu.py`'s visible winner on an exact tie at target.
- **Architectural / cleanup.** `equip_joker` accepts an optional `run` and fires `on_purchase` when provided (forward-looking — no current partner joker has a purchase hook). Dead `advance_turn()` deleted from `game.py`.
- **Still deferred** (need spec calls, not implementation work): H2 `LEgoiste` partner-trick nullification (comment vs. audit reading); `LeRebelle` `on_belote` seat/team gating (separate code path from H1).
- **Tests + gates** — 568 tests (up from 551, +17 regressions). Five existing `test_north_*_returns_none` tests in `test_belatro.py` were flipped to assert the new team-aware behaviour (they had encoded the H1 bug as a contract). Strict gates still clean: pytest 568/568, mypy 0 errors (76 files), ruff 0 violations.

## What's new in 3.4.1

- **Audit verification pass — no code changes.** An external LLM audit ("Comprehensive Audit Report — Belote CLI v3.4.0") flagged 4 Critical, 10 High, and 12 Medium issues. Direct verification against the source confirmed **7 real bugs** (3 Critical, 4 High), **1 architectural latent issue**, and **1 disputed claim** needing a spec decision; **8 claims were false positives**. The roadmap and the false-positive catalogue are recorded in `CHANGELOG.md` so the next session has a vetted target list and the rejected claims aren't re-investigated. *Note (3.4.2): the catalogue is now closed — all 7 confirmed bugs plus H10 and M4 are fixed in 3.4.2. The 3.4.1 entry is preserved as a historical record of the verification-only release.*
- **Confirmed bugs deferred to 3.4.2+**: AI ignoring `hide_partner_hand` (C1), Dix de Der announcement not La Rupture-aware (C3), AI `opp_trumps` over-count (C4), 8 BelAtro jokers still gated on South instead of NS team (H1), TournoiAnte bonus not actually 50% (H4), `load_profile` losing default unlocks (H5), classic-mode tie-break operator mismatch with the menu summary (H7). Plus latent: `equip_joker` skipping `on_purchase` (H10), and a dead `advance_turn()` (M4).
- **Audit calibration findings** — recurring failure modes documented for the next pass: defense-in-depth confused with bugs (C2/H8/H9), intent inversion against adjacent comments (H2/M2/M12), self-cancelling dead-code claims (H3), and joker-name hallucination (H1's `LeRebelle`). Useful as feedback to the auditing model.
- **No behavioural changes.** Test count, mypy strict, ruff all unchanged from 3.4.0: pytest 551/551, mypy 0 errors (76 files), ruff 0 violations.

## What's new in 3.4.0

- **BelAtro joker correctness** — `BidMadeEvent` no longer double-fires `on_bid` joker handlers on coinche paths. Pre-3.4.0 the player-coinche, AI-partner-coinche, `auto_coinche` boss, and `start_coinched` deck-mod paths all re-emitted the same bid event a second time with the resolved `coinche_level`, so on_bid jokers (Le Passeur today, anything new tomorrow) were silently invoked twice for the same bid. Fixed via a `re_emit: bool` field on the event; refreshes update `joker_state["contract"]` but skip joker firing.
- **Endless mode honours its prompt** — Accepting "Continue into Endless Mode? (Ante 9+ scales ×2.2)" used to leave the player at Ante 8 Boss Blind for one more *un-scaled* round before the ×2.2 kicked in. `enter_endless()` now advances into the first scaled cycle (offset=1, blind_index=0) immediately, so the very next round is the scaled Small Blind as advertised.
- **Classic mode tie-breaker actually plays** — When both teams ended a round tied at exactly the target score, the classic loop unconditionally forced GAME_OVER, overriding `apply_round_score`'s deliberate `phase=DEAL` for tie-breaker rounds. The redundant re-check is gone; the scoring layer is the single source of truth for game-over phase.
- **Terminal raw-mode no longer leaks on SSH drop** — `_UnixKeyReader.restore()` now wraps `termios.tcsetattr` in `contextlib.suppress(termios.error, OSError)` and marks the reader restored regardless. A dropped SSH session previously left the parent shell in no-echo mode.
- **Shop reroll OOB fix** — Shop selection index after reroll is now correctly clamped to `len(inventory) - 1` instead of `len(inventory)`, preventing an out-of-range access on the next render.
- **HUD: joker pip strip + synergy tooltip + polished trust bar** — Top-row 5-slot strip shows your jokers as compact pips with edition tint (Foil cyan / Holo magenta / Polychrome pink-violet / Negative reverse-video); slots in an active synergy pair gain a `*` marker, and a one-line tooltip below the score line describes the synergy. The trust bar gains a four-tier colour ramp (cramoisi/orange/gold/emeraude) and a leading tier glyph (`✗ ♡ ♥ ♦ ★`) — Loyal/Mécène glyphs are bolded so the top tiers pop.
- **Audit reconciliation** — A fresh three-agent audit pass surfaced ~80 candidate findings; verification rejected ~95% as false positives or by-design patterns. The seven survivors are the fixes above; the rejected claims are catalogued in `CHANGELOG.md` so they aren't re-investigated.
- **Test coverage** — 551 tests (up from 549). Strict gates still clean: pytest 551/551, mypy 0 errors (76 files), ruff 0 violations.

## What's new in 3.3.4

- **Portability fix** — Removed all terminal-bell / sound code, which was triggering SIGSYS ("Bad system call") on Alpine 23 (musl libc) the moment the first trick completed in classic Belote mode. BelAtro mode and every glibc-based distro (Kubuntu / Lubuntu 24.10 / 25.10) were unaffected, but rather than guard the BEL writes behind a libc check, the entire sound subsystem is gone — `play_sound`, `AudioManager` / `AUDIO`, `is_muted` / `toggle_mute`, the `[M]` mute key, and the help-screen mute line. Classic Belote and BelAtro now share the same "no bells" baseline.
- **Test coverage** — Still 549 tests. Strict gates clean: pytest 549/549, mypy 0 errors, ruff 0 violations.

## What's new in 3.3.3

- **Determinism** — Boss assignment in BelAtro mode now draws from the run's seeded RNG instead of the module-level `random`. This was the last unseeded RNG site in the round flow (shop and tarots were converted in 3.2.0, AI in 3.3.1, replay analysis in 3.3.2). Same seed now reproduces the same boss on the boss blind.
- **UI** — Hands sort by the trump-rank ladder under Tout Atout (Jack first, then 9 / A / 10 / K / Q / 8 / 7). Pre-3.3.3 the predicate `c.suit == trump` was always false under TA because Card.suit is never `Suit.TOUT_ATOUT`, so the South hand displayed in the non-trump order whenever the player bid TA.
- **Tarot** — Le Jugement now correctly grants only Common jokers as advertised. Pre-3.3.3 the code drew from the full unlocked pool, so late-run players with Rare/Legendary unlocks could roll out-of-rarity jokers off this tarot.
- **Test moat** — Three new invariant test suites added: scoring-conservation property (`table_taker + table_defender == 162 / 258 / 130` for normal / Tout Atout / Sans Atout), seeded-round replay determinism (same seed → same card sequence → same final state), and HUD synergy-badge negative test (solo half of a pair must not fire the badge). These would have caught most of the 3.3.x bug cycle from below.
- **Audit reconciliation** — A fresh three-agent codebase pass surfaced ~50 candidate findings; the three above held up under verification and the rest are catalogued in `CHANGELOG.md` so they aren't re-investigated.
- **Test coverage** — 549 tests (up from 537). Strict gates still clean: pytest 549/549, mypy 0 errors (76 files), ruff 0 violations.

## What's new in 3.3.1

- **Scoring correctness under bosses** — La Rupture (`no_consecutive_team_wins`) used to be applied to the live HUD but silently ignored by `score_round`, so the running total and final score diverged and impossible capots could be reported. L'Anarchie (dynamic trump) rotated `state.trump` mid-round, after which scoring's `belote_holders.get(trump)` lookup missed any Belote announced on the original trump and silently zeroed the 20/40 bonus. Both are fixed: a new `compute_trick_winners` helper is the single source of truth for La Rupture-aware winner resolution, and a new `belote_announcer: Seat` field captures the announcing seat at declaration time so the rotated trump no longer matters.
- **Boss interactions** — Le Zéro Final (`no_dix_de_der`) is now honored by the chute branch and by La Compétition's per-player tally (both used to unconditionally add +10 de der). La Compétition's `ban_clubs` check now matches the main scoring path (`any` rather than `lead-only`).
- **Determinism** — `AIPlayer` now accepts and threads a seeded `Random` from the round driver. Pre-3.3.1 it constructed an unseeded `Random()` regardless of the run seed, breaking ghost-run reproducibility and replay determinism. Partner's `should_coinche` (Le Flambeur) was also using the global `random` module; now uses the driver's seeded RNG and is actually wired into the coinche flow (it had no production caller before).
- **AI memory across undo** — Hard AI's void inference is no longer stuck with stale voids after a mid-round undo: `update_memory` detects state regression and rebuilds inferences from the live tricks.
- **Hard AI under Sans Atout** — Used to deterministically return `legal[0]`; now falls back to easy (random) like medium, removing the worst-case under SA.
- **Audit fixes** — `ban_clubs` HUD/final divergence (was real); per-round stats now flush to disk (achievement unlocks no longer lost on crash); `fuse_jokers` now carries over edition (FOIL/HOLO/POLY) and corruption; `assert` in `modifier_patch` replaced with `raise ValueError` (was strippable by `python -O`); unlock notifications routed through the TUI banner instead of raw `print()` (no more alt-screen scroll); ante themes (Café/Tournoi) wired into the live game loop (the Phase 3.1 module was previously test-only).
- **UI** — Trust bar is three-tier (red ≤3, gold 4–6, green ≥7). Pre-3.3.1 the default trust of 5 rendered red, falsely signalling distrust at run start.
- **Test coverage** — 535 tests still passing. Strict gates clean: pytest 535/535, mypy 0 errors, ruff 0 violations.

## What's new in 3.3.0

- **BelAtro [H] history overlay** — Pressing **H** during a BelAtro run now opens a populated, run-aware ledger: one row per blind with ante, blind label (Small/Big/Boss), target, boss name (when active), taker, contract, NS/EW trick split, BelAtro score, status (`WON` / `FAILED` / `CAPOT` / `SURVIVED`), and money delta. Before 3.3, [H] always showed "No rounds completed yet." in BelAtro because the round driver never invoked `apply_round_score` — the classic-mode writer of `state.score_history`. The fix keeps a parallel `BelAtroRun.history` ledger and routes [H] to a new BelAtro renderer via a small override hook in `belote.ui.prompts`. Classic Belote's [H] path is unchanged.
- **Test coverage** — 535 tests (up from 528). Strict gates still clean: pytest 535/535, mypy 0 errors, ruff 0 violations.

## What's new in 3.2.0

- **Joker correctness** — La Sentinelle and Le Dernier Mot both used to key on `Seat.SOUTH` instead of the NS team, so the joker silently no-op'd when North (the AI partner) held the trump Jack or won the last trick. Both now correctly fire on team membership.
- **Score floor** — L'Égoïste's `add_chips = -event.card_points` per partner-won trick could drive the running total negative and produce a negative final round score; `ScoreAccumulator.get_total` now clamps at 0 so the intermediate log can still show the deduction without the visible score going below zero.
- **Auto-coinche event parity** — The NS-taker `auto_coinche` boss path now re-emits `BidMadeEvent` with the new `coinche_level`, matching the EW-taker branch. Pre-3.2 jokers and HUD subscribed to `on_bid` silently missed this code path.
- **Determinism** — The shop and the three RNG-using tarots (`LeJugement`, `LaPretresse`, `LeFou`) now all draw from the run's seeded `_get_rng()` instead of the module-level `random`. Ghost-run replays are now reproducible across shop generations. `LaPretresse` additionally `sample`s instead of `choice`-ing twice, so the two planets it grants are always distinct.
- **Registry / boss-field hygiene** — `register_joker/planet/tarot/voucher` now assert against duplicate IDs (typo'd registrations used to silently overwrite the original). `boss_fields` in `modifier_patch.py` is now derived from `BossModifiers`' dataclass fields, so adding a new flag no longer requires updating an out-of-band allowlist.
- **UI fix** — `patch_trick_card` now re-applies `render`'s vertical-centering offset; on tall terminals (>40 rows) it used to draw single-card patches too high.
- **Audit reconciliation** — This release consolidates the verified findings from two independent LLM code audits (Qwen 3.6 27B + Ring 1T). Both audits had load-bearing false positives — Qwen's two P0 "dead voucher / dead boss flag" claims were both wrong (the flags are consumed); Ring's "critical IllegalMoveError" only fires under test mocks. Eleven rejected claims are catalogued in the changelog so they aren't re-investigated.
- **Test coverage** — 528 tests (up from 525). Strict gates still clean: pytest 528/528, mypy 0 errors, ruff 0 violations.

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
│   ├── context.py     # Global managers (Terminal)
│   ├── themes.py      # Color theme management
│   ├── ui/            # Modular UI package
│   ├── ansi.py        # ANSI escape helpers (colors, cursor)
│   ├── input.py       # Platform-dispatched key reader and interruptible sleep
│   ├── stats.py       # Global and session statistics tracking
│   └── rules.py       # Game rules content
├── tests/             # Comprehensive test suite (568 tests)
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

Currently **568 tests** passing with 100% coverage on game-logic modules.

## Technical Integrity

The codebase is strictly validated with the following tools:
- **mypy**: 0 errors (strict type safety)
- **ruff**: 0 violations (linting & formatting)
- **pytest**: 568/568 passed
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
