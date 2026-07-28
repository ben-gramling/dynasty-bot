"""compute_all end-to-end: v3 output shape, scrape guards, crosswalk fixtures,
mode switching. Pins from the committed fixtures."""

from __future__ import annotations

import json
from dataclasses import replace as dc_replace

from core.scoring import Snapshot, validate_snapshot

from .conftest import board_legs


def test_output_is_json_serializable(result):
    payload = json.dumps(result)
    assert len(payload) > 10_000


def test_top_level_shape(result):
    assert set(result) == {"meta", "waiver_board", "trade_recs", "league_table", "my_team_detail"}
    meta = result["meta"]
    assert meta["mode"] == "offseason"
    assert meta["draft_status"] == "pre_draft"
    assert meta["my_team"] == "bengramling"
    assert meta["unvalued_rostered"] == ["Darren Waller"]
    assert meta["alerts"] == []
    assert meta["w_min"] == 150.0
    tr = result["trade_recs"]
    assert set(tr) == {
        "disabled", "pairs", "presets", "counts_by_threshold", "bands",
        "truncated", "recommendations", "watch", "notes",
    }
    assert tr["disabled"] is False
    # the PRIMARY list (§5 v3.3.1): stratified per-band storage behind the
    # return RANGE — dense on this fixture (every band at quota, honest floors)
    assert 0 < len(tr["pairs"]) <= 500
    assert tr["presets"] == [1.0, 2.5, 5.0, 10.0, 20.0]
    assert {e["threshold"] for e in tr["counts_by_threshold"]} == set(tr["presets"])
    # v3.3.1 band inventory: one entry per band, derived from the presets
    assert [set(b) for b in tr["bands"]] == [
        {"lo", "hi", "stored", "count", "saturated"}
    ] * len(tr["presets"])
    assert [b["lo"] for b in tr["bands"]] == tr["presets"]
    assert [b["hi"] for b in tr["bands"]] == tr["presets"][1:] + [None]
    assert 0 <= len(tr["recommendations"]) <= 10  # secondary: building blocks
    assert isinstance(tr["watch"], list) and isinstance(tr["notes"], list)
    for pair in tr["pairs"]:
        # v3.4 adds the ledger split of the combined ΔW and the legs' isolation
        # sum alongside it (the two differ wherever the legs share a lineup)
        assert set(pair) == {
            "id", "buy", "sell", "return_pct", "dW_combined", "dW_combined_parts",
            "dW_legs_isolated", "net_roster", "net_players", "net_picks",
            "fit_summary", "sequencing", "overlaps",
        }
        assert set(pair["dW_combined_parts"]) == {"dS", "dP"}
        assert pair["net_players"] == 0 and pair["net_picks"] == 0  # §5 v3.2


def test_card_schema_matches_contract(result):
    """§5/§10 field census on every displayed trade card (pair legs + sell list)."""
    for card in board_legs(result["trade_recs"]):
        for key in (
            "id", "action", "counterparty", "give", "get", "dW", "dW_parts",
            "dW_basis", "gate", "posture", "holes", "net_roster", "net_players",
            "net_picks", "standalone", "leg_type", "sequencing", "ceiling",
            "taxi_stashed", "anchor_ask", "dip_notes", "unvalued", "exclusive_with",
        ):
            assert key in card, key
        assert card["action"] == "TRADE"
        assert card["leg_type"] in ("buy", "sell", "neutral")
        assert set(card["dW"]) == {"me", "them"}
        # §2 v3.4: each side's own ledger, split into starters and picks
        assert set(card["dW_parts"]) == {"me", "them"}
        assert set(card["dW_parts"]["me"]) == {"dS", "dP"}
        assert card["dW"]["me"] == round(
            card["dW_parts"]["me"]["dS"] + card["dW_parts"]["me"]["dP"], 1
        )
        assert card["dW_basis"] == "isolation"
        assert set(card["net_players"]) == {"me", "them"}  # §5 v3.2 count deltas
        assert set(card["net_picks"]) == {"me", "them"}
        assert isinstance(card["standalone"], bool)
        assert set(card["ceiling"]) == {"value", "note"}  # §3 v3.1 negotiating room
        g = card["gate"]
        for key in (
            "adj_give", "adj_get", "gap", "gap_pct", "band", "band_pct",
            "band_ok", "raw_ratio", "cap", "ratio_ok", "legal", "verdict",
        ):
            assert key in g, key
        p = card["posture"]
        assert p["label"] in ("BUYER", "SELLER", "NEUTRAL")
        assert p["shape"] in ("players", "picks", "mixed")
        assert p["source"] in ("trades", "override")
        for entry in card["give"] + card["get"]:
            assert entry["type"] in ("player", "pick")
            assert {"key", "name", "v"} <= set(entry)
    for card in result["trade_recs"]["recommendations"]:
        assert "rank" in card  # ranks only on the secondary list


def test_notes_mention_execution_protocol(result):
    notes = result["trade_recs"]["notes"]
    assert any("recomputes" in n for n in notes)
    assert any("fire-sale" in n for n in notes)
    assert any("0 players / 0 picks" in n for n in notes)  # §5 pair unit
    assert any("target-return range" in n for n in notes)  # §5 v3.3.1 selectivity
    assert any("stratified storage" in n for n in notes)  # v3.3.1 per-band quota
    assert any("posture is a hard engine constraint" in n for n in notes)
    assert any("saturated" in n for n in notes)  # honest-counter semantics
    # truncation is reported in the notes whenever the doc carries the flag
    if result["trade_recs"]["truncated"]:
        assert any("storage cap" in n for n in notes)


def test_scrape_guards(snapshot):
    """Clean snapshot passes; synthetic violations alert."""
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
    """Roster-4 position sums match the published table; taxi/reserve subsets."""
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
    assert unvalued == ["2505"]  # Darren Waller — alert fires if this grows


def test_in_season_mode(snapshot, params):
    """One formula, one mode flag: in-season IR leaves the pool; the board stays
    live through week 11."""
    from core.scoring import model as md
    from core.scoring import waivers as wv

    live = dc_replace(
        snapshot, state={**dict(snapshot.state), "season_type": "regular", "week": 3}
    )
    league2 = md.build_league(live, params)
    jt = league2.teams["jaketoppen"]
    assert "George Kittle" not in {p.name for p in jt.pool}  # IR out of the pool
    assert jt.L < 47214.1  # July L counted Kittle/Jones; September must not
    board = wv.waiver_board(league2, league2.teams[league2.me])
    assert board["mode"] == "in-season"
    from core.scoring import trades as tr

    assert tr.trade_board(league2)["disabled"] is False


def test_unvalued_growth_alert(snapshot, params):
    """A second rostered player falling out of KTC coverage fires the alert."""
    from core.scoring import model as md

    kid = next(
        k for k, e in snapshot.crosswalk.items() if e["ktc_name"] == "Tank Dell"
    )
    xw = {k: v for k, v in snapshot.crosswalk.items() if k != kid}
    league2 = md.build_league(dc_replace(snapshot, crosswalk=xw), params)
    assert any("unvalued rostered players grew to 2" in a for a in league2.alerts)


def test_availability_long_out(snapshot, params):
    """OUT with expected return > u_out_short_weeks (or unknown) gets 0.25;
    ≤ 3 weeks gets 0.6; offseason always 1.0. Lineup display only — never ΔW."""
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


def test_dip_note_from_archive(snapshot, params):
    """Display note: −6% vs our trailing-30-day archive tags the waiver row."""
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
