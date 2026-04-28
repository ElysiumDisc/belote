from __future__ import annotations

import random
import sys
import time

from .ansi import (
    BOLD, gold_fg, RESET,
)
from .input import KeyReader, Key
from .game import (
    GameState, Phase, Seat, start_round,
    play_card, clear_legal_cards_cache, team_of,
    TrickCard, replace, trick_winner_seat,
)
from .bidding import bidding_turn, process_bid
from .scoring import score_round, apply_round_score
from .ai import AIPlayer, Difficulty
from .ui import (
    display, prompt_card, prompt_bid, announce, 
    animate_score_update, play_sound, patch_trick_card,
)
from .stats import update_stats_round

# AI delay and trick pause durations per speed setting.
# (ai_move_delay, trick_result_pause, round_result_pause)
SPEED_TIMINGS: dict[str, tuple[float, float, float]] = {
    "slow":    (1.5, 2.0, 4.0),
    "normal":  (0.7, 1.2, 2.5),
    "fast":    (0.25, 0.4, 1.0),
    "instant": (0.0, 0.0, 0.5),
}

def interruptible_sleep(duration: float, reader: KeyReader) -> bool:
    """Sleep for duration, but return True if interrupted by Space/Esc."""
    if duration <= 0:
        return False
    
    start = time.time()
    while time.time() - start < duration:
        event = reader.read_timeout(0.05)
        if event and event.key in (Key.SPACE, Key.ESC):
            return True
    return False

def create_ai_players(diffs_map: dict[Seat, str], human_seats: set[Seat]) -> dict[Seat, AIPlayer]:
    """Create AI players for seats not occupied by humans."""
    ai_seats = {s for s in Seat if s not in human_seats}
    return {s: AIPlayer(s, Difficulty(diffs_map[s])) for s in ai_seats}


def run_bidding(state: GameState, reader: KeyReader, ai_players: dict[Seat, AIPlayer],
                ai_delay: float, history: list[GameState], human_seats: set[Seat]) -> GameState | str | None:
    """Run the bidding phase. Returns None if user quits, 'UNDO' if requested."""
    current = state
    skip_anims = False
    while current.phase == Phase.BIDDING:
        bidder = bidding_turn(current)

        if bidder in human_seats:
            display(current, None)
            if bidder != Seat.SOUTH:
                sys.stdout.write(f"\r\n  {BOLD}{gold_fg()}PLAYER {bidder.name}'s TURN{RESET}\r\n")
                sys.stdout.flush()
            bid = prompt_bid(current, reader)
            if bid == "QUIT":
                return None
            if bid == "UNDO":
                return "UNDO"
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
        current = process_bid(current, bid)  # type: ignore[arg-type]

    return current


def run_play(state: GameState, reader: KeyReader, ai_players: dict[Seat, AIPlayer],
             ai_delay: float, trick_pause: float, history: list[GameState],
             human_seats: set[Seat]) -> GameState | str | None:
    """Run the play phase (all 8 tricks). Returns None if user quits, 'UNDO' if requested."""
    clear_legal_cards_cache()
    current = state
    skip_anims = False

    while current.phase == Phase.PLAYING:
        player = current.turn

        if player in human_seats:
            display(current, None)
            if player != Seat.SOUTH:
                sys.stdout.write(f"\r\n  {BOLD}{gold_fg()}PLAYER {player.name}'s TURN{RESET}\r\n")
                sys.stdout.flush()
            card = prompt_card(current, reader)
            if card is None:
                return None
            if card == "UNDO":
                return "UNDO"
        else:
            ai = ai_players[player]
            ai.update_memory(current)
            card = ai.decide_card(current)

        # 1. Show the card on the mat IMMEDIATELY
        display_state = replace(current, current_trick=current.current_trick + (TrickCard(player, card),))
        if len(display_state.current_trick) == 1:
            display(display_state, None)
        else:
            patch_trick_card(display_state, player, card)

        # 2. Handle AI message and short delay for cards 1, 2, 3
        if player != Seat.SOUTH:
            sys.stdout.write(f"\r\n  {player.name} plays {card}\r\n")
            sys.stdout.flush()
            if len(display_state.current_trick) < 4:
                if not skip_anims and interruptible_sleep(ai_delay, reader):
                    skip_anims = True

        # 3. If this completes a trick, pause longer and show announcements
        if len(display_state.current_trick) == 4:
            play_sound("trick")
            if len(current.completed_tricks) == 7: # This was the 8th trick
                winner = trick_winner_seat(display_state.current_trick, current.trump)
                if winner:
                    team = "NS" if team_of(winner) == 0 else "EW"
                    announce(f"Dix de Der (Team {team})", duration=trick_pause * 0.8 if not skip_anims else 0)
                    display(display_state, None)
                
                # Check for Capot while cards are still visible
                taker_team = team_of(current.taker) if current.taker else None
                if taker_team is not None:
                    # Previous tricks + this one
                    all_tricks = list(current.completed_tricks) + [display_state.current_trick]
                    is_capot = all(
                        team_of(trick_winner_seat(t, current.trump)) == taker_team
                        for t in all_tricks
                    )
                    if is_capot:
                        play_sound("capot")
                        announce("CAPOT!", duration=trick_pause * 1.2 if not skip_anims else 0)
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
                        # Use detail instead of data
                        name = seq_names.get(decl.detail.length, "Sequence") # type: ignore[union-attr]
                        msg = f"{decl.seat.name}: {name}"
                    
                    announce(msg, duration=trick_pause * 0.8 if not skip_anims else 0)
                    display(display_state, None)

        # 4. Transition to next state
        history.append(current)
        current = play_card(current, card)

        if current.announced:
            if "Belote" in current.announced:
                play_sound("belote")
            announce(current.announced, duration=max(0.5, trick_pause * 0.6) if not skip_anims else 0)
            display(current, None)

    return current


def run_round(state: GameState, reader: KeyReader, ai_players: dict[Seat, AIPlayer],
              ai_delay: float, trick_pause: float, round_pause: float,
              history_stack: list[GameState], human_seats: set[Seat]) -> GameState | None:
    """Run a complete round: deal, bid, play, score. Returns None if user quits."""
    clear_legal_cards_cache()
    rng = random.Random()
    current = start_round(state, rng)

    while True:
        # Bidding Phase
        res_bid = run_bidding(current, reader, ai_players, ai_delay, history_stack, human_seats)
        if res_bid is None: return None
        if res_bid == "UNDO":
            if len(history_stack) > 1:
                current = history_stack.pop()
                continue
            else:
                current = state # Reset to start of round
                continue
        current = res_bid # type: ignore[assignment]

        if current.phase == Phase.DEAL: # All passed
            announce("All passed - Reshuffling!", duration=round_pause * 0.5)
            return current

        # Play Phase
        res_play = run_play(current, reader, ai_players, ai_delay, trick_pause, history_stack, human_seats)
        if res_play is None: return None
        if res_play == "UNDO":
            if len(history_stack) > 1:
                current = history_stack.pop()
                # If we undo into BIDDING, we continue the outer loop
                continue
            else:
                current = state # Reset to start of round
                continue
        current = res_play # type: ignore[assignment]

        # Scoring Phase
        if current.phase == Phase.SCORING:
            breakdown = score_round(current)
            if breakdown.is_failed:
                play_sound("chute")
            display(current, None)
            sys.stdout.write(f"\r\n{'='*50}\r\n")
            sys.stdout.write(f"  Round Results:\r\n")
            taker_name = current.taker.name if current.taker else "?"
            team_label = 'NS' if team_of(current.taker) == 0 else 'EW'
            sys.stdout.write(f"  Taker: {taker_name} (Team {team_label})\r\n")
            for msg in breakdown.messages:
                sys.stdout.write(f"  {BOLD}{gold_fg()}{msg}{RESET}\r\n")
            ns_pts = breakdown.taker_total if breakdown.taker_team == 0 else breakdown.defender_total
            ew_pts = breakdown.defender_total if breakdown.taker_team == 0 else breakdown.taker_total
            sys.stdout.write(f"  Team NS: {ns_pts} points\r\n")
            sys.stdout.write(f"  Team EW: {ew_pts} points\r\n")
            sys.stdout.write(f"{'='*50}\r\n\r\n")
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
            update_stats_round(breakdown.is_capot, breakdown.taker_total if breakdown.taker_team == 0 else breakdown.defender_total, trump_sym)

            return apply_round_score(current, breakdown)
