"""Ghost Run recording (3.0.0) and reading (4.11.0).

A ghost is a JSON file capturing a BelAtro run: its seed, deck, every round's
bids and card plays, and — since format v2 (4.11.0) — the run's shape around
them: each blind's boss, target, deal seed and result, shop purchases /
sells / rerolls, consumable uses and joker acquisitions. The "Watch Ghost
Run" viewer (`ui/ghost_viewer.py`) replays a ghost round by round through the
real table renderer.

Format history:

* v1 (3.0.0) — ``{"version": 1, seed, deck_id, started_at, ended_at,
  events}`` with only ``bid`` / ``play`` / ``round_end`` events.
* v2 (4.11.0) — same top-level keys plus ``format``, ``label`` and
  ``outcome``; adds ``run_start``, ``round_start``, ``round_result``,
  ``buy``, ``sell``, ``reroll``, ``use``, ``acquire`` and ``run_end``
  events. ``bid`` / ``play`` / ``round_end`` are unchanged, so v1 files load
  through the same reader (rounds are then split on ``round_end``).

The save path lives next to the regular profile file.
"""

from __future__ import annotations

import contextlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..paths import data_dir

if TYPE_CHECKING:
    from belote.deck import Card
    from belote.game import BidValue, Seat

    from .core.run_state import BelAtroRun
    from .core.state import BelatroState
    from .run.boss import BossModifier
    from .ui.history import BelAtroHistoryEntry

GHOST_FORMAT = "belatro-ghost"
GHOST_VERSION = 2


def _ghost_dir() -> Path:
    path = data_dir() / "ghosts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _item_kind(item: object) -> str:
    from .items.base import Joker, Planet, Tarot, Voucher

    for cls, kind in ((Joker, "joker"), (Tarot, "tarot"), (Planet, "planet"), (Voucher, "voucher")):
        if isinstance(item, cls):
            return kind
    return "item"


def _item_fields(item: object) -> dict[str, Any]:
    return {
        "kind": _item_kind(item),
        "id": str(getattr(item, "id", "?")),
        "name": str(getattr(item, "name", "?")),
    }


def _suit_name(suit: object) -> str | None:
    return None if suit is None else str(getattr(suit, "name", suit)).lower()


class GhostRecorder:
    """Accumulates per-decision events during a run; flushed at run end.

    Usage:
        recorder = GhostRecorder(seed=12345, deck_id="republicain")
        # ... during play (round_driver / main / shop / run.consume):
        recorder.note_bid(seat="south", trump="hearts", contract="normal")
        recorder.note_play(trick=1, seat="south", card="J♥")
        # ... when the run ends (won or lost):
        path = recorder.save("won")
    """

    def __init__(self, seed: int, deck_id: str) -> None:
        self.seed = seed
        self.deck_id = deck_id
        self.started_at = int(time.time())
        self.events: list[dict[str, Any]] = []
        self.rounds_played = 0
        self.outcome: dict[str, Any] | None = None

    # ── round (round_driver) ───────────────────────────────────────────

    def note_bid(self, seat: str, trump: str | None, contract: str) -> None:
        self.events.append({"type": "bid", "seat": seat, "trump": trump, "contract": contract})

    def note_play(self, trick: int, seat: str, card: str) -> None:
        self.events.append({"type": "play", "trick": trick, "seat": seat, "card": card})

    def note_round_end(self, breakdown: dict[str, Any]) -> None:
        self.events.append({"type": "round_end", "breakdown": breakdown})

    # ── run shape (main) ───────────────────────────────────────────────

    def note_run_start(self, run: BelAtroRun) -> None:
        self.events.append(
            {
                "type": "run_start",
                "deck_id": run.deck_id,
                "ante": run.ante_number,
                "money": run.economy.money,
                "jokers": [str(getattr(j, "id", "?")) for j in run.jokers],
                "partner_jokers": [str(getattr(j, "id", "?")) for j in run.partner.jokers],
                "challenge": run.challenge,
                "boss_rush": run.boss_rush,
                "challenge_boss": run.challenge_boss_id,
                "daily": run.daily,
            }
        )

    def note_round_start(
        self,
        run: BelAtroRun,
        *,
        boss: BossModifier | None,
        round_seed: int,
        target: int,
    ) -> None:
        self.events.append(
            {
                "type": "round_start",
                "ante": run.ante_number,
                "blind": run.blind_index,
                "endless_offset": run.endless_ante_offset,
                "boss": boss.id if boss is not None else None,
                "boss_name": boss.name if boss is not None else None,
                "target": target,
                "round_seed": round_seed,
                "money": run.economy.money,
                "jokers": [str(getattr(j, "id", "?")) for j in run.jokers],
            }
        )

    def note_round_result(
        self, run: BelAtroRun, entry: BelAtroHistoryEntry, final_state: BelatroState
    ) -> None:
        self.rounds_played += 1
        self.events.append(
            {
                "type": "round_result",
                "ante": entry.ante,
                "blind": entry.blind_label,
                "boss_name": entry.boss_name,
                "score": entry.score,
                "target": entry.target,
                "status": entry.status,
                "contract": entry.contract,
                "taker": entry.taker_label,
                "tricks_ns": entry.tricks_ns,
                "tricks_ew": entry.tricks_ew,
                "money": run.economy.money,
                "money_delta": entry.money_delta,
                **trick_summary(final_state),
            }
        )

    def note_run_end(self, run: BelAtroRun, *, won: bool) -> None:
        self.outcome = {
            "won": won,
            "ante": run.ante_number,
            "blind": run.blind_index,
            "endless": run.endless,
            "rounds": self.rounds_played,
        }
        self.events.append(
            {
                "type": "run_end",
                **self.outcome,
                "money": run.economy.money,
                "jokers": [str(getattr(j, "id", "?")) for j in run.jokers],
            }
        )

    # ── shop / consumables (run/shop.py, BelAtroRun.consume) ───────────

    def note_buy(self, item: object, cost: int) -> None:
        event = {"type": "buy", **_item_fields(item), "cost": cost}
        edition = getattr(getattr(item, "edition", None), "value", "none")
        if edition != "none":
            event["edition"] = edition
        if getattr(item, "for_partner", False):
            event["for_partner"] = True
        self.events.append(event)

    def note_sell(self, joker: object, value: int) -> None:
        self.events.append({"type": "sell", **_item_fields(joker), "value": value})

    def note_reroll(self, cost: int) -> None:
        self.events.append({"type": "reroll", "cost": cost})

    def note_use(self, item: object) -> None:
        self.events.append({"type": "use", **_item_fields(item)})

    def note_acquire(self, item: object, source: str) -> None:
        self.events.append({"type": "acquire", **_item_fields(item), "source": source})

    def note_loan(self, amount: int) -> None:
        """5.0.0: L'Usurier's loan taken."""
        self.events.append({"type": "loan", "amount": amount})

    def note_repay(self, amount: int) -> None:
        self.events.append({"type": "repay", "amount": amount})

    def note_skip(self, ante: int, blind: int, medal: str | None) -> None:
        """5.0.0: a blind skipped from the shop for a Médaille."""
        self.events.append({"type": "skip", "ante": ante, "blind": blind, "medal": medal})

    # ── persistence ────────────────────────────────────────────────────

    def to_record(self, label: str = "run") -> dict[str, Any]:
        return {
            "format": GHOST_FORMAT,
            "version": GHOST_VERSION,
            "label": label,
            "seed": self.seed,
            "deck_id": self.deck_id,
            "started_at": self.started_at,
            "ended_at": int(time.time()),
            "outcome": self.outcome,
            "events": self.events,
        }

    def save(self, label: str = "run") -> Path:
        """Write the recorded events to ``<ghosts>/<label>-<seed>-<ms>.json``.

        The millisecond timestamp keeps runs that share a label + seed (e.g.
        two "ante3" losses) from overwriting each other's file.
        """
        stamp = int(time.time() * 1000)
        path = _ghost_dir() / f"{label}-{self.seed}-{stamp}.json"
        while path.exists():
            stamp += 1
            path = _ghost_dir() / f"{label}-{self.seed}-{stamp}.json"
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(self.to_record(label), f, indent=2)
        except OSError:
            # Best-effort: ghost recording is non-essential.
            pass
        return path


def trick_summary(state: BelatroState) -> dict[str, list[Any]]:
    """Per-trick winners, card points and trump of a finished round — what
    the viewer needs to replay it without re-deriving boss rules."""
    from belote.config import GLOBAL_CONFIG
    from belote.deck import Contract
    from belote.game import compute_trick_winners, per_trick_trumps
    from belote.scoring import trick_card_points

    tricks = state.completed_tricks
    is_sa = state.contract == Contract.SANS_ATOUT
    winners = compute_trick_winners(state, state.trump, is_sa)
    trumps = per_trick_trumps(state, state.trump, len(tricks))
    points = [trick_card_points(state, t) for t in tricks]
    if len(points) == 8 and not state.variants.no_dix_de_der:
        points[-1] += GLOBAL_CONFIG.LAST_TRICK_BONUS
    return {
        "winners": [w.name.lower() if w is not None else None for w in winners],
        "trick_points": points,
        "trick_trumps": [_suit_name(t) for t in trumps],
    }


def list_ghosts() -> list[Path]:
    """Enumerate saved ghost files, oldest first."""
    try:
        return sorted(_ghost_dir().glob("*.json"))
    except OSError:
        return []


# ── reading (4.11.0) ───────────────────────────────────────────────────────


_SHOP_EVENTS = frozenset({"buy", "sell", "reroll", "use", "acquire", "skip", "loan", "repay"})


def parse_card(text: str) -> Card | None:
    """Inverse of ``repr(Card)`` ("10♥", "J♠"); None for anything else."""
    from belote.deck import CARD_SUITS, Card, Rank

    if len(text) < 2:
        return None
    suit = next((s for s in CARD_SUITS if s.symbol == text[-1]), None)
    rank = next((r for r in Rank if r.value == text[:-1]), None)
    if suit is None or rank is None:
        return None
    return Card(suit, rank)


def parse_seat(text: object) -> Seat | None:
    from belote.game import Seat

    if not isinstance(text, str):
        return None
    return next((s for s in Seat if s.name.lower() == text.lower()), None)


def parse_suit(text: object) -> Any:
    from belote.deck import Suit

    if not isinstance(text, str):
        return None
    return Suit.__members__.get(text.upper())


def bid_value(event: dict[str, Any]) -> BidValue:
    """The BidValue a recorded ``bid`` event stands for."""
    from belote.deck import Contract, Suit
    from belote.game import SANS_ATOUT_BID

    if event.get("contract") == Contract.SANS_ATOUT:
        return SANS_ATOUT_BID
    suit: Suit | None = parse_suit(event.get("trump"))
    return suit  # None = pass


@dataclass
class GhostRound:
    """One recorded blind: what was dealt, bid, played and scored."""

    index: int
    bids: list[tuple[Seat, BidValue]] = field(default_factory=list)
    plays: list[tuple[int, Seat, Card]] = field(default_factory=list)
    start: dict[str, Any] = field(default_factory=dict)  # v2 round_start
    result: dict[str, Any] = field(default_factory=dict)  # v2 round_result
    breakdown: dict[str, Any] = field(default_factory=dict)  # round_end
    shop: list[dict[str, Any]] = field(default_factory=list)  # events after it

    @property
    def title(self) -> str:
        ante = self.start.get("ante", self.result.get("ante"))
        blind = self.start.get("blind")
        label = ("Small", "Big", "Boss")[blind] if isinstance(blind, int) and 0 <= blind < 3 else ""
        label = label or str(self.result.get("blind", ""))
        boss = self.start.get("boss_name") or self.result.get("boss_name")
        parts = [f"Round {self.index + 1}"]
        if ante is not None:
            parts.append(f"Ante {ante} {label} Blind".replace("  ", " "))
        if boss:
            parts.append(f"Boss: {boss}")
        return " · ".join(parts)

    @property
    def round_seed(self) -> int | None:
        seed = self.start.get("round_seed")
        return seed if isinstance(seed, int) and not isinstance(seed, bool) else None

    def final_bids(self) -> list[tuple[Seat, BidValue]]:
        """The bids of the deal that was played. An all-pass deal (8 passes,
        then a redeal) leaves its bids in the log; drop them."""
        deal_start = 0
        passes = 0
        for i, (_seat, bid) in enumerate(self.bids):
            if bid is None:
                passes += 1
                if passes == 8:
                    deal_start, passes = i + 1, 0
            else:
                passes = 0
        return self.bids[deal_start:]

    def hands_from_plays(self) -> tuple[tuple[Card, ...], ...] | None:
        """Each seat's 8 cards, rebuilt from what it played (None when the
        round wasn't played out — e.g. a run quit mid-round)."""
        hands: list[list[Card]] = [[], [], [], []]
        for _trick, seat, card in self.plays:
            hands[seat.value].append(card)
        if any(len(h) != 8 for h in hands):
            return None
        return tuple(tuple(h) for h in hands)

    def contract(self) -> tuple[Seat | None, BidValue]:
        taker = next(((s, b) for s, b in reversed(self.final_bids()) if b is not None), None)
        return (taker[0], taker[1]) if taker is not None else (None, None)


@dataclass
class GhostFile:
    """A loaded ghost: header fields plus the events split into rounds."""

    path: Path | None
    version: int
    seed: int
    deck_id: str
    label: str
    events: list[dict[str, Any]]
    outcome: dict[str, Any] | None
    rounds: list[GhostRound]
    started_at: int = 0

    @property
    def summary(self) -> str:
        bits = [self.label or "run", f"seed {self.seed}", self.deck_id]
        if self.outcome is not None:
            bits.append(
                "WON" if self.outcome.get("won") else f"ended Ante {self.outcome.get('ante', '?')}"
            )
        bits.append(f"{len(self.rounds)} round{'s' if len(self.rounds) != 1 else ''}")
        if self.version < 2:
            bits.append("v1")
        return " · ".join(str(b) for b in bits)


def _int(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def split_rounds(events: list[dict[str, Any]]) -> list[GhostRound]:
    """Group a ghost's events into rounds.

    v2 rounds open on ``round_start``; v1 files (no round_start) close a
    round on ``round_end`` instead. Shop events attach to the round they
    follow. Malformed events are skipped, not fatal.
    """
    rounds: list[GhostRound] = []
    has_starts = any(e.get("type") == "round_start" for e in events)
    current: GhostRound | None = None

    def _open() -> GhostRound:
        rnd = GhostRound(index=len(rounds))
        rounds.append(rnd)
        return rnd

    for event in events:
        kind = event.get("type")
        if kind == "round_start":
            current = _open()
            current.start = event
            continue
        if kind in _SHOP_EVENTS:
            if rounds:
                rounds[-1].shop.append(event)
            continue
        if kind not in ("bid", "play", "round_end", "round_result"):
            continue
        if current is None:
            current = _open()
        _absorb(current, event)
        if kind == "round_end" and not has_starts:
            current = None
    return rounds


def _absorb(rnd: GhostRound, event: dict[str, Any]) -> None:
    kind = event.get("type")
    seat = parse_seat(event.get("seat"))
    if kind == "bid" and seat is not None:
        rnd.bids.append((seat, bid_value(event)))
    elif kind == "play" and seat is not None:
        card = parse_card(str(event.get("card", "")))
        if card is not None:
            rnd.plays.append((_int(event.get("trick")), seat, card))
    elif kind == "round_end":
        breakdown = event.get("breakdown")
        rnd.breakdown = breakdown if isinstance(breakdown, dict) else {}
    elif kind == "round_result":
        rnd.result = event


def load_ghost(path: Path) -> GhostFile | None:
    """Read a ghost file (v1 or v2). None when it isn't a readable ghost."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return ghost_from_dict(data, path)


def ghost_from_dict(data: object, path: Path | None = None) -> GhostFile | None:
    if not isinstance(data, dict):
        return None
    events = data.get("events")
    if not isinstance(events, list):
        return None
    events = [e for e in events if isinstance(e, dict)]
    outcome = data.get("outcome")
    label = data.get("label")
    if not isinstance(label, str):
        label = path.stem.split("-")[0] if path is not None else "run"
    with contextlib.suppress(TypeError, ValueError):
        return GhostFile(
            path=path,
            version=_int(data.get("version"), 1),
            seed=_int(data.get("seed")),
            deck_id=str(data.get("deck_id", "classique")),
            label=label,
            events=events,
            outcome=outcome if isinstance(outcome, dict) else None,
            rounds=split_rounds(events),
            started_at=_int(data.get("started_at")),
        )
    return None


def load_all_ghosts() -> list[GhostFile]:
    """Every readable ghost, newest first."""
    ghosts = [g for g in (load_ghost(p) for p in list_ghosts()) if g is not None]
    ghosts.sort(key=lambda g: g.started_at, reverse=True)
    return ghosts
