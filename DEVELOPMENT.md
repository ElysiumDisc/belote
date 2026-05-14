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

# Full test suite (635 tests expected)
PYTHONPATH=src pytest
```

Current baseline (3.7.1):
- **mypy**: 0 errors (strict mode, 77 files)
- **ruff**: 0 violations
- **pytest**: 635 tests, 0 failures
- 3.7.1 lands the deferred 3.7.0 items plus a fresh audit pass. Three Explore agents ran in parallel against the documented false-positive catalogue. The classic-engine sweep returned no novel findings (3.4.x → 3.6.0 absorbed the surface); the BelAtro layer produced **BA-L2** (L'Accumulateur team→seat bug, HIGH) and **BA-L1** (`ContractReward` TypedDict float annotations, MEDIUM). Deferred items: **D1** — `score_round` and `play_card` extracted behind `_ScoringContext` / `_PlayContext` (zero test edits, behaviour-preserving); **D2** — `tests/belatro/test_partner_jokers.py` adds 26 tests, **100% coverage** for `passive` / `risky` / `shaper` partner-joker modules; **D3** — `prompt_surcoinche` callback on `RoundUICallbacks` plus NS-taker player-surcoinche path in `round_driver.py:268-283`. **+36 regression tests** (599 → 635). Plan file at `/home/mrrobot/.claude/plans/bug-hunt-code-performance-sequential-map.md`.
- 3.6.0 lands a verified bug-hunt and refactor pass over the classic engine and the BelAtro roguelite layer. Three Explore agents produced ~50 candidate findings; verification against current code rejected several as false positives (notably "dix-de-der double counting" — separate counters; "underscore-boss-attr anti-pattern" — already pinned by tests) and confirmed the items shipped here. **+4 regression tests** (595 → 599). Plan file at `/home/mrrobot/.claude/plans/bug-hunt-code-performance-functional-naur.md`.
  - **H1** (`belatro/engine/round_driver.py:210-289`) — EW AI can now coinche an NS taker via a new `_ew_should_coinche` heuristic. Pre-3.6.0 there was no path that set `coinche_level > 0` when NS was taker (outside `auto_coinche` / `start_coinched`), making the Libra planet effectively unreachable in natural play.
  - **H2** (`belatro/items/registry.py:184-194`) — synergy-ID validation converted from `assert` to a real `raise RuntimeError(...)` so the check survives `python -O` / `PYTHONOPTIMIZE=1` in packaged installs.
  - **H3** (`belatro/engine/event_bus.py:emit`) — handler exceptions are now logged and the remaining subscribers still fire. A single buggy joker's `on_event` can no longer halt mid-round accumulator/unlock dispatch.
  - **M1+M2** (`scoring.py`) — extracted `_card_points_with_zero_ranks`, `_trick_zeroed_by_ban_clubs`, and `_trick_points_with_modifiers`. Three sites that previously inlined the zero-rank flag table (drift-prone) now route through one helper. New zero-rank boss flags need one edit, not three.
  - **M3** (`belatro/engine/modifier_patch.py:patch`) — narrowed the leading-underscore guard to reject ONLY `_<boss_field>` (the actual 3.0.x anti-pattern). Legitimate scalar GameState fields (`_chips`, `_mult`, `_joker_state`, `_rng`) are now patchable through `PatchedGameState`.
  - **M4/R1** (`deck.py:Contract`, plus `scoring.py`/`game.py`/`ai.py`/`gameflow.py`/`belatro/engine/round_driver.py`) — `class Contract(str, Enum)` defines `NORMAL`/`SANS_ATOUT`/`TOUT_ATOUT`/`COINCHE`/`SURCOINCHE` and the dense comparison sites switched from string literals. Values remain plain strings so JSON serialisation and legacy comparisons keep working.
  - **P4** (`game.py:sort_hand`) — `@lru_cache(maxsize=512)`. Benchmark showed ~34 % wall-clock win on the UI render's repeated `(hand, trump)` access pattern. P2 (`deck.card_points` caching) was **rejected** by benchmark — the function is too small for `lru_cache` to win against call overhead (1.86× slower with cache).
  - **R4** (`belatro/core/scoring.py:ContractReward`) — `TypedDict` schema for `contract_levels` entries; catches planet-reward key typos (e.g. `bonus_per_trick` vs `bonus_mult_per_trick`) at type-check time. `BelAtroRun.contract_levels` keeps its wider `dict[str, dict[str, Any]]` type to avoid an import cycle; the consumer site casts at the boundary.
  - **L1** (`game.py:place_bid` belote detection) — single-pass per hand: previously rebuilt a `(rank, suit)` set and re-iterated 4 suits.
  - **L2** (`deck.py`) — `card_points`/`trick_rank` signatures widened to `trump: Suit | None` to match the SA call sites.
  - **L3** (`scoring.py:_carre_points`) — switched from dict `[]` access to `.get(..., 0)` for asymmetry with sibling lookups; the dict is complete today so this is fail-soft only.
  - **T1** (`tests/test_properties.py`) — three new invariants: `test_chute_and_capot_are_mutually_exclusive`, `test_dynamic_trump_never_overrides_sans_atout`, `test_no_consecutive_team_wins_invariant_when_rupture_active`.
  - **Verified clean (NOT bugs)**: the "dix-de-der double counting" the audit initially flagged turned out to be two independent counters (`play_card` writes the HUD's `current_round_points`; `score_round` derives from `completed_tricks`). The "underscore-boss-attr anti-pattern" is already pinned by `tests/belatro/test_boss_modifiers_integration.py::test_invariant_no_underscore_boss_attrs`. `AIMemory.last_voids_key` reset on new round is already correct and covered by `tests/test_ai.py::test_void_cache_invalidates_across_rounds`.
  - **Deferred to 3.7.0**: full `score_round()` / `play_card()` helper splits (L4/L5/R2/R3) — would need an intermediate `ScoringContext` dataclass to avoid 15-param helper signatures, which is its own refactor. Partner-jokers test coverage (T5) — broader surface than this audit's scope. Player-side coinche / surcoinche UI prompts when NS is taker (currently AI-only).
- 3.5.0 lands a 15-fix audit pass over the classic engine + BelAtro layer: C1 (consumables UI + Le Fou ordering), H1 (run-summary fsync), H2 (Key.EOF distinct from ESC), H3 (EventBus round-scope docs + `clear()`), M1 (declaration first-announcer tie-break), M3 (typed `RoundEndEvent.breakdown`), M4 (deprecate `partner_jokers_double`), M5 (SA belote invariant hoisted), L1 (`patch_trick_card` single-write), L2/L3 (doc pins), M2 (3 new benchmark micro-tests), P1/P2/P3 (perf hoist + cache-key + accumulator-profile analyses). +24 regression tests across 5 new files; 0 existing tests modified. Plan file at `/home/mrrobot/.claude/plans/bug-hunt-code-performance-tidy-meerkat.md`.
- 3.4.2 closed the 3.4.1 catalogue. All 7 confirmed bugs (C1 AI cheat under `hide_partner_hand`, C3 Dix de Der under La Rupture, C4 `opp_trumps` formula + TA total, H1 8 jokers seat→team, H4 TournoiAnte true 50%, H5 `load_profile` default unlocks, H7 classic-mode tie operator) plus H10 (`equip_joker` wires `on_purchase`) and M4 (delete dead `advance_turn`) shipped in 3.4.2. +17 regression tests (551 → 568). H2 (`LEgoiste` partner-trick nullification) remains deferred — needs a spec call between code-comment intent and the audit's reading.
- 3.4.1 was **documentation-only** — an external LLM audit was verified against the source. 7 confirmed bugs were catalogued in `CHANGELOG.md` as deferred to 3.4.2+; 8 audit claims were rejected as false positives and are listed in the "Verified clean" section to block re-investigation. No source code changed in 3.4.1.
- 3.4.0 covered: A1 `BidMadeEvent` double-fire on coinche paths (HIGH), E1 endless mode replaying Ante 8 Boss instead of advancing to the first scaled cycle (HIGH), E2 classic-mode tie-breaker overridden by main loop (HIGH), A2 termios raw-mode leak on SSH drop (MED), A3 shop selection index off-by-one after reroll (MED), A5 prompts.py dead return (LOW). Plus HUD additions: joker pip strip with edition glow (B.3), synergy tooltip (B.4), four-tier trust bar with tier glyph (B.5). Score gutter (B.2) and trick-lane compass (B.1) intentionally deferred — they touch `ui/render.py`'s vertical-centering logic and want a dedicated session.

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
trick winners, and round results to stderr — readable by terminal screen
readers (Orca, NVDA over WSL, VoiceOver via iTerm2).

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
