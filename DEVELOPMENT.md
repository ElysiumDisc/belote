# Development Guide

Welcome to the Belote development guide. This project is structured as a standard Python package.

## Cheat Sheet

Everything below assumes you're in the repo with the venv active:

```bash
cd ~/Projects/belote
source .venv/bin/activate        # gives you `python`, `pip`, pytest, mypy, ruff
```

**1. Check everything is green (do this before every commit):**
```bash
PYTHONPATH=src python -m pytest -q && \
  PYTHONPATH=src python -m mypy --strict src/ && \
  python -m ruff check src/ tests/
```

**2. Push code to GitHub (no PyPI release):**
```bash
git status                       # see what changed — don't commit editor swap files
git add <files>                  # or: git add -A   (after checking git status)
git commit -m "what changed"
git push origin master
```

**3. Release a new version to PyPI** (example: 4.9.7):
```bash
# a) bump the version in BOTH files (they must match):
#      pyproject.toml          ->  version = "4.9.7"
#      src/belote/__init__.py  ->  __version__ = "4.9.7"
# b) add a "## 4.9.7" entry at the top of CHANGELOG.md
# c) run the gates (step 1), then commit, tag and push:
git add -A
git commit -m "Release v4.9.7"
git tag -a v4.9.7 -m "v4.9.7"
git push origin master --tags
# d) build, check and upload:
rm -rf dist/ build/ *.egg-info/
pipx run build --sdist --wheel
pipx run twine check dist/*
pipx run twine upload dist/*
#    username: __token__
#    password: your PyPI API token (starts with pypi-)
#    make one at https://pypi.org/manage/account/token/
```

**4. Update the game installed with pipx** (from PyPI — https://pypi.org/project/belote-cli/):
```bash
pipx install belote-cli          # first time only
pipx upgrade belote-cli          # after each release
belote --version                 # confirm the new version
```
PyPI can take a minute to show a new upload. If `pipx upgrade` says you're
already on the latest, wait a moment and retry, or force it with
`pipx install --force belote-cli`.

## Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd belote
   ```

2. **Create a virtual environment** (use `python3` — many Linux distros don't
   ship a bare `python` or `pip` outside a venv):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install in editable mode with the test + dev tools** (pytest, pytest-cov,
   mypy, ruff):
   ```bash
   pip install -e ".[test,dev]"
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

We use `pytest` (installed by `pip install -e ".[test,dev]"` above).

`tests/conftest.py` points `HOME`, `XDG_CONFIG_HOME` and `XDG_DATA_HOME` at a
throwaway temp dir for the whole run, so the suite never reads or writes your
real `~/.config/belote/theme.json`, stats or BelAtro saves, and always renders
with the default theme (the golden-frame snapshot depends on that).

Run tests:
```bash
# Run all tests (Classic + BelAtro)
PYTHONPATH=src pytest

# Run only Classic Belote tests (tests/belatro/ lives inside tests/)
PYTHONPATH=src pytest tests/ --ignore=tests/belatro

# Run only BelAtro tests
PYTHONPATH=src pytest tests/belatro/

# Run a single test file
PYTHONPATH=src pytest tests/test_game_logic.py
PYTHONPATH=src pytest tests/belatro/test_round_driver.py

# Run a single test by name
PYTHONPATH=src pytest tests/test_render_golden.py::test_golden_frame_sha256
PYTHONPATH=src pytest -k "capot"

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

# Full test suite (1228 tests expected)
PYTHONPATH=src pytest
```

Run all gates before committing:

```bash
PYTHONPATH=src python -m pytest --tb=short -q && \
  PYTHONPATH=src python -m mypy --strict src/ && \
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
results — readable by terminal screen readers (Orca, NVDA over WSL,
VoiceOver via iTerm2).

Where the lines go (4.9.7 — writing them onto the full-screen game used to
scroll and scramble the frame):

- `BELOTE_A11Y_OUT=/path` — appended to that file or terminal device, e.g.
  run `tty` in a second terminal and use its `/dev/pts/N`.
- otherwise stderr, when it's redirected (`belote 2>a11y.txt`) or is a
  different terminal from the game.
- otherwise `~/.local/share/belote/a11y.log` (`%APPDATA%\belote\a11y.log` on
  Windows) — follow it with `tail -f` in another terminal.

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
  `~/.local/share/belote/ghosts/<label>-<seed>-<timestamp>.json`. The file
  is written once when the run ends and never overwrites an earlier one. Useful for sharing or replaying interesting
  runs. Backed by `src/belote/belatro/ghost_run.py`.
- `NO_COLOR=<any-non-empty>` — suppress truecolor SGR escapes from
  `fg()` / `bg()` per the [no-color.org](https://no-color.org/) spec.
  Bold/dim/underline/reverse/strikethrough and cursor sequences remain
  (they aren't color). Added in 3.9.0. Backed by `src/belote/ansi.py`.
- `BELOTE_NO_ANIM=1` — short-circuit every animation helper (4.8.0
  baseline: `pulse_text`, `float_text`, `tick_bar`, the joker callouts,
  the shop purchase/reroll feedback, the trust-bar tick-up, the
  classic-mode trail / winner glow) to its end-state with no
  perceptible delay. 4.9.0's `interruptible_sleep_with_spinner` (G4
  AI-delay spinner) and `collect_trick_to_winner` (U3 trick-collection
  animation) were removed entirely in 4.9.3; AI pacing during card
  play now uses plain `interruptible_sleep`, and trick-end visuals are
  carried by the existing `pulse_winner_glow` banner alone.
  Useful on slow terminals, in CI, or under scripted runs. Read once at
  import; tests that mutate it must call
  `belote.ui.anim._refresh_animations_enabled_from_env()` after the
  patch. Independent of `BELOTE_NO_DIFF` — each lever is its own
  toggle. Backed by `src/belote/ui/anim.py`.
- `BELOTE_NO_DIFF=1` — disable the render-diff layer in
  `belote/ui/render.py::display`; every call paints a full frame
  instead of only changed rows. Escape hatch for debugging visual
  artifacts on uncommon terminal emulators.

## Releasing a New Version

The short version is in the [Cheat Sheet](#cheat-sheet) at the top. Details:

### Code-only update (push to GitHub without releasing a new PyPI version)

```bash
git add <files>
git commit -m "<what changed>"
git push origin master
```

### Full release (GitHub + PyPI)

1. **Run all gates** (see Code Quality) — don't release a red build.
2. **Bump the version** in BOTH `pyproject.toml` AND `src/belote/__init__.py`
   (they must stay in sync — `belote --version` / `belatro --version` read
   `__version__` while PyPI / pipx read `pyproject.toml`).
3. **Add a CHANGELOG entry** at the top of `CHANGELOG.md`.
4. **Commit, tag and push:**
   ```bash
   git add -A          # check `git status` first
   git commit -m "Release vX.Y.Z"
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin master --tags
   ```
5. **Clean stale build artifacts, then build, validate and upload:**
   ```bash
   rm -rf dist/ build/ *.egg-info/
   pipx run build --sdist --wheel
   pipx run twine check dist/*
   pipx run twine upload dist/*
   ```
   `twine upload` uses `~/.pypirc` if present; otherwise it prompts — enter
   `__token__` as the username and a PyPI API token as the password.
   PyPI never accepts the same version twice, so a botched upload means
   bumping to the next patch version.
6. **Update your own install:** `pipx upgrade belote-cli`.

## Performance measurement

`tests/test_perf_regression.py` is the in-suite guard: it times a few hot paths
(`render()`, `legal_cards()`, `score_round()`, `trick_card_points()`) and
fails only on a >2.5× regression vs `tests/perf_baselines.json`. Set
`BELOTE_SKIP_PERF=1` on slow CI to skip it.

When you need a deeper read or are about to re-baseline:

```bash
# Wider micro-benchmarks (render, AI decide, full BelAtro round)
PYTHONPATH=src python scripts/benchmark.py

# Then update tests/perf_baselines.json with the new medians, and record
# the date + host in the JSON's _comment field so future drift is interpretable.
```

If you suspect a per-frame allocation regression, the canonical hot paths to
profile live (e.g. with `py-spy record --rate 100`) are `render()` in
`src/belote/ui/render.py` and `_calculate_legal_cards_impl` in
`src/belote/game.py`. The 4.9.4 / 4.9.5 / 4.9.6 audit passes found only minor wins
beyond those already landed in the 4.6.x / 4.7.x perf cleanups (4.9.5 bumped
the `_pip_at` cache to 8192, trimmed `visible_len`'s cache to ANSI strings,
and memoised the BelAtro history overlay; 4.9.6 made `visible_len` measure
terminal *cells* via a minimal `char_width`, keeping the allocation-free
ASCII fast path so the hot path is unchanged) — start from a profiler trace,
not from guesswork, before adding new caches.
