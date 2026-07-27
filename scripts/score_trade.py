"""Score an arbitrary trade proposal against the live dynasty-bot database.

Unlike the nightly trade-recs board (which enumerates from the engine's give-lists
— cornerstones and taxi players excluded), this resolves ANY rostered player or
owned pick by name and scores the exact package with the v3 card:
ΔW = Σv(in) − Σv(out) at face KTC (§2), the fairness gate (§3), posture shape
(§4), and sequencing (§5). Powers the trade-negotiator skill.

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

MAX_SWEETENER_V = 3500.0  # alternatives: largest add-on asset considered
SWAP_BAND_V = 1500.0  # alternatives: |v delta| for like-for-like swaps


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
    transactions = list(
        db["transactions"].find({"type": "trade", "status": "complete"})
    )

    mapped = {e["sleeper_id"] for e in crosswalk.values()}
    rostered = {pid for r in rosters for pid in (r.get("players") or [])}
    traded_sids = {
        str(sid)
        for t in transactions
        for sid in {**(t.get("adds") or {}), **(t.get("drops") or {})}
    }
    player_names = {
        p["_id"]: {"name": p.get("full_name") or f"#{p['_id']}", "pos": p.get("position") or "UNK"}
        for p in db["players"].find({"_id": {"$in": list((rostered | traded_sids) - mapped)}})
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
        transactions=transactions,
        posture_overrides=store.posture_overrides(db=db),
    )
    last_run = next(iter(db["runs"].find({"ok": True}).sort("finished", -1)), None)
    freshness = {"last_collect": last_run["finished"] if last_run else None}
    return snapshot, freshness


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


def alternatives(
    league: md.LeagueState,
    opp_name: str,
    give: list[tr.Asset],
    get: list[tr.Asset],
    base: dict,
) -> dict:
    """Single-tweak variants, gate-passers only, ranked by my ΔW (§5)."""
    me = league.teams[league.me]
    opp = league.teams[opp_name]
    my_pool = tr.team_assets(league, me)
    their_pool = tr.team_assets(league, opp)
    in_give = {a.key for a in give}
    in_get = {a.key for a in get}

    variants: list[tuple[str, list[tr.Asset], list[tr.Asset]]] = []
    for a in their_pool.values():  # they add a sweetener
        if a.key not in in_get and a.v <= MAX_SWEETENER_V:
            variants.append((f"they add {a.name}", give, get + [a]))
    for a in my_pool.values():  # I add a sweetener
        if a.key not in in_give and a.v <= MAX_SWEETENER_V:
            variants.append((f"you add {a.name}", give + [a], get))
    if len(give) > 1:
        for a in give:
            variants.append((f"you keep {a.name}", [x for x in give if x.key != a.key], get))
    if len(get) > 1:
        for a in get:
            variants.append((f"they keep {a.name}", give, [x for x in get if x.key != a.key]))
    for a in give:  # like-for-like swaps on my side
        for b in my_pool.values():
            if b.key not in in_give and abs(b.v - a.v) <= SWAP_BAND_V:
                variants.append(
                    (f"swap {a.name} -> {b.name}",
                     [x for x in give if x.key != a.key] + [b], get)
                )

    passers: list[tuple[float, str, dict]] = []
    for label, gv, gt in variants:
        if not gv or not gt:
            continue
        try:
            card = tr.propose(league, opp_name, gv, gt)
        except Exception:  # unresolvable/degenerate variant — skip
            continue
        if card["gate"]["verdict"] == "PASS":
            passers.append((card["dW"]["me"], label, card))
    passers.sort(key=lambda x: (-x[0], x[1]))
    return {
        "variants_scored": len(variants),
        "gate_passers": [{"tweak": l, "card": c} for _, l, c in passers[:5]],
    }


def find_hedges(
    league, opp_name: str, give: list, get: list, needed: int
) -> list[dict]:
    """Gate-passing sell-legs against OTHER counterparties that restore roster
    neutrality for a +needed buy leg (§5: every buy pairs with a sell). Assets in
    the proposal are excluded; the proposal's counterparty is excluded (unrelated
    hedge parties leak less)."""
    me_t = league.teams[league.me]
    used = {a.key for a in give} | {a.key for a in get}
    my_assets = [a for a in tr.give_list(league, me_t) if a.key not in used]
    # a hedge is a clean exit, not a blockbuster: at most 2 assets out
    my_pkgs = [p for p in tr._packages(league, my_assets) if len(p.assets) <= 2]
    cands: list[tuple] = []
    for opp in league.opponents:
        if opp == opp_name:
            continue
        cands.extend(tr._enumerate_opponent(league, my_pkgs, opp))
    cands.sort(key=lambda c: (-c[0], c[1]))
    out: list[dict] = []
    seen_core: set[tuple] = set()
    for _dw, _shape, opp, g, t, *_ in cands[:80]:
        core = (opp, max(g.assets, key=lambda a: a.v).key)
        if core in seen_core:
            continue
        card = tr.propose(league, opp, list(g.assets), list(t.assets))
        if not card["gate"]["verdict"].startswith("PASS"):
            continue
        if card["net_roster"]["me"] > -needed:
            continue
        seen_core.add(core)
        out.append(card)
        if len(out) >= 3:
            break
    return out


def fmt_asset(a: dict) -> str:
    tag = f"{a['name']} ({a['v']}"
    if a.get("concrete") is not None:
        tag += f"; board slot {a['concrete']} — info only"
    if a.get("unvalued"):
        tag += "; UNVALUED"
    return tag + ")"


def fmt_card(card: dict, header: str = "") -> str:
    g = card["gate"]
    p = card["posture"]
    dw = card["dW"]["me"]
    lines = [
        header or f"Trade with {card['counterparty']} — ΔW(you) {dw:+.0f} (them {-dw:+.0f})",
        f"  You send: {', '.join(fmt_asset(a) for a in card['give'])}",
        f"  You get:  {', '.join(fmt_asset(a) for a in card['get'])}",
        f"  Gate: {g['verdict']}  ·  gap {g['gap']:.0f} ({g['gap_pct']:.1f}% of {max(g['adj_give'], g['adj_get']):.0f}, "
        f"band {g['band']:.0f})  ·  ratio {g['raw_ratio']} (cap {g['cap']})",
        f"  Posture: {card['counterparty']} is {p['label']}"
        + (f" (override)" if p["source"] == "override" else f" ({p['evidence_count']} classifying trades)")
        + f" · offer shape {p['shape']} ({'fits' if p['fit'] else 'does not fit'})",
        f"  Leg: {card['leg_type']} (net roster {card['net_roster']['me']:+d} you / "
        f"{card['net_roster']['them']:+d} them) · {card['sequencing']}",
        f"  Anchor ask: open at ≈{card['anchor_ask']['ask']} ({card['anchor_ask']['note']})",
    ]
    if card.get("ceiling"):
        lines.append(
            f"  Band ceiling for this package: ≈{card['ceiling']['value']} — "
            "negotiating room above the proposal"
        )
    if card.get("holes"):
        holes = ", ".join(f"{h['pos']} (their rank {h['their_rank']})" for h in card["holes"])
        lines.append(f"  Their visible holes at positions you send: {holes}")
    if card.get("dip_notes"):
        lines.append(f"  Dip notes (30-day archive, info only): {', '.join(card['dip_notes'])}")
    for side in ("me", "them"):
        stashed = card.get("taxi_stashed", {}).get(side) or []
        if stashed:
            who = "your" if side == "me" else "their"
            lines.append(f"  Taxi routing: {', '.join(stashed)} would stash on {who} surplus taxi slot")
    for note in card.get("notes", []):
        lines.append(f"  Note: {note}")
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
    sc.add_argument(
        "--hedge",
        action="store_true",
        help="for a buy leg: find gate-passing sell-legs elsewhere that restore roster neutrality",
    )
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
            p = league.postures.get(name, {})
            label = p.get("label", "NEUTRAL")
            src = "override" if p.get("source") == "override" else f"{len(p.get('evidence', []))} ev"
            print(
                f"{name:15} roster {t.rid:>2}  L {t.lineup.L:>9.1f} (rank {league.rank_l[name]:>2})  "
                f"F {t.f:>7.0f}  {label:7} ({src}, {p.get('trades', 0)} trades/12mo)  FAAB ${t.faab}{tag}"
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
        for name, a in sorted(tr.team_assets(league, t).items(), key=lambda kv: -kv[1].v):
            mark = "*" if name in shoppable else " "
            kind = a.pos or "PICK"
            extra = f"  (board slot {a.concrete:.0f} — info only)" if a.concrete is not None else ""
            extra += "  [UNVALUED]" if a.unvalued else ""
            print(f" {mark} {name:32} {kind:4} v {a.v:>7.0f}{extra}")
        return

    match = [n for n in league.teams if n.lower() == args.opponent.lower()] or [
        n for n in league.teams if args.opponent.lower() in n.lower()
    ]
    if len(match) != 1 or match[0] == league.me:
        sys.exit(f"Opponent {args.opponent!r} not found/ambiguous. Teams: {sorted(set(league.teams) - {league.me})}")
    opp_name = match[0]
    me_assets = tr.team_assets(league, league.teams[league.me])
    opp_assets = tr.team_assets(league, league.teams[opp_name])
    give = [resolve(me_assets, q, league.me) for q in args.give.split(",") if q.strip()]
    get = [resolve(opp_assets, q, opp_name) for q in args.get.split(",") if q.strip()]

    card = tr.propose(league, opp_name, give, get)
    alts = alternatives(league, opp_name, give, get, card) if args.alternatives else None
    hedges = None
    if args.hedge:
        needed = card["net_roster"]["me"]
        if needed > 0:
            hedges = find_hedges(league, opp_name, give, get, needed)
        else:
            hedges = []

    if args.json:
        out = {"proposal": card}
        if alts:
            out["alternatives"] = alts
        if hedges is not None:
            out["hedges"] = hedges
        print(json.dumps(out, indent=1, default=str))
        return

    print(fmt_card(card))
    if hedges is not None:
        needed = card["net_roster"]["me"]
        if needed <= 0:
            print("\nHedge: not needed — this leg is roster-neutral or a net sell.")
        elif not hedges:
            print(f"\nHedge: no gate-passing sell-leg found that frees {needed} spot(s) — "
                  "this buy has no clean exit today; treat it as blocked.")
        else:
            print(f"\nHedges (sell-legs elsewhere freeing ≥{needed} spot(s); pair nets roster-neutral):")
            for h in hedges:
                pair_dw = card["dW"]["me"] + h["dW"]["me"]
                print()
                print(fmt_card(
                    h,
                    header=f"Hedge — sell to {h['counterparty']}: pair ΔW {pair_dw:+.0f} "
                    f"(this leg {h['dW']['me']:+.0f}) · execute this sell FIRST",
                ))
    if alts:
        print(f"\nAlternatives ({alts['variants_scored']} single-tweak variants scored; "
              f"gate-passers ranked by your ΔW):")
        if not alts["gate_passers"]:
            print("  none pass the gate")
        for v in alts["gate_passers"]:
            print(f"\n{fmt_card(v['card'], header=f'Variant — {v['tweak']}: ΔW(you) {v['card']['dW']['me']:+.0f}')}")


if __name__ == "__main__":
    main()
