"""Unit tests for the minimal wcwidth support added in 4.9.6.

`visible_len` measures terminal display *cells*, not codepoints. These pin the
per-character widths and the cell-correctness of the centering / justify /
truncate helpers, including the ASCII fast path and ANSI-escape skipping.
"""

from __future__ import annotations

from belote.ansi import (
    ansi_center,
    ansi_ljust,
    ansi_truncate,
    char_width,
    visible_len,
)

RED = "\x1b[31m"
RESET = "\x1b[0m"


def test_char_width_ascii() -> None:
    for ch in "aZ0 ?#":
        assert char_width(ch) == 1


def test_char_width_wide_cjk() -> None:
    assert char_width("世") == 2  # East-Asian Wide
    assert char_width("Ａ") == 2  # Fullwidth Latin A (U+FF21)


def test_char_width_emoji_wide() -> None:
    assert char_width("😀") == 2


def test_char_width_combining_zero() -> None:
    assert char_width("́") == 0  # combining acute accent
    assert char_width("​") == 0  # zero-width space (Cf)


def test_char_width_box_drawing_is_narrow() -> None:
    # Card-art borders must stay single-width or the felt would mis-align.
    for ch in "╭━┳╮╰╯│":
        assert char_width(ch) == 1


def test_visible_len_counts_cells() -> None:
    assert visible_len("abc") == 3
    assert visible_len("a世c") == 4  # 1 + 2 + 1
    assert visible_len("😀x") == 3


def test_visible_len_strips_ansi() -> None:
    assert visible_len(f"{RED}ab{RESET}") == 2
    assert visible_len(f"{RED}世{RESET}") == 2


def test_visible_len_ascii_fast_path_matches_len() -> None:
    s = "plain ascii string 123"
    assert visible_len(s) == len(s)


def test_ansi_center_is_cell_correct() -> None:
    assert visible_len(ansi_center("世", 5)) == 5
    assert visible_len(ansi_center(f"{RED}世界{RESET}", 10)) == 10


def test_ansi_ljust_is_cell_correct() -> None:
    out = ansi_ljust("世", 5)
    assert visible_len(out) == 5
    assert out.startswith("世")


def test_ansi_truncate_never_splits_wide_glyph() -> None:
    # 'a'(1) + '世'(2) = 3 cells; budget 2 must drop the wide glyph entirely.
    assert ansi_truncate("a世b", 2) == "a"
    assert ansi_truncate("a世b", 3) == "a世"


def test_ansi_truncate_ascii_and_fit() -> None:
    assert ansi_truncate("abc", 2) == "ab"
    assert ansi_truncate("abc", 5) == "abc"  # already fits → unchanged


def test_ansi_truncate_preserves_escapes() -> None:
    out = ansi_truncate(f"{RED}abc{RESET}", 2)
    assert out == f"{RED}ab"
    assert visible_len(out) == 2
