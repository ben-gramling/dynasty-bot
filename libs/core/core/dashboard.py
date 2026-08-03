"""The per-counterparty hedge dashboard: search, payload, and a self-contained
HTML page (v7.1).

The trade-negotiator skill opens a negotiating session by asking one question —
*for each counterparty, what are my best hedges right now?* — and this module
answers it. A hedge is the §5 unit: a count-neutral buy leg + sell leg that
nets exactly 0 players / 0 picks for my side. It therefore has TWO
counterparties, and a team is "in" a hedge when it sits on either leg.

Two pure functions, no I/O of its own:

    hedge_payload(league, ...) -> dict   # one finder run per counterparty
    render_html(payload)      -> str     # a standalone page, no external refs

`scripts/score_trade.py dashboard` is the thin wrapper that reads Mongo, calls
both, and writes the file.

**Why one search per counterparty.** A single global top-N is dominated by
whichever two teams happen to match up best, and the desk needs a read on
EVERY team — including the ones with nothing, which is itself information.
`find_spreads(with_team=X)` pushes the scope down into the crossing (§4a v6),
so each run is exhaustive rather than budget-truncated: on the committed
fixtures all eleven report `exact: True` at ~26 s each. The pool build (~15 s
of that) is identical across the eleven — same constraints, same opponent
slate, since `with_team` constrains the PAIR and not the enumeration — so the
runs are farmed to a process pool instead, which recovers the duplication in
wall clock without touching the heavily-pinned `find_spreads` itself.
"""

from __future__ import annotations

import html
import json
import os
from typing import Any, Mapping, Sequence

from core.scoring import finder as fd
from core.scoring import ktc_link as kl
from core.scoring import league as lg
from core.scoring import model as md
from core.scoring import trades as tr

# ------------------------------------------------------------------- payload

# KTC moves through the day; past this the board is quoting numbers the
# counterparty's screen no longer shows, so the page says so in red.
_STALE_HOURS = 6.0

_SLIDER_DEFAULTS: dict[str, Any] = {
    "delta": "robust",
    "min_return": 1.0,
    # the §4a v5 fair window: |favor| ≤ 5 is literally what the counterparty's
    # own KTC calculator calls FAIR, so this is the band the user negotiates in
    "favor_min": -5.0,
    "favor_max": 5.0,
    "top": 5,
}

# module-global for the fork-based worker pool: the league is inherited
# copy-on-write rather than pickled (it holds every Package the pool needs)
_WORKER_STATE: dict[str, Any] = {}


def _run_one(opp: str) -> tuple[str, dict]:
    league = _WORKER_STATE["league"]
    query = {**_WORKER_STATE["query"], "with_team": opp}
    res = fd.find_spreads(
        league, query, intel=_WORKER_STATE["intel"], cache_dir=_WORKER_STATE["cache_dir"]
    )
    return opp, res


def _search_all(
    league: md.LeagueState,
    query: Mapping,
    intel: Sequence[Mapping],
    cache_dir,
    workers: int,
) -> dict[str, dict]:
    """One `find_spreads` per opponent, in opponent order. `workers <= 1` runs
    them in-process — the path tests take, and the only path with no fork."""
    opponents = list(league.opponents)
    _WORKER_STATE.update(
        league=league, query=dict(query), intel=list(intel), cache_dir=cache_dir
    )
    if workers <= 1:
        return dict(_run_one(o) for o in opponents)
    import multiprocessing as mp

    # fork so the workers inherit `_WORKER_STATE` (and the league inside it)
    # without pickling; spawn would rebuild the world per worker
    ctx = mp.get_context("fork")
    with ctx.Pool(processes=min(workers, len(opponents))) as pool:
        return dict(pool.map(_run_one, opponents))


def default_workers() -> int:
    """Leave a core for the shell; the searches are pure-Python CPU work."""
    return max(1, (os.cpu_count() or 2) - 1)


def _link_dict(link: kl.Link) -> dict:
    return {
        "url": link.url,
        "numbered_url": link.numbered_url,
        "dropped": list(link.dropped),
        "numbered": [
            {"name": n.name, "tranche_v": n.tranche_v} for n in link.numbered
        ],
    }


def _spread_links(league: md.LeagueState, sp: Mapping, ids: Mapping) -> dict:
    """Calculator links for a hedge: one per leg, plus the whole spread rolled
    into a single hypothetical trade.

    The per-leg links are the real ones — each leg IS a trade with one
    counterparty, and its `teamOne` total is exactly `gate.adj_give` because
    the link opens the calculator at the settings our gate ports (var 5,
    format 1, no pick scaling).

    The combined link is a DIFFERENT question: "what would this whole spread
    look like as one trade against one manager?" Nobody executes it that way —
    the legs go to two different teams — and KTC's value adjustment does not
    cancel across the pair (§3.1 v3.4), so its fairness reading is genuinely
    its own, not the sum of the two legs'. It is here because it is the
    quickest way to see the shape of what you are actually doing; the page
    says both of those things next to it.

    Links are best-effort: an asset with no KTC identity is dropped and
    disclosed, and the 12-asset calculator cap can make the combined link
    impossible even when both legs are fine."""
    buy_give, buy_get = tr.card_packages(league, sp["buy"])
    sell_give, sell_get = tr.card_packages(league, sp["sell"])
    cy = league.current_year
    out = {
        "buy": _link_dict(kl.tc_link(buy_give.assets, buy_get.assets, ids, current_year=cy)),
        "sell": _link_dict(kl.tc_link(sell_give.assets, sell_get.assets, ids, current_year=cy)),
    }
    try:
        combined = kl.tc_link(
            list(buy_give.assets) + list(sell_give.assets),
            list(buy_get.assets) + list(sell_get.assets),
            ids,
            current_year=cy,
        )
    except ValueError as exc:  # KTC holds at most 12 assets across both sides
        out["spread"] = {"url": None, "numbered_url": None, "dropped": [],
                         "numbered": [], "blocked": str(exc)}
    else:
        out["spread"] = _link_dict(combined)
    return out


def hedge_payload(
    league: md.LeagueState,
    *,
    sliders: Mapping | None = None,
    intel: Sequence[Mapping] = (),
    cache_dir=None,
    workers: int = 1,
    generated_at: str | None = None,
    data_age: str | None = None,
    data_age_hours: float | None = None,
) -> dict:
    """The dashboard's data: per counterparty, their market read plus the best
    hedges the finder can reach for them under `sliders`.

    Everything here is exactly what the CLI would print — the same
    `find_spreads` call, the same leg cards, the same honest counts. Nothing is
    re-derived for display, so the page can never disagree with `find`."""
    query = {**_SLIDER_DEFAULTS, **(sliders or {})}
    results = _search_all(league, query, intel, cache_dir, workers)
    # derived from the snapshot every run — the RDP asset list rolls forward
    # during the season and must never be hardcoded (docs/keeptradecut.md)
    ids = kl.rdp_ids(league)

    teams = []
    for name in sorted(league.opponents):
        res = results[name]
        market = lg.market_map(league, league.teams[name])
        spreads = []
        for sp in res["spreads"]:
            # which leg is THIS team's? (the other leg's counterparty is the
            # hedge partner — a hedge always touches two teams)
            side = "buy" if sp["buy"]["counterparty"] == name else "sell"
            other = sp["sell" if side == "buy" else "buy"]["counterparty"]
            spreads.append(
                {
                    **sp,
                    "their_side": side,
                    "partner": other,
                    "links": _spread_links(league, sp, ids),
                }
            )
        teams.append(
            {
                "name": name,
                "market": market,
                "spreads": spreads,
                "counts": res["counts"],
                "exact": res["exact"],
                "constraints": res["applied_constraints"],
            }
        )

    return {
        "me": league.me,
        "generated_at": generated_at,
        "data_age": data_age,
        "data_age_hours": data_age_hours,
        "sliders": query,
        "teams": teams,
        "totals": {
            "teams": len(teams),
            "with_hedges": sum(1 for t in teams if t["spreads"]),
            "matched": sum(t["counts"]["matched"] for t in teams),
            "all_exact": all(t["exact"] for t in teams),
        },
    }


def _leg_link(league: md.LeagueState, card: Mapping, ids: Mapping) -> dict:
    """Calculator link for one arbitrary leg card (v8 offer/hedge pinning).
    Best-effort exactly like `_spread_links`: KTC's 12-asset cap is disclosed
    as `blocked`, never swallowed."""
    give, get = tr.card_packages(league, card)
    try:
        return _link_dict(
            kl.tc_link(give.assets, get.assets, ids, current_year=league.current_year)
        )
    except ValueError as exc:
        return {"url": None, "numbered_url": None, "dropped": [], "numbered": [],
                "blocked": str(exc)}


def db_payload(
    db,
    team_results: Mapping[str, Mapping],
    *,
    sliders: Mapping | None,
    focus: str | None = None,
    generated_at: str | None = None,
    mongo_newer: bool = False,
    data_age: str | None = None,
    data_age_hours: float | None = None,
) -> dict:
    """The v8 hedge-DB board payload: `hedge_payload`'s exact shape, assembled
    from per-counterparty `HedgeDB.search` payloads instead of live finder runs.

    Everything renders against the STORED snapshot's league (`db.league`) —
    the §12 "page cannot disagree" contract: market blocks, KTC links and leg
    cards all come from the world the DB was priced from, never live Mongo.
    `team_results` maps counterparty username -> its search payload; teams
    render in sorted order with the `focus` team first. Spreads are sliced to
    the display `top` in `sliders`; counts stay the search's full tallies.

    Additions over `hedge_payload`, all additive so `render_html` keeps
    working on either payload:

    - per team: `bar_raised` (the §4a v6 warm bar rose above min_return, so
      `matched` is a floor — rendered "≥ N");
    - `db`: provenance {band, legs, content_fingerprint16, cached_counts,
      bar_raised_any};
    - `constraints_in_effect`: applied/shed/ignored with provenance, deduped
      across the team searches (they compile identically per search);
    - `focus`: that team's card first;
    - `mongo_newer`: the live collect moved past the DB — its own red banner,
      distinct from the snapshot-age axis.

    Offers no longer pin onto this board (v8.1): a scored offer gets its OWN
    page — `offer_payload` below — so the board artifact stays offer-free.
    """
    league = db.league
    query = {**_SLIDER_DEFAULTS, **(sliders or {})}
    show = query.get("top")
    ids = kl.rdp_ids(league)

    names = sorted(team_results)
    if focus is not None and focus in names:
        names.remove(focus)
        names.insert(0, focus)

    applied: list[dict] = []
    shed: list[dict] = []
    ignored: list[dict] = []
    seen: dict[str, set] = {"applied": set(), "shed": set(), "ignored": set()}

    def _dedupe(kind: str, into: list, items) -> None:
        for it in items or ():
            key = json.dumps(it, sort_keys=True, default=str)
            if key not in seen[kind]:
                seen[kind].add(key)
                into.append(it)

    teams = []
    cached = 0
    bar_raised_any = False
    for name in names:
        res = team_results[name]
        market = lg.market_map(league, league.teams[name])
        spreads = []
        for sp in res["spreads"][: show or None]:
            side = "buy" if sp["buy"]["counterparty"] == name else "sell"
            other = sp["sell" if side == "buy" else "buy"]["counterparty"]
            spreads.append(
                {
                    **sp,
                    "their_side": side,
                    "partner": other,
                    "links": _spread_links(league, sp, ids),
                }
            )
        bar = bool(res.get("bar_raised"))
        bar_raised_any |= bar
        if (res.get("db") or {}).get("cached"):
            cached += 1
        _dedupe("applied", applied, res.get("applied_constraints"))
        _dedupe("shed", shed, res.get("shed_constraints"))
        _dedupe("ignored", ignored, res.get("ignored_intel"))
        teams.append(
            {
                "name": name,
                "market": market,
                "spreads": spreads,
                "counts": res["counts"],
                "exact": res["exact"],
                "constraints": res["applied_constraints"],
                "bar_raised": bar,
            }
        )

    payload = {
        "me": league.me,
        "generated_at": generated_at,
        "data_age": data_age,
        "data_age_hours": data_age_hours,
        "sliders": query,
        "teams": teams,
        "totals": {
            "teams": len(teams),
            "with_hedges": sum(1 for t in teams if t["spreads"]),
            "matched": sum(t["counts"]["matched"] for t in teams),
            "all_exact": all(t["exact"] for t in teams),
        },
        "focus": focus,
        "mongo_newer": bool(mongo_newer),
        "db": {
            "band": db.meta["band"],
            "legs": db.meta["legs"],
            "content_fingerprint16": db.meta["content_fingerprint"][:16],
            "cached_counts": {"cached": cached, "fresh": len(teams) - cached},
            "bar_raised_any": bar_raised_any,
        },
        "constraints_in_effect": {
            "applied": applied,
            "shed": shed,
            "ignored_intel": ignored,
        },
    }
    return payload


def _offer_links(league, offer_card: Mapping, hedge_card: Mapping, ids: Mapping) -> dict:
    """Calculator links for one pinned-offer hedge: the hedge leg itself, plus
    the offer+hedge PAIR rolled into a single hypothetical trade — the same
    what-if (and the same 12-asset cap) as the board's spread link."""
    out = {"hedge": _leg_link(league, hedge_card, ids)}
    o_give, o_get = tr.card_packages(league, offer_card)
    h_give, h_get = tr.card_packages(league, hedge_card)
    try:
        combined = kl.tc_link(
            list(o_give.assets) + list(h_give.assets),
            list(o_get.assets) + list(h_get.assets),
            ids,
            current_year=league.current_year,
        )
    except ValueError as exc:  # KTC holds at most 12 assets across both sides
        out["pair"] = {"url": None, "numbered_url": None, "dropped": [],
                       "numbered": [], "blocked": str(exc)}
    else:
        out["pair"] = _link_dict(combined)
    return out


def offer_payload(
    db,
    offer_result: Mapping,
    *,
    sliders: Mapping | None,
    generated_at: str | None = None,
    mongo_newer: bool = False,
    data_age: str | None = None,
    data_age_hours: float | None = None,
) -> dict:
    """The v8.1 PINNED-OFFER page: the offer at the top of the PAGE, then one
    card per remaining counterparty with its exact hedge set against that
    offer. Built from the `HedgeDB.offer` result alone — no per-team searches;
    the one crossing already visited every eligible stored leg — under the
    same stored-snapshot contract as `db_payload` (everything renders from
    `db.league`, so the page can never disagree with its coordinates).

    Teams follow `by_team` order: best pair floor return first, hedge-less
    teams last, the offer's counterparty absent (their trade IS the pin).
    Per-team `counts.matched` is the crossing's full tally for that team;
    `hedges` is the display slice, each row carrying a hedge-leg link and a
    whole-pair link. An offer that never crossed (count-neutral, or an empty
    complement bucket) has no team cards — its `note` says why."""
    league = db.league
    query = {**_SLIDER_DEFAULTS, **(sliders or {})}
    show = query.get("top")
    ids = kl.rdp_ids(league)
    card = offer_result["offer"]
    counts = offer_result.get("counts")
    matched_by = (counts or {}).get("matched_by_team") or {}
    exact = bool(offer_result.get("exact", True))

    teams = []
    if counts is not None:  # the crossing ran — count-neutral offers never do
        for name, hs in (offer_result.get("by_team") or {}).items():
            teams.append(
                {
                    "name": name,
                    "market": lg.market_map(league, league.teams[name]),
                    "hedges": [
                        {**h, "links": _offer_links(league, card, h["hedge"], ids)}
                        for h in hs[: show or None]
                    ],
                    "counts": {"matched": matched_by.get(name, 0)},
                    "exact": exact,
                }
            )
    return {
        "mode": "offer",
        "me": league.me,
        "generated_at": generated_at,
        "data_age": data_age,
        "data_age_hours": data_age_hours,
        "sliders": query,
        "offer": {
            "card": card,
            "link": _leg_link(league, card, ids),
            "note": offer_result.get("note"),
            "counts": counts,
            "exact": exact,
        },
        "teams": teams,
        "totals": {
            "teams": len(teams),
            "with_hedges": sum(1 for t in teams if t["hedges"]),
            "matched": (counts or {}).get("matched", 0),
            "all_exact": exact,
        },
        "mongo_newer": bool(mongo_newer),
        "db": {
            "band": db.meta["band"],
            "legs": db.meta["legs"],
            "content_fingerprint16": db.meta["content_fingerprint"][:16],
        },
        "constraints_in_effect": {
            "applied": list(offer_result.get("applied_constraints") or []),
            "shed": list(offer_result.get("shed_constraints") or []),
            "ignored_intel": list(offer_result.get("ignored_intel") or []),
        },
    }


# ---------------------------------------------------------------------- HTML

# The `apps/web` design contract (docs/web-design.md) verbatim: Chicago-flag
# palette, one accent system, and the ledger discipline that RED IS ONLY EVER A
# NEGATIVE NUMBER (or the six-pointed star) — positives are ink, never green,
# because the page reads as a ledger and not a traffic light. Dark steps are
# added here and only here: an artifact renders in the viewer's theme, and a
# desk tool read at midnight should not flashbang. They are re-steps of the
# same hues onto a lake-navy ground, not an inversion — the sky band and the
# stars stay exactly the flag's.
_CSS = """
:root{
  --field:#F2F7FA; --surface:#FFFFFF; --ink:#14212E; --ink-muted:#5B6E7E;
  --line:#D8E4EC; --sky:#A8D8F0; --sky-deep:#1877B8; --star:#C8102E;
  --chip:#E5F1F8; --shadow:0 1px 2px rgba(20,33,46,.06);
}
@media (prefers-color-scheme:dark){
  :root{
    --field:#0C1620; --surface:#14212E; --ink:#E4EDF3; --ink-muted:#8CA3B4;
    --line:#24384A; --sky:#A8D8F0; --sky-deep:#4FA9E4; --star:#FF5C72;
    --chip:#1B2E3E; --shadow:0 1px 2px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"]{
  --field:#0C1620; --surface:#14212E; --ink:#E4EDF3; --ink-muted:#8CA3B4;
  --line:#24384A; --sky:#A8D8F0; --sky-deep:#4FA9E4; --star:#FF5C72;
  --chip:#1B2E3E; --shadow:0 1px 2px rgba(0,0,0,.35);
}
:root[data-theme="light"]{
  --field:#F2F7FA; --surface:#FFFFFF; --ink:#14212E; --ink-muted:#5B6E7E;
  --line:#D8E4EC; --sky:#A8D8F0; --sky-deep:#1877B8; --star:#C8102E;
  --chip:#E5F1F8; --shadow:0 1px 2px rgba(20,33,46,.06);
}
/* Faces: the web app self-hosts Big Shoulders / Public Sans / IBM Plex Mono
   via next/font. A standalone artifact cannot link a CDN (CSP) and embedding
   three faces would add ~300KB to every generation, so these are the project's
   own sanctioned fallbacks — Arial Narrow for the condensed display face (the
   one CLAUDE.md already names), system UI for body, and the platform mono for
   every numeral, which is the signature that actually has to survive. */
*{box-sizing:border-box}
body{
  margin:0; background:var(--field); color:var(--ink);
  font:14px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-text-size-adjust:100%;
}
.mono{font-family:ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
  font-variant-numeric:tabular-nums}
h1,h2,h3,.display{
  font-family:"Big Shoulders Display","Arial Narrow",Arial,sans-serif-condensed,sans-serif;
  font-weight:700; letter-spacing:.01em; margin:0;
}
a{color:var(--sky-deep)}
:focus-visible{outline:2px solid var(--sky-deep); outline-offset:2px; border-radius:3px}

/* masthead: the flag-band construction */
.band{height:6px;background:var(--sky)}
header.mast{background:var(--surface);border-bottom:1px solid var(--line);padding:14px 20px}
.mast-in{max-width:1200px;margin:0 auto;display:flex;flex-wrap:wrap;gap:14px 22px;align-items:baseline}
.wordmark{display:flex;flex-direction:column;gap:1px}
.stars{color:var(--star);letter-spacing:.22em;font-size:11px;line-height:1}
h1{font-size:28px;line-height:1}
.sub{font-size:11px;color:var(--ink-muted);letter-spacing:.09em;text-transform:uppercase}
.mast-meta{margin-left:auto;display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:flex-end}

main{max-width:1200px;margin:0 auto;padding:20px 20px 64px}

/* chips — docs/web-design.md §4 anatomy */
.chip{display:inline-flex;align-items:baseline;gap:5px;background:var(--chip);
  border-radius:4px;padding:2px 7px;white-space:nowrap}
.chip-k{font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-muted)}
.chip-v{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-variant-numeric:tabular-nums;
  font-size:12.5px;color:var(--ink)}
.chip-v.neg{color:var(--star)}
.chip-lead{border:1px solid var(--sky-deep)}
.chip-flat{background:transparent;border:1px solid var(--line)}

.card{background:var(--surface);border:1px solid var(--line);border-radius:8px;
  box-shadow:var(--shadow);margin-bottom:14px;overflow:hidden}
.card-head{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:baseline;
  padding:13px 16px;border-bottom:1px solid var(--line)}
.card-head h2{font-size:22px;line-height:1}
.card-head .right{margin-left:auto;display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end}
.posture{font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-muted);
  border:1px solid var(--line);border-radius:4px;padding:2px 7px}
.holes{font-size:12.5px;color:var(--ink-muted)}
.empty{padding:16px;color:var(--ink-muted);font-size:13px}

/* the decomposition sentence, reused as the hedge atom */
details.hedge{border-top:1px solid var(--line)}
details.hedge:first-of-type{border-top:none}
details.hedge>summary{list-style:none;cursor:pointer;padding:11px 16px;
  display:flex;flex-wrap:wrap;gap:7px 9px;align-items:center}
details.hedge>summary::-webkit-details-marker{display:none}
details.hedge>summary:hover{background:var(--chip)}
details.hedge[open]>summary{background:var(--chip)}
.rank{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--ink-muted);
  min-width:2.1em}
.sent{font-size:12.5px;color:var(--ink-muted)}
.caret{margin-left:auto;display:block;flex:none;color:var(--ink-muted);
  transition:transform .12s ease}
.caret svg{display:block}
details.hedge[open] .caret{transform:rotate(90deg)}
@media (prefers-reduced-motion:reduce){.caret{transition:none}}

.audit{padding:4px 16px 16px;display:grid;gap:12px;grid-template-columns:1fr 1fr}
@media (max-width:760px){.audit{grid-template-columns:1fr}}
.leg{border:1px solid var(--line);border-radius:6px;padding:10px 12px}
.leg h3{font-size:17px;line-height:1.1;margin-bottom:2px}
.leg .who{font-size:11.5px;color:var(--ink-muted);margin-bottom:8px}
.leg.theirs{border-color:var(--sky-deep)}
table.assets{width:100%;border-collapse:collapse;font-size:13px}
table.assets th{text-align:left;font-weight:400;font-size:10.5px;text-transform:uppercase;
  letter-spacing:.06em;color:var(--ink-muted);padding:3px 0}
table.assets td{padding:2px 0;vertical-align:baseline}
table.assets td.num{text-align:right;font-family:ui-monospace,Menlo,monospace;
  font-variant-numeric:tabular-nums;white-space:nowrap}
.lens{font-size:11px;color:var(--ink-muted)}
.note{font-size:12px;color:var(--ink-muted);padding:0 16px 14px}
/* staleness: the one thing on this page that is allowed to shout. KTC's board
   moves continuously (a mid-tier WR drifted 2,595 -> 2,574 in six hours), so a
   stale board disagrees with the counterparty's screen asset by asset — the
   exact failure this dashboard exists to avoid. */
.stale{border:1px solid var(--star);border-radius:8px;padding:11px 14px;margin-bottom:14px;
  background:var(--surface);font-size:13px}
.stale b{color:var(--star)}
.gate{font-size:12px;color:var(--ink-muted);display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:8px}
.scroll{overflow-x:auto}
/* calculator links: the only outbound thing on the page, so they get the one
   interactive hue and never compete with a numeral */
.ktc{margin-top:8px;display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;align-items:baseline}
.ktc a{color:var(--sky-deep);text-decoration:none;border-bottom:1px solid var(--line);
  padding-bottom:1px}
.ktc a:hover{border-bottom-color:var(--sky-deep)}
.ktc .warn{color:var(--ink-muted)}
.spread-link{padding:0 16px 14px;font-size:12.5px;display:flex;flex-wrap:wrap;
  gap:4px 12px;align-items:baseline}
.spread-link a{color:var(--sky-deep)}
footer{max-width:1200px;margin:0 auto;padding:0 20px 40px;font-size:12px;color:var(--ink-muted)}
footer p{margin:.5em 0}
/* v8 hedge-DB board additions: constraints disclosure, offer pin. The pass
   hue is the ONE sanctioned exception to "positives are ink": a pinned offer's
   gate verdict is the page's single loudest fact (spec §5), so PASS/FAIL get
   verdict colors — on the verdict word only, never on a numeral. */
:root{--pass:#1E7F45}
@media (prefers-color-scheme:dark){:root{--pass:#43B97F}}
:root[data-theme="dark"]{--pass:#43B97F}
:root[data-theme="light"]{--pass:#1E7F45}
details.constraints{background:var(--surface);border:1px solid var(--line);border-radius:8px;
  box-shadow:var(--shadow);margin-bottom:14px;font-size:13px}
details.constraints>summary{list-style:none;cursor:pointer;padding:11px 16px;font-weight:600}
details.constraints>summary::-webkit-details-marker{display:none}
details.constraints>summary:hover{background:var(--chip)}
.constraints-body{padding:0 16px 12px}
.constraints-body h3{font-size:14px;margin:10px 0 4px}
.constraints-body ul{margin:4px 0;padding-left:18px}
.constraints-body li{margin:2px 0}
.offer{border-bottom:1px solid var(--line);padding:13px 16px;background:var(--chip)}
/* v8.1: the pin is its own top-of-page card, not a section inside a team card */
.offer-pin .offer{border-bottom:none}
.offer-head{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:baseline;margin-bottom:8px}
.offer-head h3{font-size:18px}
.verdict{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:13px;
  font-weight:700;border:1px solid currentColor;border-radius:4px;padding:2px 8px}
.verdict-pass{color:var(--pass)}
.verdict-fail{color:var(--star)}
.offer .leg{background:var(--surface)}
.offer details.hedge{background:var(--surface);border:1px solid var(--line);
  border-radius:6px;margin-top:8px}
.offer-hedges-label{font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;
  color:var(--ink-muted);margin-top:12px}
"""

_STAR = "✶"  # six-pointed star (U+2736) — the identity marker, never a bullet
_MINUS = "−"  # true minus, per the ledger convention


def _esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _num(v: float | None, *, signed: bool = False, dp: int = 0, pct: bool = False) -> str:
    """A ledger numeral: true minus, thousands separators, explicit + when the
    sign carries meaning. Negative styling is the caller's (`.neg`)."""
    if v is None:
        return "—"
    body = f"{abs(v):,.{dp}f}" + ("%" if pct else "")
    if v < 0:
        return _MINUS + body
    return ("+" + body) if signed else body


def _chip(key: str, v: float | None, *, signed: bool = True, dp: int = 0,
          pct: bool = False, lead: bool = False) -> str:
    neg = " neg" if (v is not None and v < 0) else ""
    cls = "chip chip-lead" if lead else "chip"
    return (
        f'<span class="{cls}"><span class="chip-k">{_esc(key)}</span>'
        f'<span class="chip-v{neg}">{_esc(_num(v, signed=signed, dp=dp, pct=pct))}</span></span>'
    )


def _favor_chip(f: float | None, label: str = "favor") -> str:
    """Favor is a signed SKEW toward the counterparty, not a ledger entry — a
    NEGATIVE favor is good for me. Rendering it in the ledger's negative-red
    would say the opposite, so it gets a flat chip and the direction in words.
    (docs/web-design.md: red is only ever a negative NUMBER or the star.)"""
    if f is None:
        return ""
    if not f:
        val = "even"
    else:
        val = f"{abs(f):.1f} " + ("to them" if f > 0 else "to you")
    return (
        f'<span class="chip chip-flat"><span class="chip-k">{_esc(label)}</span>'
        f'<span class="chip-v">{_esc(val)}</span></span>'
    )


def _assets_table(title: str, assets: Sequence[Mapping]) -> str:
    rows = []
    for a in assets:
        lens = ""
        if a.get("v_me") is not None:
            # §1 v7.5: unreachable — one price per pick now (flat Mid beyond
            # this year, v7.6). Tripwire: a re-diverged lens shows both.
            lens = f'<div class="lens">yours {_num(a["v_me"])}</div>'
        flag = ' <span class="lens">unvalued</span>' if a.get("unvalued") else ""
        rows.append(
            f'<tr><td>{_esc(a["name"])}{flag}{lens}</td>'
            f'<td class="num">{_esc(_num(a.get("v")))}</td></tr>'
        )
    return (
        f'<table class="assets"><thead><tr><th>{_esc(title)}</th>'
        f'<th class="num">KTC</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )


def _ktc_links(link: Mapping, *, label: str, aside: str = "") -> str:
    """The calculator link plus every disclosure it carries. A dropped asset or
    a numbered-pick gap changes what the counterparty's screen totals, so it is
    stated next to the link rather than swallowed by it."""
    if link.get("blocked"):
        return f'<div class="ktc"><span class="warn">{_esc(label)}: {_esc(link["blocked"])}</span></div>'
    if not link.get("url"):
        return (
            '<div class="ktc"><span class="warn">'
            f"{_esc(label)}: not linkable — every asset on one side is missing a "
            "KTC id, and a one-sided link would read as a giveaway</span></div>"
        )
    bits = [f'<a href="{_esc(link["url"])}">{_esc(label)}</a>']
    if aside:
        bits.append(f'<span class="warn">{_esc(aside)}</span>')
    if link.get("dropped"):
        bits.append(
            '<span class="warn">not on the calculator: '
            f'{_esc(", ".join(link["dropped"]))}</span>'
        )
    if link.get("numbered_url"):
        names = ", ".join(n["name"] for n in link["numbered"])
        bits.append(
            f'<a href="{_esc(link["numbered_url"])}">numbered picks</a>'
            f'<span class="warn">— {_esc(names)} also exist on KTC as numbered '
            "entries priced above the tranche this link uses; that version totals "
            "differently from the gate</span>"
        )
    return '<div class="ktc">' + "".join(bits) + "</div>"


def _leg_block(leg: Mapping, *, role: str, is_theirs: bool, link: Mapping | None) -> str:
    g = leg["gate"]
    cls = "leg theirs" if is_theirs else "leg"
    who = f'with {_esc(leg["counterparty"])}' + (" — this team" if is_theirs else "")
    gate = (
        f'<div class="gate"><span>KTC calculator '
        f'<span class="mono">{_num(g["adj_give"])}</span> you / '
        f'<span class="mono">{_num(g["adj_get"])}</span> them</span>'
        f'<span>gap <span class="mono">{_num(g["gap_pct"], dp=1, pct=True)}</span> '
        f'of a <span class="mono">{_num(g["band_pct"], dp=0, pct=True)}</span> band</span>'
        f'<span>ratio <span class="mono">{_esc(g["raw_ratio"])}</span></span>'
        f'<span>{_esc(g["verdict"])}</span></div>'
    )
    link_html = (
        _ktc_links(link, label="Open this leg in KTC",
                   aside="totals exactly what the gate above shows")
        if link is not None
        else ""
    )
    return (
        f'<div class="{cls}"><h3>{_esc(role)}</h3><div class="who">{who}</div>'
        f'{_assets_table("You send", leg["give"])}'
        f'{_assets_table("You get", leg["get"])}'
        f"{gate}{link_html}</div>"
    )


def _swing_note(sw: Mapping | None, coords: Mapping) -> str:
    """§2 v8.2 the band-swing audit line: which origins drive the widened
    floor/ceiling, in words ('if they finish strong / crater'), plus whether
    the §2 verdict survives the band's worst edge. Silent when no future pick
    is at stake — the interval then IS the plain maximin one."""
    if not sw or (not sw["down"] and not sw["up"]):
        return ""
    origins = "; ".join(
        f'{o["year"]} picks from {o["origin"]}: '
        f'{_num(o["if_strong"], signed=True)} if they finish strong, '
        f'{_num(o["if_weak"], signed=True)} if they crater'
        for o in sw.get("by_origin") or ()
    )
    survives = (
        "the verdict survives the whole band"
        if sw.get("verdict_worst")
        else "at the band's worst edge this is no longer objectively good"
    )
    return (
        f'<p class="note">Future picks priced at Mid could really land anywhere in '
        f'KTC’s published Early/Late band: face {_num(coords["dF"], signed=True)} '
        f'could resolve between {_num(sw["down"], signed=True)} and '
        f'{_num(sw["up"], signed=True)} of that — the floor and ceiling chips fold '
        f"this in ({survives}). One finish per origin team per year: {origins}.</p>"
    )


def _hedge(sp: Mapping, rank: int) -> str:
    c = sp["coords"]
    fav = sp["favor"]
    summary = (
        f'<summary><span class="rank mono">{rank:02d}</span>'
        + _chip("floor", sp["floor"], lead=True)
        + _chip("ceiling", sp["ceiling"])
        + _chip("return", sp["return_robust"], dp=2, pct=True)
        + _chip("starters", c["dS"])
        + _chip("face", c["dF"])
        + _favor_chip(fav["min"])
        + f'<span class="sent">on <span class="mono">{_num(sp["sent"])}</span> sent</span>'
        + '<span class="caret" aria-hidden="true">'
        '<svg width="10" height="10" viewBox="0 0 10 10">'
        '<path d="M3 1l4 4-4 4" fill="none" stroke="currentColor" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg></span></summary>'
    )
    their_side = sp["their_side"]
    links = sp.get("links") or {}
    audit = (
        '<div class="audit">'
        + _leg_block(sp["buy"], role="Buy leg", is_theirs=their_side == "buy",
                     link=links.get("buy"))
        + _leg_block(sp["sell"], role="Sell leg", is_theirs=their_side == "sell",
                     link=links.get("sell"))
        + "</div>"
        + (
            '<div class="spread-link">'
            + _ktc_links(
                links["spread"],
                label="Open the WHOLE spread in KTC as one trade",
                aside="a what-if, not the trade: the two legs go to different "
                "managers, and KTC's adjustment does not cancel across a pair, "
                "so this reads differently from either leg above",
            )
            + "</div>"
            if links.get("spread")
            else ""
        )
        + _swing_note(sp.get("swing"), c)
        + f'<p class="note">{_esc(sp["sequencing"])}. '
        f'Partner on the other leg: {_esc(sp["partner"])}. '
        f'Nets 0 players / 0 picks; active roster {_num(sp["net_roster"], signed=True)}.</p>'
    )
    return f'<details class="hedge">{summary}{audit}</details>'


def _what_text(w: Mapping) -> str:
    """Tolerant OBJECT text for a serialized constraint `what` dict — covers
    the §4 vocabulary including v8 any-of and scoped pick classes, and falls
    back to the raw dict rather than ever raising over display."""
    if not isinstance(w, Mapping):
        return str(w)
    if "any" in w:
        return " | ".join(_what_text(a) for a in w["any"])
    if w.get("class") == "pick" and ("year" in w or "round" in w):
        bits = [str(w["year"]) if w.get("year") else "",
                f"R{w['round']}" if w.get("round") else ""]
        return (" ".join(b for b in bits if b) + " picks").strip()
    if "class" in w:
        return {"pick": "picks", "player": "players"}.get(w["class"], str(w["class"]))
    if "pos" in w:
        return f"pos:{w['pos']}"
    if "asset" in w:
        return f'"{w["asset"]}"'
    return str(dict(w))


def _constraint_line(c: Mapping) -> str:
    tail = f' with {c["with"]}' if c.get("with") else ""
    return (
        f'{c.get("mode", "?")} {c.get("who", "?")} {c.get("side", "?")} '
        f'{_what_text(c.get("what") or {})}{tail}'
    )


def _constraints_block(ce: Mapping) -> str:
    """The v8 "constraints in effect" disclosure: every applied constraint with
    its provenance, everything shed by precedence (silent replacement made
    visible), and intel that could not be parsed — reported, never guessed."""
    applied = ce.get("applied") or []
    shed = ce.get("shed") or []
    ignored = ce.get("ignored_intel") or []
    summary = (
        f"Constraints in effect — {len(applied)} applied · {len(shed)} shed · "
        f"{len(ignored)} intel ignored"
    )
    parts: list[str] = []
    if applied:
        parts.append(
            "<h3>Applied (§4 precedence query &gt; intel &gt; posture, per team &amp; side)</h3><ul>"
            + "".join(
                f'<li><span class="mono">{_esc(_constraint_line(c))}</span>'
                f' — {_esc(c.get("origin") or c.get("source") or "")}</li>'
                for c in applied
            )
            + "</ul>"
        )
    else:
        parts.append("<p>No constraints applied — an unconstrained search.</p>")
    if shed:
        parts.append(
            "<h3>Shed — overridden by your query (or by later intel; §4 precedence)</h3><ul>"
            + "".join(
                f'<li><span class="mono">{_esc(_constraint_line(s.get("constraint") or {}))}</span>'
                f' — {_esc(s.get("why") or "")}</li>'
                for s in shed
            )
            + "</ul>"
        )
    if ignored:
        parts.append(
            "<h3>Intel ignored (unparseable/NOTE — reported, never guessed)</h3><ul>"
            + "".join(
                f'<li><span class="mono">{_esc(d.get("kind"))} [{_esc(d.get("team"))}] '
                f'{_esc(repr(d.get("subject")))}</span>: {_esc(item.get("reason") or "")}</li>'
                for item in ignored
                for d in (item.get("doc") or {},)
            )
            + "</ul>"
        )
    return (
        f'<details class="constraints"><summary>{_esc(summary)}</summary>'
        f'<div class="constraints-body">{"".join(parts)}</div></details>'
    )


def _offer_hedge(h: Mapping, rank: int) -> str:
    """One offer-mode hedge as the familiar disclosure row: pair chips in the
    summary (coords/favor are the offer and this hedge applied TOGETHER), the
    hedge leg's full card in the audit."""
    c = h["coords"]
    fav = h.get("favor") or {}
    summary = (
        f'<summary><span class="rank mono">{rank:02d}</span>'
        + _chip("floor", h["floor"], lead=True)
        + _chip("ceiling", h["ceiling"])
        + _chip("return", h["return_robust"], dp=2, pct=True)
        + _chip("starters", c["dS"])
        + _chip("face", c["dF"])
        + _favor_chip(fav.get("offer"), label="offer favor")
        + _favor_chip(fav.get("hedge"), label="hedge favor")
        + f'<span class="sent">on <span class="mono">{_num(h["sent"])}</span> sent</span>'
        + '<span class="caret" aria-hidden="true">'
        '<svg width="10" height="10" viewBox="0 0 10 10">'
        '<path d="M3 1l4 4-4 4" fill="none" stroke="currentColor" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg></span></summary>'
    )
    hc = h["hedge"]
    links = h.get("links") or {}
    hedge_side = "sell" if h.get("offer_side") == "buy" else "buy"
    audit = (
        '<div class="audit">'
        + _leg_block(hc, role=f"Hedge leg ({hedge_side} side)", is_theirs=False,
                     link=links.get("hedge"))
        + "</div>"
        + (
            '<div class="spread-link">'
            + _ktc_links(
                links["pair"],
                label="Open the WHOLE pair in KTC as one trade",
                aside="a what-if, not the trade: the offer and this hedge go "
                "to different managers, and KTC's adjustment does not cancel "
                "across a pair, so this reads differently from either leg",
            )
            + "</div>"
            if links.get("pair")
            else ""
        )
        + _swing_note(h.get("swing"), c)
        + f'<p class="note">Pair figures are the offer and this hedge applied '
        f'together — your offer is the {_esc(h.get("offer_side"))} side. '
        f'{_esc(hc["sequencing"])}.</p>'
    )
    return f'<details class="hedge offer-hedge">{summary}{audit}</details>'


def _offer_pin(offer: Mapping) -> str:
    """The v8.1 pinned offer as its own top-of-page card: the REAL gate
    verdict loud — PASS in the pass hue, FAIL in red with its reasons — the
    offer's leg card, and the crossing's honesty line. The hedges themselves
    live in the per-counterparty cards below, never in the pin."""
    card = offer["card"]
    verdict = str(card["gate"].get("verdict") or "")
    ok = verdict.startswith("PASS")
    vcls = "verdict-pass" if ok else "verdict-fail"
    head = (
        '<div class="offer-head"><h3>Pinned offer — with '
        f'{_esc(card["counterparty"])}</h3>'
        f'<span class="verdict {vcls}">GATE {_esc(verdict)}</span></div>'
    )
    body = (
        '<div class="audit">'
        + _leg_block(card, role="The offer", is_theirs=True, link=offer.get("link"))
        + "</div>"
    )
    note = (
        f'<p class="note">{_esc(offer["note"])}</p>' if offer.get("note") else ""
    )
    fail_note = (
        '<p class="note">Every hedge on this page assumes you executed the '
        "offer regardless — as scored, it FAILS the gate.</p>"
        if not ok
        else ""
    )
    # §2 v8.2: the band check on the ACCEPT decision — the one surface where
    # "is their future 1st secretly a 1.01?" is a live question
    sw = card.get("swing")
    swing_line = ""
    if sw and (sw["down"] or sw["up"]):
        cme = card["coords"]["me"]
        survives = (
            "your accept verdict survives the whole band"
            if sw.get("verdict_worst")
            else "at the band's worst edge the accept is no longer objectively good"
        )
        swing_line = (
            '<p class="note">Future-pick band check: if every unknown slot '
            "breaks against you (your sends land Early, your gets Late), face "
            f'{_num(cme["dF"], signed=True)} becomes '
            f'{_num(cme["dF"] + sw["down"], signed=True)} and the guaranteed '
            f'floor is {_num(card["floor"]["me"], signed=True)} — {survives}. '
            "That is the worst within KTC's published band, not a hard bound.</p>"
        )
    counts = offer.get("counts")
    tally = ""
    if counts:
        honesty = (
            "the crossing completed over every eligible stored leg, so the "
            "per-team tallies below are exact — a team at zero has NO "
            "qualifying hedge among its stored legs"
            if offer.get("exact", True)
            else "the crossing hit its search budget, so the per-team tallies "
            "below are verified floors, never proof of absence"
        )
        tally = (
            f'<p class="note">Hedge crossing: {counts["candidates"]:,} stored '
            f'complement legs · {counts["matched"]:,} matched — {honesty}.</p>'
        )
    return (
        f'<section class="card offer-pin"><div class="offer">'
        f"{head}{body}{note}{fail_note}{swing_line}{tally}</div></section>"
    )


def _card_head(name: str, m: Mapping, tally: str) -> str:
    """The team-card head both boards share: identity, posture, holes, and the
    market chips, with the hedge tally already formatted by the caller."""
    holes = ", ".join(f'{h["pos"]} (their rank {h["rank"]})' for h in m["holes"])
    return (
        f'<div class="card-head"><h2>{_esc(name)}</h2>'
        f'<span class="posture">{_esc(m["posture"])}</span>'
        + (f'<span class="holes">holes: {_esc(holes)}</span>' if holes else "")
        + '<span class="right">'
        + f'<span class="chip chip-flat"><span class="chip-k">picks</span>'
        f'<span class="chip-v">{_num(m["pick_inventory"]["count"])}</span></span>'
        + f'<span class="chip chip-flat"><span class="chip-k">pick KTC</span>'
        f'<span class="chip-v">{_num(m["pick_inventory"]["value"])}</span></span>'
        + f'<span class="chip chip-flat"><span class="chip-k">faab</span>'
        f'<span class="chip-v">{_num(m["faab"])}</span></span>'
        + f'<span class="chip chip-flat"><span class="chip-k">hedges</span>'
        f'<span class="chip-v">{_esc(tally)}</span></span>'
        + "</span></div>"
    )


def _team_card(team: Mapping) -> str:
    counts = team["counts"]
    # v8 count honesty: a raised warm bar makes `matched` a verified floor even
    # when the walk completed, so it reads "≥ N"; a budget-truncated walk keeps
    # the v5.1 trailing "+"
    if team.get("bar_raised"):
        tally = "≥ " + _num(counts["matched"])
    else:
        tally = _num(counts["matched"]) + ("" if team["exact"] else "+")
    head = _card_head(team["name"], team["market"], tally)
    if not team["spreads"]:
        body = (
            '<p class="empty">No hedge clears the sliders with this team. '
            + (
                "The search was exhaustive, so that is a real answer about the "
                "pooled legs — not a budget artefact."
                if team["exact"]
                else "The crossing hit its budget, so read this as “none found”, not “none exists”."
            )
            + "</p>"
        )
    else:
        body = "".join(_hedge(sp, i) for i, sp in enumerate(team["spreads"], 1))
    return f'<section class="card">{head}{body}</section>'


def _offer_team_card(team: Mapping) -> str:
    """One counterparty's exact hedge set against the pinned offer — the
    v8.1 offer page's unit. Same head as the board card; rows are pair
    disclosures (`_offer_hedge`), and the empty state keeps the count-honesty
    language keyed to the crossing's exactness."""
    counts = team["counts"]
    tally = _num(counts["matched"]) + ("" if team["exact"] else "+")
    head = _card_head(team["name"], team["market"], tally)
    if not team["hedges"]:
        body = (
            '<p class="empty">No stored hedge against this offer clears the '
            "sliders with this team. "
            + (
                "The crossing was exhaustive, so that is a real answer about "
                "the stored legs — not a budget artefact."
                if team["exact"]
                else "The crossing hit its budget, so read this as “none found”, not “none exists”."
            )
            + "</p>"
        )
    else:
        body = "".join(_offer_hedge(h, i) for i, h in enumerate(team["hedges"], 1))
    return f'<section class="card">{head}{body}</section>'


def render_html(payload: Mapping) -> str:
    """A standalone page — no scripts, no external requests, `details/summary`
    for every disclosure so it works with JS off."""
    s = payload["sliders"]
    t = payload["totals"]
    delta = s["delta"]
    dial = (
        "robust — the guaranteed floor, good at every stored-value preference"
        if delta == "robust"
        else f"δ {delta:g} — a labeled preference view of the ranking"
    )
    fav = (
        f'{_num(s["favor_min"], signed=True, dp=0)} to {_num(s["favor_max"], signed=True, dp=0)}'
        if s["favor_min"] is not None and s["favor_max"] is not None
        else "no favor window"
    )
    meta_bits = [
        f'<span class="chip chip-flat"><span class="chip-k">min return</span>'
        f'<span class="chip-v">{_num(s["min_return"], dp=1, pct=True)}</span></span>',
        f'<span class="chip chip-flat"><span class="chip-k">favor</span>'
        f'<span class="chip-v">{_esc(fav)}</span></span>',
        f'<span class="chip chip-flat"><span class="chip-k">teams</span>'
        f'<span class="chip-v">{t["with_hedges"]}/{t["teams"]}</span></span>',
    ]
    if payload.get("data_age"):
        meta_bits.append(
            f'<span class="chip chip-flat"><span class="chip-k">data</span>'
            f'<span class="chip-v">{_esc(payload["data_age"])}</span></span>'
        )
    # v8: DB provenance under the wordmark — the reader should know the board
    # is a view over a complete leg database, not a fresh budgeted search
    prov = ""
    dbp = payload.get("db")
    if dbp:
        cc = dbp.get("cached_counts") or {}
        served = (
            f' · {cc["cached"]}/{cc["cached"] + cc["fresh"]} searches served from cache'
            if cc
            else ""
        )
        mid = (
            "one offer crossing · "
            if payload.get("mode") == "offer"
            else "exact per-team searches · "
        )
        prov = (
            f'<div class="sub">complete ±{dbp["band"]:g} leg database · '
            f'{dbp["legs"]:,} legs · {mid}'
            f'db <span class="mono">{_esc(dbp["content_fingerprint16"])}</span>'
            f"{served}</div>"
        )
    # v8 two-axis freshness, axis 2: the live collect moved past the DB's
    # content fingerprint — a rebuild question, distinct from snapshot age
    newer = ""
    if payload.get("mongo_newer"):
        newer = (
            '<div class="stale"><b>The collector has newer data than this '
            "board's database.</b> Every value below was priced from the older "
            "snapshot the DB was built on. Rebuild — <span class='mono'>"
            "score_trade.py hedgedb build</span> — before you quote any of it."
            "</div>"
        )
    cons = (
        _constraints_block(payload["constraints_in_effect"])
        if payload.get("constraints_in_effect") is not None
        else ""
    )
    stale = ""
    hrs = payload.get("data_age_hours")
    if hrs is None:
        stale = (
            '<div class="stale"><b>Unknown data age.</b> This board was not built '
            "from a dated collector run, so nothing here can be trusted against a "
            "live calculator. Run <span class=\'mono\'>just collect</span>, then "
            "regenerate.</div>"
        )
    elif hrs >= _STALE_HOURS:
        stale = (
            f'<div class="stale"><b>Data is {_esc(payload.get("data_age") or "old")}.</b> '
            "KTC re-prices continuously, so every value below has drifted from what "
            "your counterparty sees. Run <span class=\'mono\'>just collect</span> and "
            "regenerate before you quote any of it.</div>"
        )
    # v8.1: two page modes off one chrome — the session hedge board, and the
    # pinned-offer page (the offer atop per-counterparty hedge sets)
    if payload.get("mode") == "offer":
        offer = payload["offer"]
        cards = (
            newer + stale + _offer_pin(offer) + cons
            + "".join(_offer_team_card(x) for x in payload["teams"])
        )
        title = "Pinned offer"
        sub = (
            f'{_esc(payload["me"])} · exact hedges per counterparty for the '
            f'offer from {_esc(offer["card"]["counterparty"])}'
        )
        intro = (
            "Each row is one <strong>hedge leg</strong>: execute it alongside the "
            "pinned offer and the pair nets 0 players and 0 picks for your side. "
            "Chips are the PAIR — the offer and that hedge applied together (one "
            "combined lineup solve; face adds across legs). Open a row for the "
            "hedge's package, its own KTC-calculator gate, and a link rolling the "
            "whole pair. The offer's counterparty has no card — their trade is "
            "the pin. Ranking is maximin on the flat-Mid convention: best pair "
            "floor return first, best team first; the shown floor/ceiling also "
            f"fold the future-pick band (footer). Dial: {_esc(dial)}."
        )
        if offer.get("counts") is None:
            # the crossing never ran (count-neutral offer, or no complement
            # signature exists) — claiming an exhaustive crossing here would
            # violate the count-honesty contract
            honesty = (
                "No hedge crossing ran for this offer — the pinned card's note "
                "says why (a count-neutral offer stands alone; an empty "
                "complement signature is proof of absence at the DB's edges)."
            )
        elif t["all_exact"]:
            honesty = (
                "The crossing visited every eligible stored complement leg, so "
                "the per-team tallies are exact counts — a team at zero has no "
                "qualifying hedge among its stored legs."
            )
        else:
            honesty = (
                "The crossing hit its search budget; tallies carry a trailing + "
                "and are verified floors — never estimates, never proof of absence."
            )
    else:
        cards = newer + stale + cons + "".join(
            _team_card(x) for x in payload["teams"]
        )
        title = "Hedge board"
        sub = f'{_esc(payload["me"])} · best spreads per counterparty'
        intro = (
            "Each row is a count-neutral <strong>hedge</strong>: a buy leg and a "
            "sell leg that together net 0 players and 0 picks. A hedge touches "
            "two teams — it is listed under both, with that team's leg outlined. "
            "Open a row for the packages, the KTC-calculator gate on each leg, "
            "and the sequencing. Ranking is maximin on the flat-Mid convention: "
            "best guaranteed floor first; the shown floor/ceiling also fold the "
            f"future-pick band (footer). Dial: {_esc(dial)}."
        )
        honesty = (
            "Every counterparty's crossing ran to completion, so the hedge tallies are "
            "exact counts over the pooled legs."
            if t["all_exact"]
            else "Some crossings hit the budget; their tallies carry a trailing + and are "
            "verified floors, never estimates."
        )
    gen = f' · generated {_esc(payload["generated_at"])}' if payload.get("generated_at") else ""
    return f"""<style>{_CSS}</style>
<div class="band"></div>
<header class="mast"><div class="mast-in">
  <div class="wordmark">
    <div class="stars">{_STAR}{_STAR}{_STAR}{_STAR}</div>
    <h1>{title}</h1>
    <div class="sub">{sub}</div>
    {prov}
  </div>
  <div class="mast-meta">{''.join(meta_bits)}</div>
</div></header>
<main>
  <p class="note" style="padding:0 0 14px">
    {intro}
  </p>
  {cards}
</main>
<footer>
  <p>{_esc(honesty)} Coordinates are per side: <strong>starters</strong> is the change in
  your max-Σv legal lineup at raw KTC, <strong>face</strong> the change in total value you
  own. A pick's slot is never forecast: current-year picks price at KTC's exact number
  for their known slot, and every future pick at the middle of its round — the same
  price whoever holds it. The gate on each leg runs KTC's own calculator over exactly
  those prices, and its links carry them.</p>
  <p>Guaranteed floor is min(starters, face) with every future pick additionally resolved
  against you inside KTC's published Early/Mid/Late band — your sends landing early, your
  gets landing late, one finish per origin team per year, so two picks riding the same
  team's season net exactly. The ceiling is the mirror best case. The gain lies between
  them at every rational preference and every in-band slot outcome, so quote the floor
  and never a blend — but the band is KTC's tranche spread (an average of the round's
  ends, not a hard bound: a true 1.01 beats it). Prices, the gate, the verdict and the
  ranking never move off Mid — the ranking is maximin on the neutral convention, which
  is why a row's shown interval can sit slightly out of order. Favor is the signed skew
  toward the counterparty in KTC's own variance units; |favor| ≤ 5 is their calculator's
  FAIR window.</p>
  <p>The only links on this page open keeptradecut.com's trade calculator, pinned to
  the settings the gate ports (variance 5, 1QB, no pick scaling) so a leg's page total
  is exactly its <em>you</em> / <em>them</em> figures above. Current-year picks link at
  KTC's numbered entry for their exact slot; future picks link at the Mid tranche the
  gate priced.{gen}</p>
</footer>"""
