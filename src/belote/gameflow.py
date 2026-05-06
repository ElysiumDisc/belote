from __future__ import annotations

import random
import sys
from dataclasses import replace

from .ai import AIPlayer, Difficulty
from .ansi import (
    BOLD,
    RESET,
    gold_fg,
)
from .deck import Card, Suit
from .game import (
    Carre,
    GameState,
    Phase,
    Seat,
    Sequence,
    TrickCard,
    bidding_turn,
    clear_announced,
    clear_legal_cards_cache,
    play_card,
    process_bid,
    start_round,
    team_of,
    trick_winner_seat,
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
    display,
    patch_trick_card,
    play_sound,
    prompt_bid,
    prompt_card,
)


def create_ai_players(diffs_map: dict[Seat, str]) -> dict[Seat, AIPlayer]:
    """Create AI players for seats not occupied by humans."""
    ai_seats = {Seat.EAST, Seat.NORTH, Seat.WEST}
    return {s: AIPlayer(s, Difficulty(diffs_map[s])) for s in ai_seats}


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
            if isinstance(res, str):
                return None
            bid: Suit | None = res
        else:
            ai = ai_players[bidder]
            bid = ai.decide_bid(current)
            display(current, None)
            if bid:
                sys.stdout.write(f"\r\n  {bidder.name} takes it as {bid.symbol}!\r\n")
            else:
                sys.stdout.write(f"\r\n  {bidder.name} passes\r\n")
            sys.stdout.flush()

            # If someone takes, pause longer so user can see it
            if not skip_anims:
                delay = ai_delay * 2 + 0.5 if bid else ai_delay
                if interruptible_sleep(delay, reader):
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
) -> GameState | str | None:
    """Run the play phase (all 8 tricks). Returns None if user quits, 'UNDO' if requested."""
    current = state
    skip_anims = False

    while current.phase == Phase.PLAYING:
        player = current.turn
        if player == Seat.SOUTH:
            skip_anims = False  # M6: Reset skip flag when it's the human's turn
            display(current, None)
            card, current = prompt_card(current, reader)
            if card is None:
                return None
            if card == "UNDO":
                return "UNDO"
            if card == "OVERLAY":
                # Classic mode has no separate score overlay; re-prompt for a real card.
                continue
            if not isinstance(card, Card):
                return "UNDO"
        else:
            ai = ai_players[player]
            ai.update_memory(current)
            card = ai.decide_card(current)

        # 1. Show the card on the mat IMMEDIATELY
        display_state = replace(
            current, current_trick=current.current_trick + (TrickCard(player, card),)
        )
        if len(display_state.current_trick) == 1:
            display(display_state, None)
        else:
            patch_trick_card(display_state, player, card)

        # 2. Handle AI message and short delay for cards 1, 2, 3
        if player != Seat.SOUTH:
            sys.stdout.write(f"\r\n  {player.name} plays {card}\r\n")
            sys.stdout.flush()
            if (
                len(display_state.current_trick) < 4
                and not skip_anims
                and interruptible_sleep(ai_delay, reader)
            ):
                skip_anims = True

        # 3. If this completes a trick, pause longer and show announcements
        if len(display_state.current_trick) == 4:
            play_sound("trick")
            if len(current.completed_tricks) == 7:  # This was the 8th trick
                se_trump = current.boss_modifiers.seven_eight_trump
                winner = trick_winner_seat(display_state.current_trick, current.trump, se_trump)
                if winner:
                    team = "NS" if team_of(winner) == 0 else "EW"
                    announce(
                        f"Dix de Der (Team {team})",
                        duration=trick_pause * 0.8 if not skip_anims else 0,
                        reader=reader,
                    )
                    display(display_state, None)

                # Check for Capot while cards are still visible
                if (
                    is_capot(
                        current,
                        tricks=list(current.completed_tricks) + [display_state.current_trick],
                    )
                    is not None
                ):
                    play_sound("capot")
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
                    play_sound("declaration")
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
        current = play_card(current, card)

        if current.announced:
            if "Belote" in current.announced:
                play_sound("belote")
            announce(
                current.announced,
                duration=max(0.5, trick_pause * 0.6) if not skip_anims else 0,
                reader=reader,
            )
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
            if len(history_stack) > stack_base:
                current = history_stack.pop()
                continue
            # Nothing left to undo in this round — restart with a fresh deal
            del history_stack[stack_base:]
            current = start_round(state, rng)
            continue
        current = res_bid  # type: ignore[assignment]

        if current.phase == Phase.DEAL:  # All passed
            announce("All passed - Reshuffling!", duration=round_pause * 0.5, reader=reader)
            return current

        # Play Phase
        res_play = run_play(current, reader, ai_players, ai_delay, trick_pause, history_stack)
        if res_play is None:
            return None
        if res_play == "UNDO":
            clear_legal_cards_cache()
            if len(history_stack) > stack_base:
                current = history_stack.pop()
                # If we undo into BIDDING, we continue the outer loop
                continue
            # Nothing left to undo in this round — restart with a fresh deal
            del history_stack[stack_base:]
            current = start_round(state, rng)
            continue
        current = res_play  # type: ignore[assignment]

        # Scoring Phase
        if current.phase == Phase.SCORING:
            breakdown = score_round(current)
            if breakdown.is_failed:
                play_sound("chute")
            display(current, None)
            sys.stdout.write(f"\r\n{'=' * 50}\r\n")
            sys.stdout.write("  Round Results:\r\n")
            taker_name = current.taker.name if current.taker else "?"
            team_label = "NS" if current.taker is not None and team_of(current.taker) == 0 else "EW"
            sys.stdout.write(f"  Taker: {taker_name} (Team {team_label})\r\n")
            for msg in breakdown.messages:
                sys.stdout.write(f"  {BOLD}{gold_fg()}{msg}{RESET}\r\n")
            ns_pts = (
                breakdown.taker_total if breakdown.taker_team == 0 else breakdown.defender_total
            )
            ew_pts = (
                breakdown.defender_total if breakdown.taker_team == 0 else breakdown.taker_total
            )
            sys.stdout.write(f"  Team NS: {ns_pts} points\r\n")
            sys.stdout.write(f"  Team EW: {ew_pts} points\r\n")
            sys.stdout.write(f"{'=' * 50}\r\n\r\n")
            sys.stdout.flush()

            skip_round_pause = interruptible_sleep(round_pause, reader)

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

            # Update global stats
            trump_sym = current.trump.symbol if current.trump else None
            update_stats_round(
                breakdown.is_capot,
                breakdown.taker_total if breakdown.taker_team == 0 else breakdown.defender_total,
                trump_sym,
            )

            return apply_round_score(current, breakdown)
