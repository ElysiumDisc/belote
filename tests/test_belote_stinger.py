"""Tests for the 4.8.0 `belote_stinger` banner used for Belote / Rebelote."""
from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout

announce = sys.modules["belote.ui.announce"]
render = sys.modules["belote.ui.render"]


def test_belote_stinger_paints_message_and_invalidates_diff():
    render._last_emitted_lines = ("dummy",)
    buf = io.StringIO()
    with redirect_stdout(buf):
        announce.belote_stinger("Belote!", duration=0)
    output = buf.getvalue()
    assert "Belote!" in output
    # Box-drawing frame chars are present (full banner, not the slim fallback).
    assert "╔" in output and "╝" in output
    assert render._last_emitted_lines is None


def test_belote_stinger_falls_back_on_tiny_terminal(monkeypatch):
    # Force a narrow terminal so the helper falls back to `announce()`.
    # belote.ui.announce imported `get_term_size` into its module namespace,
    # so we patch the bound name where it's looked up, not on `render`.
    monkeypatch.setattr(announce, "get_term_size", lambda: (10, 24))
    render._last_emitted_lines = ("dummy",)
    buf = io.StringIO()
    with redirect_stdout(buf):
        announce.belote_stinger("Rebelote!", duration=0)
    output = buf.getvalue()
    assert "Rebelote!" in output
    # No full frame on the slim fallback path.
    assert "╔" not in output
    assert render._last_emitted_lines is None
