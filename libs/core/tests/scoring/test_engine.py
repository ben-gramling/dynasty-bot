"""compute_all end-to-end: schema, §12 explanation-equals-computation, §13.9 guards,
§13.2 crosswalk fixtures."""

from __future__ import annotations

import json
from dataclasses import replace as dc_replace

import pytest

from core.scoring import Snapshot, validate_snapshot
from core.scoring.params import ACTIVITY_PRIOR, OMEGA_SEEDS


def test_output_is_json_serializable(result):
    payload = json.dumps(result)
    assert len(payload) > 10_000


def test_top_level_shape(result):
    assert set(result) == {"meta", "waiver_board", "trade_recs", "league_table", "my_team_detail"}
    assert result["meta"]["mode"] == "offseason"
    assert result["meta"]["draft_status"] == "pre_draft"
    assert result["meta"]["my_team"] == "bengramling"
    assert result["meta"]["unvalued_rostered"] == ["Darren Waller"]
    assert result["meta"]["alerts"] == []
    tr = result["trade_recs"]
    assert tr["disabled"] is False
    assert 1 <= len(tr["recommendations"]) <= 10
    for opp, cards in tr["per_opponent"].items():
        assert len(cards) <= 3
        assert all(c["counterparty"] == opp for c in cards)


def test_components_sum_to_score(result):
    """§13.8/§12: displayed components sum to the score (0.1) and dL_terms sum to
    dL, for EVERY emitted card — claims and trades alike."""
    cards = list(result["trade_recs"]["recommendations"])
    for cs in result["trade_recs"]["per_opponent"].values():
        cards.extend(cs)
    claim_rows = result["waiver_board"]["targets"]
    drop_rows = result["waiver_board"]["drops"]
    assert cards and claim_rows and drop_rows
    for card in cards:
        for side in card["sides"].values():
            _check_side(side)
    for row in claim_rows[:25]:
        _check_side(row["sides"]["me"])
    for row in drop_rows:  # §12: DROP rows share the decomposition schema
        _check_side(row["sides"]["me"])
        assert -row["sides"]["me"]["score"] == row["rv"]


def _check_side(side):
    total = side["lineup_weighted"] + side["wealth_weighted"] + side["crunch_term"]
    assert abs(total - side["score"]) <= 0.16, side  # three 0.1-rounded components
    recomputed = side["omega"] * (side["dL"] + side["dNC"]) + (1 - side["omega"]) * side["dA"] - side["dC"]
    assert abs(recomputed - side["score"]) <= 0.2, side
    terms_sum = sum(t["delta"] for t in side["dL_terms"])
    assert abs(terms_sum - side["dL"]) <= 0.1 + 0.05 * len(side["dL_terms"]), side


def test_audit_tables_on_every_card(result):
    for card in result["trade_recs"]["recommendations"]:
        tables = card["audit"]["lineup_tables"]
        for who in ("me", "them"):
            assert len(tables[who]["before"]) == 9
            assert len(tables[who]["after"]) == 9
            slots = [r["slot"] for r in tables[who]["before"]]
            assert slots == ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX1", "FLEX2"]


def test_card_schema_matches_contract(result):
    """§12 field census on a real emitted trade card."""
    card = result["trade_recs"]["recommendations"][0]
    for key in (
        "action", "counterparty", "give", "get", "sides", "fairness", "tier",
        "posture_fit", "activity", "anchor_ask_pct", "omega_sensitivity", "audit",
        "rank_score_H",
    ):
        assert key in card, key
    assert card["action"] == "TRADE"
    for side in ("me", "them"):
        s = card["sides"][side]
        for key in ("omega", "dL", "dNC", "dA", "dC", "score", "dL_terms", "crunch"):
            assert key in s, key
    for entry in card["give"] + card["get"]:
        assert entry["type"] in ("player", "pick")
        if entry["type"] == "pick":
            assert "pricing" in entry and "mv" in entry
    assert set(card["fairness"]) >= {"adj", "raw_ratio", "cap"}
    assert len(card["omega_sensitivity"]) == 3
    assert ACTIVITY_PRIOR[card["counterparty"]] == card["activity"]


def test_scrape_guards(snapshot):
    """§13.9: clean snapshot passes; synthetic violations alert."""
    assert validate_snapshot(snapshot) == []
    few = dc_replace(snapshot, ktc_assets=list(snapshot.ktc_assets)[:100])
    alerts = validate_snapshot(few)
    assert any("480-520" in a for a in alerts)
    no_rdp = dc_replace(
        snapshot, ktc_assets=[a for a in snapshot.ktc_assets if a["position"] != "RDP"]
    )
    assert any("RDP" in a for a in validate_snapshot(no_rdp))
    missing_map = dc_replace(
        snapshot, crosswalk={k: v for k, v in list(snapshot.crosswalk.items())[:400]}
    )
    assert any("crosswalk" in a for a in validate_snapshot(missing_map))


def test_crosswalk_fixtures(snapshot, league):
    """§13.2: roster-4 position sums match the published table; taxi/reserve subsets."""
    r4 = next(r for r in snapshot.rosters if r["roster_id"] == 4)
    sums = {"QB": 0.0, "RB": 0.0, "WR": 0.0, "TE": 0.0}
    for sid in r4["players"]:
        p = league.players[sid]
        if p.pos in sums:
            sums[p.pos] += p.v
    assert sums == {"QB": 11095, "RB": 34349, "WR": 30860, "TE": 10869}
    for r in snapshot.rosters:
        players = set(r["players"])
        assert set(r.get("taxi") or []) <= players
        assert set(r.get("reserve") or []) <= players
    rostered = {sid for r in snapshot.rosters for sid in r["players"]}
    unvalued = [sid for sid in rostered if league.players[sid].unvalued]
    assert unvalued == ["2505"]  # Darren Waller — alert fires if this grows (§9.6)


def test_omega_seed_table_complete():
    assert len(OMEGA_SEEDS) == 11
    assert set(ACTIVITY_PRIOR) == set(OMEGA_SEEDS) | {"joeydavis299"}


def test_taxi_promotion_rows(result):
    """§9.3: the board evaluates taxi promotions (Cam Ward: ω·ΔL = +126.5)."""
    promos = {p["player"]: p for p in result["waiver_board"]["taxi_promotions"]}
    assert set(promos) == {"Cam Ward", "Elijah Arroyo"}
    assert promos["Cam Ward"]["omega_dl"] == 126.5
    assert promos["Cam Ward"]["lock_penalty"] == 0.0  # pre-lock in July


def test_in_season_mode(snapshot, params):
    """§9.5 one formula, one mode flag: in-season IR leaves the pool, ω ramps by
    standings, the trade tab stays live through week 11."""
    from core.scoring import model as md
    from core.scoring import waivers as wv

    rosters = []
    for r in snapshot.rosters:
        r = dict(r)
        s = dict(r["settings"])
        s["wins"] = 3 if r["roster_id"] == 2 else 1
        r["settings"] = s
        rosters.append(r)
    live = dc_replace(
        snapshot,
        state={**dict(snapshot.state), "season_type": "regular", "week": 3},
        rosters=rosters,
    )
    league2 = md.build_league(live, params)
    jt = league2.teams["jaketoppen"]
    assert "George Kittle" not in {p.name for p in jt.pool}  # IR out of the pool
    assert jt.L < 47214.1  # July L counted Kittle/Jones; September must not
    assert jt.omega == pytest.approx(0.70 + 0.15 * 3 / 11)  # seed-1 ramp
    board = wv.waiver_board(league2, league2.teams[league2.me])
    assert board["mode"] == "in-season"


def test_ir_recommended_before_drop(snapshot, params, league):
    """§9.4: claim needing a spot + an OUT active + a free IR slot → IR move, no drop.
    Offseason: game statuses don't exist, never suggest IR."""
    from core.scoring import model as md
    from core.scoring import waivers as wv

    # synthetically knock out Tank Dell (my bench WR) in the KTC feed, in-season
    assets = []
    for a in snapshot.ktc_assets:
        if a.get("playerName") == "Tank Dell":
            a = {**a, "injury": {"injuryCode": 4, "injuryName": "Out", "injuryReturn": "Oct 1, 2026"}}
        assets.append(a)
    live = dc_replace(
        snapshot,
        state={**dict(snapshot.state), "season_type": "regular", "week": 3},
        ktc_assets=assets,
    )
    league2 = md.build_league(live, params)
    me2 = league2.teams[league2.me]
    cand = wv.ir_move_candidate(league2, me2)
    assert cand is not None and cand.name == "Tank Dell"
    board = wv.waiver_board(league2, me2)
    top = board["targets"][0]
    assert top["ir_move"] == "Tank Dell"
    assert top["drop"] is None
    # never in the offseason (§9.4), even with the same injury feed
    assert wv.ir_move_candidate(league, league.teams["bengramling"]) is None


def test_unvalued_growth_alert(snapshot, params):
    """§13.2: a second rostered player falling out of KTC coverage fires the alert."""
    from core.scoring import model as md

    kid = next(
        k for k, e in snapshot.crosswalk.items() if e["ktc_name"] == "Tank Dell"
    )
    xw = {k: v for k, v in snapshot.crosswalk.items() if k != kid}
    league2 = md.build_league(dc_replace(snapshot, crosswalk=xw), params)
    assert any("unvalued rostered players grew to 2" in a for a in league2.alerts)


def test_availability_long_out(snapshot, params):
    """§9.5: OUT with expected return > u_out_short_weeks (or unknown) gets 0.25;
    ≤ 3 weeks gets 0.6; offseason always 1.0."""
    from core.scoring import model as md

    def knocked(ret: str | None) -> list[dict]:
        out = []
        for a in snapshot.ktc_assets:
            if a.get("playerName") == "Tank Dell":
                inj = {"injuryCode": 4, "injuryName": "Out"}
                if ret:
                    inj["injuryReturn"] = ret
                a = {**a, "injury": inj}
            out.append(a)
        return out

    def u_of(league2):
        return next(p.u for p in league2.players.values() if p.name == "Tank Dell")

    live = {**dict(snapshot.state), "season_type": "regular", "week": 3}
    # week 3 of 2026 (no season_start_date) → reference date Sept 15
    for ret, want in [
        ("Oct 1, 2026", params.u_out_short),  # 16 days out
        ("Dec 20, 2026", params.u_out_long),  # months out
        (None, params.u_out_long),  # unknown return
        ("soon", params.u_out_long),  # unparseable return
    ]:
        league2 = md.build_league(
            dc_replace(snapshot, state=live, ktc_assets=knocked(ret)), params
        )
        assert u_of(league2) == want, ret
    offseason = md.build_league(
        dc_replace(snapshot, ktc_assets=knocked("Dec 20, 2026")), params
    )
    assert u_of(offseason) == params.u_healthy


def test_dip_flag(snapshot, params):
    """§7.6: −6% vs our trailing-30-day archive tags DIP."""
    from core.scoring import model as md
    from core.scoring import waivers as wv

    dulcich_ktc_id = "1256"
    hist = dc_replace(snapshot, value_history_max={dulcich_ktc_id: 3000.0})
    league2 = md.build_league(hist, params)
    board = wv.waiver_board(league2, league2.teams[league2.me])
    row = next(r for r in board["targets"] if r["player"] == "Greg Dulcich")
    assert row["dip"] is True
    others = [r for r in board["targets"] if r["player"] != "Greg Dulcich"]
    assert all(r["dip"] is False for r in others)  # no archive → never flagged


def test_recommendation_ordering(result):
    """Display order: acceptance tier first, then H (documented deviation: the
    reference doc implies H-ranking; tier-first keeps takeable deals on top)."""
    recs = result["trade_recs"]["recommendations"]
    tiers = [r["tier"] for r in recs]
    assert tiers == sorted(tiers)
