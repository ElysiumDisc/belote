"""5.0.0 — click targets for mouse support.

Renderers record the screen rectangles of what can be clicked (`set_regions`,
per namespace: "hand", "shop", ...); a screen that reads a `Key.MOUSE` event
asks `hit` what lies under the pointer. Coordinates are 1-based terminal
cells, the same as `KeyEvent.pos`. Each render replaces its namespace, so a
stale target never outlives the frame that drew it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Region:
    row: int  # 1-based top row
    col: int  # 1-based left column
    height: int
    width: int
    target: object

    def contains(self, col: int, row: int) -> bool:
        return self.row <= row < self.row + self.height and self.col <= col < self.col + self.width


_regions: dict[str, tuple[Region, ...]] = {}


def set_regions(namespace: str, regions: Iterable[Region]) -> None:
    _regions[namespace] = tuple(regions)


def clear(namespace: str | None = None) -> None:
    if namespace is None:
        _regions.clear()
    else:
        _regions.pop(namespace, None)


def hit(namespace: str, pos: tuple[int, int] | None) -> object | None:
    """The target under `pos` (col, row) in `namespace`, or None. Later
    regions win where they overlap (drawn on top)."""
    if pos is None:
        return None
    col, row = pos
    for region in reversed(_regions.get(namespace, ())):
        if region.contains(col, row):
            return region.target
    return None


def targets_from_lines(
    namespace: str,
    lines: Sequence[str],
    labels: Sequence[tuple[str, object]],
    *,
    first_row: int = 1,
    pad: int = 2,
    full_row: bool = False,
) -> None:
    """Record click targets for a screen painted as `lines` (row `first_row`
    downwards): each (label, target) is found, in order, in the lines'
    visible text — the search resumes after the previous match, so a title
    that happens to contain a later label can't steal it. The region spans
    the label ± `pad` cells, or the whole row with `full_row`."""
    from ..ansi import _RESET_RE, visible_len

    plain = [_RESET_RE.sub("", line) for line in lines]
    regions: list[Region] = []
    row_i, from_char = 0, 0  # resume point: just after the previous match
    for label, target in labels:
        for i in range(row_i, len(plain)):
            idx = plain[i].find(label, from_char if i == row_i else 0)
            if idx < 0:
                continue
            row = first_row + i
            if full_row:
                regions.append(Region(row, 1, 1, 10_000, target))
                row_i, from_char = i + 1, 0
            else:
                col = visible_len(plain[i][:idx]) + 1
                width = visible_len(label) + 2 * pad
                regions.append(Region(row, max(1, col - pad), 1, width, target))
                row_i, from_char = i, idx + len(label)
            break
    set_regions(namespace, regions)


def select_or_act(clicked: object, selected: int) -> tuple[int, bool]:
    """The common two-step click: a click on another row selects it; a
    click on the selected row acts (Enter). Returns (selection, act)."""
    if not isinstance(clicked, int):
        return selected, False
    return clicked, clicked == selected
