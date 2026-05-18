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

# Full test suite (933 tests expected)
PYTHONPATH=src pytest
```

Current baseline (4.6.3):

- **933 tests** passing (4.6.2 had 926; +7 in 4.6.3: `tests/belatro/test_hud_toggle.py` pins the new `I`/`V` BelAtro top-HUD toggle).
- 4.6.3 is a UX fix: pressing `I` (or `V`) now toggles the BelAtro top-HUD overlay (joker pip strip, ante/blind/target line, chips×mult score, trust bar, synergy tooltip) so the classic Belote HUD's `Trump:` and `Taker:` fields on row 1 are reachable. Pre-fix, `render_joker_pip_strip` at `move(1, 2)` unconditionally painted over the leading ~24 chars of the classic HUD produced by `_build_hud()`, clobbering `T:♥` with no way to hide the overlay; the `I` key was already wired to `Key.OVERLAY` but only flashed a transient score popup. New flag `_top_hud_visible` in `src/belote/belatro/ui/announce.py` is consulted by `BelAtroHUD.render`, `render_joker_pip_strip`, `render_synergy_tooltip`, and `TrustBar.render`. The verbose classic-HUD hint string at `src/belote/ui/render.py:922` gained `[I]HUD` for discoverability. Auto trick-end score popup at `on_trick_end()` is unchanged.

Previous baselines:

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
