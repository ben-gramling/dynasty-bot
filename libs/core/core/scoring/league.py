"""§7 league tab: strength map + future assets (carried) and the market map (new)."""

from __future__ import annotations

from math import sqrt

from core.scoring import model as md
from core.scoring.lineup import GROUPS


def _rank(values: dict[str, float], name: str) -> int:
    ordered = sorted(values, key=lambda n: (-values[n], n))
    return ordered.index(name) + 1


def _pick_detail(league: md.LeagueState, p) -> dict:
    d = {
        "label": p.label,
        "v": round(p.mv),  # face tranche value — the ΔW/wealth number (§1)
        "band": p.band,
        "band_reason": p.band_reason,
    }
    if p.year == league.current_year and p.p != p.mv:
        d["concrete"] = round(p.p)  # rookie-board slot value: display annotation only
    return d


def market_map(league: md.LeagueState, t: md.TeamCtx) -> dict:
    """§7 market map: posture + evidence, positional holes, pick inventory, FAAB."""
    posture = league.postures.get(t.name, {})
    holes = [
        {"pos": pos, "rank": league.group_rank[pos][t.name]}
        for pos in ("QB", "RB", "WR", "TE")
        if league.group_rank[pos][t.name] >= 9
    ]
    by_year: dict[str, int] = {}
    for p in t.picks:
        by_year[str(p.year)] = by_year.get(str(p.year), 0) + 1
    return {
        "posture": posture.get("label", "NEUTRAL"),
        "posture_source": posture.get("source", "trades"),
        "bought": posture.get("bought", 0),
        "sold": posture.get("sold", 0),
        "trades_12mo": posture.get("trades", 0),
        "evidence": posture.get("evidence", []),
        "holes": holes,
        "pick_inventory": {
            "count": len(t.picks),
            "by_year": by_year,
            "value": round(t.picks_mv),
        },
        "faab": t.faab,
    }


def league_table(league: md.LeagueState) -> dict:
    teams = league.teams
    ls = {n: t.L for n, t in teams.items()}
    fs = {n: t.f for n, t in teams.items()}
    mean = sum(ls.values()) / len(ls)
    sigma = sqrt(sum((x - mean) ** 2 for x in ls.values()) / len(ls))
    rows = []
    for name in sorted(teams, key=lambda n: league.rank_l[n]):
        t = teams[name]
        row = {
            "team": name,
            "roster_id": t.rid,
            "lineup": {
                grp: {
                    "sum": round(t.lineup.group_sums[grp]),
                    "rank": league.group_rank[grp][name],
                    "players": [
                        {"player": p.name, "v": p.v} for p in t.lineup.starters[grp]
                    ],
                }
                for grp in GROUPS
            },
            "L": round(t.L, 1),
            "L_rank": league.rank_l[name],
            "L_z": round((t.L - mean) / sigma, 2) if sigma else 0.0,
            "future": {
                "picks": round(t.picks_mv),
                "picks_detail": [
                    _pick_detail(league, p)
                    for p in sorted(t.picks, key=lambda p: (p.year, p.round, p.origin_rid))
                ],
                "taxi": round(sum(p.v for p in t.taxi)),
                "taxi_detail": [{"player": p.name, "v": p.v} for p in t.taxi],
                "F": round(t.f),
                "F_rank": _rank(fs, name),
            },
            "market": market_map(league, t),
        }
        rows.append(row)
    return {"rows": rows, "L_mean": round(mean, 1), "L_sigma": round(sigma, 1)}


def my_team_detail(league: md.LeagueState) -> dict:
    """The my-team row with the full underlying breakdown."""
    table = league_table(league)
    me_row = next(r for r in table["rows"] if r["team"] == league.me)
    t = league.teams[league.me]
    by_year: dict[int, list] = {}
    for p in sorted(t.picks, key=lambda p: (p.year, p.round)):
        by_year.setdefault(p.year, []).append(_pick_detail(league, p))
    return {
        **me_row,
        "picks_by_year": {str(y): v for y, v in by_year.items()},
        "unvalued": [p.name for p in t.pool if p.unvalued],
    }
