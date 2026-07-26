"""Scoring engine for dynasty-bot — implements docs/scoring-system.md.

Pure functions over a Snapshot; no network, no Mongo. Entry point:

    compute_all(snapshot, params) -> {waiver_board, trade_recs, league_table, my_team_detail}
"""

from core.scoring.engine import compute_all
from core.scoring.params import ACTIVITY_PRIOR, OMEGA_SEEDS, Params
from core.scoring.snapshot import Snapshot, validate_snapshot

__all__ = [
    "ACTIVITY_PRIOR",
    "OMEGA_SEEDS",
    "Params",
    "Snapshot",
    "compute_all",
    "validate_snapshot",
]
