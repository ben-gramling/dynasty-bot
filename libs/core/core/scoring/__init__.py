"""Scoring engine for dynasty-bot — implements docs/scoring-system.md (v3).

Pure functions over a Snapshot; no network, no Mongo. Entry point:

    compute_all(snapshot, params) -> {waiver_board, league_table, my_team_detail}
"""

from core.scoring.engine import compute_all
from core.scoring.params import Params
from core.scoring.snapshot import Snapshot, validate_snapshot

__all__ = [
    "Params",
    "Snapshot",
    "compute_all",
    "validate_snapshot",
]
