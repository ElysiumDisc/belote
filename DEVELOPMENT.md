# Development Guide

Welcome to the Belote development guide. This project is structured as a standard Python package.

## Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd belote
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install in editable mode:**
   ```bash
   pip install -e .
   ```

## Running the Game

After installing, you can run the game using the `belote` command for Classic mode:
```bash
belote
```

Or the `belatro` command for the Roguelite expansion:
```bash
belatro
```

Or via python:
```bash
python -m belote.main
python -m belote.belatro.main
PYTHONPATH=src python3 -m belote.main
```

## Testing

We use `pytest` for testing. Install it if you haven't already:
```bash
pip install pytest
```

Run tests:
```bash
# Run all tests (Classic + BelAtro)
PYTHONPATH=src pytest

# Run only Classic Belote tests
PYTHONPATH=src pytest tests/

# Run only BelAtro tests
PYTHONPATH=src pytest tests/belatro/

# Run a single test file
PYTHONPATH=src pytest tests/test_game.py
PYTHONPATH=src pytest tests/belatro/test_scoring.py

# Run a single test by name
PYTHONPATH=src pytest tests/test_game.py::test_play_card_legal
PYTHONPATH=src pytest -k "test_scoring"

# Run with verbose output
PYTHONPATH=src pytest -v

# Run with coverage report
PYTHONPATH=src pytest --cov=belote --cov-report=term-missing
```

## Code Quality

The project maintains zero lint and type-check violations. Run all checks with:

```bash
# Type checking (0 errors expected, strict mode)
PYTHONPATH=src mypy --strict src/

# Linting (0 violations expected)
ruff check src/ tests/

# Full test suite (941 tests expected)
PYTHONPATH=src pytest
```

Current baseline (4.6.5):

- **941 tests** passing (4.6.4 had 939; +2 in 4.6.5 for the LePrêteur economy exploit and Windows-EOF reader regressions).
- 4.6.5 is a follow-up audit pass (six parallel Explore agents covered the surface area the 4.6.4 sweep didn't reach: partner-trust + bidding state machine, shop / economy / items / ghost-run, progression / replay / a11y / input). Two verified critical bugs + three perf wins + four quality items. Plan file: `/home/mrrobot/.claude/plans/bug-hunt-code-performance-sparkling-fairy.md`. Highlights:
  - **(Critical) LePrêteur's $5 skim cost was silently dropped.** `belatro/main.py:453` gated the `_bonus_money` payout on `> 0`, so `JokerResult(add_money=-5, times_mult=1.2)` from LePrêteur's "$50+ → skim $5 for ×1.2 Mult" branch let the multiplier through but never debited the cost. Result: every $50+ round granted a free ×1.2 multiplier. Fix: route negative `_bonus_money` through `Economy.spend_money(abs(x))`; symmetric with the 4.6.4 `Economy.add_money` non-negative guard. Pinned by `tests/belatro/test_jokers_4_5.py::test_preteur_skim_actually_debits_economy`.
  - **(Critical) Windows EOF never surfaced as `Key.EOF`.** `_WindowsKeyReader.read()` (`input.py:275`) handled the `b"\x00"` / `b"\xe0"` escape prefixes but had no guard for empty bytes (`msvcrt.getch()` returning `b""` on closed stdin). Control fell through to `ch.decode("utf-8")` → `KeyEvent(Key.CHAR, "")`, and any prompt loop that ignored empty CHAR events would hot-spin. Mirrors the long-standing `_UnixKeyReader` EOF guard. Pinned by `tests/test_input_eof.py::test_windows_reader_returns_eof_on_empty_read` (Windows-conditional + a cross-platform static-shape check).
  - **Perf: `_medium_lead` walked the legal hand 3×.** Counter-pass collapses one pre-fix `non_trumps` walk + per-suit `sum(1 for c in non_trumps ...)` dict-comp + best-suit re-filter into one pass via `Counter(c.suit for c in non_trumps if c.suit.is_card_suit).most_common(1)`.
  - **Perf: `animate_score_update` no longer allocates a fresh frozen `GameState` per frame.** 20-step score-roll animation pre-fix called `dataclasses.replace(state, team_scores=(curr_ns, curr_ew))` per frame. 4.6.5 threads an optional `team_scores_override` kwarg through `display_hud` / `_build_hud`; the loop now passes the intermediate scores directly. Existing `invalidate_diff()` in the `finally` block is preserved (still pinned by `test_animate_score_update_invalidates_diff_baseline`).
  - **Perf: declaration tie-break (`scoring.py:300-326`) collapsed from nested-zips to a dict lookup.** Micro speedup but the dict form reads more clearly than "first match wins NS, else EW".
  - **Q1: `UnlockTracker.on_event` now documents which event types it handles** (`RoundEndEvent`, `DeclarationScoredEvent`). Other bus events stay no-op by design; future unlocks that key off `BidMadeEvent` / `TrickWonEvent` / `BeloteAnnouncedEvent` add an `elif` here.
  - **Q2: `SaveManager._migrate` rejects forward-incompatible save schemas.** Pre-fix, a future-version save would silently load as the current schema; 4.6.5 raises a clear `ValueError` instead. Loading from a fresh profile is intentionally NOT auto-fallback'd — silently dropping progress is worse than a loud failure.
  - **Q3: A11y now announces the locked contract and the round result.** `a11y.py` gains `announce_contract(taker, contract_label, coinche_level)` and `announce_declaration(seat, kind, points)` helpers; `announce_round_result()` takes an optional `contract` param. Hooked from `gameflow.py` at the bid→play transition and at round-end. Pre-fix `announce_round_result` was declared but had **zero call sites** (latent dead helper since 3.0.0). Screen-reader users with `BELOTE_A11Y=1` now hear "contract: south takes hearts" and "round complete on hearts. north-south taker scores 162; defenders score 0".
  - **Q4: `JokerResult.add_money` sign convention documented** on the dataclass docstring — positive = credit, negative = debit, zero = no-op; negative values route through `Economy.spend_money` at the payout site.
  - **L1:** Dead constant `_TIER_NAMES` removed from `belatro/ui/trust_bar.py:13` (was never indexed; mood names come from `TrustTrack.mood()` directly).

Previous baselines:

- 4.6.4 (939 tests): deep-audit pass fixing five confirmed bugs surfaced by a multi-agent codebase audit:
  - **(Critical) `bus.emit()` was never called from `round_driver._emit`.** `drive_round` accepted the `EventBus` and `belatro/main.py` subscribed `UnlockTracker.on_event` to it, but the production path only invoked `acc.process_event(...)`. Consequence: every event-driven unlock (L'Exécuteur on first Capot, L'Idéologue on Sans Atout win, Le Fanatique on Tout Atout win, Quinte Royale on ≥100-pt NS sequence) silently never fired in natural play. The contract-unlocks tests passed because they `bus.emit(...)` directly. Fix: `_emit()` now publishes to the bus after `acc.process_event()`. Imported `AnyEvent` from `event_bus` so the type-checker stays happy.
  - **`RoundLedger.transactional()` was defined but never wired in.** A buggy joker handler raising mid-dispatch could leave chips/mult/money/joker_state in a partial state AND skip every sibling joker. Fix: `ScoreAccumulator._fire_jokers` now wraps each per-joker invocation in `with ledger.transactional():` plus a try/except that mirrors EventBus's isolation pattern — log via `logger.exception` and continue with siblings. Also snapshots `self._log` len since `_apply` writes to the accumulator's log (separate from `ledger.log`).
  - **Le Mime + L'Architecte score-leak combo.** `DeclarationScoredEvent` handler in `core/scoring.py` stamped `_ns_annonce_cards` into joker_state regardless of `declarations_zero`, so L'Architecte's `annonce_cash_x2` deck rule still paid +$2 per NS trick containing a declared card. Fix: harvest gated on `not state.boss_modifiers.declarations_zero`.
  - **Dead `card in self.memory.partner_hand` check in hard AI.** `card` came from MY hand; `partner_hand` held partner's cards. 32 unique deck cards / disjoint hands → branch was always False. Fix in `_score_winning_strategy`: walk partner_hand for a strictly stronger same-suit card via `trick_rank(...)`, apply the −5 penalty only when partner can actually cover.
  - **`animate_score_update` didn't invalidate the diff baseline.** `display_hud` writes row 1 directly, bypassing the render-diff cache; without `invalidate_diff()` the next `display()` might diff against the stale pre-animation baseline. Fix: post-loop `invalidate_diff()` in a `finally` block, matching the convention already enforced for help / history / rules / card-detail / stats overlays (pinned by `test_alt_screen_scroll.py::test_belatro_overlays_invalidate_diff`).
  - **Polish:** `Economy.add_money` now rejects negative amounts (symmetry with `spend_money`; no production caller passes negative — verified by grep). `_is_honor` closure in `_hard_bid` hoisted out of the per-suit loop (was rebuilt 4× per call for no benefit).
- 4.6.3 (933 tests): UX fix — pressing `I` (or `V`) now toggles the BelAtro top-HUD overlay (joker pip strip, ante/blind/target line, chips×mult score, trust bar, synergy tooltip) so the classic Belote HUD's `Trump:` and `Taker:` fields on row 1 are reachable. Pre-fix, `render_joker_pip_strip` at `move(1, 2)` unconditionally painted over the leading ~24 chars of the classic HUD produced by `_build_hud()`, clobbering `T:♥` with no way to hide the overlay; the `I` key was already wired to `Key.OVERLAY` but only flashed a transient score popup. New flag `_top_hud_visible` in `src/belote/belatro/ui/announce.py` is consulted by `BelAtroHUD.render`, `render_joker_pip_strip`, `render_synergy_tooltip`, and `TrustBar.render`. The verbose classic-HUD hint string at `src/belote/ui/render.py:922` gained `[I]HUD` for discoverability. Auto trick-end score popup at `on_trick_end()` is unchanged.
- 4.6.2 (926 tests): deep-audit / hardening pass. Real changes: (1) `src/belote/belatro/engine/round_driver.py` zeros `DeclarationScoredEvent.points` when `state.boss_modifiers.declarations_zero` is set — pre-fix, Le Mime's "declarations score 0" promise was leaking into the BelAtro accumulator path (raw `event.points` was added to chips at `core/scoring.py:324` and on_declaration jokers like LeMathematicien / QuinteRoyale fired on raw points); (2) `src/belote/belatro/core/scoring.py:197` clamps `partner_tier` to `[0, 4]` defensively so a corrupted save state (tier > 4) degrades to tier 4 rather than crashing the round with `IndexError`. New audit-matrix test files `tests/belatro/test_joker_contracts.py` and `tests/belatro/test_boss_contracts.py` (+136 tests over 4.6.1).
- 4.6.1 (790 tests): third audit pass — `src/belote/ui/menu.py` `invalidate_diff()` on every overlay-bypass exit; `belatro/ui/shop.py::_render` batched into a single `sys.stdout.write` + `flush`.
- 4.6.0 (787 tests): removed the Grimaud `card_detail` overlay — module, `Key.CARD_DETAIL` enum value + `f` binding, prompt-card / prompt-bid case arms, the help-screen `[F]` entry, the `tests/test_card_detail.py` suite (5 tests), and the `GRIMAUD Standard Playing-Cards-1898.png` reference image. `render.invalidate_diff()` preserved (still used by `show_help`/`show_history`/`show_rules`).
- 4.5.1 (792 tests): audit / hardening pass over 4.5.0. `LeCollectionneur.on_trick_won` re_emit guard, L'Architecte deck description NS-won qualifier, `_record_belote_announcement` returns `tuple[bool, bool]` directly. Two clarifying comments (L'Infiltré TOUT_ATOUT degeneracy, LePrêteur snapshot semantics).
- 4.5.0 (790 tests): WASD nav at the reader source layer, bid quick-keys remapped A→X and S→N, two new starting decks (L'Infiltré, L'Architecte), six new "Conditional Engine" jokers. `ScoreAccumulator.trigger_round_start` now applies `JokerResult` returns from `on_round_start`.

Run all gates before committing:

```bash
PYTHONPATH=src python -m pytest --tb=short -q && \
  python -m mypy --strict src/ && \
  python -m ruff check src/ tests/
```

## Benchmarking

A benchmarking script is provided to measure rendering and AI performance:
```bash
PYTHONPATH=src python scripts/benchmark.py
```

3.0.0 baseline numbers (Linux, Python 3.10+, 1000 iterations):
- Render: 0.27 ms (±0.04)
- AI Hard decide_card: 0.026 ms (±0.003)
- BelAtro state update: 0.032 ms (±0.004)
- score_round: 0.169 ms
- legal_cards: 0.012 ms

Use these as a regression-detection floor for future changes.

## Accessibility

Set `BELOTE_A11Y=1` to emit one-line plain-text descriptions of card plays,
trick winners, locked contracts (4.6.5), declarations (4.6.5), and round
results to stderr — readable by terminal screen readers (Orca, NVDA over
WSL, VoiceOver via iTerm2).

The env var is read once at import; tests that mutate it must call
`belote.a11y._refresh_enabled_from_env()` after the patch. Hook points live
in `gameflow.py` (card plays, trick winners, contract announce at bid→play
transition, round result) and `belatro/main.py` (boss reveal, ante advance,
run won/lost).

## Optional Runtime Flags

The following environment variables enable opt-in features. Each is read
once at startup; toggling mid-run has no effect.

- `BELOTE_REPLAY=1` — after every Classic round, print a one-line summary
  of how often South's plays matched the Hard-AI's preferred line
  (e.g. `Replay: Optimal plays: 6/8 (75%)`). Educational only — never
  affects scoring. Backed by `src/belote/replay.py`.
- `BELOTE_GHOST=1` — silently record every BelAtro run (seed, deck,
  bids, plays, round outcomes) to
  `~/.local/share/belote/ghosts/<label>-<seed>.json`. The file is written
  once when the run ends. Useful for sharing or replaying interesting
  runs. Backed by `src/belote/belatro/ghost_run.py`.
- `NO_COLOR=<any-non-empty>` — suppress truecolor SGR escapes from
  `fg()` / `bg()` per the [no-color.org](https://no-color.org/) spec.
  Bold/dim/underline/reverse/strikethrough and cursor sequences remain
  (they aren't color). Added in 3.9.0. Backed by `src/belote/ansi.py`.

## Releasing a New Version

### Code-only update (push to GitHub without releasing a new PyPI version)

If you're just iterating on code, fixing typos, updating docs, etc., and don't want to cut a new PyPI release yet:

```bash
git add <files>
git commit -m "<what changed>"
git push origin master
```

## Releasing a New Version (Manual)

1. **Bump the version** in `pyproject.toml`.
2. **Add a CHANGELOG entry** at the top of `CHANGELOG.md`.
3. **Clean stale build artifacts:**
   ```bash
   rm -rf dist/ build/ *.egg-info/
   ```
4. **Build, validate, and upload:**
   ```bash
   pipx run build --sdist --wheel
   pipx run twine check dist/*
   pipx run twine upload dist/*
   ```

   *Note: `twine upload` will prompt for your PyPI credentials or use your `~/.pypirc` file.*

5. **Commit and tag in git:**
   ```bash
   git add pyproject.toml CHANGELOG.md
   git commit -m "Release vX.Y.Z"
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin master --tags
   ```
```
