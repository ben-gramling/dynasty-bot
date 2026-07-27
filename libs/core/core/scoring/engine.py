"""compute_all: one snapshot in, all four tab payloads out (JSON-serializable)."""

from __future__ import annotations

from core.scoring import league as lg
from core.scoring import model as md
from core.scoring import trades as tr
from core.scoring import waivers as wv
from core.scoring.params import Params
from core.scoring.snapshot import Snapshot


def compute_all(snapshot: Snapshot, params: Params | None = None) -> dict:
    params = params or Params()
    league = md.build_league(snapshot, params)
    me = league.teams[league.me]

    board = wv.waiver_board(league, me)
    trade_recs = tr.trade_board(league)
    table = lg.league_table(league)

    unvalued = sorted(
        p.name for t in league.teams.values() for p in t.pool + t.taxi if p.unvalued
    )
    return {
        "meta": {
            "mode": "offseason" if league.offseason else "in-season",
            "week": snapshot.week,
            "draft_status": "pre_draft" if league.draft_pre else "complete",
            "current_year": league.current_year,
            "w_min": params.w_min,
            "replacement": {k: round(v) for k, v in league.replacement.items()},
            "unvalued_rostered": unvalued,
            "alerts": list(league.alerts),
            "my_team": league.me,
        },
        "waiver_board": board,
        "trade_recs": trade_recs,
        "league_table": table,
        "my_team_detail": lg.my_team_detail(league),
    }
