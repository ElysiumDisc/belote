from __future__ import annotations

import os
import random
from dataclasses import replace

from . import a11y
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
    bidding_turn,
    clear_announced,
    clear_legal_cards_cache,
    compute_trick_winners,
    play_card,
    process_bid,
    start_round,
    team_of,
)
from .input import KeyReader, interruptible_sleep
from .scoring import (
    apply_round_score,
    detect_carres,
    detect_sequences,
    get_declaration_points,
    is_capot,
    score_round,
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
    pulse_winner_glow,
    show_round_summary,
    slide_card_to_table_hint,
)

# Minimum time the four cards stay on the mat before a trick clears. This
# applies even when the user has skipped earlier animations (so a fast-paced
# session still lets the player read every completed trick).
MIN_TRICK_DWELL: float = 0.5


def create_ai_players(diffs_map: dict[Seat, str]) -> dict[Seat, AIPlayer]:
    """Create AI players for seats not occupied by humans."""
    ai_seats = {Seat.EAST, Seat.NORTH, Seat.WEST}
    return {s: AIPlayer(s, Difficulty(diffs_map[s])) for s in ai_seats}


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


def run_bidding(
    state: GameState,
    reader: KeyReader,
    ai_players: dict[Seat, AIPlayer],
    ai_delay: float,
    history: list[GameState],
) -> GameState | str | None:
    """Run the bidding phase. Returns None if user quits, 'UNDO' if requested."""
    current = state
    skip_anims = False
    while current.phase == Phase.BIDDING:
        bidder = bidding_turn(current)

        if bidder == Seat.SOUTH:
            skip_anims = False  # M6: Reset skip flag when it's the human's turn
            display(current, None)
            res = prompt_bid(current, reader)
            if res == "QUIT":
                return None
            if res == "UNDO":
                return "UNDO"
            if res == "OVERLAY":
                # Classic mode has no separate score overlay; re-prompt for a real bid.
                continue
            if isinstance(res, str) and res != SANS_ATOUT_BID:
                # Sentinels like "QUIT"/"UNDO"/"OVERLAY" are not real bids.
                return None
            bid: BidValue = res
        else:
            ai = ai_players[bidder]
            bid = ai.decide_bid(current)
            display(current, None)
            if bid is not None:
                message = f"{bidder.name} takes it as {_bid_label(bid)}!"
                duration = (ai_delay * 2 + 0.5) if not skip_anims else 0
            else:
                message = f"{bidder.name} passes"
                duration = ai_delay if not skip_anims else 0
            if announce(message, duration=duration, reader=reader) is not None:
                skip_anims = True

        history.append(current)
        current = process_bid(current, bid)

    return current


def run_play(
    state: GameState,
    reader: KeyReader,
    ai_players: dict[Seat, AIPlayer],
    ai_delay: float,
    trick_pause: float,
    history: list[GameState],
    replay_decisions: list[tuple[GameState, Card]] | None = None,
) -> GameState | str | None:
    """Run the play phase (all 8 tricks). Returns None if user quits, 'UNDO' if requested."""
    current = state
    skip_anims = False

    while current.phase == Phase.PLAYING:
        player = current.turn
        if player == Seat.SOUTH:
            skip_anims = False  # M6: Reset skip flag when it's the human's turn
            display(current, None)
            state_before_south = current
            card, current = prompt_card(current, reader)
            if card is None:
                return None
            if card == "UNDO":
                return "UNDO"
            if card == "OVERLAY":
                # Classic mode has no separate score overlay; re-prompt for a real card.
                continue
            if card == "INVENTORY":
                # 4.7.0: V key opens the BelAtro inventory overlay. Classic
                # Belote has no run-state to inspect, so V is a no-op here
                # — re-prompt for a real card play.
                continue
            if not isinstance(card, Card):
                return "UNDO"
            if replay_decisions is not None:
                replay_decisions.append((state_before_south, card))
        else:
            ai = ai_players[player]
            ai.update_memory(current)
            card = ai.decide_card(current)

        # 1. Show the card on the mat IMMEDIATELY
        display_state = replace(
            current, current_trick=current.current_trick + (TrickCard(player, card),)
        )
        # 4.8.0 / C3: tactile launch trail when the player (SOUTH) plays a
        # card. Cheap (~120ms, skippable). AI seats skip — their plays
        # already feel different via the per-card AI delay below.
        if player == Seat.SOUTH and not skip_anims:
            slide_card_to_table_hint(reader)
        if len(display_state.current_trick) == 1:
            display(display_state, None)
        else:
            patch_trick_card(display_state, player, card)

        # 2. Short delay for cards 1, 2, 3. The card is already visible on the
        # mat from step 1 (display() or patch_trick_card just above); no text
        # banner is needed — pre-4.0.1 wrote "X plays Y" to stdout, which
        # scrolled the alt-screen and corrupted the diff baseline. The TTS
        # path in a11y.py:87 still announces the play independently for
        # screen-reader users.
        if (
            player != Seat.SOUTH
            and len(display_state.current_trick) < 4
            and not skip_anims
            and interruptible_sleep(ai_delay, reader)
        ):
            skip_anims = True

        # 3. If this completes a trick, pause longer and show announcements
        if len(display_state.current_trick) == 4:
            # Non-skippable minimum dwell so all four cards are always visible
            # before the trick clears, even when the user has skipped earlier
            # animations or is on the "instant" speed preset.
            interruptible_sleep(MIN_TRICK_DWELL, None)
            # 4.8.0 / C4: brief gold pulse identifying the trick winner. The
            # winner is the natural trick winner (pre-Rupture-override) for
            # the just-completed trick — Rupture's swing only takes effect
            # at scoring time, so the on-table visual stays accurate.
            if not skip_anims:
                from .game import trick_winner_seat as _twin
                is_sa = current.contract == Contract.SANS_ATOUT
                w = _twin(
                    display_state.current_trick,
                    current.trump,
                    current.boss_modifiers.seven_eight_trump,
                    is_sa,
                )
                if w is not None:
                    pulse_winner_glow(w, reader)
            if len(current.completed_tricks) == 7:  # This was the 8th trick
                is_sa = current.contract == Contract.SANS_ATOUT
                # Use the Rupture-aware helper so the announcement names the
                # team that actually gets credited in scoring (see
                # `compute_trick_winners` in game.py). Pass the projected
                # 8-trick list because the 8th trick hasn't been pushed to
                # `completed_tricks` yet. Reuse the list across the Capot
                # check below to avoid a redundant rebuild.
                projected = list(current.completed_tricks) + [display_state.current_trick]
                winner = compute_trick_winners(
                    current, current.trump, is_sa, tricks=projected
                )[-1]
                if winner:
                    team = "NS" if team_of(winner) == 0 else "EW"
                    announce(
                        f"Dix de Der (Team {team})",
                        duration=trick_pause * 0.8 if not skip_anims else 0,
                        reader=reader,
                    )
                    display(display_state, None)

                # Check for Capot while cards are still visible
                if is_capot(current, tricks=projected) is not None:
                    announce(
                        "CAPOT!", duration=trick_pause * 1.2 if not skip_anims else 0, reader=reader
                    )
                    display(display_state, None)

            if not skip_anims and interruptible_sleep(trick_pause, reader):
                skip_anims = True

        # 3b. If first trick completed, announce sequences/carres
        if len(display_state.current_trick) == 4 and len(current.completed_tricks) == 0:
            for decl in current.declarations:
                if decl.kind in ("sequence", "carre"):
                    msg = f"{decl.seat.name}: {decl.kind.upper()}"
                    if decl.kind == "sequence":
                        # Sequence length (3=tierce, 4=quarte, 5=quinte)
                        seq_names = {3: "Tierce", 4: "Quarte", 5: "Quinte"}
                        # Safely access length
                        length = 0
                        if isinstance(decl.detail, Sequence):
                            length = decl.detail.length
                        name = seq_names.get(length, "Sequence")
                        msg = f"{decl.seat.name}: {name}"

                    announce(
                        msg, duration=trick_pause * 0.8 if not skip_anims else 0, reader=reader
                    )
                    display(display_state, None)

        # 4. Transition to next state
        history.append(current)
        a11y.announce_play(current.turn, card)
        prior_completed = len(current.completed_tricks)
        current = play_card(current, card)
        # If a trick just closed, emit a11y hint for the winner. The pts use
        # the canonical scoring helper so boss zero-rank flags (Le Sauvage,
        # L'Iconoclaste, Le Roi Mort, Les Dix Maudits, Les Clubs Bannis)
        # are honoured — the screen-reader hears the same number the HUD
        # eventually shows.
        if (
            len(current.completed_tricks) > prior_completed
            and current.last_trick_winner is not None
        ):
            from .scoring import trick_card_points as _trick_pts
            pts = _trick_pts(current, current.completed_tricks[-1])
            a11y.announce_trick_won(current.last_trick_winner, pts)

        if current.announced:
            # 4.8.0 / C5: Belote / Rebelote get a dramatic 4-row centered
            # stinger; other announcements (none today, but the path is
            # generic) keep the slim one-line `announce`.
            msg = current.announced
            dur = max(0.5, trick_pause * 0.6) if not skip_anims else 0
            if msg in ("Belote!", "Rebelote!"):
                belote_stinger(msg, duration=dur, reader=reader)
            else:
                announce(msg, duration=dur, reader=reader)
            current = clear_announced(current)
            display(current, None)

    return current


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
        [] if os.environ.get("BELOTE_REPLAY") else None
    )

    # Pre-game hand preview
    show_hand_preview(current, reader)

    while True:
        # Bidding Phase
        res_bid = run_bidding(current, reader, ai_players, ai_delay, history_stack)
        if res_bid is None:
            return None
        if res_bid == "UNDO":
            # `legal_cards` memoizes on hand/trick tuple ids. After we restore
            # an earlier GameState, those tuples may again be live — flush so
            # we never serve a stale cached entry from before the undo.
            clear_legal_cards_cache()
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
        current = res_bid  # type: ignore[assignment]

        if current.phase == Phase.DEAL:  # All passed
            announce("All passed - Reshuffling!", duration=round_pause * 0.5, reader=reader)
            return current

        # 4.6.5 a11y: announce the locked contract at bid→play transition.
        # Without this, screen-reader users heard card plays and trick winners
        # but never the trump / Tout Atout / Sans Atout context. Classic
        # Belote has no coinche concept — that lives in BelAtro's
        # `round_driver` only, so coinche_level defaults to 0 here.
        if current.taker is not None:
            a11y.announce_contract(current.taker, _contract_word(current) or "no trump")

        # Play Phase
        res_play = run_play(
            current, reader, ai_players, ai_delay, trick_pause, history_stack,
            replay_decisions=replay_decisions,
        )
        if res_play is None:
            return None
        if res_play == "UNDO":
            clear_legal_cards_cache()
            # Drop captured decisions so the replay matches the play that
            # actually finished the round, not the rewound branch.
            if replay_decisions is not None:
                replay_decisions.clear()
            restored = _undo_pop_to_south(history_stack, stack_base)
            if restored is not None:
                current = restored
                announce("↶ Undo", duration=0.8, reader=reader)
                display(current, None)
                # If we undo into BIDDING, we continue the outer loop
                continue
            # Nothing left to undo in this round — restart with a fresh deal
            del history_stack[stack_base:]
            current = start_round(state, rng)
            announce("↶ Undo — fresh deal", duration=0.8, reader=reader)
            continue
        current = res_play  # type: ignore[assignment]

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

            # Animate score update
            ns_old, ew_old = current.team_scores
            if breakdown.taker_team == 0:
                target_ns = ns_old + breakdown.taker_total
                target_ew = ew_old + breakdown.defender_total
            else:
                target_ns = ns_old + breakdown.defender_total
                target_ew = ew_old + breakdown.taker_total

            if not skip_round_pause:
                animate_score_update(current, target_ns, target_ew)

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
            update_stats_round(
                breakdown.is_capot,
                breakdown.taker_total if breakdown.taker_team == 0 else breakdown.defender_total,
                trump_sym,
            )

            return apply_round_score(current, breakdown)
