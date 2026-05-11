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

# Full test suite (568 tests expected)
PYTHONPATH=src pytest
```

Current baseline (3.4.2):
- **mypy**: 0 errors (strict mode, 76 files)
- **ruff**: 0 violations
- **pytest**: 568 tests, 0 failures
- 3.4.2 closes the 3.4.1 catalogue. All 7 confirmed bugs (C1 AI cheat under `hide_partner_hand`, C3 Dix de Der under La Rupture, C4 `opp_trumps` formula + TA total, H1 8 jokers seat→team, H4 TournoiAnte true 50%, H5 `load_profile` default unlocks, H7 classic-mode tie operator) plus H10 (`equip_joker` wires `on_purchase`) and M4 (delete dead `advance_turn`) ship in 3.4.2. +17 regression tests (551 → 568). H2 (`LEgoiste` partner-trick nullification) remains deferred — needs a spec call between code-comment intent and the audit's reading.
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
