"""Score an arbitrary trade proposal against the live dynasty-bot database.

Unlike the pair board (which enumerates from the engine's give-lists
— cornerstones and taxi players excluded), this resolves ANY rostered player or
owned pick by name and scores the exact package with the v4 card: TWO objective
coordinates per side — ΔS (change in starter value: the max-Σv legal lineup at
raw KTC over active + taxi) and ΔF (change in total face owned: players at KTC
face; picks at ONE price — KTC's exact numbered slot this year, the flat Mid
tranche beyond, the slot never estimated, v7.6) — with the derived verdict (objectively good ⟺ both ≥ 0, one
strict), the guaranteed interval [floor, ceiling] = [min, max], and, on
preference trades, the breakeven δ* = ΔS/(ΔS − ΔF) (§2). Plus the exact
KTC-calculator fairness gate (§3), posture shape (§4) and sequencing (§5).
Powers the trade-negotiator skill.

Coordinates are per side, and since v7 through per-side LENSES: yours prices
picks your way, theirs at market face, so neither coordinate negates across the
parties — a good spread can be objectively good for BOTH sides. A buy leg can be
floor-negative on its own — pair it with a sell leg and read the PAIR's
combined coordinates, which `--hedge` computes exactly (both legs applied
together).

Usage (from the repo root, .env required):
  uv run python scripts/score_trade.py teams
  uv run python scripts/score_trade.py list-assets [TEAM]
  uv run python scripts/score_trade.py score --opponent NAME \
      --give "Mike Evans, Courtland Sutton" --get "2027 R1 (own)" \
      [--alternatives] [--hedge] [--json]
  uv run python scripts/score_trade.py pairs --min 5 --favor-min -5 [--json]
  uv run python scripts/score_trade.py dashboard --out hedge-board.html
  uv run python scripts/score_trade.py hedgedb build [--workers N] [--no-bake] [--allow-stale]
  uv run python scripts/score_trade.py hedgedb board [--focus TEAM] [filters...] [--out FILE]
  uv run python scripts/score_trade.py hedgedb offer --opponent X --give "A, B" --get "C" [filters...]
  uv run python scripts/score_trade.py hedgedb status
  uv run python scripts/score_trade.py find \
      --require "ronak receives picks" --require "joey receives pos:RB" \
      --exclude "* receives Stefon Diggs" \
      --min-return 1 --favor-min -5 [--delta robust] [--top 20] [--json]

`pairs` computes the §5 pair board (v7.1: this IS the board — it left the
nightly pipeline with the Trades tab, so nothing is stored and this is always
fresh; same engine code path as before:
enumerate-then-filter, posture as a hard constraint, VERDICT as a hard storage
constraint — every stored pair is objectively good — count-neutral pairs,
storage STRATIFIED BY FAVOR BUCKET, v5) and prints the bucket inventory
followed by the stored pairs behind your dials: `--min` floors the TOTAL pair
return (v4: guaranteed floor ÷ face Σv sent), `--favor-min` floors the pair's
counterparty favorability min(f_buy, f_sell) — each leg's signed
KTC-calculator skew in KTC's own variance units (|f| <= 5 is literally their
calculator's FAIR window; it replaces the retired v3.4.1 per-leg market-return
cap). The list always sorts maximin: floor-based return desc, ceiling as
tie-break. `--target N` survives as an alias for `--min N`; omit --favor-min
for no floor. Bucket counts are EXACT tallies when the collection walk ran to
completion under the v5.1 sound crossing bound (it crosses legs on
ΔF − r·Σv sent, which is exactly additive and bounds every pair's guaranteed
floor from above) and verified FLOORS — printed ">= N" — only where the walk
saturated; the inventory marks each bucket. "Exact" is over the POOLED legs:
the pool keeps `variants_per_signature` package variants per (counterparty,
give, count-signature), a disclosed pre-ranking heuristic (§5).

`dashboard` (v7.1) is the negotiating session's opening move: it runs `find`
once per counterparty — `with_team` pushes the scope into the crossing, so each
run is exhaustive rather than budget-truncated — and renders the lot as a
standalone HTML page (no scripts, no external requests) for the skill to
publish. Counterparty searches are farmed to a process pool; expect minutes,
not seconds, and a team with nothing to show is itself a real answer.

`find` is the §4a v5 spread finder: constrained search over the legal pair
space the pool enumerates (not just stored board inventory) with the three
sliders. Repeatable
constraint flags --require / --exclude / --prefer each take one string:

    "WHO receives|sends OBJECT [with TEAM]"

WHO = a league username (case-insensitive prefix/substring ok) | me | *;
OBJECT = picks | players | pos:QB|RB|WR|TE | an asset name ("Stefon Diggs",
"2027 R1 (own)"). Posture defaults and market-intel constraints auto-apply
per §4 strict precedence (query > intel > posture, per team) unless
--no-posture / --no-intel. Sliders: --delta (robust default), --min-return,
--favor-min/--favor-max, plus structural --shape / --legs A+B / --with TEAM.
A favor window pushes down to LEG level before the crossing (v5.0.1), so
favor-banded queries usually finish exhaustively; numeric-δ walks order by a
per-leg δ-score instead of the isolation floor. Warm/cold cache and count
honesty are reported in the header. v5.1: a completed crossing is EXACT — the
crossing never prunes, so every pooled pair was visited and priced by its exact
combined coordinates, whatever --delta says, and "no spreads matched" means no
such spread exists AMONG THE POOLED LEGS; a budget-truncated crossing stays a
verified floor. That scope is real: the pool keeps only
`variants_per_signature` package variants per (counterparty, give,
count-signature), a disclosed pre-ranking heuristic (§5), so "none exists" is
never a claim about the whole legal package space. A numeric --delta remains a
labeled preference VIEW of the RANKING (§4a).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv

load_dotenv()

from core import dashboard as dash  # noqa: E402
from core import store  # noqa: E402
from core.db import get_db  # noqa: E402
from core.scoring import Params, Snapshot  # noqa: E402
from core.scoring import constraints as cn  # noqa: E402
from core.scoring import finder as fi  # noqa: E402
from core.scoring import model as md  # noqa: E402
from core.scoring import trades as tr  # noqa: E402

MAX_SWEETENER_V = 3500.0  # alternatives: largest add-on asset considered
SWAP_BAND_V = 1500.0  # alternatives: |v delta| for like-for-like swaps
STALE_HOURS = dash._STALE_HOURS  # one staleness threshold everywhere (6h)


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
        ktc_calculator=store.ktc_calculator(db=db),
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


def favor_tag(f: float) -> str:
    """Plain-language read of a §4a v5 favor figure (signed KTC-calculator
    skew to the counterparty, in KTC's own variance units): |f| <= 5 is
    literally their calculator's FAIR window at default variance."""
    if abs(f) <= 5.0:
        return "their calculator: FAIR"
    return f"favors them {f:+g}" if f > 0 else f"favors you {f:+g}"


def match_team(league, tok: str, where: str, allow_me: bool = True) -> str:
    """Resolve a username token (case-insensitive exact, else unique
    substring). Errors name the offending token and list valid usernames."""
    m = [n for n in league.teams if n.lower() == tok.lower()] or [
        n for n in league.teams if tok.lower() in n.lower()
    ]
    valid = sorted(league.teams) if allow_me else sorted(set(league.teams) - {league.me})
    if len(m) > 1:
        sys.exit(f"{where}: ambiguous team token {tok!r} (matches {sorted(m)}) — "
                 f"valid usernames: {valid}")
    if not m:
        sys.exit(f"{where}: unknown team token {tok!r} — valid usernames: {valid}")
    if not allow_me and m[0] == league.me:
        sys.exit(f"{where}: team token {tok!r} resolves to you ({league.me}) — "
                 f"name a counterparty: {valid}")
    return m[0]


def parse_constraint(league, mode: str, text: str) -> dict:
    """One --require/--exclude/--prefer string -> a §4 constraint dict:

        "WHO receives|sends OBJECT [with TEAM]"

    WHO = username | me | *; OBJECT = picks | players | pos:POS | asset name.
    Parse errors name the offending token and list the valid usernames; the
    dict is validated eagerly through cn.query_constraint (same rules the
    finder applies), so a bad position or unrostered asset dies here too."""
    where = f'--{mode} "{text}"'
    toks = text.split()
    if len(toks) < 3:
        sys.exit(
            f"{where}: expected 'WHO receives|sends OBJECT [with TEAM]' — "
            f"got only {len(toks)} token(s)"
        )
    who_tok, side = toks[0], toks[1]
    if who_tok.lower() == "me":
        who = "me"
    elif who_tok == "*":
        who = "*"
    else:
        who = match_team(league, who_tok, f"{where} (WHO)")
    if side not in ("receives", "sends"):
        sys.exit(f"{where}: bad side token {side!r} — must be 'receives' or 'sends'")
    rest = toks[2:]
    with_ = None
    if len(rest) >= 3 and rest[-2].lower() == "with":
        with_ = match_team(league, rest[-1], f"{where} (with TEAM)", allow_me=False)
        rest = rest[:-2]
    obj = " ".join(rest).strip().strip("\"'")
    if not obj:
        sys.exit(f"{where}: missing OBJECT (picks | players | pos:RB | asset name)")
    low = obj.lower()
    if low in ("pick", "picks"):
        what: dict = {"class": "pick"}
    elif low in ("player", "players"):
        what = {"class": "player"}
    elif low.startswith("pos:"):
        what = {"pos": obj[4:].strip().upper()}
    else:
        what = {"asset": obj}
    d = {"who": who, "side": side, "what": what, "with": with_, "mode": mode}
    try:
        cn.query_constraint(league, d)
    except ValueError as e:
        sys.exit(f"{where}: {e}")
    return d


def fmt_constraint(c: dict) -> str:
    """One applied-constraint echo line from Constraint.to_dict() output."""
    ((kind, val),) = c["what"].items()
    obj = {"pick": "picks", "player": "players"}[val] if kind == "class" else (
        f"pos:{val}" if kind == "pos" else f'"{val}"'
    )
    tail = f" with {c['with']}" if c.get("with") else ""
    return f"{c['mode']:7} {c['who']} {c['side']} {obj}{tail}   [{c['origin']}]"


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
    fav = card.get("favor")
    fav_s = f", favor {fav:+g} ({favor_tag(fav)})" if fav is not None else ""
    return (
        f"send {give} -> get {get}  "
        f"(floor alone {card['floor']['me']:+.0f}{tail}, leg floor return {ret:g}%{fav_s})"
    )


def fmt_asset(a: dict) -> str:
    tag = f"{a['name']} ({a['v']}"
    if a.get("v_me") is not None:
        # §1 v7.5: unreachable — one price per pick (flat Mid beyond this
        # year, v7.6). Tripwire: a re-diverged lens is disclosed, never hidden.
        tag += f" market / {a['v_me']} yours"
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
        "  (your dF prices picks conservatively — v7 §1; theirs is market face)",
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
        f"  Favor (v5 §4a): {card['favor']:+g} — {favor_tag(card['favor'])} "
        "(signed skew to the counterparty from the gate's own adjusted totals, "
        "KTC's variance units; |f| <= 5 = their calculator's FAIR window)"
        if card.get("favor") is not None
        else "  Favor (v5 §4a): n/a",
        f"  Posture: {card['counterparty']} is {p['label']}"
        + (f" (override)" if p["source"] == "override" else f" ({p['evidence_count']} classifying trades)")
        + f" · offer shape {p['shape']} ({'fits' if p['fit'] else 'does not fit'})",
        f"  Leg: {card['leg_type']} · counts you: {card['net_players']['me']:+d} players / "
        f"{card['net_picks']['me']:+d} picks (§5 v3.2; net active roster "
        f"{card['net_roster']['me']:+d} you / {card['net_roster']['them']:+d} them)"
        + (
            f" · market return {card['market_return_pct']:+g}% (info only — "
            "the raw face skim; the v5 dial reads Favor above)"
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


def run_find(args, db, league: md.LeagueState) -> None:
    """The §4a v5 `find` subcommand: parse constraint flags, pull active
    market-intel from Mongo (the finder is I/O-free — the caller reads the
    collection), run the finder, and print header (constraints echo, intel
    applied/ignored, honest counts, cache cold/warm + timing) then spreads."""
    constraints = (
        [parse_constraint(league, "require", s) for s in args.require]
        + [parse_constraint(league, "exclude", s) for s in args.exclude]
        + [parse_constraint(league, "prefer", s) for s in args.prefer]
    )
    if args.delta == "robust":
        delta: str | float = "robust"
    else:
        try:
            delta = float(args.delta)
        except ValueError:
            sys.exit(f"--delta {args.delta!r}: must be 'robust' or a number in "
                     "[0, 1] (presets 0 / 0.25 / 0.5 / 0.75 / 1)")
        if not 0.0 <= delta <= 1.0:
            sys.exit(f"--delta {delta:g}: must lie in [0, 1]")
    legs = None
    if args.legs:
        parts = [p.strip() for p in args.legs.split("+")]
        if len(parts) != 2 or not all(parts):
            sys.exit(f"--legs {args.legs!r}: expected exactly 'A+B' — two "
                     "counterparty usernames joined by '+'")
        a = match_team(league, parts[0], "--legs (A)", allow_me=False)
        b = match_team(league, parts[1], "--legs (B)", allow_me=False)
        if a == b:
            sys.exit(f"--legs {args.legs!r}: A and B both resolve to {a} — name two teams")
        # "one leg with A, the other with B": restrict enumeration to A and B;
        # the cross already requires distinct counterparties, so the pairs are
        # exactly (buy A, sell B) and (buy B, sell A)
        legs = {"buy_with": [a, b], "sell_with": [a, b]}
    with_team = (
        match_team(league, args.with_team, "--with", allow_me=False)
        if args.with_team else None
    )
    intel: list[dict] = []
    if not args.no_intel:
        intel = list(db["market-intel"].find({}).sort("_id", 1))
        for doc in intel:  # skill protocol stores the subject text as `note`
            if "subject" not in doc and doc.get("note") is not None:
                doc["subject"] = doc["note"]
    query = {
        "constraints": constraints,
        "use_intel": not args.no_intel,
        "use_posture": not args.no_posture,
        "delta": delta,
        "min_return": args.min_return,
        "favor_min": args.favor_min,
        "favor_max": args.favor_max,
        "legs": legs,
        "with_team": with_team,
        "shape": args.shape,
        "top": args.top,
    }
    warm = fi.cache_path(league).exists()
    t0 = perf_counter()
    res = fi.find_spreads(league, query, intel=intel)
    dt = perf_counter() - t0

    if args.json:
        print(json.dumps(
            {"query": query, "cache": "warm" if warm else "cold",
             "seconds": round(dt, 2), **res,
             # v5.1: `exact` says the crossing was not budget-truncated, and
             # since the crossing never prunes that is exactly the certificate
             # — every pooled pair was visited and priced exactly, at any δ. It
             # is scoped to the POOLED legs: `variants_per_signature` package
             # variants per (counterparty, give, count-signature) is a
             # disclosed pre-ranking heuristic (§5), so matched == 0 with
             # exact == true means "none among the pooled legs".
             "exact_scope": "pooled-legs"},
            indent=1, default=str,
        ))
        return

    # ---- header: cache + timing, sliders, constraints echo, intel, counts
    print(f"Spread finder (§4a v5) — cache {'WARM' if warm else 'COLD (leg tables built + cached)'} "
          f"· query {dt:.1f}s")
    dial = ("robust (guaranteed floor — good at EVERY delta)"
            if delta == "robust" else f"{delta:g} (labeled preference VIEW)")
    slid = [f"delta {dial}", f"min return {args.min_return:g}%"]
    slid.append(f"favor min {args.favor_min:+g}" if args.favor_min is not None else "no favor floor")
    if args.favor_max is not None:
        slid.append(f"favor max {args.favor_max:+g} (either leg)")
    if args.shape:
        slid.append(f"shape {args.shape}")
    if legs:
        slid.append(f"legs {legs['buy_with'][0]}+{legs['buy_with'][1]}")
    if with_team:
        slid.append(f"with {with_team}")
    print("Sliders: " + " · ".join(slid))
    ac = res["applied_constraints"]
    if ac:
        print(f"Constraints applied ({len(ac)}; §4 precedence query > intel > posture, per team):")
        for c in ac:
            print(f"  {fmt_constraint(c)}")
    else:
        print("Constraints applied: none (unconstrained search)")
    if args.no_intel:
        print("Intel: OFF (--no-intel)")
    else:
        n_int = sum(1 for c in ac if c["source"] == "intel")
        ig = res["ignored_intel"]
        print(f"Intel: {len(intel)} doc(s) read · {n_int} constraint(s) applied · "
              f"{len(ig)} ignored (unparseable/NOTE — reported, never guessed):")
        for item in ig:
            d = item["doc"]
            print(f"  ignored {d.get('kind')} [{d.get('team')}] "
                  f"{d.get('subject')!r}: {item['reason']}")
    if args.no_posture:
        print("Posture defaults: OFF (--no-posture)")
    c = res["counts"]
    # v5.1 honesty. The engine's `exact` flag says the constrained crossing was
    # NOT budget-truncated — and the finder's crossing never prunes (the v5.1
    # sound key only decides what a TRUNCATION keeps), so a completed crossing
    # visited and exactly priced every pooled pair at any δ. The one live
    # caveat is the pool: `variants_per_signature` variants per (counterparty,
    # give, count-signature) is a disclosed pre-ranking heuristic (§5), so the
    # certificate is over the POOLED legs, never the whole package space.
    if res["exact"]:
        honesty = (
            "EXACT over the pooled legs — the constrained crossing completed "
            "(it never prunes: every pooled pair was visited and priced by its "
            "exact combined coordinates); these counts are provable, with the "
            "pool's per-signature variant cap as the disclosed limit (§5)"
        )
    else:
        honesty = (
            f"VERIFIED FLOORS — crossing budget {league.params.finder_cross_budget:,} "
            "hit; the space runs deeper (never estimates)"
        )
    print(f"Counts [{honesty}]: {c['legs']['buy']:,} buy legs / {c['legs']['sell']:,} sell legs "
          f"· crossings {c['crossings']:,} · valid pairs {c['valid']:,} "
          f"· matched sliders {c['matched']:,} · returned {c['returned']}")

    # ---- the spreads
    if not res["spreads"]:
        if res["exact"]:
            print("\nNo spreads matched — NONE EXIST among the pooled legs. The "
                  "crossing completed and it never prunes, so every pair the pool "
                  "can form was visited and priced by its exact combined "
                  "coordinates: this is proof of absence over that pool, not a "
                  "budget artifact. The one hedge is the pool itself — it keeps "
                  f"{league.params.variants_per_signature} package variants per "
                  "(counterparty, give, count-signature) as a disclosed "
                  "pre-ranking heuristic (§5), so a variant outside that cap is "
                  "not ruled out. Loosen a slider or drop a constraint; the counts "
                  "above show where candidates died.")
        else:
            print("\nNo spreads matched WITHIN THE CROSSING BUDGET — a verified "
                  "floor, not proof of absence: the space runs deeper than the walk "
                  "reached. Narrow the space (favor window, --legs, constraints) so "
                  "the crossing finishes exhaustively, or loosen a slider.")
        return
    for sp in res["spreads"]:
        head = f"\n{sp['id']}"
        if sp["preferred"]:
            head += "  ★ preferred (a prefer-constraint matches)"
        if delta == "robust":
            head += (f"  guaranteed {sp['floor']:+g} · up to {sp['ceiling']:+g} "
                     f"(floor return {sp['return_robust']:g}% on {sp['sent']:g} face sent)")
        else:
            head += (f"  return(delta={delta:g}) {sp['return_view']:g}% — labeled VIEW "
                     f"(robust floor return {sp['return_robust']:g}% on {sp['sent']:g} face sent)")
        head += f"  [{fmt_coords(sp['coords'])}]"
        print(head)
        if sp["verdict"]:
            lo_hi = ("gain exactly" if sp["floor"] == sp["ceiling"] else "gain between")
            print(f"  verdict: OBJECTIVELY GOOD — {lo_hi} {sp['floor']:+g} and "
                  f"{sp['ceiling']:+g} (floor guaranteed, §2 v4)")
        else:
            bkv = tr.breakeven_of(sp["coords"]["dS"], sp["coords"]["dF"])
            print("  verdict: NOT objectively good — preference trade"
                  + (f", breakeven delta* = {bkv:.2f}" if bkv is not None else "")
                  + f" (interval {sp['floor']:+g} to {sp['ceiling']:+g})")
        f = sp["favor"]
        print(f"  favor: buy {f['buy']:+g} ({favor_tag(f['buy'])}) · "
              f"sell {f['sell']:+g} ({favor_tag(f['sell'])}) · "
              f"pair min {f['min']:+g} (the least-happy counterparty)")
        for tag, card in (("BUY ", sp["buy"]), ("SELL", sp["sell"])):
            give = " + ".join(fmt_asset(a) for a in card["give"])
            get = " + ".join(fmt_asset(a) for a in card["get"])
            print(f"  {tag} {card['counterparty']:<15} send {give} -> get {get}  "
                  f"(leg floor alone {card['floor']['me']:+.0f})")
        print(f"  net: 0 players / 0 picks · active roster {sp['net_roster']:+d} · "
              f"{sp['sequencing']}")
        if 0 < sp["floor"] < league.params.w_min:
            print(f"  note: floor +{sp['floor']:g} sits inside KTC's "
                  f"±{league.params.w_min:g} noise band (display note only)")


def run_dashboard(args, db, league: md.LeagueState, fresh: dict) -> None:
    """The v7.1 hedge board: one exhaustive `find_spreads` per counterparty,
    rendered as a standalone HTML page. The skill publishes the file; nothing
    here is recomputed for display, so the page cannot disagree with `find`."""
    if args.delta == "robust":
        delta: str | float = "robust"
    else:
        try:
            delta = float(args.delta)
        except ValueError:
            sys.exit(f"--delta {args.delta!r}: must be 'robust' or a number in [0, 1]")
        if not 0.0 <= delta <= 1.0:
            sys.exit(f"--delta {delta:g}: must lie in [0, 1]")
    intel: list[dict] = []
    if not args.no_intel:
        intel = list(db["market-intel"].find({}).sort("_id", 1))
        for doc in intel:  # skill protocol stores the subject text as `note`
            if "subject" not in doc and doc.get("note") is not None:
                doc["subject"] = doc["note"]
    workers = args.workers or dash.default_workers()
    age, age_hours = None, None
    if fresh["last_collect"]:
        age_hours = (
            datetime.now(timezone.utc)
            - fresh["last_collect"].replace(tzinfo=timezone.utc)
        ).total_seconds() / 3600
        age = f"{age_hours:.1f}h old"
    n_opp = len(league.opponents)
    print(
        f"Hedge board: {n_opp} counterparty searches on {workers} worker(s) — "
        "each one exhaustive, so this is minutes not seconds.",
        file=sys.stderr,
    )
    t0 = perf_counter()
    payload = dash.hedge_payload(
        league,
        sliders={
            "delta": delta,
            "min_return": args.min_return,
            "favor_min": args.favor_min,
            "favor_max": args.favor_max,
            "top": args.top,
            "use_intel": not args.no_intel,
            "use_posture": not args.no_posture,
        },
        intel=intel,
        workers=workers,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        data_age=age,
        data_age_hours=age_hours,
    )
    dt = perf_counter() - t0
    if args.json:
        print(json.dumps(payload, indent=1, default=str))
        return
    out = Path(args.out)
    out.write_text(dash.render_html(payload), encoding="utf-8")
    t = payload["totals"]
    print(
        f"Wrote {out} in {dt:.0f}s — {t['with_hedges']}/{t['teams']} counterparties "
        f"have a hedge clearing the sliders, {t['matched']:,} in total"
        + ("" if t["all_exact"] else " (some crossings budget-truncated — counts are floors)"),
        file=sys.stderr,
    )
    print(out)


# --------------------------------------------------- the hedge database (v8 §12)


def _say(msg: str) -> None:
    print(msg, file=sys.stderr)


def read_intel(db) -> list[dict]:
    """Active market-intel docs with the skill's note→subject shim — the same
    shim `find` applies (the compiler re-checks `active` itself; filtering here
    just keeps revoked docs out of the counts and the bake)."""
    intel = [
        d for d in db["market-intel"].find({}).sort("_id", 1) if d.get("active", True)
    ]
    for doc in intel:  # skill protocol stores the subject text as `note`
        if "subject" not in doc and doc.get("note") is not None:
            doc["subject"] = doc["note"]
    return intel


def parse_delta(raw: str):
    if raw == "robust":
        return "robust"
    try:
        d = float(raw)
    except ValueError:
        sys.exit(f"--delta {raw!r}: must be 'robust' or a number in [0, 1]")
    if not 0.0 <= d <= 1.0:
        sys.exit(f"--delta {d:g}: must lie in [0, 1]")
    return d


def match_opp(opp_names, tok: str, where: str) -> str:
    """Resolve a counterparty token against the DB's own opponent list —
    case-insensitive exact, else unique substring; ambiguity lists candidates."""
    m = [n for n in opp_names if n.lower() == tok.lower()] or [
        n for n in opp_names if tok.lower() in n.lower()
    ]
    if len(m) > 1:
        sys.exit(
            f"{where}: ambiguous team token {tok!r} (matches {sorted(m)}) — "
            f"counterparties: {sorted(opp_names)}"
        )
    if not m:
        sys.exit(
            f"{where}: unknown team token {tok!r} — counterparties: {sorted(opp_names)}"
        )
    return m[0]


def parse_favor_for(specs, opp_names) -> dict | None:
    """Repeatable --favor-for TEAM=MIN:MAX (either bound omittable: 'TEAM=-3:'
    floors only, 'TEAM=:2' caps only), in the engine's counterparty-positive
    units."""
    out: dict[str, dict] = {}
    for spec in specs:
        where = f'--favor-for "{spec}"'
        team_tok, eq, window = spec.partition("=")
        if not eq or not team_tok.strip():
            sys.exit(f"{where}: expected TEAM=MIN:MAX (either bound omittable)")
        team = match_opp(opp_names, team_tok.strip(), where)
        lo_s, colon, hi_s = window.partition(":")
        if not colon:
            sys.exit(
                f"{where}: expected MIN:MAX after '=' (either bound omittable: "
                "'-3:' floors only, ':2' caps only)"
            )
        try:
            lo = float(lo_s) if lo_s.strip() else None
            hi = float(hi_s) if hi_s.strip() else None
        except ValueError:
            sys.exit(f"{where}: bounds must be numbers, got {window!r}")
        if lo is None and hi is None:
            sys.exit(f"{where}: at least one bound is required")
        out[team] = {"min": lo, "max": hi}
    return out or None


def open_hedgedb(snapshot):
    from core.scoring import hedgedb as hd

    try:
        return hd.HedgeDB.open_for(snapshot)
    except FileNotFoundError:
        sys.exit(
            "no hedge DB matches the current Mongo content — run "
            "`uv run python scripts/score_trade.py hedgedb build` first "
            "(the data changed since the last build, or none was ever built)"
        )
    except ImportError as e:
        sys.exit(str(e))


def hedgedb_query(args, hddb, league) -> dict:
    """The full §4 filter state as a hedgedb query dict. `top` is pinned to the
    DB's stored search depth so the default board hits the baked cache; the
    display slice is the CLI's --top."""
    constraints = (
        [parse_constraint(league, "require", s) for s in args.require]
        + [parse_constraint(league, "exclude", s) for s in args.exclude]
        + [parse_constraint(league, "prefer", s) for s in args.prefer]
    )
    return {
        "constraints": constraints,
        "use_intel": not args.no_intel,
        "use_posture": not args.no_posture,
        "delta": parse_delta(args.delta),
        "min_return": args.min_return,
        "favor_min": args.favor_min,
        "favor_max": args.favor_max,
        "favor_for": parse_favor_for(args.favor_for, hddb.opp_names),
        "shape": args.shape,
        "top": int(hddb.meta.get("store_top", 50)),
    }


def db_data_age(hddb, fresh) -> tuple[str | None, float | None]:
    """The snapshot-age axis: the collect the DB was PRICED from (stamped into
    meta.json at build), falling back to the live runs collection for DBs built
    before the stamp existed."""
    ts = None
    lc = hddb.meta.get("last_collect")
    if lc:
        try:
            ts = datetime.fromisoformat(lc)
        except ValueError:
            ts = None
    if ts is None:
        ts = fresh.get("last_collect")
    if ts is None:
        return None, None
    hours = (
        datetime.now(timezone.utc) - ts.replace(tzinfo=timezone.utc)
    ).total_seconds() / 3600
    return f"{hours:.1f}h old", hours


def hd_sliders(args, query) -> dict:
    """The display-slider echo both hedge-DB pages carry (the search itself
    runs at the DB's stored depth; `--top` is the display slice)."""
    return {
        "delta": query["delta"],
        "min_return": args.min_return,
        "favor_min": args.favor_min,
        "favor_max": args.favor_max,
        "favor_for": query["favor_for"],
        "shape": args.shape,
        "top": args.top,
        "use_intel": not args.no_intel,
        "use_posture": not args.no_posture,
    }


def hd_freshness(snapshot, fresh, hddb):
    """The two freshness axes every hedge-DB page shows: snapshot age, and
    whether the live collect moved past the DB's content fingerprint."""
    from core.scoring import hedgedb as hd

    age, age_hours = db_data_age(hddb, fresh)
    mongo_newer = hd.content_fingerprint(snapshot) != hddb.meta["content_fingerprint"]
    if mongo_newer:
        _say(
            "WARNING: the collector has newer data than this DB — the page "
            "will say so in red; run `hedgedb build` before quoting"
        )
    return age, age_hours, mongo_newer


def hedgedb_board_payload(args, db, snapshot, fresh, hddb, *, focus=None):
    """One `db.search` per counterparty (cache hits after the bake unless the
    filter state changed) assembled into the v8 board payload."""
    league = hddb.league
    intel = [] if args.no_intel else read_intel(db)
    query = hedgedb_query(args, hddb, league)
    results: dict[str, dict] = {}
    for opp in sorted(hddb.opp_names):
        t0 = perf_counter()
        try:
            res = hddb.search({**query, "with_team": opp}, intel=intel)
        except ValueError as e:
            sys.exit(str(e))
        dt = perf_counter() - t0
        tag = "cache" if res["db"]["cached"] else f"walk {dt:.1f}s"
        _say(
            f"  {opp}: {tag} · matched {res['counts']['matched']:,}"
            + ("" if res["exact"] else " (budget-truncated)")
        )
        results[opp] = res
    age, age_hours, mongo_newer = hd_freshness(snapshot, fresh, hddb)
    return dash.db_payload(
        hddb,
        results,
        sliders=hd_sliders(args, query),
        focus=focus,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        mongo_newer=mongo_newer,
        data_age=age,
        data_age_hours=age_hours,
    )


def run_hedgedb_build(args, db, snapshot, fresh) -> None:
    """`hedgedb build`: enumerate + persist the complete band pool from the
    live Mongo snapshot, stamp the freshness axis, bake the default board."""
    try:
        from core.scoring import hedgedb as hd
    except ImportError as e:  # pragma: no cover - environment-dependent
        sys.exit(str(e))
    last = fresh.get("last_collect")
    if last is None:
        if not args.allow_stale:
            sys.exit(
                "no successful collect on record — run `just collect` first, or "
                "pass --allow-stale to build from whatever Mongo holds"
            )
    else:
        age_h = (
            datetime.now(timezone.utc) - last.replace(tzinfo=timezone.utc)
        ).total_seconds() / 3600
        if age_h >= STALE_HOURS and not args.allow_stale:
            sys.exit(
                f"last ok collect is {age_h:.1f}h old (>= {STALE_HOURS:g}h) — the DB "
                "persists priced values, so build it from fresh data: run "
                "`just collect` first, or pass --allow-stale to build anyway"
            )
    intel = read_intel(db)
    workers = (
        args.workers if args.workers and args.workers > 0
        else max(1, (os.cpu_count() or 2) - 2)
    )
    t0 = perf_counter()
    try:
        hddb = hd.build(snapshot, Params(), bake=False, progress=_say)
    except ImportError as e:
        sys.exit(str(e))
    # stamp the freshness axis (read-modify-write: the build wrote the rest)
    meta_path = hddb.path / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["last_collect"] = last.isoformat() if last else None
    meta_path.write_text(json.dumps(meta, indent=2))
    hddb.meta["last_collect"] = meta["last_collect"]
    if not args.no_bake:
        _say(f"baking the default board on {workers} worker(s) …")
        _ = hddb.league  # materialize BEFORE the fork so children inherit it COW
        hddb.bake_default_board(intel=intel, workers=workers, progress=_say)
    _say(
        f"hedge DB ready in {perf_counter() - t0:.0f}s: {hddb.path} "
        f"({hddb.meta['legs']:,} legs, band ±{hddb.meta['band']:g})"
    )
    print(hddb.path)


def run_hedgedb_board(args, db, snapshot, fresh) -> None:
    """`hedgedb board`: the per-counterparty board rendered FROM THE DB — the
    stored snapshot's league, cached exact searches, live Mongo touched only
    for intel and the freshness banners."""
    hddb = open_hedgedb(snapshot)
    focus = match_opp(hddb.opp_names, args.focus, "--focus") if args.focus else None
    _say(
        f"hedge board from the DB at {hddb.path} — cached filter states are "
        "instant, novel ones walk once and cache"
    )
    payload = hedgedb_board_payload(args, db, snapshot, fresh, hddb, focus=focus)
    if args.json:
        print(json.dumps(payload, indent=1, default=str))
        return
    out = Path(args.out)
    out.write_text(dash.render_html(payload), encoding="utf-8")
    t = payload["totals"]
    _say(
        f"Wrote {out} — {t['with_hedges']}/{t['teams']} counterparties have a "
        f"hedge clearing the sliders, {t['matched']:,} matched in total"
        + ("" if t["all_exact"] else " (some searches budget-truncated — counts are floors)")
    )
    print(out)


def run_hedgedb_offer(args, db, snapshot, fresh) -> None:
    """`hedgedb offer` (v8.1 pinned-offer mode): score the proposal with the
    REAL gate (any assets — cornerstones, taxi, >3 pieces all scoreable),
    cross it against the stored legs of every other counterparty, and write
    the PINNED-OFFER page — the offer atop one card per remaining
    counterparty with its exact hedge set. Its own canonical --out path
    (hedge-offer.html); the board file is never touched, so both published
    artifact URLs stay stable. No per-team searches run: the page is a view
    over the one crossing, so regenerating per filter tweak is fast."""
    hddb = open_hedgedb(snapshot)
    league = hddb.league
    match = [n for n in league.teams if n.lower() == args.opponent.lower()] or [
        n for n in league.teams if args.opponent.lower() in n.lower()
    ]
    if len(match) != 1 or match[0] == league.me:
        sys.exit(
            f"Opponent {args.opponent!r} not found/ambiguous. Teams: "
            f"{sorted(set(league.teams) - {league.me})}"
        )
    opp_name = match[0]
    me_assets = tr.team_assets(league, league.teams[league.me])
    opp_assets = tr.team_assets(league, league.teams[opp_name])
    give = [resolve(me_assets, q, league.me) for q in args.give.split(",") if q.strip()]
    get = [resolve(opp_assets, q, opp_name) for q in args.get.split(",") if q.strip()]
    intel = [] if args.no_intel else read_intel(db)
    query = hedgedb_query(args, hddb, league)
    try:
        res = hddb.offer(
            opp_name,
            [a.name for a in give],
            [a.name for a in get],
            query=query,
            intel=intel,
        )
    except ValueError as e:
        sys.exit(str(e))

    if args.json:
        print(json.dumps(res, indent=1, default=str))
    else:
        card = res["offer"]
        verdict = card["gate"]["verdict"]
        print(f"OFFER — with {opp_name}: GATE {verdict}")
        print()
        print(fmt_card(card))
        if res.get("note"):
            print(f"\n{res['note']}")
        counts = res.get("counts")
        if counts:
            honesty = (
                "EXACT — the crossing completed over every eligible stored leg"
                if res.get("exact", True)
                else f"VERIFIED FLOORS — search budget "
                f"{league.params.hedgedb_search_budget:,} hit"
            )
            print(
                f"\nHedge search [{honesty}]: {counts['candidates']:,} stored "
                f"complement legs · crossings {counts['crossings']:,} · valid "
                f"{counts['valid']:,} · matched {counts['matched']:,} · "
                f"returned {counts['returned']}"
            )
        hedges = res["hedges"]
        if hedges:
            label = (
                "Hedges by counterparty (pair figures are EXACT combined — the "
                "offer and the hedge applied together; ranked maximin, best "
                f"team first; your offer is the {hedges[0]['offer_side']} side):"
                if verdict.startswith("PASS")
                else "Hedges by counterparty — IF YOU TOOK IT ANYWAY (this offer "
                "FAILS the gate; every hedge below assumes you executed it "
                f"regardless; your offer is the {hedges[0]['offer_side']} side):"
            )
            print(f"\n{label}")
            exact = res.get("exact", True)
            mb = (res.get("counts") or {}).get("matched_by_team") or {}
            for name, hs in (res.get("by_team") or {}).items():
                if not hs:
                    print(
                        f"\n  {name}: "
                        + (
                            "none exist among its stored legs"
                            if exact
                            else "none found within budget"
                        )
                    )
                    continue
                tally = f"{mb.get(name, 0):,}" + ("" if exact else "+")
                print(f"\n  {name} — {tally} matched, best {len(hs[:args.top])}:")
                for h in hs[: args.top]:
                    hc = h["hedge"]
                    gv = " + ".join(a["name"] for a in hc["give"])
                    gt = " + ".join(a["name"] for a in hc["get"])
                    print(
                        f"    {h['id']}: send {gv} → get {gt} · PAIR guaranteed "
                        f"{h['floor']:+g} · up to {h['ceiling']:+g} · floor return "
                        f"{h['return_robust']:g}% on {h['sent']:g} Σv · favor "
                        f"offer {h['favor']['offer']:+g} / hedge "
                        f"{h['favor']['hedge']:+g}"
                    )
            print(
                "\nFull cards, per-leg gates and KTC links are on the "
                "pinned-offer page."
            )
        elif not res.get("note"):
            print(
                "\nNo stored hedge clears the sliders against this offer — loosen "
                "a slider or drop a constraint (the counts above show where "
                "candidates died)."
            )

    _say("\nwriting the pinned-offer page (the offer atop per-counterparty hedge sets) …")
    age, age_hours, mongo_newer = hd_freshness(snapshot, fresh, hddb)
    payload = dash.offer_payload(
        hddb,
        res,
        sliders=hd_sliders(args, query),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        mongo_newer=mongo_newer,
        data_age=age,
        data_age_hours=age_hours,
    )
    out = Path(args.out)
    out.write_text(dash.render_html(payload), encoding="utf-8")
    _say(f"Wrote {out}")
    if not args.json:
        print(out)


def run_hedgedb_status(args, db, snapshot, fresh) -> None:
    """`hedgedb status`: where the DB is, what it holds, and whether the live
    Mongo content still matches it. Reads meta.json directly (no numpy needed)."""
    from core.scoring import hedgedb as hd

    live_cf = hd.content_fingerprint(snapshot)
    target = hd.db_dir(snapshot, Params())
    root = target.parent
    path = target if (target / "meta.json").exists() else None
    if path is None and root.exists():
        cands = sorted(
            (p.parent for p in root.glob("*/meta.json")),
            key=lambda p: (p / "meta.json").stat().st_mtime,
            reverse=True,
        )
        path = cands[0] if cands else None
    if path is None:
        sys.exit(
            "no hedge DB built — run `uv run python scripts/score_trade.py hedgedb build`"
        )
    meta = json.loads((path / "meta.json").read_text())
    searches_dir = path / "searches"
    n_cached = (
        sum(1 for _ in searches_dir.glob("*.json")) if searches_dir.exists() else 0
    )
    lc = meta.get("last_collect")
    age = ""
    if lc:
        try:
            h = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(lc).replace(tzinfo=timezone.utc)
            ).total_seconds() / 3600
            age = f" ({h:.1f}h ago)"
        except ValueError:
            pass
    current = meta["content_fingerprint"] == live_cf
    print(f"hedge DB: {path}")
    print(
        f"  legs: {meta['legs']:,} · band ±{meta['band']:g} · "
        f"packages {meta.get('packages', 0):,} · assets {meta.get('assets', 0):,}"
    )
    print(f"  content fingerprint: {meta['content_fingerprint'][:16]}")
    print(f"  snapshot last collect: {lc or 'never stamped'}{age}")
    print(
        "  live Mongo: "
        + (
            "MATCHES this DB — boards render current"
            if current
            else f"MOVED PAST this DB (live {live_cf[:16]}) — run `hedgedb build` "
            "before you quote anything"
        )
    )
    print(f"  cached searches: {n_cached} in {searches_dir}")


def run_hedgedb(args, db, snapshot, fresh) -> None:
    {
        "build": run_hedgedb_build,
        "board": run_hedgedb_board,
        "offer": run_hedgedb_offer,
        "status": run_hedgedb_status,
    }[args.hd_cmd](args, db, snapshot, fresh)


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
        help="the §5 v5 pair board behind your dials (same code path as the nightly board)",
    )
    pr.add_argument(
        "--min", "--target", dest="min_ret", type=float, default=5.0,
        help="floor on TOTAL pair return, percent (presets 1 / 2.5 / 5 / 10 / 20; "
        "--target is the v3.3 alias)",
    )
    pr.add_argument(
        "--favor-min", dest="favor_min", type=float, default=None,
        help="v5: floor on pair favor min(f_buy, f_sell) — each leg's signed "
        "KTC-calculator skew to its counterparty, KTC's own variance units "
        "(presets -10 / -5 / 0 / +2.5 / +5; |f| <= 5 is their calculator's "
        "FAIR window; omit for no floor). Replaces the retired v3.4.1 --max "
        "per-leg market-return cap",
    )
    pr.add_argument("--json", action="store_true")
    fd = sub.add_parser(
        "find",
        help="§4a v5 spread finder: constrained search over the FULL pair space "
        "with the three sliders (delta view, min return, counterparty favor)",
        description="Constraint grammar (repeatable flags): "
        '--require/--exclude/--prefer "WHO receives|sends OBJECT [with TEAM]" '
        "where WHO = username | me | * and OBJECT = picks | players | "
        "pos:QB|RB|WR|TE | an asset name. Posture defaults + market-intel "
        "auto-apply per §4 precedence (query > intel > posture, per team).",
    )
    for mode, hint in (
        ("require", "every leg involving WHO must match (hard)"),
        ("exclude", "no leg may match (hard)"),
        ("prefer", "matching spreads are starred (soft; never reorders)"),
    ):
        fd.add_argument(
            f"--{mode}", action="append", default=[], dest=mode,
            metavar='"WHO receives|sends OBJECT [with TEAM]"', help=hint,
        )
    fd.add_argument(
        "--no-intel", action="store_true",
        help="drop the market-intel constraints (§4 source 2)",
    )
    fd.add_argument(
        "--no-posture", action="store_true",
        help="drop the posture defaults (§4 source 1)",
    )
    fd.add_argument(
        "--delta", default="robust",
        help="slider 1: 'robust' (default — v4 floor/verdict, good at EVERY "
        "delta) or a number in [0, 1] (presets 0 / 0.25 / 0.5 / 0.75 / 1); "
        "numeric delta is a labeled preference VIEW, never a verdict",
    )
    fd.add_argument(
        "--min-return", dest="min_return", type=float, default=0.0,
        help="slider 2: floor on return(delta), percent (presets 1 / 2.5 / 5 / "
        "10 / 20; robust mode floors the guaranteed floor return)",
    )
    fd.add_argument(
        "--favor-min", dest="favor_min", type=float, default=None,
        help="slider 3: floor on pair favor min(f_buy, f_sell) in KTC's own "
        "variance units (presets -10 / -5 / 0 / +2.5 / +5; omit for none)",
    )
    fd.add_argument(
        "--favor-max", dest="favor_max", type=float, default=None,
        help="optional ceiling on EITHER leg's favor — stops giving edge away "
        "(omit for none)",
    )
    fd.add_argument(
        "--shape", choices=["starter>team", "team>starter"], default=None,
        help="shape constraint: starter>team means dS > dF, team>starter the reverse",
    )
    fd.add_argument(
        "--legs", default=None, metavar="A+B",
        help="one leg with A, the other with B (two counterparty usernames)",
    )
    fd.add_argument(
        "--with", dest="with_team", default=None, metavar="TEAM",
        help="TEAM must be on some leg of every returned spread",
    )
    fd.add_argument(
        "--top", type=int, default=None,
        help="result size (default: the engine's finder_top = 20)",
    )
    fd.add_argument("--json", action="store_true")

    dh = sub.add_parser(
        "dashboard",
        help="per-counterparty hedge board as a standalone HTML page — one "
        "exhaustive finder run per counterparty, written to --out",
        description="Runs `find` once per counterparty (with_team push-down, "
        "so each crossing is exhaustive) and renders the results as a "
        "self-contained HTML file. This is what the trade-negotiator skill "
        "publishes at the top of a negotiating session.",
    )
    dh.add_argument("--out", default="hedge-board.html", help="output path")
    dh.add_argument("--top", type=int, default=5, help="hedges shown per counterparty")
    dh.add_argument("--min-return", type=float, default=1.0, dest="min_return")
    dh.add_argument("--favor-min", type=float, default=-5.0, dest="favor_min")
    dh.add_argument("--favor-max", type=float, default=5.0, dest="favor_max")
    dh.add_argument(
        "--delta", default="robust",
        help="'robust' (default — the guaranteed floor) or a number in [0, 1]",
    )
    dh.add_argument(
        "--workers", type=int, default=0,
        help="parallel counterparty searches; 0 = cpu_count - 1, 1 = in-process",
    )
    dh.add_argument("--no-intel", action="store_true")
    dh.add_argument("--no-posture", action="store_true")
    dh.add_argument("--json", action="store_true", help="print the payload instead of HTML")

    hb = sub.add_parser(
        "hedgedb",
        help="§12 v8 the hedge database: complete legs, exact cached searches — "
        "build | board | offer | status",
        description="The v8 hedge database: `build` persists the COMPLETE "
        "fair-band leg pool from the live Mongo snapshot and bakes the default "
        "per-counterparty board; `board` renders the hedge board from the DB "
        "(cache hits unless the filter state is new); `offer` scores an "
        "arbitrary proposal with the REAL gate, crosses it against the stored "
        "legs of every other counterparty, and writes the pinned-offer page — "
        "the offer atop each remaining counterparty's exact hedge set (v8.1); "
        "`status` reports fingerprints and freshness.",
    )
    hsub = hb.add_subparsers(dest="hd_cmd", required=True)
    hbuild = hsub.add_parser(
        "build",
        help="build (or reopen, if the content fingerprint matches) the DB from "
        "the live Mongo snapshot, then bake the default board",
    )
    hbuild.add_argument(
        "--workers", type=int, default=0,
        help="bake parallelism (fork); 0 = cpu_count - 2",
    )
    hbuild.add_argument(
        "--no-bake", action="store_true",
        help="skip baking the default per-counterparty board searches",
    )
    hbuild.add_argument(
        "--allow-stale", action="store_true",
        help=f"build even if the last ok collect is older than {STALE_HOURS:g}h "
        "(the DB persists priced values — fresh data is the point)",
    )

    def add_hd_filters(p) -> None:
        """The full §4 filter flag set — board and offer take it IDENTICALLY
        (the skill re-passes the complete filter state on every invocation)."""
        for mode, hint in (
            ("require", "every leg involving WHO must match (hard)"),
            ("exclude", "no leg may match (hard)"),
            ("prefer", "matching spreads are starred (soft; never reorders)"),
        ):
            p.add_argument(
                f"--{mode}", action="append", default=[], dest=mode,
                metavar='"WHO receives|sends OBJECT [with TEAM]"', help=hint,
            )
        p.add_argument("--no-intel", action="store_true",
                       help="drop the market-intel constraints (§4 source 2)")
        p.add_argument("--no-posture", action="store_true",
                       help="drop the posture defaults (§4 source 1)")
        p.add_argument(
            "--delta", default="robust",
            help="'robust' (default — the guaranteed floor) or a number in [0, 1]",
        )
        p.add_argument("--min-return", dest="min_return", type=float, default=1.0,
                       help="floor on return, percent (default 1)")
        p.add_argument("--favor-min", dest="favor_min", type=float, default=-5.0,
                       help="floor on pair favor min (default -5; DB build band ±5)")
        p.add_argument("--favor-max", dest="favor_max", type=float, default=5.0,
                       help="ceiling on either leg's favor (default +5)")
        p.add_argument(
            "--favor-for", action="append", default=[], dest="favor_for",
            metavar="TEAM=MIN:MAX",
            help="per-team favor window in counterparty-positive units, "
            "repeatable; either bound omittable ('TEAM=-3:' floors only, "
            "'TEAM=:2' caps only); TEAM resolves by unique substring",
        )
        p.add_argument(
            "--shape", choices=["starter>team", "team>starter"], default=None,
            help="shape constraint: starter>team means dS > dF, team>starter the reverse",
        )
        p.add_argument(
            "--top", type=int, default=5,
            help="hedges SHOWN per team (the search itself stores the top 50)",
        )
        p.add_argument(
            "--out", default="hedge-board.html",
            help="output HTML path — ONE canonical path PER VIEW (board: "
            "hedge-board.html; offer: hedge-offer.html), so each published "
            "artifact URL stays stable",
        )
        p.add_argument("--json", action="store_true",
                       help="print the payload/result as JSON")

    hboard = hsub.add_parser(
        "board",
        help="render the hedge board from the DB — cache hits after the bake "
        "unless the filter state changed",
    )
    add_hd_filters(hboard)
    hboard.add_argument("--focus", default=None, metavar="TEAM",
                        help="that team's card first (unique substring)")
    hoffer = hsub.add_parser(
        "offer",
        help="score a proposal (REAL gate — any assets) and write the "
        "pinned-offer page: the offer atop exact hedges per counterparty "
        "(v8.1) — the board file is never touched",
    )
    hoffer.add_argument("--opponent", required=True)
    hoffer.add_argument("--give", required=True,
                        help="comma-separated asset names you send")
    hoffer.add_argument("--get", required=True,
                        help="comma-separated asset names you receive")
    add_hd_filters(hoffer)
    hoffer.set_defaults(out="hedge-offer.html")
    hsub.add_parser(
        "status",
        help="DB path, size, band, fingerprints, freshness vs live Mongo, "
        "cached-search inventory",
    )

    args = ap.parse_args()

    db = get_db()
    snapshot, fresh = build_snapshot_from_store(db)
    if fresh["last_collect"]:
        age_h = (datetime.now(timezone.utc) - fresh["last_collect"].replace(tzinfo=timezone.utc)).total_seconds() / 3600
        print(f"[data age: {age_h:.1f}h since last successful collect]\n", file=sys.stderr)

    if args.cmd == "hedgedb":
        # the hedgedb paths never build the LIVE league: boards and offers
        # price everything from the DB's STORED snapshot (§12 "the page cannot
        # disagree"), and `build` constructs its own league from what it stores
        run_hedgedb(args, db, snapshot, fresh)
        return

    league = md.build_league(snapshot, Params())

    if args.cmd == "dashboard":
        run_dashboard(args, db, league, fresh)
        return

    if args.cmd == "pairs":
        board = tr.trade_board(league)
        if board.get("disabled"):
            sys.exit("trade deadline has passed — the pair board is disabled")
        lo, fmin = args.min_ret, args.favor_min
        filter_label = f"total >= {lo:g}%" + (
            f", favor min >= {fmin:+g}" if fmin is not None else ", no favor floor"
        )
        # v5: --min floors the TOTAL return; --favor-min floors the pair's
        # min(f_buy, f_sell); the list always sorts by total return desc
        hits = [
            p for p in board["pairs"]
            if p["return_pct"] >= lo
            and (fmin is None or p["favor"]["min"] >= fmin)
        ]
        # maximin (§2 v4): floor-based return desc, ceiling desc as tie-break
        hits.sort(key=lambda p: (-p["return_pct"], -p.get("ceiling", 0.0)))
        buckets = board.get("bands", [])
        if args.json:
            print(json.dumps(
                {
                    "min": lo,
                    "favor_min": fmin,
                    "presets": board["presets"],
                    "favor_presets": board.get("favor_presets"),
                    "delta_presets": board.get("delta_presets"),
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
                return f"favor < {b['hi']:+g}"
            if b["hi"] is None:
                return f"favor >= {b['lo']:+g}"
            return f"favor [{b['lo']:+g}, {b['hi']:+g})"

        tband_names = [
            f"[{p:g},{board['presets'][i + 1]:g})" if i + 1 < len(board["presets"])
            else f"[{p:g},inf)"
            for i, p in enumerate(board["presets"])
        ]
        sat_any = any(b["saturated"] for b in buckets)
        print(
            "Favor bucket inventory (v5: bucket = pair favor min(f_buy, f_sell), "
            "the least-happy counterparty's signed KTC-calculator skew; stored = "
            "the bucket's union of tops by robust return / dS / dF). v5.1 count "
            "honesty: a count printed bare is an EXACT tally — the collection walk "
            "ran to completion under the sound crossing bound dF - r*(v you send), "
            "which is exactly additive across legs and bounds every pair's "
            "guaranteed floor, so it provably enumerated every qualifying pair the "
            "POOLED legs can form (the pool's per-signature variant cap stays a "
            "disclosed heuristic, §5); "
            + ("a count printed '>= N' is a verified floor (the walk saturated "
               "there):" if sat_any else "no bucket saturated in this run, so every "
               "count below is exact:")
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
                f"\nNo stored pairs with {filter_label} today. Loosen the favor "
                "floor or drop the total floor — the inventory above shows where "
                "the stored pairs sit"
                + (
                    " (and it is a set of exact counts, so a bucket reading 0 "
                    "means no such pair EXISTS among the pooled legs, not merely "
                    "none stored)"
                    if not sat_any
                    else " (saturated buckets read '>= N' — a 0 there is only "
                    "'none found within the walk')"
                )
                + ". The board recomputes nightly."
            )
            return
        deeper = any(b["saturated"] or b["count"] > b["stored"] for b in buckets)
        print(
            f"\nTop {min(15, len(hits))} of {len(hits)} stored pairs with {filter_label}, "
            "floor-based total return desc (ceiling tie-break — every stored "
            "pair is objectively good, §2 v4)"
            + (
                " (the legal space runs deeper than storage — the "
                + ("exact " if not sat_any else "")
                + "counts in the inventory above say by how much)"
                if deeper
                else ""
            )
            + ":"
        )
        for p in hits[:15]:
            b, s = p["buy"], p["sell"]
            coords = p.get("coords")
            tail = f" ({fmt_coords(coords)})" if coords else ""
            fav = p.get("favor")
            legs_str = (
                f"  favor buy {fav['buy']:+g} / sell {fav['sell']:+g} · "
                f"min {fav['min']:+g} ({favor_tag(fav['min'])})"
                if fav
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

    if args.cmd == "find":
        run_find(args, db, league)
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
            extra = f"  (yours {a.v_me:.0f})" if a.v_me != a.v else ""
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
