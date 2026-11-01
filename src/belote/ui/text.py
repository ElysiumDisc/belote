"""Plain-text layout helpers shared by the full-screen overlays."""

from __future__ import annotations


def wrap_words(text: str, width: int, indent: str = "") -> list[str]:
    """Greedy word wrap: each line is `indent` + words, at most `width`
    characters wide (a word longer than that gets a line of its own). Never
    emits an empty line."""
    lines: list[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}" if line else word
        if line and len(indent) + len(candidate) > width:
            lines.append(indent + line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(indent + line)
    return lines
