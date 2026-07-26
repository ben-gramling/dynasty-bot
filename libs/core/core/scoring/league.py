"""§8 league tab: strictly separated Lineup / Future blocks + market map."""

from __future__ import annotations

from math import sqrt

from core.scoring import model as md
from core.scoring.lineup import GROUPS
from core.scoring.params import omega_suggest


def _rank(values: dict[str, float], name: str) -> int:
    ordered = sorted(values, key=lambda n: (-values[n], n))
    return ordered.index(name) + 1


def league_table(league: md.LeagueState) -> dict:
    teams = league.teams
    ls = {n: t.L for n, t in teams.items()}
    fs = {n: t.f for n, t in teams.items()}
    mean = sum(ls.values()) / len(ls)
    sigma = sqrt(sum((x - mean) ** 2 for x in ls.values()) / len(ls))
    group_vals = {
        grp: {n: t.lineup.group_sums[grp] for n, t in teams.items()} for grp in GROUPS
    }
    rows = []
    for name in sorted(teams, key=lambda n: league.rank_l[n]):
        t = teams[name]
        row = {
            "team": name,
            "roster_id": t.rid,
            "lineup": {
                grp: {
                    "sum": round(t.lineup.group_sums[grp]),
                    "rank": _rank(group_vals[grp], name),
                    "players": [
                        {"player": p.name, "v": p.v} for p in t.lineup.starters[grp]
                    ],
                }
                for grp in GROUPS
            },
            "L": round(t.L, 1),
            "L_rank": league.rank_l[name],
            "L_z": round((t.L - mean) / sigma, 2) if sigma else 0.0,
            "omega": t.omega,
            "omega_suggest": round(
                omega_suggest(
                    league.params,
                    league.rank_l[name],
                    league.snapshot.pickflow.get(name, 0),
                ),
                2,
            ),
            "future": {
                "picks": round(sum(p.p for p in t.picks)),
                "picks_detail": [
                    {"label": p.label, "p": round(p.p), "mv": round(p.mv), **p.pricing()}
                    for p in sorted(t.picks, key=lambda p: (p.year, p.round, p.origin_rid))
                ],
                "taxi": round(sum(p.v for p in t.taxi)),
                "taxi_detail": [{"player": p.name, "v": p.v} for p in t.taxi],
                "F": round(t.f),
                "F_rank": _rank(fs, name),
            },
            "market": {
                "cuts": t.cuts,
                "C": round(t.c, 1),
                "cut_list": [p.name for p in t.cut_players],
                "faab": t.faab,
            },
        }
        rows.append(row)
    return {"rows": rows, "L_mean": round(mean, 1), "L_sigma": round(sigma, 1)}


def my_team_detail(league: md.LeagueState) -> dict:
    """§11.3: the my-team row with the full underlying breakdown."""
    table = league_table(league)
    me_row = next(r for r in table["rows"] if r["team"] == league.me)
    t = league.teams[league.me]
    by_year: dict[int, list] = {}
    for p in sorted(t.picks, key=lambda p: (p.year, p.round)):
        by_year.setdefault(p.year, []).append(
            {"label": p.label, "p": round(p.p), "mv": round(p.mv), "sell_floor": round(p.sell_floor)}
        )
    return {
        **me_row,
        "picks_by_year": {str(y): v for y, v in by_year.items()},
        "crunch_due": "rookie draft" if league.draft_pre else None,
        "unvalued": [p.name for p in t.pool if p.unvalued],
    }
