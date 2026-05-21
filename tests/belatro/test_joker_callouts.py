"""Tests for the 4.8.0 / B1 joker-callout layer on slot_machine_tally."""
from __future__ import annotations

from belote.belatro.ui.announce import _classify_callout


def test_classify_callout_chips():
    glyph, color = _classify_callout("Foo Joker: +25 chips")
    assert glyph == "⚡"
    assert color  # non-empty colour prefix


def test_classify_callout_times_mult():
    glyph, _ = _classify_callout("Bar Joker: ×2.5 Mult")
    assert glyph == "✦"


def test_classify_callout_add_mult():
    glyph, _ = _classify_callout("Carnet: +1 Mult (South won trick)")
    # Additive-mult branch uses the same star glyph as the multiplicative.
    assert glyph == "✦"


def test_classify_callout_money():
    glyph, _ = _classify_callout("L'Architecte: +$2 (Annonce trick)")
    assert glyph == "$"


def test_classify_callout_unknown_falls_back_to_lightning():
    glyph, _ = _classify_callout("Weird entry with no markers")
    assert glyph == "⚡"
