"""Fixtures: the committed 2026-07-26 snapshot (data/) is the ground truth every
quoted number in docs/scoring-system.md is pinned against."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.scoring import Params, Snapshot
from core.scoring import model as md

REPO = Path(__file__).resolve().parents[4]
DATA = REPO / "data"
SLEEPER = DATA / "fixtures" / "sleeper"
LOCAL = Path(__file__).resolve().parent / "fixtures"


def _load(path: Path):
    with open(path) as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def snapshot() -> Snapshot:
    ktc = _load(DATA / "ktc_raw.json")
    xw = _load(DATA / "ktc_sleeper_map.json")
    return Snapshot(
        league=_load(SLEEPER / "league26.json"),
        rosters=_load(SLEEPER / "rosters26.json"),
        users=_load(SLEEPER / "users26.json"),
        traded_picks=_load(SLEEPER / "traded_picks_26.json"),
        draft=_load(SLEEPER / "draft26.json"),
        state=_load(SLEEPER / "state.json"),
        ktc_assets=ktc["players"],
        crosswalk=xw["crosswalk"],
        my_roster_id=4,
        player_names=_load(LOCAL / "player_names_supplement.json"),
    )


@pytest.fixture(scope="session")
def params() -> Params:
    return Params()


@pytest.fixture(scope="session")
def league(snapshot, params) -> md.LeagueState:
    return md.build_league(snapshot, params)


@pytest.fixture(scope="session")
def me(league) -> md.TeamCtx:
    return league.teams[league.me]


@pytest.fixture(scope="session")
def result(snapshot, params) -> dict:
    """Full compute_all output — shared because the trade pass is the expensive part."""
    from core.scoring import compute_all

    return compute_all(snapshot, params)


@pytest.fixture(scope="session")
def ppts_fixture() -> dict:
    return _load(LOCAL / "ppts_2025.json")


def by_name(league: md.LeagueState, name: str):
    for p in league.players.values():
        if p.name == name:
            return p
    raise KeyError(name)


def pick_of(team: md.TeamCtx, year: int, rnd: int, origin_rid: int | None = None):
    for p in team.picks:
        if p.year == year and p.round == rnd and (origin_rid is None or p.origin_rid == origin_rid):
            return p
    raise KeyError((year, rnd, origin_rid))
