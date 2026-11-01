"""Optional rule variants the core Belote engine knows how to play.

The classic game runs with every variant off (the default). Expansions — the
BelAtro roguelite's boss blinds, decks and vouchers — switch variants on for
a round by setting `GameState.variants`; the core engine (legal cards, trick
resolution, scoring, AI) honors them without knowing who asked for them.

Kept dependency-free so any layer can import it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RuleVariants:
    """Per-round rule switches. All off = standard Belote."""

    # ── Contract / trump rules ──────────────────────────────────────────
    no_belote: bool = False  # Belote/Rebelote doesn't score
    dynamic_trump: bool = False  # trump rotates every 2 tricks
    no_consecutive_team_wins: bool = False  # a team can't win 2 tricks in a row
    seven_eight_trump: bool = False  # every 7 and 8 also plays as a trump
    wild_seven_eight: bool = False  # 7s and 8s are always legal plays
    auto_coinche: bool = False  # every contract starts coinched
    ban_clubs: bool = False
    # ── Scoring rules ───────────────────────────────────────────────────
    invert_scoring: bool = False
    kings_zero: bool = False
    tens_zero: bool = False
    aces_zero: bool = False
    jacks_zero: bool = False
    queen_spades_penalty: bool = False
    no_dix_de_der: bool = False
    declarations_zero: bool = False
    double_declarations: bool = False  # sequences / carrés score ×2
    no_belote_rebelote: bool = False
    tie_breaks_for_taker: bool = False  # card-point tie goes to the taker
    separate_scoring: bool = False
    # ── Partner (North) behaviour ───────────────────────────────────────
    agent_double_active: bool = False  # partner throws some tricks
    agent_double_late_only: bool = False
    sabotage_tricks: frozenset[int] = field(default_factory=frozenset)
    partner_forced_pass: bool = False
    lock_trust_zero: bool = False
    # ── Presentation ────────────────────────────────────────────────────
    hide_hud: bool = False
    # 4.11.0 (Le Bal Masqué): display-only — the opponents' cards in the first
    # trick are drawn face-down until the trick is won. Rules / AI / legal
    # moves still see the real cards.
    masked_first_trick: bool = False
    hide_partner_hand: bool = False
