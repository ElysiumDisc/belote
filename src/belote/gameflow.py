from __future__ import annotations

import random
from dataclasses import replace

from . import a11y, settings
from .ai import AIPlayer, Difficulty
from .deck import Card, Contract, Suit
from .game import (
    SANS_ATOUT_BID,
    BidValue,
    Carre,
    GameState,
    Phase,
    Seat,
    Sequence,
    TrickCard,
    clear_announced,
    clear_legal_cards_cache,
    compute_trick_winners,
    start_round,
    team_of,
    trick_winner_seat,
)
from .input import KeyReader, interruptible_sleep
from .round_engine import RoundInterrupted, RoundPolicy, play_bidding, play_round, play_tricks
from .scoring import (
    ScoringBreakdown,
    apply_round_score,
    coinche_adjusted_credits,
    detect_carres,
    detect_sequences,
    get_declaration_points,
    is_capot,
    score_round,
    trick_card_points,
)
from .stats import update_stats_round
from .ui import (
    animate_score_update,
    announce,
    belote_stinger,
    display,
    patch_trick_card,
    prompt_bid,
    prompt_card,
    prompt_coinche,
    prompt_surcoinche,
    pulse_winner_glow,
    show_round_summary,
    slide_card_to_table_hint,
)
from .ui.announce import achievement_toast
from .ui.prompts import ExtensionKey

# Minimum time the four cards stay on the mat before a trick clears. This
# applies even when the user has skipped earlier animations (so a fast-paced
# session still lets the player read every completed trick).
MIN_TRICK_DWELL: float = 0.5


def create_ai_players(diffs_map: dict[Seat, str]) -> dict[Seat, AIPlayer]:
    """Create AI players for seats not occupied by humans."""
    ai_seats = {Seat.EAST, Seat.NORTH, Seat.WEST}
    return {s: AIPlayer(s, Difficulty(diffs_map[s])) for s in ai_seats}


def _is_player_capot(breakdown: ScoringBreakdown) -> bool:
    """True when the player's team (NS, team 0) took all 8 tricks.

    `is_capot` is set for a capot by EITHER team, so passing it straight to
    the stats credited EW capots to the player. The capot team is the taker
    if the contract stood, else the defenders (`_score_capot_outcome` sets
    `is_failed` when the defenders capot the taker).
    """
    if not breakdown.is_capot:
        return False
    capot_team = breakdown.taker_team if not breakdown.is_failed else 1 - breakdown.taker_team
    return capot_team == 0


def _contract_word(state: GameState) -> str | None:
    """Render the active contract as the lowercase a11y phrase used by the
    screen-reader announce calls. Returns None when no contract is set
    (caller decides whether to substitute "no trump" or omit the slot).
    """
    if state.contract == "sans_atout":
        return "sans atout"
    if state.trump == Suit.TOUT_ATOUT:
        return "tout atout"
    if state.trump is not None:
        return a11y._suit_word(state.trump.symbol)
    return None


def _undo_pop_to_south(
    history_stack: list[GameState], stack_base: int
) -> GameState | None:
    """Pop snapshots until the next state to act on is South's turn.

    `history_stack` is populated with the state captured BEFORE each
    `play_card` / `process_bid` (one push per move, AI moves included). A naive
    single pop after an AI sequence lands the user back inside that AI
    sequence, replaying it deterministically — visually the undo did nothing.
    Pop until the *restored* state's `turn` is SOUTH so the user lands on
    their own previous decision point. Returns None if `stack_base` is hit
    first (the caller restarts the round with a fresh deal).
    """
    restored: GameState | None = None
    while len(history_stack) > stack_base:
        restored = history_stack.pop()
        if restored.turn == Seat.SOUTH:
            return restored
    return None


def _bid_label(bid: BidValue) -> str:
    """Human-readable label for an AI bid. `BidValue` is `Suit | str | None`;
    this handles each shape so the AI announcement line doesn't crash when the
    bid is the Sans Atout sentinel string."""
    if bid is None:
        return "Pass"
    if bid == SANS_ATOUT_BID:
        return "Sans Atout"
    if bid == Suit.TOUT_ATOUT:
        return "Tout Atout"
    assert isinstance(bid, Suit)
    return bid.symbol


class ClassicRound(RoundPolicy[GameState]):
    """Classic Belote over the shared round engine: South is the human
    (prompts), the other seats are AI, every move is animated/announced and
    pushed onto the undo history."""

    def __init__(
        self,
        reader: KeyReader,
        ai_players: dict[Seat, AIPlayer],
        ai_delay: float,
        trick_pause: float,
        history: list[GameState],
        replay_decisions: list[tuple[GameState, Card]] | None = None,
    ) -> None:
        self.reader = reader
        self.ai_players = ai_players
        self.ai_delay = ai_delay
        self.trick_pause = trick_pause
        self.history = history
        self.replay_decisions = replay_decisions
        # Set when the player skips an animation; reset on the player's turn
        # (M6) and at each phase start.
        self.skip_anims = False

    # ── bidding ─────────────────────────────────────────────────────────

    def choose_bid(self, state: GameState, seat: Seat) -> BidValue:
        if seat != Seat.SOUTH:
            return self.ai_players[seat].decide_bid(state)
        self.skip_anims = False  # M6: reset the skip flag on the human's turn
        while True:
            display(state, None)
            res = prompt_bid(state, self.reader)
            if res == "QUIT":
                raise RoundInterrupted("QUIT")
            if res == "UNDO":
                raise RoundInterrupted("UNDO")
            if isinstance(res, ExtensionKey):
                continue  # only expansions register extension keys
            if isinstance(res, str) and res != SANS_ATOUT_BID:
                raise RoundInterrupted("QUIT")  # unknown sentinel: not a real bid
            return res

    def before_bid(self, state: GameState, seat: Seat, bid: BidValue) -> None:
        if seat != Seat.SOUTH:
            display(state, None)
            if bid is not None:
                message = f"{seat.name} takes it as {_bid_label(bid)}!"
                duration = (self.ai_delay * 2 + 0.5) if not self.skip_anims else 0
            else:
                message = f"{seat.name} passes"
                duration = self.ai_delay if not self.skip_anims else 0
            if announce(message, duration=duration, reader=self.reader) is not None:
                self.skip_anims = True
        self.history.append(state)

    def on_contract(self, state: GameState) -> GameState:
        # 4.9.0 / G1: post-bid coinche flow (defenders, then taker side).
        state = _run_coinche_flow(state, self.reader, self.ai_players)
        # 4.6.5 a11y: announce the locked contract at the bid→play transition.
        if state.taker is not None:
            a11y.announce_contract(state.taker, _contract_word(state) or "no trump")
        self.skip_anims = False  # a fresh phase starts with animations on
        return state

    # ── play ────────────────────────────────────────────────────────────

    def choose_card(self, state: GameState, seat: Seat) -> tuple[Card, GameState]:
        if seat != Seat.SOUTH:
            ai = self.ai_players[seat]
            ai.update_memory(state)
            return ai.decide_card(state), state
        self.skip_anims = False  # M6
        while True:
            display(state, None)
            state_before_south = state
            card, state = prompt_card(state, self.reader)
            if card is None:
                raise RoundInterrupted("QUIT")
            if isinstance(card, ExtensionKey):
                continue  # only expansions register extension keys; re-prompt
            if not isinstance(card, Card):
                raise RoundInterrupted("UNDO")
            if self.replay_decisions is not None:
                self.replay_decisions.append((state_before_south, card))
            return card, state

    def before_card(self, state: GameState, seat: Seat, card: Card) -> None:
        reader = self.reader
        # 1. Show the card on the mat IMMEDIATELY.
        display_state = replace(
            state, current_trick=state.current_trick + (TrickCard(seat, card),)
        )
        # 4.8.0 / C3: tactile launch trail when the player (SOUTH) plays a
        # card. AI seats skip — their plays feel different via the AI delay.
        if seat == Seat.SOUTH and not self.skip_anims:
            slide_card_to_table_hint(reader)
        if len(display_state.current_trick) == 1:
            display(display_state, None)
        else:
            patch_trick_card(display_state, seat, card)

        # 2. Short delay for cards 1-3 (the card is already on the mat; the
        # a11y path announces the play for screen-reader users).
        if (
            seat != Seat.SOUTH
            and len(display_state.current_trick) < 4
            and not self.skip_anims
            and interruptible_sleep(self.ai_delay, reader)
        ):
            self.skip_anims = True

        # 3. A completed trick: pause longer and show announcements.
        if len(display_state.current_trick) == 4:
            self._trick_complete_effects(state, display_state)

        # 3b. After the first trick, announce sequences / carrés.
        if len(display_state.current_trick) == 4 and len(state.completed_tricks) == 0:
            self._announce_declarations(state, display_state)

        # 4. Record the move for undo + screen readers.
        self.history.append(state)
        a11y.announce_play(state.turn, card)

    def _trick_complete_effects(self, state: GameState, display_state: GameState) -> None:
        reader, trick_pause = self.reader, self.trick_pause
        # Non-skippable minimum dwell so all four cards are always visible
        # before the trick clears (even after skipping / on "instant").
        interruptible_sleep(MIN_TRICK_DWELL, None)
        is_sa = state.contract == Contract.SANS_ATOUT
        # 4.8.0 / C4: brief gold pulse on the natural trick winner (a Rupture
        # swing only takes effect at scoring time, so the visual stays right).
        if not self.skip_anims:
            w = trick_winner_seat(
                display_state.current_trick, state.trump, state.variants.seven_eight_trump, is_sa
            )
            if w is not None:
                pulse_winner_glow(w, reader)
        if len(state.completed_tricks) == 7:  # the 8th trick
            # Rupture-aware projection (the 8th trick isn't in completed_tricks
            # yet) so the announcement names the team scoring actually credits.
            projected = list(state.completed_tricks) + [display_state.current_trick]
            winner = compute_trick_winners(state, state.trump, is_sa, tricks=projected)[-1]
            if winner:
                team = "NS" if team_of(winner) == 0 else "EW"
                announce(
                    f"Dix de Der (Team {team})",
                    duration=trick_pause * 0.8 if not self.skip_anims else 0,
                    reader=reader,
                )
                display(display_state, None)
            # Check for Capot while cards are still visible.
            if is_capot(state, tricks=projected) is not None:
                announce(
                    "CAPOT!",
                    duration=trick_pause * 1.2 if not self.skip_anims else 0,
                    reader=reader,
                )
                display(display_state, None)
        if not self.skip_anims and interruptible_sleep(trick_pause, reader):
            self.skip_anims = True

    def _announce_declarations(self, state: GameState, display_state: GameState) -> None:
        seq_names = {3: "Tierce", 4: "Quarte", 5: "Quinte"}
        for decl in state.declarations:
            if decl.kind not in ("sequence", "carre"):
                continue
            msg = f"{decl.seat.name}: {decl.kind.upper()}"
            if decl.kind == "sequence":
                length = decl.detail.length if isinstance(decl.detail, Sequence) else 0
                msg = f"{decl.seat.name}: {seq_names.get(length, 'Sequence')}"
            if isinstance(decl.detail, (Sequence, Carre)):
                a11y.announce_declaration(
                    decl.seat, decl.kind, get_declaration_points([decl.detail])
                )
            announce(
                msg,
                duration=self.trick_pause * 0.8 if not self.skip_anims else 0,
                reader=self.reader,
            )
            display(display_state, None)

    def after_card(
        self, before: GameState, state: GameState, seat: Seat, card: Card
    ) -> GameState:
        # A trick just closed: tell screen readers who won and for how much,
        # via the canonical scoring helper so zero-rank variants are honored.
        if (
            len(state.completed_tricks) > len(before.completed_tricks)
            and state.last_trick_winner is not None
        ):
            pts = trick_card_points(state, state.completed_tricks[-1])
            a11y.announce_trick_won(state.last_trick_winner, pts)
        if state.announced:
            # 4.8.0 / C5: Belote / Rebelote get the 4-row stinger; any other
            # announcement keeps the slim one-line `announce`.
            msg = state.announced
            dur = max(0.5, self.trick_pause * 0.6) if not self.skip_anims else 0
            if msg in ("Belote!", "Rebelote!"):
                belote_stinger(msg, duration=dur, reader=self.reader)
            else:
                announce(msg, duration=dur, reader=self.reader)
            state = clear_announced(state)
            display(state, None)
        return state


def run_bidding(
    state: GameState,
    reader: KeyReader,
    ai_players: dict[Seat, AIPlayer],
    ai_delay: float,
    history: list[GameState],
) -> GameState | str | None:
    """Run the bidding phase (+ coinche). Returns None if the user quits,
    'UNDO' if requested."""
    policy = ClassicRound(reader, ai_players, ai_delay, 0.0, history)
    try:
        return play_bidding(state, policy)
    except RoundInterrupted as stop:
        return None if stop.reason == "QUIT" else "UNDO"


def _run_coinche_flow(
    state: GameState,
    reader: KeyReader,
    ai_players: dict[Seat, AIPlayer],
) -> GameState:
    """4.9.0 / G1: after a bid locks, ask the defending side about coinche
    and (if coinched) the taker side about surcoinche. Returns the state
    with `coinche_level` updated."""
    from .game import team_of

    if state.taker is None:
        return state
    taker_team = team_of(state.taker)
    defenders = [s for s in (Seat.NORTH, Seat.EAST, Seat.SOUTH, Seat.WEST) if team_of(s) != taker_team]

    # Defender-side coinche check. SOUTH gets the interactive prompt; AI
    # defenders use `decide_coinche`. First defender to choose to coinche
    # locks it in (no need to poll the second defender — it's the team's
    # call, not the individual's).
    coincheur: Seat | None = None
    for seat in defenders:
        if seat == Seat.SOUTH:
            if prompt_coinche(state, reader):
                coincheur = seat
                break
        else:
            ai = ai_players[seat]
            if ai.decide_coinche(state):
                coincheur = seat
                break

    if coincheur is None:
        return state

    state = replace(state, coinche_level=1)
    announce(f"{coincheur.name} coinches! (×2)", duration=0.6, reader=reader)

    # Taker-side surcoinche check. Mirror logic: poll taker team in order.
    takers = [s for s in (Seat.NORTH, Seat.EAST, Seat.SOUTH, Seat.WEST) if team_of(s) == taker_team]
    for seat in takers:
        if seat == Seat.SOUTH:
            if prompt_surcoinche(state, reader, coincheur.name):
                state = replace(state, coinche_level=2)
                announce(f"{seat.name} surcoinches! (×4)", duration=0.6, reader=reader)
                break
        else:
            ai = ai_players[seat]
            # Reuse the same heuristic — symmetric on hand strength.
            if ai.decide_coinche(state):
                state = replace(state, coinche_level=2)
                announce(f"{seat.name} surcoinches! (×4)", duration=0.6, reader=reader)
                break

    return state


def run_play(
    state: GameState,
    reader: KeyReader,
    ai_players: dict[Seat, AIPlayer],
    ai_delay: float,
    trick_pause: float,
    history: list[GameState],
    replay_decisions: list[tuple[GameState, Card]] | None = None,
) -> GameState | str | None:
    """Run the play phase (all 8 tricks). Returns None if the user quits,
    'UNDO' if requested."""
    policy = ClassicRound(reader, ai_players, ai_delay, trick_pause, history, replay_decisions)
    try:
        return play_tricks(state, policy)
    except RoundInterrupted as stop:
        return None if stop.reason == "QUIT" else "UNDO"


def show_hand_preview(state: GameState, reader: KeyReader) -> None:
    """Show player's hand and estimated declaration points before bidding."""
    hand = state.hand_of(Seat.SOUTH)
    seqs = detect_sequences(hand)
    carres = detect_carres(hand)

    # Cast for type checker
    decls: list[Sequence | Carre] = []
    decls.extend(seqs)
    decls.extend(carres)

    pts = get_declaration_points(decls)

    # 3.0.0: brief deal-flourish announcement before the hand preview, so
    # the deal feels present rather than instant. The duration is short and
    # piggy-backs on the existing speed system via `announce()`'s reader
    # interrupt — pressing Space/Esc skips it just like other cutscene beats.
    announce("Dealing…", duration=0.4, reader=reader)
    display(state, None)
    if pts > 0:
        announce(f"Estimated declarations: {pts} pts", duration=1.5, reader=reader)
    else:
        announce("Bidding Phase Starts", duration=1.0, reader=reader)


def run_round(
    state: GameState,
    reader: KeyReader,
    ai_players: dict[Seat, AIPlayer],
    ai_delay: float,
    trick_pause: float,
    round_pause: float,
    history_stack: list[GameState],
    rng: random.Random | None = None,
) -> GameState | None:
    """Run a complete round: deal, bid, play, score. Returns None if user quits."""
    clear_legal_cards_cache()
    if rng is None:
        rng = random.Random()
    current = start_round(state, rng)
    stack_base = len(history_stack)  # mark start of this round in the shared stack
    # 3.0.0: Opt-in post-round replay analysis. Read the env var once per round
    # — toggling mid-round has no effect, and we avoid touching os.environ in
    # the per-card hot path. None disables capture entirely.
    replay_decisions: list[tuple[GameState, Card]] | None = (
        [] if settings.current().replay_analysis_on() else None
    )

    # Pre-game hand preview
    show_hand_preview(current, reader)

    policy = ClassicRound(
        reader, ai_players, ai_delay, trick_pause, history_stack, replay_decisions
    )
    while True:
        policy.skip_anims = False
        try:
            current = play_round(current, policy)
        except RoundInterrupted as stop:
            if stop.reason == "QUIT":
                return None
            # `legal_cards` memoizes on hand/trick tuple ids. After we restore
            # an earlier GameState, those tuples may again be live — flush so
            # we never serve a stale cached entry from before the undo.
            clear_legal_cards_cache()
            # Drop captured decisions so the replay matches the play that
            # actually finishes the round, not the rewound branch.
            if replay_decisions is not None:
                replay_decisions.clear()
            restored = _undo_pop_to_south(history_stack, stack_base)
            if restored is not None:
                current = restored
                announce("↶ Undo", duration=0.8, reader=reader)
                display(current, None)
                continue
            # Nothing left to undo in this round — restart with a fresh deal
            del history_stack[stack_base:]
            current = start_round(state, rng)
            announce("↶ Undo — fresh deal", duration=0.8, reader=reader)
            continue

        if current.phase == Phase.DEAL:  # All passed
            announce("All passed - Reshuffling!", duration=round_pause * 0.5, reader=reader)
            return current

        # Scoring Phase
        if current.phase == Phase.SCORING:
            breakdown = score_round(current)
            display(current, None)
            replay_str: str | None = None
            if replay_decisions:
                from .replay import analyze_round, summarize
                reports = analyze_round(replay_decisions, rng=current._rng)
                replay_str = summarize(reports)
            skip_round_pause = show_round_summary(
                current,
                breakdown,
                reader,
                timeout=round_pause,
                replay_summary=replay_str,
            )

            # Animate score update. Use the same coinche-adjusted credits that
            # apply_round_score stores, so the counter lands on the real total
            # (raw breakdown totals are pre-multiplier).
            ns_old, ew_old = current.team_scores
            taker_credit, defender_credit = coinche_adjusted_credits(
                breakdown, current.coinche_level
            )
            if breakdown.taker_team == 0:
                target_ns = ns_old + taker_credit
                target_ew = ew_old + defender_credit
            else:
                target_ns = ns_old + defender_credit
                target_ew = ew_old + taker_credit

            if not skip_round_pause:
                animate_score_update(current, target_ns, target_ew, reader=reader)

            # 4.6.5 a11y: speak the round result. Helper existed since 3.0.0
            # but had no caller; screen-reader users heard trick-by-trick
            # results without a round-summary line.
            a11y.announce_round_result(
                breakdown.taker_total,
                breakdown.defender_total,
                "north-south" if breakdown.taker_team == 0 else "east-west",
                contract=_contract_word(current),
            )

            # Update global stats
            trump_sym = current.trump.symbol if current.trump else None
            unlocked = update_stats_round(
                _is_player_capot(breakdown),
                breakdown.taker_total if breakdown.taker_team == 0 else breakdown.defender_total,
                trump_sym,
            )
            for achievement in unlocked:
                achievement_toast(achievement, reader)

            return apply_round_score(current, breakdown)
