"""compute_all: one snapshot in, every dashboard payload out (JSON-serializable).

v7.1 — the §5 pair BOARD is no longer part of this. The Trades tab is gone and
nothing reads a stored `trade-recs` document, so computing it nightly was pure
cost (it is by far the most expensive pass: the pair pool runs the exact KTC
gate over the whole enumeration). `trades.trade_board` is untouched and stays
fully tested — `scripts/score_trade.py` calls it directly and always computed
its own board live rather than reading the stored one. Spread-finding is a CLI
/ trade-negotiator workflow now."""

from __future__ import annotations

from core.scoring import league as lg
from core.scoring import model as md
from core.scoring import waivers as wv
from core.scoring.params import Params
from core.scoring.snapshot import Snapshot


def compute_all(snapshot: Snapshot, params: Params | None = None) -> dict:
    params = params or Params()
    league = md.build_league(snapshot, params)
    me = league.teams[league.me]

    board = wv.waiver_board(league, me)
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
        "league_table": table,
        "my_team_detail": lg.my_team_detail(league),
    }
