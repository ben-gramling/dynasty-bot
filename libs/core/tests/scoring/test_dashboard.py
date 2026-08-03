"""The v7.1 per-counterparty hedge dashboard: payload shape and the standalone
HTML render. Fixtures only — the payload is built from the committed snapshot
through the same `find_spreads` the CLI calls.

`core.dashboard` lives outside `core.scoring` (it is presentation, not spec),
but its test lives here because it needs the session-scoped `league` fixture
and the leg-table cache that the scoring conftest already provides."""

from __future__ import annotations

import re

import pytest

from core import dashboard as dash


@pytest.fixture(scope="module")
def payload(league, tmp_path_factory) -> dict:
    """One counterparty search per opponent. `workers=1` keeps it in-process:
    the parallel path is a wall-clock optimisation, not a behaviour change, and
    forking under pytest buys nothing but flakiness."""
    return dash.hedge_payload(
        league,
        # the fair window with a HIGH return bar and a tiny top: the sound k5
        # break bites hard at 6%, which keeps eleven exhaustive searches inside
        # a sane test budget while still leaving every team something to rank
        sliders={"min_return": 6.0, "favor_min": -5.0, "favor_max": 5.0, "top": 2},
        cache_dir=tmp_path_factory.mktemp("finder-cache"),
        workers=1,
        generated_at="2026-08-02 12:00 UTC",
        data_age="0.2h old",
    )


def test_every_counterparty_gets_a_section(payload, league):
    """One entry per opponent, in a deterministic order, me excluded — a team
    with nothing to show still appears, because "nothing here" is the answer
    the desk needs about that team."""
    names = [t["name"] for t in payload["teams"]]
    assert names == sorted(league.opponents)
    assert league.me not in names
    assert payload["totals"]["teams"] == len(league.opponents) == 11


def test_the_named_team_is_actually_on_one_of_the_legs(payload):
    """A hedge has TWO counterparties. `their_side` says which leg belongs to
    the team the section is filed under, and `partner` names the other — get
    this wrong and the page attributes trades to the wrong manager."""
    seen_buy = seen_sell = False
    for team in payload["teams"]:
        for sp in team["spreads"]:
            side = sp["their_side"]
            assert side in ("buy", "sell")
            assert sp[side]["counterparty"] == team["name"]
            other = "sell" if side == "buy" else "buy"
            assert sp[other]["counterparty"] == sp["partner"] != team["name"]
            seen_buy |= side == "buy"
            seen_sell |= side == "sell"
    assert seen_buy and seen_sell  # both orientations really occur


def test_hedges_are_count_neutral_verdict_true_and_maximin_ordered(payload):
    """The §5 unit and the §2 ranking, straight from the finder — the dashboard
    re-derives nothing, so these hold by construction and this pins that."""
    for team in payload["teams"]:
        for sp in team["spreads"]:
            assert sp["net_players"] == 0 and sp["net_picks"] == 0
            assert sp["verdict"] is True
            assert sp["floor"] == min(sp["coords"]["dS"], sp["coords"]["dF"])
            assert sp["ceiling"] == max(sp["coords"]["dS"], sp["coords"]["dF"])
            assert sp["return_robust"] >= payload["sliders"]["min_return"]
            # the favor window is the fair band on BOTH legs (v5.0.1 push-down)
            for leg in ("buy", "sell"):
                assert -5.0 <= sp["favor"][leg] <= 5.0
        # maximin is on the floor-based RETURN (floor ÷ Σ face sent), not the
        # raw floor — a smaller floor on a much smaller package outranks a
        # bigger one, which is the whole point of ranking on inventory deployed
        rets = [s["return_robust"] for s in team["spreads"]]
        assert rets == sorted(rets, reverse=True)


def test_scoping_to_one_counterparty_is_exhaustive(payload):
    """§4a v6: `with_team` pushes down into the crossing, so a per-counterparty
    run completes rather than saturating. If this ever flips to False the
    tallies become floors and the page must say so — which it does, but the
    point of the per-counterparty split is that it should not have to."""
    assert payload["totals"]["all_exact"] is True
    assert all(t["exact"] for t in payload["teams"])
    assert payload["totals"]["matched"] > 0


def test_render_is_standalone_and_escapes(payload):
    """The artifact CSP blocks every external request, so the page must carry
    no src/href to anywhere and no script at all."""
    page = dash.render_html(payload)
    assert "<script" not in page.lower()
    # no `src` at all, and the ONLY hrefs are keeptradecut trade-calculator
    # deep links — an outbound link the user clicks is not a page dependency,
    # so it costs nothing under the artifact CSP
    assert not re.search(r'\bsrc\s*=', page)
    hrefs = re.findall(r'href="([^"]+)"', page)
    assert hrefs, "the calculator links must actually be rendered"
    assert all(h.startswith("https://keeptradecut.com/trade-calculator?") for h in hrefs)
    assert "http://" not in page
    # no <html>/<head>/<body> — the artifact harness supplies the skeleton.
    # Matched as complete tags: `<header>` is ours and must not trip this.
    assert not re.search(r"<\s*(!doctype|html|head|body)\b", page, re.I)
    # every team is a section, and the disclosure works without JS
    for team in payload["teams"]:
        assert f">{team['name']}</h2>" in page
    assert page.count("<details class=\"hedge\">") == sum(
        len(t["spreads"]) for t in payload["teams"]
    )


def test_every_hedge_carries_leg_and_spread_calculator_links(payload):
    """Per leg AND for the whole spread as one hypothetical trade. The leg links
    are the real ones — each leg IS a trade with one counterparty, and the link
    opens the calculator at the settings the gate ports, so its page total is
    `gate.adj_give` / `adj_get`. The spread link is a what-if and is labeled as
    one on the page."""
    seen = 0
    for team in payload["teams"]:
        for sp in team["spreads"]:
            links = sp["links"]
            assert set(links) == {"buy", "sell", "spread"}
            for leg in ("buy", "sell"):
                url = links[leg]["url"]
                assert url and url.startswith("https://keeptradecut.com/trade-calculator?")
                # the settings the gate assumes — format=1 is load-bearing, a
                # Superflex page prices every asset in the wrong column
                for want in ("var=5", "pickVal=0", "format=1", "isStartup=0", "tep=0"):
                    assert want in url, (leg, want)
                assert "teamOne=" in url and "teamTwo=" in url
                # teamOne is what I SEND, which is what makes the page total
                # line up with adj_give (ktc_link's stated convention)
                one = url.split("teamOne=")[1].split("&")[0]
                assert one.count("%7C") + 1 == len(sp[leg]["give"]) - len(
                    links[leg]["dropped"]
                ) or links[leg]["dropped"]
            sprd = links["spread"]
            assert sprd["url"] or sprd.get("blocked")
            seen += 1
    assert seen > 0


def test_spread_link_is_both_legs_rolled_into_one_trade(payload):
    """It sends everything both legs send and receives everything they receive
    — the whole spread as a single trade against a single manager."""
    for team in payload["teams"]:
        for sp in team["spreads"]:
            sprd = sp["links"]["spread"]
            if not sprd["url"]:
                continue  # KTC's 12-asset cap; disclosed as `blocked`
            n_give = len(sp["buy"]["give"]) + len(sp["sell"]["give"])
            n_get = len(sp["buy"]["get"]) + len(sp["sell"]["get"])
            one = sprd["url"].split("teamOne=")[1].split("&")[0]
            two = sprd["url"].split("teamTwo=")[1].split("&")[0]
            dropped = len(sprd["dropped"])
            assert (one.count("%7C") + 1) + (two.count("%7C") + 1) + dropped == (
                n_give + n_get
            )


def test_a_page_with_no_linkable_assets_says_so_instead_of_linking(payload):
    """`url=None` means one side emptied out; a link then would render as a
    one-sided giveaway on the counterparty's screen. The page must say why."""
    page = dash.render_html(
        {
            **payload,
            "teams": [
                {
                    **payload["teams"][0],
                    "spreads": [
                        {
                            **payload["teams"][0]["spreads"][0],
                            "links": {
                                "buy": {"url": None, "numbered_url": None,
                                        "dropped": ["Some Guy"], "numbered": []},
                                "sell": {"url": None, "numbered_url": None,
                                         "dropped": [], "numbered": []},
                                "spread": {"url": None, "numbered_url": None,
                                           "dropped": [], "numbered": [],
                                           "blocked": "too many assets"},
                            },
                        }
                    ],
                }
            ],
        }
    )
    assert "not linkable" in page and "giveaway" in page
    assert "too many assets" in page


def test_render_uses_the_ledger_conventions(payload):
    """docs/web-design.md: red is ONLY a negative number (or the star), the
    minus is a true U+2212, and both themes are defined at token level."""
    page = dash.render_html(payload)
    assert "--star:#C8102E" in page and "--sky:#A8D8F0" in page  # flag palette
    assert "prefers-color-scheme:dark" in page
    assert ':root[data-theme="dark"]' in page and ':root[data-theme="light"]' in page
    assert "green" not in page.lower()  # positives are ink, never a traffic light
    assert 'class="chip-k">' in page
    # Every hedge on this page is verdict-true (both coordinates >= 0), so a
    # real board is almost all positives — which is exactly why the negative
    # styling has to be exercised deliberately rather than assumed present.
    assert dash._num(-1234) == "\u22121,234"  # true minus U+2212, not a hyphen
    assert dash._num(1234, signed=True) == "+1,234"
    assert 'class="chip-v neg">\u2212250</span>' in dash._chip("face", -250)
    assert "neg" not in dash._chip("face", 250)  # positives never wear it
    # and favor is deliberately NOT a ledger number: negative favor is GOOD for
    # us, so it never takes the red, it says the direction in words instead
    assert dash._favor_chip(-4.6) == dash._favor_chip(-4.6).replace("neg", "")
    assert "4.6 to you" in dash._favor_chip(-4.6)
    assert "4.6 to them" in dash._favor_chip(4.6)
    assert "even" in dash._favor_chip(0.0)


def test_slider_echo_survives_into_the_page(payload):
    page = dash.render_html(payload)
    assert "guaranteed floor" in page
    assert "0.2h old" in page and "2026-08-02 12:00 UTC" in page
    assert "min return" in page and "favor" in page


def test_stale_data_is_called_out_in_red(payload):
    """KTC re-prices continuously — a mid-tier WR drifted 2,595 -> 2,574 in six
    hours — so a board built off an old collect quotes numbers the counterparty's
    screen no longer shows. That is the failure this dashboard exists to avoid,
    so age is the one thing on the page allowed to shout.

    (This is here because a board rendered from the committed FIXTURE was
    published and read as live: it showed Stefon Diggs at 2,641, the 2026-07-26
    value, against 2,574 on the user's screen. The engine was right; the vintage
    was a week old and the page did not say so loudly enough.)"""
    fresh = dash.render_html({**payload, "data_age": "0.4h old", "data_age_hours": 0.4})
    assert 'class="stale"' not in fresh

    old = dash.render_html({**payload, "data_age": "31.0h old", "data_age_hours": 31.0})
    assert 'class="stale"' in old
    assert "31.0h old" in old and "just collect" in old

    unknown = dash.render_html({**payload, "data_age": None, "data_age_hours": None})
    assert "Unknown data age" in unknown and "just collect" in unknown

    # the threshold is a real boundary, not decoration
    assert dash._STALE_HOURS > 0
    edge = dash.render_html(
        {**payload, "data_age": "x", "data_age_hours": dash._STALE_HOURS - 0.01}
    )
    assert 'class="stale"' not in edge


# ------------------------------------------------------- v8: the hedge-DB board
#
# `db_payload` mirrors `hedge_payload`'s shape exactly (so `render_html` works
# on either) and adds the §12 blocks: db provenance, constraints-in-effect,
# focus/pin, and the second freshness axis. One module-scoped reduced-params DB
# (max_package=2 — the same fixture pattern test_hedgedb.py pins) keeps the
# runtime modest; searches cache inside the DB dir across tests.


@pytest.fixture(scope="module")
def hdb(snapshot, tmp_path_factory):
    pytest.importorskip("numpy", reason="hedgedb needs the core[hedgedb] extra")
    import core.scoring.hedgedb as hd
    from core.scoring import Params

    params = Params(
        max_package=2,
        hedgedb_search_budget=2_000_000,
        finder_cross_budget=2_000_000,
    )
    return hd.build(
        snapshot, params, cache_dir=tmp_path_factory.mktemp("hedgedb-dash"), bake=False
    )


_DB_QUERY = {
    "min_return": 1.0,
    "favor_min": -5.0,
    "favor_max": 5.0,
    "delta": "robust",
    "top": 10,
    "use_intel": False,
    "use_posture": False,
}

_DB_SLIDERS = {**_DB_QUERY, "top": 5}


@pytest.fixture(scope="module")
def db_results(hdb) -> dict:
    """Three per-counterparty searches — enough to exercise ordering, links and
    both leg orientations without paying for the full slate."""
    names = ["cmgaither43", "ronakpatel32"]
    names.append(next(n for n in sorted(hdb.opp_names) if n not in names))
    return {n: hdb.search({**_DB_QUERY, "with_team": n}, intel=()) for n in names}


def _db_payload(hdb, db_results, **kw):
    kw.setdefault("sliders", _DB_SLIDERS)
    kw.setdefault("generated_at", "2026-08-03 12:00 UTC")
    kw.setdefault("data_age", "0.1h old")
    kw.setdefault("data_age_hours", 0.1)
    return dash.db_payload(hdb, db_results, **kw)


def test_db_payload_mirrors_hedge_payload_shape(payload, hdb, db_results):
    """Key-for-key parity with the v7.1 payload — per team, per spread and in
    the totals — so `render_html` never needs to know which engine fed it."""
    p = _db_payload(hdb, db_results)
    assert set(payload) <= set(p)
    assert set(payload["totals"]) == set(p["totals"])
    ref_team = next(t for t in payload["teams"] if t["spreads"])
    ref_sp = ref_team["spreads"][0]
    assert any(t["spreads"] for t in p["teams"])  # the render below is real
    for t in p["teams"]:
        assert set(ref_team) <= set(t)
        assert len(t["spreads"]) <= _DB_SLIDERS["top"]  # display slice only
        for sp in t["spreads"]:
            assert set(ref_sp) <= set(sp)
            side = sp["their_side"]
            assert sp[side]["counterparty"] == t["name"]
            assert sp["sell" if side == "buy" else "buy"]["counterparty"] == sp["partner"]
            assert set(sp["links"]) == {"buy", "sell", "spread"}


def test_db_payload_focus_reorders(hdb, db_results):
    names = sorted(db_results)
    focus = names[-1]
    p = _db_payload(hdb, db_results, focus=focus)
    assert [t["name"] for t in p["teams"]] == [focus] + [n for n in names if n != focus]
    assert p["focus"] == focus
    base = _db_payload(hdb, db_results)
    assert [t["name"] for t in base["teams"]] == names


def test_mongo_newer_renders_its_own_red_banner(hdb, db_results):
    """The second freshness axis: content moved past the DB. Distinct from the
    snapshot-age banner — here the age is fresh, so the ONLY shout is the
    fingerprint one, and it names the rebuild command."""
    fresh_page = dash.render_html(_db_payload(hdb, db_results))
    assert "newer data" not in fresh_page
    assert 'class="stale"' not in fresh_page
    page = dash.render_html(_db_payload(hdb, db_results, mongo_newer=True))
    assert "newer data" in page and "hedgedb build" in page
    assert page.count('class="stale"') == 1


def test_constraints_in_effect_block(hdb, db_results):
    """The disclosure block always renders on a DB board, and a query
    constraint appears once with its provenance — deduped across the team
    searches, which compile identically."""
    p = _db_payload(hdb, db_results)
    assert p["constraints_in_effect"] == {"applied": [], "shed": [], "ignored_intel": []}
    page = dash.render_html(p)
    assert "Constraints in effect" in page

    n1, n2 = sorted(db_results)[:2]
    con = [{"who": "me", "side": "receives", "what": {"class": "pick"},
            "with": None, "mode": "require"}]
    r1 = hdb.search({**_DB_QUERY, "with_team": n1, "constraints": con}, intel=())
    r2 = hdb.search({**_DB_QUERY, "with_team": n2, "constraints": con}, intel=())
    p2 = _db_payload(hdb, {n1: r1, n2: r2})
    ce = p2["constraints_in_effect"]
    assert len(ce["applied"]) == len(r1["applied_constraints"]) == 1
    assert ce["applied"][0]["source"] == "query"
    page2 = dash.render_html(p2)
    assert "Constraints in effect" in page2
    assert "me receives picks" in page2
    assert "ad-hoc query constraint" in page2


def test_pinned_offer_page(hdb):
    """v8.1: a real `HedgeDB.offer` (built from a pool leg's own packages, so
    it is gate-clean by construction) renders as its OWN page — the offer
    pinned at the top, then one card per REMAINING counterparty with its
    hedge set (the offerer absent), every row carrying a hedge-leg link and
    a whole-pair link, best team first."""
    buckets = hdb.buckets()
    sig = (1, -1) if (1, -1) in buckets else sorted(buckets)[0]
    li = int(buckets[sig][0])
    give = hdb.package(int(hdb._cols["give_pid"][li]))
    get = hdb.package(int(hdb._cols["get_pid"][li]))
    opp = hdb.opp_names[int(hdb._cols["opp"][li])]
    res = hdb.offer(
        opp, [a.name for a in give.assets], [a.name for a in get.assets],
        query=_DB_QUERY, intel=(),
    )
    assert res["hedges"], "a (1,-1) pool leg must cross at the 1% floor"
    p = dash.offer_payload(
        hdb, res, sliders=_DB_SLIDERS, generated_at="2026-08-03 12:00 UTC",
        data_age="0.1h old", data_age_hours=0.1,
    )
    assert p["mode"] == "offer"
    assert p["offer"]["card"]["counterparty"] == opp
    names = [t["name"] for t in p["teams"]]
    assert opp not in names and hdb.league.me not in names
    assert set(names) == {n for n in hdb.opp_names if n != opp}
    assert names == list(res["by_team"])  # best team first, empties trailing
    mb = res["counts"]["matched_by_team"]
    for t in p["teams"]:
        assert len(t["hedges"]) <= _DB_SLIDERS["top"]  # display slice
        assert t["counts"]["matched"] == mb[t["name"]]
        for h in t["hedges"]:
            assert h["hedge"]["counterparty"] == t["name"]
            assert set(h["links"]) == {"hedge", "pair"}
    page = dash.render_html(p)
    assert "Pinned offer" in page
    assert "GATE PASS" in page  # a pool leg passed the real gate at build time
    shown = sum(len(t["hedges"]) for t in p["teams"])
    assert page.count('<details class="hedge offer-hedge">') == shown
    assert page.count('<details class="hedge">') == 0  # no board rows here
    assert "Hedge board" not in page  # its own page, not a board with a pin
    assert page.index("Pinned offer") < page.index(
        '<details class="hedge offer-hedge">'
    )
    nonempty = [t for t in p["teams"] if t["hedges"]]
    assert nonempty and nonempty[0]["hedges"][0]["id"] == "H1"


def test_pinned_offer_page_count_neutral(hdb):
    """v8.1: an offer that never crossed (count-neutral) has no team cards —
    the pin and its disclosure note ARE the page."""
    import core.scoring.trades as tr

    league = hdb.league
    me = league.teams[league.me]
    opp = sorted(n for n in league.teams if n != league.me)[0]
    mine = [a for a in tr.team_assets(league, me).values() if a.kind == "player"]
    theirs = [
        a for a in tr.team_assets(league, league.teams[opp]).values()
        if a.kind == "player"
    ]
    res = hdb.offer(opp, [mine[0].name], [theirs[0].name], query=_DB_QUERY, intel=())
    p = dash.offer_payload(
        hdb, res, sliders=_DB_SLIDERS, generated_at="2026-08-03 12:00 UTC",
        data_age="0.1h old", data_age_hours=0.1,
    )
    assert p["teams"] == [] and p["totals"]["teams"] == 0
    page = dash.render_html(p)
    assert "count-neutral" in page
    assert page.count('<details class="hedge offer-hedge">') == 0
    # count honesty: no crossing ran, so the footer must not claim one
    assert "crossing visited every eligible" not in page
    assert "No hedge crossing ran" in page


def test_db_provenance_line_and_bar_raised_tally(hdb, db_results):
    """render_html on a db_payload raises nothing, carries the provenance line,
    and flips a team's matched tally to a '≥ N' floor when the warm bar rose."""
    p = _db_payload(hdb, db_results)
    d = p["db"]
    assert d["legs"] == hdb.meta["legs"]
    assert d["band"] == hdb.meta["band"]
    assert d["content_fingerprint16"] == hdb.meta["content_fingerprint"][:16]
    assert set(d["cached_counts"]) == {"cached", "fresh"}
    page = dash.render_html(p)
    assert "leg database" in page
    assert f"{hdb.meta['legs']:,} legs" in page
    assert hdb.meta["content_fingerprint"][:16] in page
    # the bar-raised honesty marker, exercised both ways deliberately
    p["teams"] = [{**t, "bar_raised": False} for t in p["teams"]]
    assert "≥" not in dash.render_html(p)
    p["teams"] = [{**p["teams"][0], "bar_raised": True}, *p["teams"][1:]]
    assert "≥" in dash.render_html(p)


def test_html_escaping_of_asset_names():
    """Names come from KTC and Sleeper; a stray angle bracket must not become
    markup. Built by hand so the case exists regardless of the fixture."""
    nasty = '<script>alert("x")</script> & Co.'
    payload = {
        "me": "bengramling",
        "generated_at": None,
        "data_age": None,
        "sliders": dict(dash._SLIDER_DEFAULTS),
        "totals": {"teams": 1, "with_hedges": 1, "matched": 1, "all_exact": True},
        "teams": [
            {
                "name": nasty,
                "market": {
                    "posture": "BUYER",
                    "holes": [{"pos": "WR", "rank": 10}],
                    "pick_inventory": {"count": 3, "value": 9000},
                    "faab": 50,
                },
                "counts": {"matched": 1},
                "exact": True,
                "constraints": [],
                "spreads": [],
            }
        ],
    }
    page = dash.render_html(payload)
    assert "<script>" not in page
    assert "&lt;script&gt;" in page and "&amp; Co." in page
