"""Score an arbitrary trade proposal against the live dynasty-bot database.

Unlike the nightly trade-recs board (which enumerates from the engine's give-lists
— cornerstones and taxi players excluded), this resolves ANY rostered player or
owned pick by name and scores the exact package with the v4 card: TWO objective
coordinates per side — ΔS (change in starter value: the max-Σv legal lineup at
raw KTC over active + taxi) and ΔF (change in total face owned: players + picks
at tranche) — with the derived verdict (objectively good ⟺ both ≥ 0, one
strict), the guaranteed interval [floor, ceiling] = [min, max], and, on
preference trades, the breakeven δ* = ΔS/(ΔS − ΔF) (§2). Plus the exact
KTC-calculator fairness gate (§3), posture shape (§4) and sequencing (§5).
Powers the trade-negotiator skill.

Coordinates are per side: ΔF is exactly zero-sum across a leg's parties, ΔS is
not — a good spread can be objectively good for BOTH sides. A buy leg can be
floor-negative on its own — pair it with a sell leg and read the PAIR's
combined coordinates, which `--hedge` computes exactly (both legs applied
together).

Usage (from the repo root, .env required):
  uv run python scripts/score_trade.py teams
  uv run python scripts/score_trade.py list-assets [TEAM]
  uv run python scripts/score_trade.py score --opponent NAME \
      --give "Mike Evans, Courtland Sutton" --get "2027 R1 (own)" \
      [--alternatives] [--hedge] [--json]
  uv run python scripts/score_trade.py pairs --min 5 --max 10 [--json]

`pairs` computes the §5 pair board (same engine code path as the nightly run:
enumerate-then-filter, posture as a hard constraint, VERDICT as a hard storage
constraint — every stored pair is objectively good — count-neutral pairs,
storage STRATIFIED BY MAX-LEG BUCKET) and prints the bucket inventory followed
by the stored pairs behind your two dials: `--min` floors the TOTAL pair
return (v4: guaranteed floor ÷ face Σv sent), `--max` caps EACH LEG's market
return. The list always sorts maximin: floor-based return desc, ceiling as
tie-break. `--target N` survives as an alias for `--min N`; omit --max for no
cap. Every count is a verified floor (the walk orders legs by their isolation
floors while pairs are priced by their exact combined coordinates).
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
    """Single-tweak variants, gate-passers only, ranked by my GUARANTEED FLOOR
    (§2 v4 maximin — min(ΔS, ΔF), this leg in isolation)."""
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

    passers: list[tuple[float, float, str, dict]] = []
    for label, gv, gt in variants:
        if not gv or not gt:
            continue
        try:
            card = tr.propose(league, opp_name, gv, gt)
        except Exception:  # unresolvable/degenerate variant — skip
            continue
        if card["gate"]["verdict"] == "PASS":
            # maximin: floor desc, ceiling desc as tie-break (§2 v4)
            c = card["coords"]["me"]
            passers.append((card["floor"]["me"], max(c["dS"], c["dF"]), label, card))
    passers.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return {
        "variants_scored": len(variants),
        "gate_passers": [{"tweak": l, "card": c} for _, _, l, c in passers[:5]],
    }


def find_hedges(
    league, opp_name: str, give: list, get: list, net_players: int, net_picks: int
) -> list[dict]:
    """Gate-passing legs against OTHER counterparties that offset BOTH of the
    proposal's count deltas EXACTLY — the pair nets 0 players / 0 picks for me
    (§5 v3.2 strict count-neutrality, not just freed roster spots). Assets in
    the proposal are excluded; the proposal's counterparty is excluded (unrelated
    hedge parties leak less). v3.3: candidates come from the engine's pair pool
    WITHOUT the posture constraint (the desk treats posture qualitatively);
    the per-leg return floor is retired, so candidates may be floor-negative
    alone — what matters is the pair. Ranked by isolation FLOOR (§2 v4), top 3."""
    pool = tr.build_pair_pool(league, enforce_posture=False)
    used = {a.key for a in give} | {a.key for a in get}
    want = (-net_players, -net_picks)
    cands: list[tuple] = []
    for leg in pool.legs:
        if (leg[tr.L_NP], leg[tr.L_NK]) != want:
            continue
        opp = pool.opp_names[leg[tr.L_OPP]]
        if opp == opp_name:
            continue
        g, t = leg[tr.L_GIVE], leg[tr.L_GET]
        if len(g.assets) > 2:
            continue  # a hedge is a clean exit, not a blockbuster
        if used & set(g.keys) or used & set(t.keys):
            continue
        cands.append((leg[tr.L_FLOOR], opp, g, t))
    cands.sort(key=lambda c: (-c[0], c[1], c[2].keys, c[3].keys))
    out: list[dict] = []
    seen_core: set[tuple] = set()
    for _dw, opp, g, t in cands[:80]:
        core = (opp, max(g.assets, key=lambda a: (a.v, a.key)).key)
        if core in seen_core:
            continue
        card = tr.propose(league, opp, list(g.assets), list(t.assets))
        if not card["gate"]["verdict"].startswith("PASS"):
            continue
        seen_core.add(core)
        out.append(card)
        if len(out) >= 3:
            break
    return out


def fmt_coords(coords: dict) -> str:
    """The §2 v4 coordinates: starters (ΔS) + face (ΔF), raw — no discount
    exists anywhere."""
    return f"starters {coords['dS']:+.0f} · face {coords['dF']:+.0f}"


def fmt_verdict(coords: dict, verdict: bool, breakeven: float | None) -> str:
    """The §2 v4 verdict line: objectively good (with the guaranteed
    interval), a preference trade (with its breakeven δ* and direction), or
    bad for every rational preference."""
    lo = min(coords["dS"], coords["dF"])
    hi = max(coords["dS"], coords["dF"])
    if verdict:
        if lo == hi:
            return f"OBJECTIVELY GOOD — gain exactly {lo:+.0f} at every rational preference"
        return f"OBJECTIVELY GOOD — gain between {lo:+.0f} and {hi:+.0f} (floor guaranteed)"
    if breakeven is None:
        return "BAD for every rational preference (both coordinates <= 0)"
    if coords["dF"] > coords["dS"]:
        return (
            f"preference trade — good only if you value stored future capital "
            f"above delta* = {breakeven:.2f} of face (floor {lo:+.0f}, ceiling {hi:+.0f})"
        )
    return (
        f"preference trade — good only if you value stored future capital "
        f"below delta* = {breakeven:.2f} of face (floor {lo:+.0f}, ceiling {hi:+.0f})"
    )


def fmt_legline(card: dict) -> str:
    give = " + ".join(a["name"] for a in card["give"])
    get = " + ".join(a["name"] for a in card["get"])
    ret = card.get("return_pct")
    coords = card.get("coords", {}).get("me")
    tail = f"; {fmt_coords(coords)}" if coords else ""
    mkt = card.get("market_return_pct")
    mkt_s = f", market {mkt:+g}%" if mkt is not None else ""
    return (
        f"send {give} -> get {get}  "
        f"(floor alone {card['floor']['me']:+.0f}{tail}, leg floor return {ret:g}%{mkt_s})"
    )


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
    coords = card["coords"]
    lines = [
        header
        or (
            f"Trade with {card['counterparty']} — "
            f"you: {fmt_verdict(coords['me'], card['verdict']['me'], card['breakeven']['me'])}"
        ),
        f"  You send: {', '.join(fmt_asset(a) for a in card['give'])}",
        f"  You get:  {', '.join(fmt_asset(a) for a in card['get'])}",
        f"  Coordinates: you {fmt_coords(coords['me'])}  ·  "
        f"{card['counterparty']} {fmt_coords(coords['them'])}"
        + ("  (this leg alone)" if card.get("coords_basis") == "isolation" else ""),
        f"  Their side: "
        f"{fmt_verdict(coords['them'], card['verdict']['them'], card['breakeven']['them'])}"
        "  (dF is zero-sum on a leg; dS is each side's own deployment)",
        f"  Floor-based return: {card['return_pct']:g}% of the "
        f"{sum(a['v'] for a in card['give'])} face you send"
        if card.get("return_pct") is not None
        else "  Floor-based return: n/a",
    ]
    lines += [
        f"  Gate: {g['verdict']}  ·  KTC-calculator totals {g['adj_give']:.0f} you / "
        f"{g['adj_get']:.0f} them  ·  gap {g['gap']:.0f} "
        f"({g['gap_pct']:.1f}% of {max(g['adj_give'], g['adj_get']):.0f}, "
        f"band {g['band']:.0f})  ·  ratio {g['raw_ratio']} (cap {g['cap']})",
        f"  Posture: {card['counterparty']} is {p['label']}"
        + (f" (override)" if p["source"] == "override" else f" ({p['evidence_count']} classifying trades)")
        + f" · offer shape {p['shape']} ({'fits' if p['fit'] else 'does not fit'})",
        f"  Leg: {card['leg_type']} · counts you: {card['net_players']['me']:+d} players / "
        f"{card['net_picks']['me']:+d} picks (§5 v3.2; net active roster "
        f"{card['net_roster']['me']:+d} you / {card['net_roster']['them']:+d} them)"
        + (
            f" · market return {card['market_return_pct']:+g}% (the v3.4.1 leg-cap number)"
            if card.get("market_return_pct") is not None
            else ""
        ),
        f"  Sequencing: {card['sequencing']}",
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
        help="find gate-passing legs elsewhere that exactly offset this proposal's "
        "player AND pick count deltas (the pair nets 0 players / 0 picks for you)",
    )
    sc.add_argument("--json", action="store_true")
    pr = sub.add_parser(
        "pairs",
        help="the §5 v3.4.1 pair board behind your two dials (same code path as the nightly board)",
    )
    pr.add_argument(
        "--min", "--target", dest="min_ret", type=float, default=5.0,
        help="floor on TOTAL pair return, percent (presets 1 / 2.5 / 5 / 10 / 20; "
        "--target is the v3.3 alias)",
    )
    pr.add_argument(
        "--max", dest="leg_cap", type=float, default=None,
        help="v3.4.1: exclusive cap on EACH LEG's market return — face ΔW ÷ face "
        "Σv sent on that leg, the skim that leg's counterparty sees (presets "
        "2.5 / 5 / 10 / 20; omit for no cap). Independent of --min: --min 5 "
        "--max 2.5 is the balanced-legs/high-total query",
    )
    pr.add_argument("--json", action="store_true")
    args = ap.parse_args()

    db = get_db()
    snapshot, fresh = build_snapshot_from_store(db)
    league = md.build_league(snapshot, Params())
    if fresh["last_collect"]:
        age_h = (datetime.now(timezone.utc) - fresh["last_collect"].replace(tzinfo=timezone.utc)).total_seconds() / 3600
        print(f"[data age: {age_h:.1f}h since last successful collect]\n", file=sys.stderr)

    if args.cmd == "pairs":
        board = tr.trade_board(league)
        if board.get("disabled"):
            sys.exit("trade deadline has passed — the pair board is disabled")
        lo, cap = args.min_ret, args.leg_cap
        filter_label = f"total >= {lo:g}%" + (
            f", every leg < {cap:g}%" if cap is not None else ", no leg cap"
        )
        # v3.4.1: --min floors the TOTAL return; --max caps EACH LEG's market
        # return; the list always sorts by total return desc
        hits = [
            p for p in board["pairs"]
            if p["return_pct"] >= lo
            and (cap is None or p["max_leg_return_pct"] < cap)
        ]
        # maximin (§2 v4): floor-based return desc, ceiling desc as tie-break
        hits.sort(key=lambda p: (-p["return_pct"], -p.get("ceiling", 0.0)))
        buckets = board.get("bands", [])
        if args.json:
            print(json.dumps(
                {
                    "min": lo,
                    "leg_cap": cap,
                    "presets": board["presets"],
                    "leg_cap_presets": board.get("leg_cap_presets"),
                    "bands": buckets,
                    "counts_by_threshold": board["counts_by_threshold"],
                    "truncated": board["truncated"],
                    "pairs": hits[:15],
                    "notes": board["notes"],
                },
                indent=1, default=str,
            ))
            return

        def bucket_name(b: dict) -> str:
            if b["lo"] is None:
                return f"max leg < {b['hi']:g}%"
            if b["hi"] is None:
                return f"max leg >= {b['lo']:g}%"
            return f"max leg [{b['lo']:g}, {b['hi']:g})%"

        tband_names = [
            f"[{p:g},{board['presets'][i + 1]:g})" if i + 1 < len(board["presets"])
            else f"[{p:g},inf)"
            for i, p in enumerate(board["presets"])
        ]
        print(
            "Max-leg bucket inventory (v3.4.1: bucket = the pair's larger leg market "
            "return; stored = the bucket's top pairs by TOTAL return; every count a "
            "verified floor — '>=' throughout):"
        )
        for b in buckets:
            mark = ">= " if b["saturated"] else ""
            grid = "  ".join(
                f"{name}:{n}" for name, n in zip(tband_names, b["by_total"]) if n
            ) or "-"
            print(
                f"  {bucket_name(b):>20}: stored {b['stored']:>3} of {mark}{b['count']:<8}"
                f" by total {grid}"
            )
        if not hits:
            print(
                f"\nNo stored pairs with {filter_label} today. Loosen the leg cap "
                "or drop the total floor — the inventory above shows where the "
                "stored pairs sit. The board recomputes nightly."
            )
            return
        deeper = any(b["saturated"] or b["count"] > b["stored"] for b in buckets)
        print(
            f"\nTop {min(15, len(hits))} of {len(hits)} stored pairs with {filter_label}, "
            "floor-based total return desc (ceiling tie-break — every stored "
            "pair is objectively good, §2 v4)"
            + (" (the legal space runs deeper — see the inventory above)" if deeper else "")
            + ":"
        )
        for p in hits[:15]:
            b, s = p["buy"], p["sell"]
            coords = p.get("coords")
            tail = f" ({fmt_coords(coords)})" if coords else ""
            lr = p.get("leg_returns", {})
            legs_str = (
                f"  legs market {lr.get('buy', 0):+g}% buy / {lr.get('sell', 0):+g}% sell"
                if lr
                else ""
            )
            print(
                f"\n{p['id']}  total return {p['return_pct']:g}%  guaranteed "
                f"{p['floor']:+g} · up to {p['ceiling']:+g}"
                f"{tail}{legs_str}  [0 players / 0 picks net · {p['fit_summary']}]"
            )
            print(f"  BUY  {b['counterparty']:<15} {fmt_legline(b)}")
            print(f"  SELL {s['counterparty']:<15} {fmt_legline(s)}")
        print(
            "\nSequencing: agreement-first — verbal yes on the buy, execute the sell, "
            "then the buy. The board recomputes after any executed trade."
        )
        return

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
        np_me, nk_me = card["net_players"]["me"], card["net_picks"]["me"]
        if np_me == 0 and nk_me == 0:
            hedges = []  # already count-neutral — nothing to offset
        else:
            hedges = find_hedges(league, opp_name, give, get, np_me, nk_me)

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
        np_me, nk_me = card["net_players"]["me"], card["net_picks"]["me"]
        if np_me == 0 and nk_me == 0:
            print("\nHedge: not needed — this leg is already count-neutral "
                  "(0 players / 0 picks net).")
        elif not hedges:
            print(f"\nHedge: no gate-passing leg found netting {-np_me:+d} players / "
                  f"{-nk_me:+d} picks — this proposal has no count-complementary exit "
                  "today; treat it as blocked (§5 v3.2).")
        else:
            print(f"\nHedges (legs elsewhere offsetting {np_me:+d} players / {nk_me:+d} picks "
                  "exactly; pair nets 0 players / 0 picks). Pair coordinates are "
                  "EXACT combined — both legs applied together, not the leg sum:")
            for h in hedges:
                pair = tr.pair_coords(league, card, h)
                order = (
                    "execute this sell FIRST"
                    if h["net_players"]["me"] < 0
                    else "agreement-first on both legs"
                )
                pair_verdict = fmt_verdict(
                    {"dS": pair["dS"], "dF": pair["dF"]},
                    pair["verdict"], pair["breakeven"],
                )
                print()
                print(fmt_card(
                    h,
                    header=f"Hedge — with {h['counterparty']}: PAIR {pair_verdict} "
                    f"({fmt_coords(pair)}) · pair floor return {pair['return_pct']:g}% on "
                    f"{pair['sent']:.0f} Σv you send (this leg's floor alone "
                    f"{h['floor']['me']:+.0f}) · {order}",
                ))
    if alts:
        print(f"\nAlternatives ({alts['variants_scored']} single-tweak variants scored; "
              f"gate-passers ranked maximin — guaranteed floor desc, ceiling tie-break):")
        if not alts["gate_passers"]:
            print("  none pass the gate")
        for v in alts["gate_passers"]:
            print(f"\n{fmt_card(v['card'], header=f'Variant — {v['tweak']}: guaranteed floor(you) {v['card']['floor']['me']:+.0f}')}")


if __name__ == "__main__":
    main()
