from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar

from belote.deck import Card, Suit

if TYPE_CHECKING:
    from ..core.run_state import BelAtroRun
    from ..engine.event_bus import (
        BeloteAnnouncedEvent,
        BidMadeEvent,
        CardCapturedEvent,
        DeclarationScoredEvent,
        RoundEndEvent,
        TrickWonEvent,
    )


def is_trump_card(card: Card, trump: Suit | None) -> bool:
    """Does `card` count as trump under `trump`?

    Under Tout Atout every card is trump, but `trump` is the `Suit.TOUT_ATOUT`
    marker that no card carries, so a bare `card.suit == trump` is always
    False there. Sans Atout (`trump=None`) has no trump at all.
    """
    return trump is not None and (trump == Suit.TOUT_ATOUT or card.suit == trump)


class Rarity(str, Enum):
    """Item rarity for shop weighting and unlock-gating."""

    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    LEGENDARY = "legendary"


class Edition(str, Enum):
    """3.0.0: optional Balatro-style joker editions, rolled at shop generation.

    Each edition stacks on top of the joker's normal triggers — Foil/Holo/
    Polychrome via ScoreAccumulator's per-trigger application path; Negative
    is consumed at purchase time (extra slot via run.joker_slots).
    """

    NONE = "none"
    FOIL = "foil"  # +50 chips per trigger
    HOLO = "holo"  # +10 mult per trigger
    POLYCHROME = "poly"  # ×1.5 mult per trigger
    NEGATIVE = "neg"  # +1 joker slot, doesn't consume one


@dataclass(frozen=True)
class JokerResult:
    """Payload returned by a joker handler. All fields are additive.

    Sign convention for `add_money` (4.6.5): positive = credit the player,
    negative = debit (cost), zero = no-op. The payout site in
    `belatro/main.py` routes negative values through `Economy.spend_money`;
    do NOT use `Economy.add_money` (which now rejects negatives) directly.
    See LePreteur in `items/jokers/economy.py` for a debit-style example.
    """

    add_chips: int = 0
    add_mult: float = 0.0
    times_mult: float = 0.0
    add_money: int = 0


class Joker(ABC):
    id: str
    name: str
    description: str
    cost: int = 7
    rarity: Rarity = Rarity.COMMON
    fusable: bool = True
    is_partner_joker: bool = False
    is_corrupted: bool = False
    # 4.11.0: unlockable jokers flagged secret stay out of the Collection
    # gallery (not even a "???" row) until the profile unlocks them; the
    # gallery shows a riddle hint instead (`secret_hint`).
    is_secret: bool = False
    secret_hint: str = ""
    # 4.11.0: Le Téléphone voucher — a shop offer stamped `for_partner=True`
    # equips onto the partner's own joker slots (PartnerState.jokers) instead
    # of the player's. Per-instance flag set by the shop; False everywhere else.
    for_partner: bool = False
    # 3.0.0: edition is mutable per-instance and stamped by the shop. Default
    # NONE for backward compatibility with existing tests that instantiate
    # jokers directly.
    edition: Edition = Edition.NONE
    # 3.4.0: short 2-char label used by the joker pip strip in the HUD. Sub-
    # classes may override; the default takes the first two ASCII letters of
    # `name` for instances that don't set their own. Resolved lazily so the
    # default doesn't snapshot during class definition before name is set.
    _shortcode_override: str = ""
    # 4.12.0: duplicate copies are safe. Every joker keys its per-round
    # joker_state entries through `state_key(...)`. The first copy keys on its
    # bare id (the historical `f"{id}_..."` keys, so tests, ghost files and
    # run-scoped counters are unchanged); later copies key on "id#2",
    # "id#3"… so two copies never share — and corrupt — a counter.
    # `assign_copy_indices` hands the indices out; per instance once set.
    copy_index: int = 0
    # 4.12.0 Le Serment: three copies sworn into one Arc-en-ciel joker. The
    # accumulator doubles every Chips / Mult / $ it pays (`doubled_result`).
    sworn: bool = False
    # joker_state key *names* (see `state_key`) that outlive the round:
    # `BelAtroGame._harvest_round_state` copies `state_key(name)` into
    # `run.card_enhancements`, which seeds the next round's joker_state.
    persistent_keys: ClassVar[tuple[str, ...]] = ()
    # 4.12.0: fusion results (Le Serment recipes) never appear in the shop.
    shop_excluded: ClassVar[bool] = False

    @property
    def state_prefix(self) -> str:
        """The joker_state namespace of this copy: the id, or "id#N"."""
        return self.id if self.copy_index == 0 else f"{self.id}#{self.copy_index + 1}"

    def state_key(self, name: str) -> str:
        """This copy's joker_state key for `name` (``f"{state_prefix}_{name}"``)."""
        return f"{self.state_prefix}_{name}"

    @property
    def display_name(self) -> str:
        """Name with the Arc-en-ciel mark of a sworn joker."""
        return f"{self.name} ✦" if self.sworn else self.name

    @property
    def shortcode(self) -> str:
        if self._shortcode_override:
            return self._shortcode_override[:2]
        # Strip non-letters (avoid leading "L'" or "Le " producing empty codes)
        letters = "".join(c for c in (self.name or self.id or "??") if c.isalpha())
        return (letters[:2] or "??").upper()

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        return None

    def on_belote(self, event: BeloteAnnouncedEvent, state: dict[str, Any]) -> JokerResult | None:
        return None

    def on_declaration(
        self, event: DeclarationScoredEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        return None

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        return None

    def on_round_end(self, event: RoundEndEvent, state: dict[str, Any]) -> JokerResult | None:
        return None

    def on_bid(self, event: BidMadeEvent, state: dict[str, Any]) -> JokerResult | None:
        return None

    def on_card_captured(
        self, event: CardCapturedEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        """5.0.0: your team captured an enhanced / sealed card (L'Atelier)."""
        return None

    def on_purchase(self, run: BelAtroRun) -> None:  # noqa: B027
        """Called once when the joker is bought. Apply permanent run-level effects here."""


class Planet(ABC):
    id: str
    name: str
    contract_id: str  # which contract this levels up
    level: int = 0
    cost: int = 4
    rarity: Rarity = Rarity.COMMON
    suit_symbol: str = "?"
    ascii_art: tuple[str, str, str] = (
        "              ",
        "   (  ?  ?  ) ",
        "   Planet  ♪  ",
    )
    shop_lines: tuple[str, str] = ("              ", "              ")

    @abstractmethod
    def level_up_reward(self) -> dict[str, Any]:
        """Returns a dict of stat bumps to apply to contract."""
        ...

    def use(self, run: BelAtroRun) -> None:
        """Apply this planet's level-up reward to the run's contract_levels."""
        reward = self.level_up_reward()
        existing = run.contract_levels.get(self.contract_id, {})
        merged: dict[str, Any] = {}
        for key, val in {**existing, **reward}.items():
            if key in existing and key in reward:
                merged[key] = existing[key] + reward[key]
            else:
                merged[key] = val
        run.contract_levels[self.contract_id] = merged


class Tarot(ABC):
    id: str
    name: str
    description: str
    cost: int = 4
    rarity: Rarity = Rarity.COMMON

    def refusal(self, run: BelAtroRun) -> str | None:
        """4.11.0: why this tarot can't be used right now, or None if it can.

        `BelAtroRun.consume` checks this BEFORE removing the card, so a tarot
        whose effect is momentarily impossible (Le Juge after its once-per-
        ante reroll) stays in the tray instead of being wasted.
        """
        return None

    @abstractmethod
    def use(self, run: BelAtroRun, context: object) -> None:
        """Apply the one-shot effect."""
        ...


class Voucher(ABC):
    """Permanent run-level upgrade.

    Subclasses implement `_apply_once(run)` for the actual effect. The base
    class wraps it with `apply(run)` which consults `run._applied_voucher_ids`
    to guarantee a no-op on a second invocation — important for vouchers that
    use `+=` semantics (LaTelescope's `+=` on joker_slots, LeCouteau's `+=`
    on consumable_slots, etc.) that would silently double-stack on a future
    save/load or replay round-trip.

    3.9.3 — guard relocated here from `Shop._apply_item` so any future
    caller of `voucher.apply()` (replays, deck-builder previews, etc.)
    inherits the same protection.
    """

    id: str
    name: str
    description: str
    cost: int = 10
    rarity: Rarity = Rarity.COMMON
    purchased: bool = False

    def apply(self, run: BelAtroRun) -> None:
        """Idempotent wrapper. Calls `_apply_once` only the first time per run."""
        if self.id in run._applied_voucher_ids:
            return
        run._applied_voucher_ids.add(self.id)
        self._apply_once(run)

    @abstractmethod
    def _apply_once(self, run: BelAtroRun) -> None:
        """Subclass-defined permanent effect. Called exactly once per run."""
        ...


def assign_copy_indices(jokers: Iterable[Joker]) -> None:
    """Give every copy of the same joker its own `copy_index` (4.12.0).

    Walks `jokers` in order; a joker whose index is already taken by an
    earlier copy of the same id gets the lowest free one. Indices already
    unique are left alone, so a copy keeps its joker_state namespace — and
    its run-scoped counters — for the rest of the run, even after another
    copy is sold. Idempotent.
    """
    taken: dict[str, set[int]] = {}
    for joker in jokers:
        joker_id = getattr(joker, "id", None)
        if joker_id is None:
            continue  # test doubles without an id have no state namespace
        used = taken.setdefault(joker_id, set())
        if joker.copy_index in used:
            index = 0
            while index in used:
                index += 1
            joker.copy_index = index
        used.add(joker.copy_index)


def doubled_result(result: JokerResult) -> JokerResult:
    """Le Serment's Arc-en-ciel payout: Chips, +Mult and $ doubled, and a
    ×Mult's bonus doubled (×1.5 → ×2, ×3 → ×5)."""
    return JokerResult(
        add_chips=result.add_chips * 2,
        add_mult=result.add_mult * 2,
        times_mult=(1.0 + 2 * (result.times_mult - 1.0)) if result.times_mult else 0.0,
        add_money=result.add_money * 2,
    )


# ── Phase 3.2: Joker fusion (Endless mode) ────────────────────────────────


_RARITY_LADDER = (Rarity.COMMON, Rarity.UNCOMMON, Rarity.RARE, Rarity.LEGENDARY)


class FusionError(Exception):
    """Raised when two jokers can't be fused (legendary, marked unfusable, etc.)."""


def fuse_jokers(a: Joker, b: Joker) -> Joker:
    """Combine two jokers into a single upgraded one.

    Rules:
    - Both must have `fusable=True`.
    - Neither may be Legendary (no compounding endgame ramps).
    - The result inherits the *first* joker's identity (id/name/desc/hooks),
      with `fusable=False` so it can't be re-fused, and rarity bumped one
      tier (clamped at RARE — never auto-promotes to LEGENDARY).
    """
    if not getattr(a, "fusable", True) or not getattr(b, "fusable", True):
        raise FusionError("One of the jokers is marked fusable=False")
    if a.rarity == Rarity.LEGENDARY or b.rarity == Rarity.LEGENDARY:
        raise FusionError("Legendary jokers cannot be fused")

    fused = type(a)()
    # Bump rarity one tier (clamp at RARE).
    base_idx = max(_RARITY_LADDER.index(a.rarity), _RARITY_LADDER.index(b.rarity))
    new_idx = min(base_idx + 1, _RARITY_LADDER.index(Rarity.RARE))
    fused.rarity = _RARITY_LADDER[new_idx]
    fused.fusable = False  # one-time fusion only
    # Carry over the better edition. type(a)() returns a fresh instance with
    # the class default (NONE), so without this the player would silently lose
    # any Foil/Holo/Polychrome they paid for. NEGATIVE is purchase-time only
    # (the extra slot was already granted) so it doesn't propagate through
    # fusion — fall back to NONE in that case.
    fused.edition = _better_edition(a.edition, b.edition)
    # Corruption is sticky — if either input was corrupted, so is the fusion.
    fused.is_corrupted = a.is_corrupted or b.is_corrupted
    # Stamp a marker so callers can identify fused jokers
    fused.name = f"{a.name} + {b.name}"
    return fused


_EDITION_RANK: dict[Edition, int] = {
    Edition.NONE: 0,
    Edition.NEGATIVE: 0,  # purchase-time only, doesn't survive fusion
    Edition.FOIL: 1,
    Edition.HOLO: 2,
    Edition.POLYCHROME: 3,
}


def _better_edition(a: Edition, b: Edition) -> Edition:
    pick = a if _EDITION_RANK[a] >= _EDITION_RANK[b] else b
    # NEGATIVE collapses to NONE post-fusion (slot already counted).
    return Edition.NONE if pick == Edition.NEGATIVE else pick
