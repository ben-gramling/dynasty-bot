"""Score an arbitrary trade proposal against the live dynasty-bot database.

Unlike the nightly trade-recs board (which enumerates from the engine's curated
give-lists), this resolves ANY rostered player or owned pick by name — including
cornerstones the enumerator deliberately protects — and scores the exact package
two-sided with the same §12 card the engine produces. Powers the trade-negotiator
skill.

Usage (from the repo root, .env required):
  uv run python scripts/score_trade.py teams
  uv run python scripts/score_trade.py list-assets [TEAM]
  uv run python scripts/score_trade.py score --opponent NAME \
      --give "Mike Evans, Courtland Sutton" --get "2027 R1 (own)" \
      [--alternatives] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from core import store  # noqa: E402
from core.db import get_db  # noqa: E402
from core.scoring import Params, Snapshot  # noqa: E402
from core.scoring import model as md  # noqa: E402
from core.scoring import trades as tr  # noqa: E402

MAX_SWEETENER_MV = 3500.0  # alternatives: largest add-on asset considered
SWAP_BAND_MV = 1500.0  # alternatives: |mv delta| for like-for-like swaps


def build_snapshot_from_store(db) -> tuple[Snapshot, dict]:
    league_coll = db["league"]
    league = league_coll.find_one({"kind": "league"})
    if not league:
        sys.exit("No league doc in Mongo — run `just collect` first.")
    state = league_coll.find_one({"_id": "state:nfl"}) or {}
    draft = next(
        iter(
            league_coll.find({"kind": "draft", "season": league.get("season")}).sort(
                "fetched_at", -1
            )
        ),
        {},
    )
    rosters = list(db["rosters"].find({}))
    users = list(db["users"].find({}))
    traded_picks = list(db["picks"].find({}))
    ktc_assets = list(db["ktc-latest"].find({}))
    crosswalk = {str(d["_id"]): d for d in db["crosswalk"].find({}) if d["_id"] != "meta"}

    mapped = {e["sleeper_id"] for e in crosswalk.values()}
    rostered = {pid for r in rosters for pid in (r.get("players") or [])}
    player_names = {
        p["_id"]: {"name": p.get("full_name") or f"#{p['_id']}", "pos": p.get("position") or "UNK"}
        for p in db["players"].find({"_id": {"$in": list(rostered - mapped)}})
    }
    snapshot = Snapshot(
        league=league,
        rosters=rosters,
        users=users,
        traded_picks=traded_picks,
        draft=draft,
        state=state,
        ktc_assets=ktc_assets,
        crosswalk=crosswalk,
        player_names=player_names,
        value_history_max=store.ktc_value_history_max(db=db),
    )
    last_run = next(iter(db["runs"].find({"ok": True}).sort("finished", -1)), None)
    freshness = {"last_collect": last_run["finished"] if last_run else None}
    return snapshot, freshness


def all_assets(league: md.LeagueState, t: md.TeamCtx) -> dict[str, tr.Asset]:
    """Every tradeable asset for a team: engine give-list ∪ every rostered player."""
    assets = {a.name: a for a in tr.give_list(league, t)}
    cut_ids = {p.sid for p in t.cut_players}
    for p in t.act + t.taxi:
        if p.name not in assets:
            assets[p.name] = tr.Asset(
                kind="player", key=p.sid, name=p.name, mv=p.v, truth=p.v, pos=p.pos,
                age=p.age, is_cut=p.sid in cut_ids, is_2026=False, sell_floor=p.v, player=p,
            )
    return assets


def resolve(assets: dict[str, tr.Asset], query: str, team: str) -> tr.Asset:
    q = query.strip().lower()
    exact = [a for n, a in assets.items() if n.lower() == q]
    if len(exact) == 1:
        return exact[0]
    partial = [a for n, a in assets.items() if q in n.lower()]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        sys.exit(
            f"No asset matching {query!r} on {team}. "
            f"Run `list-assets {team}` for exact names."
        )
    sys.exit(f"Ambiguous {query!r} on {team}: {sorted(a.name for a in partial)}")


def score_package(
    league: md.LeagueState, opp_name: str, give: list[tr.Asset], get: list[tr.Asset]
) -> dict:
    """propose() with pre-resolved assets (so protected/non-shoppable players work)."""
    params = league.params
    me = league.teams[league.me]
    opp = league.teams[opp_name]
    g = tr._package_of(league, give)
    gt = tr._package_of(league, get)
    res_me = tr._score_side(league, me, get=gt, give=g)
    res_them = tr._score_side(league, opp, get=g, give=gt)
    h = res_me.score + params.mutual_weight * min(max(res_them.score, 0.0), res_me.score)
    _ok, fair_info = tr._fairness(league, g, gt)
    raw_ratio = (
        max(g.mv_sum, gt.mv_sum) / min(g.mv_sum, gt.mv_sum)
        if min(g.mv_sum, gt.mv_sum) > 0
        else float("inf")
    )
    return tr._card(league, opp, g, gt, res_me, res_them, h, fair_info, raw_ratio)


def alternatives(
    league: md.LeagueState,
    opp_name: str,
    give: list[tr.Asset],
    get: list[tr.Asset],
    base: dict,
) -> dict:
    """Single-tweak variants of the proposal, split by whom the tweak favors."""
    me = league.teams[league.me]
    opp = league.teams[opp_name]
    my_pool = all_assets(league, me)
    their_pool = all_assets(league, opp)
    in_give = {a.key for a in give}
    in_get = {a.key for a in get}

    variants: list[tuple[str, list[tr.Asset], list[tr.Asset]]] = []
    for a in their_pool.values():  # they add a sweetener -> favors me
        if a.key not in in_get and a.mv <= MAX_SWEETENER_MV:
            variants.append((f"they add {a.name}", give, get + [a]))
    for a in my_pool.values():  # I add a sweetener -> favors them
        if a.key not in in_give and a.mv <= MAX_SWEETENER_MV:
            variants.append((f"you add {a.name}", give + [a], get))
    if len(give) > 1:
        for a in give:
            variants.append((f"you keep {a.name}", [x for x in give if x.key != a.key], get))
    if len(get) > 1:
        for a in get:
            variants.append((f"they keep {a.name}", give, [x for x in get if x.key != a.key]))
    for a in give:  # like-for-like swaps on my side
        for b in my_pool.values():
            if b.key not in in_give and abs(b.mv - a.mv) <= SWAP_BAND_MV:
                variants.append(
                    (f"swap {a.name} -> {b.name}",
                     [x for x in give if x.key != a.key] + [b], get)
                )

    my_base, their_base = base["sides"]["me"]["score"], base["sides"]["them"]["score"]
    me_friendly: list[tuple[float, str, dict]] = []
    them_friendly: list[tuple[float, str, dict]] = []
    for label, gv, gt in variants:
        if not gv or not gt:
            continue
        try:
            card = score_package(league, opp_name, gv, gt)
        except Exception:  # illegal package (roster legality etc.) — skip variant
            continue
        m, th = card["sides"]["me"]["score"], card["sides"]["them"]["score"]
        if m > my_base and th > 0:
            me_friendly.append((m, label, card))
        if th > their_base and m > 0:
            them_friendly.append((th, label, card))
    me_friendly.sort(key=lambda x: -x[0])
    them_friendly.sort(key=lambda x: -x[0])
    return {
        "me_friendly": [{"tweak": l, "card": c} for _, l, c in me_friendly[:2]],
        "them_friendly": [{"tweak": l, "card": c} for _, l, c in them_friendly[:2]],
        "variants_scored": len(variants),
    }


def fmt_side(tag: str, side: dict) -> str:
    return (
        f"  {tag}: score {side['score']:+.1f}  "
        f"(lineup {side['lineup_weighted']:+.1f} · wealth {side['wealth_weighted']:+.1f} "
        f"· crunch {side['crunch_term']:+.1f})"
    )


def fmt_asset(a: dict) -> str:
    if a["type"] == "pick" and "mv" in a and a["mv"] != a["v"]:
        return f"{a['name']} (market {a['mv']}, concrete {a['v']})"
    return f"{a['name']} ({a['v']})"


def fmt_card(card: dict, header: str = "") -> str:
    fair = card["fairness"]
    fair_ok = fair["gap_pct"] <= fair["band_pct"]
    lines = [
        header or f"Trade with {card['counterparty']} — tier {card['tier']}, H {card['rank_score_H']:.1f}",
        f"  You send: {', '.join(fmt_asset(a) for a in card['give'])}",
        f"  You get:  {', '.join(fmt_asset(a) for a in card['get'])}",
        fmt_side("You ", card["sides"]["me"]),
        fmt_side("Them", card["sides"]["them"]),
        f"  Tier {card['tier']} ({card['posture_fit']}) · fairness gap {fair['gap_pct']:.1f}% "
        f"(band {fair['band_pct']:.0f}%, {'PASS' if fair_ok else 'FAIL'}) · "
        f"raw ratio {fair['raw_ratio']:.2f} (cap {fair['cap']})",
    ]
    if card.get("dip_targets"):
        lines.append(f"  Dip-buy flags: {', '.join(card['dip_targets'])}")
    for note in card.get("pick_anchor", []):
        floor = " BELOW SELL FLOOR" if note.get("below_sell_floor") else ""
        lines.append(
            f"  Pick note ({note['side']}): {note['pick']} market-anchor {note['tranche']} "
            f"vs concrete {note['concrete']}{floor}"
        )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("teams")
    la = sub.add_parser("list-assets")
    la.add_argument("team", nargs="?", default=None)
    sc = sub.add_parser("score")
    sc.add_argument("--opponent", required=True)
    sc.add_argument("--give", required=True, help="comma-separated asset names you send")
    sc.add_argument("--get", required=True, help="comma-separated asset names you receive")
    sc.add_argument("--alternatives", action="store_true")
    sc.add_argument("--json", action="store_true")
    args = ap.parse_args()

    db = get_db()
    snapshot, fresh = build_snapshot_from_store(db)
    league = md.build_league(snapshot, Params())
    if fresh["last_collect"]:
        age_h = (datetime.now(timezone.utc) - fresh["last_collect"].replace(tzinfo=timezone.utc)).total_seconds() / 3600
        print(f"[data age: {age_h:.1f}h since last successful collect]\n", file=sys.stderr)

    if args.cmd == "teams":
        for name, t in sorted(league.teams.items(), key=lambda kv: kv[1].lineup.L, reverse=True):
            tag = "  <- YOU" if name == league.me else ""
            print(
                f"{name:15} roster {t.rid:>2}  L {t.lineup.L:>9.1f} (rank {league.rank_l[name]:>2})  "
                f"F {t.f:>7.0f}  omega {t.omega:.2f}  cuts due {t.cuts}  FAAB ${t.faab}{tag}"
            )
        return

    if args.cmd == "list-assets":
        team_name = args.team or league.me
        match = [n for n in league.teams if n.lower() == team_name.lower()] or [
            n for n in league.teams if team_name.lower() in n.lower()
        ]
        if len(match) != 1:
            sys.exit(f"Team {team_name!r} not found/ambiguous. Teams: {sorted(league.teams)}")
        t = league.teams[match[0]]
        shoppable = {a.name for a in tr.give_list(league, t)}
        print(f"Assets for {match[0]} (engine-shoppable marked *):")
        for name, a in sorted(all_assets(league, t).items(), key=lambda kv: -kv[1].mv):
            mark = "*" if name in shoppable else " "
            cut = "  [cut due]" if a.is_cut else ""
            kind = a.pos or "PICK"
            print(f" {mark} {name:32} {kind:4} mv {a.mv:>7.0f}{cut}")
        return

    match = [n for n in league.teams if n.lower() == args.opponent.lower()] or [
        n for n in league.teams if args.opponent.lower() in n.lower()
    ]
    if len(match) != 1 or match[0] == league.me:
        sys.exit(f"Opponent {args.opponent!r} not found/ambiguous. Teams: {sorted(set(league.teams) - {league.me})}")
    opp_name = match[0]
    me_assets = all_assets(league, league.teams[league.me])
    opp_assets = all_assets(league, league.teams[opp_name])
    give = [resolve(me_assets, q, league.me) for q in args.give.split(",") if q.strip()]
    get = [resolve(opp_assets, q, opp_name) for q in args.get.split(",") if q.strip()]

    card = score_package(league, opp_name, give, get)
    alts = alternatives(league, opp_name, give, get, card) if args.alternatives else None

    if args.json:
        out = {"proposal": card}
        if alts:
            out["alternatives"] = alts
        print(json.dumps(out, indent=1, default=str))
        return

    print(fmt_card(card))
    if alts:
        print(f"\nAlternatives (scored {alts['variants_scored']} single-tweak variants):")
        for group, label in (("me_friendly", "More you-friendly"), ("them_friendly", "More them-friendly")):
            if not alts[group]:
                print(f"  {label}: none found that keeps both sides positive")
            for v in alts[group]:
                print(f"\n{fmt_card(v['card'], header=f'{label} — {v['tweak']}')}")


if __name__ == "__main__":
    main()
