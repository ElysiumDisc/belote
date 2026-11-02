"""4.11.0 — "Watch Ghost Run": replay a saved ghost through the real table.

Each round is rebuilt from the ghost alone:

* the 8-card hands come from the recorded plays (every card of a finished
  round is played, so each seat's plays ARE its hand). When the ghost has the
  round's deal seed (format v2), the deal is re-dealt from that seed with the
  core engine (`start_round` + the recorded bids through `place_bid`) and
  checked against those hands — the frame then also carries the engine's
  dealer and declarations; a mismatch (e.g. an all-pass redeal, whose cards
  come from the run's RNG stream) falls back to the play-derived deal;
* the recorded plays are laid onto the table one card at a time and drawn
  with the classic renderer (`belote.ui.render.display`);
* trick winners / points come from the v2 ``round_result`` (so boss rules
  such as La Rupture or L'Anarchie replay exactly), else from the core
  trick-winner rule.

Controls: ``+`` / ``-`` speed, Space / ``p`` pause, → step while paused,
``n`` / Enter skip the round, Esc / ``q`` quit.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from belote.ansi import (
    BOLD,
    DIM,
    RESET,
    REVERSE,
    ansi_center,
    clear_screen,
    clear_to_eol,
    gold_fg,
    hide_cursor,
    light_gray_fg,
    move,
    white_fg,
)
from belote.input import Key

if TYPE_CHECKING:
    from belote.deck import Card
    from belote.game import GameState, Seat
    from belote.input import KeyEvent, KeyReader

    from ..ghost_run import GhostFile, GhostRound

DEFAULT_DELAY = 0.6
MIN_DELAY = 0.05
MAX_DELAY = 3.0
_SPEED_STEP = 1.5
CONTROLS = "+/- speed   Space pause   n skip round   Esc quit"


@dataclass(frozen=True)
class ReplayFrame:
    state: GameState
    caption: str
    hold: float = 1.0  # multiple of the current per-frame delay


@dataclass
class ReplayControl:
    delay: float = DEFAULT_DELAY
    paused: bool = False

    def faster(self) -> None:
        self.delay = max(MIN_DELAY, self.delay / _SPEED_STEP)

    def slower(self) -> None:
        self.delay = min(MAX_DELAY, self.delay * _SPEED_STEP)

    @property
    def speed_label(self) -> str:
        return f"{DEFAULT_DELAY / self.delay:.1f}x" + (" PAUSED" if self.paused else "")


# ── round reconstruction (pure) ────────────────────────────────────────────


def _same_hands(a: tuple[tuple[Card, ...], ...], b: tuple[tuple[Card, ...], ...]) -> bool:
    return all(set(x) == set(y) for x, y in zip(a, b, strict=True))


def deal_from_seed(rnd: GhostRound) -> GameState | None:
    """Re-deal the round from its seed and replay the recorded bids through
    the core engine. None when there is no seed, the deal was redealt, or the
    result disagrees with the recorded plays."""
    from belote.game import Phase, new_game, place_bid, start_round

    seed = rnd.round_seed
    hands = rnd.hands_from_plays()
    if seed is None or hands is None or rnd.final_bids() != rnd.bids:
        return None
    try:
        state = start_round(new_game(target=1000), random.Random(seed))
        for _seat, bid in rnd.bids:
            state = place_bid(state, bid)
    except Exception:  # a ghost from another build: fall back
        return None
    if state.phase != Phase.PLAYING or not _same_hands(state.hands, hands):
        return None
    return replace(state, hands=hands)


def round_base(rnd: GhostRound) -> tuple[GameState, bool] | None:
    """The table at the start of trick 1, and whether the seed verified it."""
    from belote.deck import Contract, Suit
    from belote.game import SANS_ATOUT_BID, GameState, Phase

    hands = rnd.hands_from_plays()
    if hands is None or not rnd.plays:
        return None
    seeded = deal_from_seed(rnd)
    if seeded is not None:
        return seeded, True
    taker, bid = rnd.contract()
    if bid == SANS_ATOUT_BID:
        trump, contract = None, Contract.SANS_ATOUT
    elif bid == Suit.TOUT_ATOUT:
        trump, contract = Suit.TOUT_ATOUT, Contract.TOUT_ATOUT
    else:
        trump, contract = (bid if isinstance(bid, Suit) else None), Contract.NORMAL
    first = rnd.plays[0][1]
    return (
        GameState(
            hands=hands,
            initial_hands=hands,
            trump=trump,
            contract=contract,
            taker=taker,
            dealer=_previous(first),
            leader=first,
            turn=first,
            phase=Phase.PLAYING,
        ),
        False,
    )


def _previous(seat: Seat) -> Seat:
    from belote.game import Seat

    return Seat((seat.value - 1) % 4)


def _trick_outcomes(
    rnd: GhostRound, base: GameState, tricks: list[tuple[Seat, Card]]
) -> tuple[list[Seat], list[int]]:
    """Winner and points of every trick (recorded when the ghost has them)."""
    from belote.config import GLOBAL_CONFIG
    from belote.deck import Contract
    from belote.game import TrickCard, compute_trick_winners
    from belote.scoring import trick_card_points

    from ..ghost_run import parse_seat

    n = len(tricks) // 4
    recorded = rnd.result.get("winners")
    winners = [parse_seat(w) for w in recorded] if isinstance(recorded, list) else []
    pts = rnd.result.get("trick_points")
    points = [p for p in pts if isinstance(p, int)] if isinstance(pts, list) else []
    trick_tuples = tuple(
        tuple(TrickCard(s, c) for s, c in tricks[i * 4 : i * 4 + 4]) for i in range(n)
    )
    if len(winners) != n or any(w is None for w in winners):
        is_sa = base.contract == Contract.SANS_ATOUT
        computed = compute_trick_winners(base, base.trump, is_sa, trick_tuples)
        winners = [
            w if w is not None else t[0].seat for w, t in zip(computed, trick_tuples, strict=True)
        ]
    if len(points) != n:
        points = [trick_card_points(base, t) for t in trick_tuples]
        if n == 8:
            points[-1] += GLOBAL_CONFIG.LAST_TRICK_BONUS
    return [w for w in winners if w is not None], points


def _bid_label(bid: object) -> str:
    from belote.deck import Suit
    from belote.game import SANS_ATOUT_BID

    if bid == SANS_ATOUT_BID:
        return "Sans Atout"
    if bid == Suit.TOUT_ATOUT:
        return "Tout Atout"
    return bid.symbol if isinstance(bid, Suit) else "pass"


def replay_frames(rnd: GhostRound) -> list[ReplayFrame]:
    """Every table frame of one round, in order (empty if unplayable)."""
    from belote.game import TrickCard, team_of

    built = round_base(rnd)
    if built is None:
        return []
    base, verified = built
    taker, bid = rnd.contract()
    tag = "deal verified from seed" if verified else "deal rebuilt from plays"
    who = taker.name if taker is not None else "nobody"
    frames = [ReplayFrame(base, f"{rnd.title} — {_bid_label(bid)} by {who} ({tag})", 2.0)]
    ordered = [(seat, card) for _trick, seat, card in rnd.plays]
    winners, points = _trick_outcomes(rnd, base, ordered)
    hands = [list(h) for h in base.hands]
    state = base
    completed: tuple[tuple[TrickCard, ...], ...] = ()
    round_pts = [0, 0]
    trick: tuple[TrickCard, ...] = ()
    for seat, card in ordered:
        if card in hands[seat.value]:
            hands[seat.value].remove(card)
        trick = (*trick, TrickCard(seat, card))
        state = replace(
            state,
            hands=tuple(tuple(h) for h in hands),
            current_trick=trick,
            completed_tricks=completed,
            turn=seat.next_seat(),
        )
        k = len(completed)
        if len(trick) < 4 or k >= len(winners):
            frames.append(ReplayFrame(state, f"Trick {k + 1}: {seat.name} plays {card!r}"))
            continue
        winner = winners[k]
        round_pts[team_of(winner)] += points[k]
        frames.append(ReplayFrame(state, f"Trick {k + 1} → {winner.name} (+{points[k]} pts)", 1.5))
        completed = (*completed, trick)
        trick = ()
        state = replace(
            state,
            current_trick=(),
            completed_tricks=completed,
            last_trick_winner=winner,
            leader=winner,
            turn=winner,
            current_round_points=(round_pts[0], round_pts[1]),
            first_trick_done=True,
        )
    return frames


# ── text screens (pure) ────────────────────────────────────────────────────


def round_summary_lines(rnd: GhostRound) -> list[str]:
    """Result + the shop visit that followed a round."""
    res = rnd.result
    lines = [f"{BOLD}{gold_fg()}{rnd.title}{RESET}", ""]
    if res:
        lines.append(
            f"{res.get('status', '?')}: scored {res.get('score', '?')} / "
            f"target {res.get('target', '?')}   tricks {res.get('tricks_ns', '?')}-"
            f"{res.get('tricks_ew', '?')}   money ${res.get('money', '?')}"
        )
    elif rnd.breakdown:
        bd = rnd.breakdown
        lines.append(
            f"Taker {bd.get('taker_total', '?')} — defenders {bd.get('defender_total', '?')}"
            + ("  (contract failed)" if bd.get("is_failed") else "")
        )
    shop = [shop_line(e) for e in rnd.shop]
    if shop:
        lines += ["", f"{white_fg()}Between rounds:{RESET}", *shop[:8]]
        if len(shop) > 8:
            lines.append(f"{DIM}… and {len(shop) - 8} more{RESET}")
    return lines


def shop_line(event: dict[str, object]) -> str:
    kind = event.get("type")
    name = event.get("name", "?")
    if kind == "buy":
        where = " (partner slot)" if event.get("for_partner") else ""
        edition = f" [{event['edition']}]" if event.get("edition") else ""
        return f"  bought {name}{edition}{where} for ${event.get('cost', '?')}"
    if kind == "sell":
        return f"  sold {name} for ${event.get('value', '?')}"
    if kind == "reroll":
        return f"  rerolled the shop (${event.get('cost', '?')})"
    if kind == "use":
        return f"  used {name}"
    if kind == "acquire":
        return f"  gained {name} (from {event.get('source', '?')})"
    if kind == "loan":
        return f"  borrowed ${event.get('amount', '?')} from L'Usurier"
    if kind == "repay":
        return f"  repaid ${event.get('amount', '?')} to L'Usurier"
    if kind == "skip":
        from ..run.medals import MEDALS

        medal = MEDALS.get(str(event.get("medal")))
        raw = event.get("blind")
        blind = ("Small", "Big", "Boss")[raw] if isinstance(raw, int) and 0 <= raw <= 2 else "?"
        return f"  skipped the {blind} Blind" + (f" for {medal.name}" if medal else "")
    return f"  {kind}"


def picker_lines(ghosts: list[GhostFile], selected: int, term_w: int, max_rows: int) -> list[str]:
    lines = [ansi_center(gold_fg() + BOLD + "WATCH GHOST RUN" + RESET, term_w), ""]
    if not ghosts:
        lines += [
            ansi_center(white_fg() + "No ghost runs saved yet." + RESET, term_w),
            ansi_center(
                DIM + "Turn on 'Ghost run recording' in Settings, then play a run." + RESET,
                term_w,
            ),
            "",
            ansi_center(light_gray_fg() + "Esc: Back" + RESET, term_w),
        ]
        return lines
    top = max(0, min(selected - max_rows + 1, len(ghosts) - max_rows))
    for i, ghost in enumerate(ghosts[top : top + max_rows], start=top):
        text = ghost.summary[: max(20, term_w - 8)]
        color = REVERSE + gold_fg() + BOLD if i == selected else white_fg()
        lines.append(ansi_center(color + f" {text} " + RESET, term_w))
    lines += [
        "",
        ansi_center(light_gray_fg() + "↑↓ Choose   Enter: Watch   Esc: Back" + RESET, term_w),
    ]
    return lines


# ── interactive player ─────────────────────────────────────────────────────


def _paint_lines(lines: list[str]) -> None:
    from belote.ui.layout import vcenter_lines
    from belote.ui.render import get_term_size, invalidate_diff

    term_w, term_h = get_term_size()
    body = vcenter_lines([ansi_center(line, term_w) for line in lines], term_h)
    sys.stdout.write(clear_screen() + hide_cursor() + "\r\n".join(body))
    sys.stdout.flush()
    invalidate_diff()


def _paint_frame(frame: ReplayFrame, ctl: ReplayControl) -> None:
    from belote.game import Phase
    from belote.ui.render import display, get_term_size

    # Drawn outside the PLAYING phase so the phase line doesn't prompt
    # ">> YOUR TURN <<" during a replay.
    display(replace(frame.state, phase=Phase.DEAL), show_north_hand=True)
    term_w, term_h = get_term_size()
    status = f" GHOST {ctl.speed_label} │ {frame.caption}"
    footer = f"{status[: term_w - 1]}"
    sys.stdout.write(
        move(term_h, 1)
        + gold_fg()
        + footer
        + RESET
        + clear_to_eol()
        + move(term_h - 1, 1)
        + DIM
        + CONTROLS[: term_w - 1]
        + RESET
        + clear_to_eol()
    )
    sys.stdout.flush()


def _is_char(event: KeyEvent, *chars: str) -> bool:
    return event.char is not None and event.char.lower() in chars


def control_action(event: KeyEvent | None, ctl: ReplayControl) -> str:
    """Map one key (None = the frame delay elapsed) to an action:
    "next", "stay", "skip" or "quit"."""
    if event is None:
        return "next"
    key = event.key
    if key in (Key.ESC, Key.QUIT, Key.EOF):
        return "quit"
    if _is_char(event, "n") or key == Key.ENTER:
        return "skip"
    if key in (Key.SPACE, Key.MOUSE) or _is_char(event, " ", "p"):  # 5.0.0: click pauses
        ctl.paused = not ctl.paused
        return "stay" if ctl.paused else "next"
    if _is_char(event, "+", "="):
        ctl.faster()
        return "stay" if ctl.paused else "next"
    if _is_char(event, "-", "_"):
        ctl.slower()
        return "stay" if ctl.paused else "next"
    if key == Key.RIGHT:
        return "next"
    return "stay" if ctl.paused else "next"


def _wait(reader: KeyReader, ctl: ReplayControl, hold: float) -> str:
    event = reader.read() if ctl.paused else reader.read_timeout(ctl.delay * hold)
    return control_action(event, ctl)


def play_round(rnd: GhostRound, reader: KeyReader, ctl: ReplayControl) -> str:
    """Replay one round. Returns "done", "skip" or "quit"."""
    from belote.ui.render import invalidate_diff

    frames = replay_frames(rnd)
    invalidate_diff()
    i = 0
    while i < len(frames):
        _paint_frame(frames[i], ctl)
        action = _wait(reader, ctl, frames[i].hold)
        if action in ("skip", "quit"):
            return action
        if action == "next":
            i += 1
    return "done"


def watch_ghost(ghost: GhostFile, reader: KeyReader, ctl: ReplayControl | None = None) -> None:
    """Replay every round of `ghost`, with a summary card between rounds."""
    ctl = ctl or ReplayControl()
    for rnd in ghost.rounds:
        if play_round(rnd, reader, ctl) == "quit":
            return
        _paint_lines([*round_summary_lines(rnd), "", f"{DIM}{CONTROLS}{RESET}"])
        if _wait(reader, ctl, 4.0) == "quit":
            return
    outcome = ghost.outcome or {}
    verdict = "VICTORY" if outcome.get("won") else "End of the recording"
    _paint_lines(
        [
            f"{BOLD}{gold_fg()}{verdict}{RESET}",
            "",
            ghost.summary,
            "",
            f"{DIM}[Any key] Back{RESET}",
        ]
    )
    reader.read()


def show_ghost_picker(reader: KeyReader) -> None:
    """Menu entry: list saved ghosts, watch the chosen one."""
    from belote.ui.fit_guard import require_minimum
    from belote.ui.layout import vcenter_lines
    from belote.ui.render import get_term_size, invalidate_diff

    from ..ghost_run import load_all_ghosts

    ghosts = load_all_ghosts()
    selected = 0
    while True:
        require_minimum(reader)
        term_w, term_h = get_term_size()
        max_rows = max(3, term_h - 8)
        lines = vcenter_lines(picker_lines(ghosts, selected, term_w, max_rows), term_h)
        sys.stdout.write(clear_screen() + hide_cursor() + "\r\n".join(lines))
        sys.stdout.flush()
        invalidate_diff()
        from belote.ui import hitmap

        top = max(0, min(selected - max_rows + 1, len(ghosts) - max_rows))
        shown = range(top, min(len(ghosts), top + max_rows))
        hitmap.targets_from_lines(
            "menu",
            lines,
            [(ghosts[i].summary[: max(20, term_w - 8)], i) for i in shown],
            full_row=True,
        )
        event = reader.read()
        key = event.key
        if key == Key.MOUSE:  # 5.0.0: a click watches that run
            clicked = hitmap.hit("menu", event.pos)
            if isinstance(clicked, int):
                selected, key = clicked, Key.ENTER
        if key in (Key.ESC, Key.QUIT, Key.EOF):
            return
        if not ghosts:
            continue
        if key == Key.UP:
            selected = (selected - 1) % len(ghosts)
        elif key == Key.DOWN:
            selected = (selected + 1) % len(ghosts)
        elif key == Key.ENTER:
            watch_ghost(ghosts[selected], reader)
