from __future__ import annotations

from typing import Any

from .base import Planet


class Saturn(Planet):
    id = "saturn"
    name = "Saturn"
    contract_id = "spades"
    description = "Level up Spades: +8 chips per trick won."
    suit_symbol = "♠"
    ascii_art = (
        "              ",
        "  ( · · · )   ",
        "  Saturn   ♪  ",
    )
    shop_lines = (
        " ♠ Trump:     ",
        " +8 chip/trick",
    )

    def level_up_reward(self) -> dict[str, Any]:
        return {"add_chips": 8}


class Venus(Planet):
    id = "venus"
    name = "Venus"
    contract_id = "hearts"
    description = "Level up Hearts: +0.3 Mult per trick won."
    suit_symbol = "♥"
    ascii_art = (
        "              ",
        "  ( ♥ ♥ ♥ )   ",
        "  Venus    ♪  ",
    )
    shop_lines = (
        " ♥ Trump:     ",
        " +0.3 Mult    ",
    )

    def level_up_reward(self) -> dict[str, Any]:
        return {"add_mult": 0.3}


class Mercury(Planet):
    id = "mercury"
    name = "Mercury"
    contract_id = "diamonds"
    description = "Level up Diamonds: +6 chips + $1 on round win."
    suit_symbol = "♦"
    ascii_art = (
        "              ",
        "  ( ·  ·  )   ",
        "  Mercury  ♪  ",
    )
    shop_lines = (
        " ♦ Trump:     ",
        " +6chip +$1   ",
    )

    def level_up_reward(self) -> dict[str, Any]:
        return {"add_chips": 6, "add_money": 1}


class Jupiter(Planet):
    id = "jupiter"
    name = "Jupiter"
    contract_id = "clubs"
    description = "Level up Clubs: +10 chips per Jack or 9 captured."
    suit_symbol = "♣"
    ascii_art = (
        "              ",
        "  ( ♣ · ♣ )   ",
        "  Jupiter  ♪  ",
    )
    shop_lines = (
        " ♣ Trump:     ",
        " +10chip/J,9  ",
    )

    def level_up_reward(self) -> dict[str, Any]:
        return {"jack_9_bonus": 10}


class TheSun(Planet):
    id = "the_sun"
    name = "The Sun"
    contract_id = "tout_atout"
    description = "Level up Tout Atout: +1 Mult per trick beyond the 4th."
    suit_symbol = "☀"
    ascii_art = (
        "   \\  |  /    ",
        "  --  ☀ --    ",
        "   /  |  \\    ",
    )
    shop_lines = (
        " Tout Atout:  ",
        " +1Mult/trick ",
    )

    def level_up_reward(self) -> dict[str, Any]:
        return {"bonus_mult_per_trick": 1.0}


class TheMoon(Planet):
    id = "the_moon"
    name = "The Moon"
    contract_id = "sans_atout"
    description = "Level up Sans Atout: +15 chips per honor won."
    suit_symbol = "☽"
    ascii_art = (
        "      )       ",
        "    (   )     ",
        "      )       ",
    )
    shop_lines = (
        " Sans Atout:  ",
        " +15chip/honor",
    )

    def level_up_reward(self) -> dict[str, Any]:
        return {"honor_bonus": 15}


class Pluto(Planet):
    id = "pluto"
    name = "Pluto"
    contract_id = "capot"
    description = "Level up Capot: Capot is worth 300 points instead of 252."
    suit_symbol = "✶"
    ascii_art = (
        "      ·       ",
        "    ──·──     ",
        "      ·       ",
    )
    shop_lines = (
        " Capot:       ",
        " worth 300pts ",
    )

    def level_up_reward(self) -> dict[str, Any]:
        return {"capot_bonus": 48}


class Libra(Planet):
    id = "libra"
    name = "Libra"
    contract_id = "coinche"
    description = "Level up Coinche: Successful Coinche pays ×4 instead of ×3."
    suit_symbol = "⚖"
    ascii_art = (
        "   /   \\      ",
        " ──  ⚖  ──    ",
        "   \\   /      ",
    )
    shop_lines = (
        " Coinche:     ",
        " pays ×4      ",
    )

    def level_up_reward(self) -> dict[str, Any]:
        return {"coinche_multiplier": 1.0}
