"""5.0.0 — Atelier jokers: they trigger when your team captures an enhanced
or sealed card (`on_card_captured`, see `core/card_mods.py`)."""

from __future__ import annotations

from typing import Any

from ...engine.event_bus import CardCapturedEvent
from ..base import Joker, JokerResult, Rarity


class LeVitrier(Joker):
    """The glazier: glass is his trade, broken glass his living."""

    id = "le_vitrier"
    name = "Le Vitrier"
    description = "Each Verre card your team captures: +3 Mult. One that shatters: +$3 instead."
    cost = 6

    def on_card_captured(
        self, event: CardCapturedEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        if event.enhancement != "verre":
            return None
        return JokerResult(add_money=3) if event.shattered else JokerResult(add_mult=3.0)


class LeFerronnier(Joker):
    """Works the steel."""

    id = "le_ferronnier"
    name = "Le Ferronnier"
    description = "Each Acier card your team captures: +25 chips."
    cost = 5

    def on_card_captured(
        self, event: CardCapturedEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        return JokerResult(add_chips=25) if event.enhancement == "acier" else None


class LaVoyante(Joker):
    """Reads luck in the cards."""

    id = "la_voyante"
    name = "La Voyante"
    description = "Each Chance card your team captures: +1 Mult and +$1."
    cost = 5

    def on_card_captured(
        self, event: CardCapturedEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        return JokerResult(add_mult=1.0, add_money=1) if event.enhancement == "chance" else None


class LeSigillaire(Joker):
    """Keeper of the seals."""

    id = "le_sigillaire"
    name = "Le Sigillaire"
    description = "Each sealed card your team captures: +$1 and ×1.25 Mult."
    cost = 8
    rarity = Rarity.UNCOMMON

    def on_card_captured(
        self, event: CardCapturedEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        return JokerResult(add_money=1, times_mult=1.25) if event.seal else None
