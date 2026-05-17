from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class StartingDeck:
    id: str
    name: str
    description: str
    initial_money: int = 4
    initial_jokers: list[str] = field(default_factory=list)  # Store Joker IDs
    deck_modifications: dict[str, Any] = field(default_factory=dict)
    ascii_art: tuple[str, ...] = field(default_factory=tuple)


STARTING_DECKS: list[StartingDeck] = [
    StartingDeck(
        id="classique",
        name="Le Classique",
        description="Standard 32-card deck. Baseline.",
        ascii_art=(
            "  ┌──┐ ┌──┐ ┌──┐ ┌──┐  ",
            "  │♠ │ │♥ │ │♦ │ │♣ │  ",
            "  └──┘ └──┘ └──┘ └──┘  ",
            "  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ",
            "   32 cards  Baseline   ",
        ),
    ),
    StartingDeck(
        id="aristocrate",
        name="L'Aristocrate",
        description="All four Aces start with Gold Seal (+ cash).",
        initial_money=6,
        deck_modifications={"gold_seal_aces": True},
        ascii_art=(
            "  ┌──┐ ┌──┐ ┌──┐ ┌──┐  ",
            "  │A★│ │A★│ │A★│ │A★│  ",
            "  └──┘ └──┘ └──┘ └──┘  ",
            "    ★  Gold  Sealed  ★  ",
            "   Aces  bear  fortune  ",
        ),
    ),
    StartingDeck(
        id="republicain",
        name="Le Républicain",
        description="7s and 8s are wild — play them on any trick. +5 chips for every 7 or 8 your team captures.",
        ascii_art=(
            "  ┌──┐ ┌──┐  ★  ★  ★   ",
            "  │7★│ │8★│  wild cards ",
            "  └──┘ └──┘             ",
            "  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ",
            "  +5 chips per 7 or 8   ",
        ),
    ),
    StartingDeck(
        id="joueur",
        name="Le Joueur",
        description="Start with $10 extra cash. Boss Blind every 2 rounds.",
        initial_money=14,
        deck_modifications={"boss_every_2": True},
        ascii_art=(
            "   $   $   $   $   $    ",
            "  ┌──────────────────┐  ",
            "  │   START:  $14    │  ",
            "  └──────────────────┘  ",
            "   Boss  every 2 ants   ",
        ),
    ),
    StartingDeck(
        id="ermite",
        name="L'Ermite",
        description="Start with La Sentinelle Joker pre-installed.",
        initial_jokers=["la_sentinelle"],
        ascii_art=(
            "      ╔═══════════╗     ",
            "      ║   J ♠     ║     ",
            "      ╚═══════════╝     ",
            "      │   S T A Y │     ",
            "   Sentinel. Watching   ",
        ),
    ),
    StartingDeck(
        id="veteran",
        name="Le Vétéran",
        description="One Planet card pre-applied to your chosen suit.",
        deck_modifications={"free_planet": True},
        ascii_art=(
            "     ( · · · · )        ",
            "  ──── PLANET ─────     ",
            "   contract pre-levld   ",
            "  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ",
            "   Choose your trump    ",
        ),
    ),
    StartingDeck(
        id="flambeur",
        name="Le Flambeur",
        description="Start with L'Aventurier Partner Joker equipped.",
        initial_jokers=["l_aventurier"],
        ascii_art=(
            "   ? ! ? ! ? ! ? ! ?    ",
            "   ╔══════════╗         ",
            "   ║ COINCHE! ║         ",
            "   ╚══════════╝         ",
            "   Wild partner within  ",
        ),
    ),
    StartingDeck(
        id="anarchiste",
        name="L'Anarchiste",
        description="Start with extra $15. Corrupted Joker pool visible.",
        initial_money=19,
        deck_modifications={"corrupted_pool_visible": True},
        ascii_art=(
            "  ░░░░░░░░░░░░░░░░░░░   ",
            "  ░  CORRUPTED POOL  ░  ",
            "  ░  VISIBLE  + $15  ░  ",
            "  ░░░░░░░░░░░░░░░░░░░   ",
            "   Chaos  is  the path  ",
        ),
    ),
    StartingDeck(
        id="marseille",
        name="Le Marseillais",
        description="Annonces (Tierce/Quarte/Quinte) score x2. Belote/Rebelote disabled.",
        deck_modifications={"announce_x2": True, "no_belote_rebelote": True},
        ascii_art=(
            "  ╔════════════════════╗ ",
            "  ║  ANNONCES   ×2     ║ ",
            "  ║  Belote disabled    ║",
            "  ╚════════════════════╝ ",
            "   Old-school Marseille ",
        ),
    ),
    StartingDeck(
        id="coinche",
        name="Le Coincheur",
        description="Every round starts pre-coinched. +50 starting Chips, $8 starting cash.",
        initial_money=8,
        deck_modifications={"start_coinched": True, "start_chips_bonus": 50},
        ascii_art=(
            "    ★  COINCHE!  ★      ",
            "  ┌──────────────────┐  ",
            "  │  +50 Chips +$4   │  ",
            "  └──────────────────┘  ",
            "   Pre-coinched rounds  ",
        ),
    ),
    StartingDeck(
        id="infiltre",
        name="L'Infiltré",
        description="Ghost Lead: win a trick by playing a Trump on a suit you have ZERO of → +2 Mult, +$1.",
        deck_modifications={"ghost_lead": True},
        ascii_art=(
            "    ░░  GHOST  LEAD  ░░ ",
            "  ┌──┐  ╔══╗   void →    ",
            "  │A♥│  ║J♠║   atout!    ",
            "  └──┘  ╚══╝             ",
            "   +2 Mult  +$1 / void   ",
        ),
    ),
    StartingDeck(
        id="architecte",
        name="L'Architecte",
        description="Pay $10 in bidding to choose the contract yourself. Tricks containing a declared Annonce pay +$2.",
        initial_money=8,
        deck_modifications={"buy_contract": True, "annonce_cash_x2": True},
        ascii_art=(
            "    ┌──────────────┐    ",
            "    │ BUY CONTRACT │    ",
            "    │     $10      │    ",
            "    └──────────────┘    ",
            "   Annonce tricks +$2   ",
        ),
    ),
]
