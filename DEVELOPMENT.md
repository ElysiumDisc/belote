# Development Guide

Welcome to the Belote development guide. This project is structured as a standard Python package.

## Cheat Sheet

Everything below assumes you're in the repo with the venv active:

```bash
cd ~/Projects/belote
source .venv/bin/activate        # gives you `python`, `pip`, pytest, mypy, ruff
```

**1. Check everything is green (do this before every commit — CI runs the same):**
```bash
PYTHONPATH=src python -m pytest -q && \
  PYTHONPATH=src python -m mypy --strict src/ && \
  python -m ruff check src/ tests/ scripts/ && \
  python -m ruff format --check src/ tests/ scripts/
```
Refactoring game logic? Also run the seeded fingerprints before and after
(see [Refactor safety](#refactor-safety-seeded-fingerprints)).

**2. Push code to GitHub (no PyPI release):**
```bash
git status                       # see what changed — don't commit editor swap files
git add <files>                  # or: git add -A   (after checking git status)
git commit -m "what changed"
git push origin master
```

**3. Release a new version to PyPI** (example: 4.11.0):
```bash
# a) bump the version in BOTH files (they must match):
#      pyproject.toml          ->  version = "4.11.0"
#      src/belote/__init__.py  ->  __version__ = "4.11.0"
# b) add a "## [4.11.0]" entry at the top of CHANGELOG.md
# c) run the gates (step 1), then commit, tag and push:
git add -A
git commit -m "Release v4.11.0"
git tag -a v4.11.0 -m "v4.11.0"
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

UI tests drive screens headlessly through `tests/harness.py` (4.11.0): the
`tui` fixture gives a fixed-size fake terminal, captured screen text (ANSI
stripped, split into repaints), isolated config/data dirs, and a
`ScriptedReader` fed key specs like `tui.reader("down", "down", "enter")` —
it returns EOF when the script runs out, so a stuck loop fails instead of
hanging. Use it for any new screen.

## Code Quality

Zero lint, format and type-check violations, enforced by CI
(`.github/workflows/ci.yml`: ruff + format + mypy on 3.13, the test suite on
Python 3.10 → 3.14):

```bash
PYTHONPATH=src mypy --strict src/              # 0 errors, strict mode
ruff check src/ tests/ scripts/                # 0 violations
ruff format --check src/ tests/ scripts/       # one style: `ruff format` it
PYTHONPATH=src pytest                          # whole suite, ~2 s
```

Lint rules worth knowing (`pyproject.toml`):

- **McCabe complexity ≤ 15 (C901), no exceptions** — split a function that
  grows past it (4.11.0 cleared the last offenders).
- **RUF** and **unused arguments** (ARG001/ARG004; tests are exempt). An
  argument kept only as an `lru_cache` key gets `# noqa: ARG001 — cache key`.
- RUF001-003 (ambiguous unicode) are off: é, ’ and ♥ are intentional.
- mypy has `ignore_missing_imports = false` — there are no third-party
  dependencies, so an unresolved import is always a real bug (it caught
  broken relative imports during the 4.11.0 package splits).

## Refactor safety: seeded fingerprints

`scripts/fingerprint.py` plays hundreds of deterministic rounds through the
real engines (450 classic games with random undo; 800 BelAtro rounds across
every boss with random joker loadouts) and hashes each round's final state
and event trail. A pure refactor must be byte-identical:

```bash
python scripts/fingerprint.py --save /tmp/before.json   # before
python scripts/fingerprint.py --check /tmp/before.json  # after
```

New BelAtro content legitimately changes the BelAtro half (the item pools
change) — re-baseline after adding content. Adding a field to `GameState` or
`RuleVariants` changes every digest too (the state's repr is hashed): confirm
the change is repr-only by stripping the new `, field=default` text from the
hashed repr and checking against the old baseline, then re-baseline. The script pins
`PYTHONHASHSEED`: set iteration order follows the per-process hash salt, so
anything that iterates a set of seats/suits/cards must not decide gameplay
(4.11.0 removed the last two such spots).

## Benchmarking

```bash
PYTHONPATH=src python scripts/benchmark.py   # micro-benchmarks
python scripts/hotspots.py                   # cProfile top-30: render / classic / BelAtro
python scripts/hotspots.py classic --sort tottime --top 15
```

4.11.0 numbers (Intel Core Ultra 7 258V, CPython 3.14): full-frame render
0.09 ms, `legal_cards` 0.002 ms, `score_round` 0.024 ms, one BelAtro round
1.06 ms. See also [Performance measurement](#performance-measurement).

## Architecture

Where things live (4.11.0 split the four largest modules into packages; every
old import path such as `belote.game.legal_cards` still works through
re-exports):

| Area | Modules |
|---|---|
| Rules | `game/` — `state` (GameState, seats), `legal` (legal cards, trick winner), `bidding`, `play`, `sorting`, `view` (`rotate_view`) |
| Scoring | `scoring/` — `announcements`, `tricks`, `round_score` |
| AI | `ai/` — `base` (memory), `easy` / `medium` / `hard` tier mixins, `player` (`AIPlayer`) |
| Table drawing | `ui/render.py` (frame assembly, diff renderer, `display`, `patch_trick_card`), `ui/cards.py`, `ui/table.py`, `ui/hud_classic.py`, `ui/layout.py` (presets, `fit_table`) |
| Round flow | `round_engine.py` (phase order), `gameflow.py` (classic policy), `table_modes.py` (solo / Spectate / Hot-seat) |
| Cosmetics | `cosmetics.py` (card backs, table frames, unlocks), `ui/customize.py` |

### The table always fits the terminal

`ui/layout.py::fit_table(cols, rows)` picks the largest card size whose
*essential* rows fit (`12 + 4 × card_h`: MINI 24, COMPACT 32, STANDARD 40,
SPACIOUS 48 rows) and then adds optional rows while they fit: highlight bar,
mat N/S labels, card readout, decorative frame, blank spacers. `render()`
records where it put the trick mat (`_MatGeometry`) and `patch_trick_card`
reuses that instead of re-deriving it. Add a row to the table? Count it in
`TableFit.height`, and `tests/test_table_fit.py` will hold you to it (no
frame may be taller than the terminal at any size).

### Table modes

`gameflow.ClassicRound` takes a `TableMode`: which seats are human, whether
it's hot-seat (the table is drawn from the device holder's chair via
`game.rotate_view`, with a pass-the-device screen between players), and an
optional spectator `PaceControl`. Only `SOLO` records statistics.

### Core game vs. BelAtro expansion

- **The core never imports BelAtro.** `tests/test_repo_layout.py` enforces
  it; only the composition root `belote/main.py` wires the expansion in via
  `belote/belatro/integration.py` (menu modes, stats section, settings
  toggle) and BelAtro installs its run-scoped hooks itself (history
  override, bid hint, extension keys I/V).
- **One round engine.** `belote/round_engine.py::play_round` owns the phase
  order (bidding with all-pass handling → contract → tricks). Classic
  (`gameflow.ClassicRound`) and BelAtro (`belatro/engine/round_driver.py::
  _RoundContext`) are `RoundPolicy` implementations — change the round's
  flow there, once.
- **Rule variants are core.** Boss / deck / voucher effects that change how
  Belote is played live on `GameState.variants` (`belote/variants.py`);
  bosses only switch variants on.
- **Expansion hooks into core features go through registries the core
  owns**, e.g. `cosmetics.register_unlock_provider` (BelAtro registers the
  "win a run" / Daily unlocks from `integration.py`) and
  `ui.render.set_overlay_provider` (BelAtro reports the rows its in-round
  HUD paints over, so the table is fitted between them).
- **BelAtro balance:** `python scripts/balance.py --trials 150 --ante 3`
  compares every joker's score / win rate with and without it over seeded
  real rounds — run it after adding or tuning content.
- **Expansion state rides on a subclass.** BelAtro's chips / mult / money /
  joker state live on `belatro/core/state.py::BelatroState`. Core
  transitions are generic over `GameState` subclasses and build states with
  `replace()`, so the subclass survives every move.

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

Players toggle these from the in-game **Settings** screen (`belote/settings.py`
→ `settings.json`; `settings.apply()` pushes the values into the modules).
The environment variables below still work and *override* the saved setting
while set — handy for debugging and CI. Each is read once at startup.

- `BELOTE_REPLAY=1` — after every Classic round, print a one-line summary
  of how often South's plays matched the Hard-AI's preferred line
  (e.g. `Replay: Optimal plays: 6/8 (75%)`). Educational only — never
  affects scoring. Backed by `src/belote/replay.py`.
- `BELOTE_GHOST=1` — silently record every BelAtro run, won or lost
  (format v2 since 4.11.0: seed, deck, per-round boss / target / result,
  bids, plays, shop activity, item use) to
  `~/.local/share/belote/ghosts/<label>-<seed>-<timestamp>.json`. Written
  once when the run ends (not for a run quit before its first blind); never
  overwrites an earlier file. Watch them from BelAtro → Watch Ghost Run
  (`belatro/ui/ghost_viewer.py`). Backed by `src/belote/belatro/ghost_run.py`.
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
fails only on a >2.5× regression vs `tests/perf_baselines.json`. CI sets
`BELOTE_SKIP_PERF=1` (shared runners are too noisy for a timing gate), so run
it locally before a release.

When you need a deeper read or are about to re-baseline:

```bash
# Wider micro-benchmarks (render, AI decide, full BelAtro round)
PYTHONPATH=src python scripts/benchmark.py

# Then update tests/perf_baselines.json with the new medians, and record
# the date + host in the JSON's _comment field so future drift is interpretable.
```

Start from `python scripts/hotspots.py` (or `py-spy record --rate 100` on
the real game). The canonical hot paths are `render()` in
`src/belote/ui/render.py` and `_calculate_legal_cards_impl` in
`src/belote/game/legal.py`. 4.11.0 found the round engines spending ~25% of
their time hashing `Card`s (the dataclass hash went through two Python-level
`Enum.__hash__` calls); `Card` now caches a small deterministic int hash
(classic rounds −21%). The 4.9.4 / 4.9.5 / 4.9.6 audit passes found only minor wins
beyond those already landed in the 4.6.x / 4.7.x perf cleanups (4.9.5 bumped
the `_pip_at` cache to 8192, trimmed `visible_len`'s cache to ANSI strings,
and memoised the BelAtro history overlay; 4.9.6 made `visible_len` measure
terminal *cells* via a minimal `char_width`, keeping the allocation-free
ASCII fast path so the hot path is unchanged) — start from a profiler trace,
not from guesswork, before adding new caches.
