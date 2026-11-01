"""Classic Belote scoring. 4.11.0: split into a package.

    announcements.py  declarations: detection, resolution, points
    tricks.py         card / trick points under rule variants, capot
    round_score.py    ScoringBreakdown, score_round, apply_round_score

Every name (including the underscore helpers tests and BelAtro use) stays
importable from `belote.scoring`.
"""

from __future__ import annotations

from ..game import Carre as Carre
from ..game import Declaration as Declaration
from ..game import Sequence as Sequence
from .announcements import (
    _CARRE_POINTS as _CARRE_POINTS,
)
from .announcements import (
    _RANK_VALUES as _RANK_VALUES,
)
from .announcements import (
    _SEQUENCE_POINTS as _SEQUENCE_POINTS,
)
from .announcements import (
    _VALUE_TO_RANK as _VALUE_TO_RANK,
)
from .announcements import (
    ResolvedDeclarations as ResolvedDeclarations,
)
from .announcements import (
    SeatDeclarations as SeatDeclarations,
)
from .announcements import (
    _best_carre as _best_carre,
)
from .announcements import (
    _best_sequence as _best_sequence,
)
from .announcements import (
    _carre_points as _carre_points,
)
from .announcements import (
    _carre_strength as _carre_strength,
)
from .announcements import (
    _decl_short_label as _decl_short_label,
)
from .announcements import (
    _detect_all_declarations as _detect_all_declarations,
)
from .announcements import (
    _sequence_points as _sequence_points,
)
from .announcements import (
    _sequence_strength as _sequence_strength,
)
from .announcements import (
    detect_belote as detect_belote,
)
from .announcements import (
    detect_carres as detect_carres,
)
from .announcements import (
    detect_sequences as detect_sequences,
)
from .announcements import (
    get_declaration_points as get_declaration_points,
)
from .announcements import (
    get_declarations as get_declarations,
)
from .announcements import (
    resolve_declarations as resolve_declarations,
)
from .round_score import (
    ScoringBreakdown as ScoringBreakdown,
)
from .round_score import (
    _apply_scoring_modifiers as _apply_scoring_modifiers,
)
from .round_score import (
    _calculate_base_points as _calculate_base_points,
)
from .round_score import (
    _compute_belote_points as _compute_belote_points,
)
from .round_score import (
    _compute_declaration_points as _compute_declaration_points,
)
from .round_score import (
    _empty_breakdown as _empty_breakdown,
)
from .round_score import (
    _score_capot_outcome as _score_capot_outcome,
)
from .round_score import (
    _score_normal_outcome as _score_normal_outcome,
)
from .round_score import (
    _ScoringContext as _ScoringContext,
)
from .round_score import (
    apply_round_score as apply_round_score,
)
from .round_score import (
    coinche_adjusted_credits as coinche_adjusted_credits,
)
from .round_score import (
    score_round as score_round,
)
from .tricks import (
    _card_points_with_zero_ranks as _card_points_with_zero_ranks,
)
from .tricks import (
    _trick_points_with_modifiers as _trick_points_with_modifiers,
)
from .tricks import (
    _trick_zeroed_by_ban_clubs as _trick_zeroed_by_ban_clubs,
)
from .tricks import (
    card_points_with_modifiers as card_points_with_modifiers,
)
from .tricks import (
    is_capot as is_capot,
)
from .tricks import (
    trick_card_points as trick_card_points,
)
