"""3.9.0: NO_COLOR env-var support (https://no-color.org/).

When `NO_COLOR` is set to any non-empty value, `fg()` and `bg()` return the
empty string. SGR formatting (BOLD/DIM/REVERSE/UNDERLINE/STRIKETHROUGH) and
cursor/clear sequences are not affected — only color, per the spec.

Mirror the `BELOTE_A11Y` test pattern: monkeypatch the env, call
`_refresh_no_color_from_env()` to re-read the cached flag, restore in teardown
via the fixture so module state doesn't leak.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from belote import ansi


@pytest.fixture(autouse=True)
def _restore_no_color() -> Iterator[None]:
    """Snapshot _NO_COLOR before each test, restore after — keeps module
    state from leaking across tests in this file or to the broader suite."""
    saved = ansi._NO_COLOR
    yield
    ansi._NO_COLOR = saved


def test_fg_returns_empty_when_no_color_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    ansi._refresh_no_color_from_env()
    assert ansi.fg(255, 0, 0) == ""
    assert ansi.bg(0, 255, 0) == ""
    assert ansi.no_color_active() is True


def test_fg_emits_sgr_when_no_color_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    ansi._refresh_no_color_from_env()
    assert ansi.fg(255, 0, 0) == "\x1b[38;2;255;0;0m"
    assert ansi.bg(0, 255, 0) == "\x1b[48;2;0;255;0m"
    assert ansi.no_color_active() is False


def test_no_color_empty_string_means_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Per the no-color.org spec: NO_COLOR="" is treated as unset."""
    monkeypatch.setenv("NO_COLOR", "")
    ansi._refresh_no_color_from_env()
    assert ansi.no_color_active() is False
    assert ansi.fg(10, 20, 30) == "\x1b[38;2;10;20;30m"


def test_sgr_constants_unaffected_by_no_color() -> None:
    """BOLD/DIM/REVERSE/UNDERLINE/STRIKETHROUGH are SGR formatting, not color —
    must remain emittable under NO_COLOR per the spec."""
    assert ansi.BOLD == "\x1b[1m"
    assert ansi.DIM == "\x1b[2m"
    assert ansi.REVERSE == "\x1b[7m"
    assert ansi.UNDERLINE == "\x1b[4m"
    assert ansi.STRIKETHROUGH == "\x1b[9m"
    assert ansi.RESET == "\x1b[0m"
