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

# Full test suite (751 tests expected)
PYTHONPATH=src pytest
```

Current baseline (4.1.1):

- **751 tests** passing (4.1.0 had 742; +9 in 4.1.1: 4 in `tests/test_ai.py` (`test_ai_no_raw_card_points_import` structural pin, `test_hard_ai_play_score_uses_jacks_zero` + `_ban_clubs` discarding-strategy delta pins, `test_medium_ai_discard_consults_boss_modifier_helper` wrap pin), 3 in `tests/test_alt_screen_scroll.py` (`test_require_minimum_invalidates_diff_on_return`, `test_require_minimum_does_not_invalidate_if_never_paints`, `test_classic_ui_overlays_invalidate_diff` static check), 2 in `tests/test_announce_stats.py` (`test_show_stats_invalidates_diff`, `test_show_stats_builds_lines_once_across_keystrokes`)).
- 4.1.1 is a second audit pass over 4.1.0. The BelAtro layer came back clean; the classic engine + UI surfaced two real bugs and one P2 architectural fragility. **Verified bug fixes**: Hard / Medium AI *play* heuristics now route every card valuation through `scoring.card_points_with_modifiers` instead of raw `card_points` (4.1.0 fixed the bid path but missed `_medium_play:418/441`, `_score_card_play:640`, `_score_leading_strategy:668`) — without the fix, the AI evaluated cards at their pre-boss point value when scoring discards or probes under `aces_zero` / `kings_zero` / `jacks_zero` / `tens_zero` / `declarations_zero` / `ban_clubs`. `fit_guard.require_minimum` now invalidates the render-diff baseline before returning (closes the same overlay-residue family that 4.0.1 fixed across BelAtro overlays — the "Terminal too small" overlay was leaking the baseline). `show_stats` modal does the same on exit. **Performance**: `show_stats` line-list build hoisted out of the read loop (`load_stats()` + `SaveManager().load_profile()` now called once per modal invocation instead of per keystroke), with centered rendering cached per terminal width. Plan file at `/home/mrrobot/.claude/plans/foamy-plotting-wand.md`.

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
