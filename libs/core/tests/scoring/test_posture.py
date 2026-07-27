"""§4 posture classification + §11.4: determinism, evidence, override.

Fixture: data/fixtures/sleeper/transactions_trades.json — both league seasons'
completed trades (33 docs, recorded 2026-07-27). The trailing-12-month window is
anchored at the newest trade in the fixture (2026-05-22), so the labels below are
stable properties of the committed file.
"""

from __future__ import annotations

from dataclasses import replace as dc_replace

from core.scoring import model as md
from core.scoring import posture as ps

DAY_MS = 86_400_000
REF = 1_700_000_000_000  # arbitrary synthetic epoch-ms anchor


def _trade(tid, ts, adds=None, drops=None, picks=None, rosters=(1, 2), **kw):
    return {
        "transaction_id": tid,
        "type": kw.get("type", "trade"),
        "status": kw.get("status", "complete"),
        "status_updated": ts,
        "created": ts - 1000,
        "roster_ids": list(rosters),
        "adds": adds or {},
        "drops": drops or {},
        "draft_picks": picks or [],
    }


def _pick(owner, prev, season="2027", rnd=2):
    return {"season": season, "round": rnd, "roster_id": prev, "owner_id": owner, "previous_owner_id": prev}


# ------------------------------------------------------------- unit-level rule


def test_trade_verdict_shapes():
    t = _trade("t1", REF, adds={"100": 1}, drops={"100": 2}, picks=[_pick(owner=2, prev=1)])
    assert ps.trade_verdict(t, 1) == "bought"  # player in, pick out
    assert ps.trade_verdict(t, 2) == "sold"  # mirror
    # player-for-player: neither shape
    t2 = _trade("t2", REF, adds={"100": 1, "200": 2}, drops={"100": 2, "200": 1})
    assert ps.trade_verdict(t2, 1) is None and ps.trade_verdict(t2, 2) is None
    # pick-for-pick: neither shape
    t3 = _trade("t3", REF, picks=[_pick(owner=1, prev=2), _pick(owner=2, prev=1, season="2028")])
    assert ps.trade_verdict(t3, 1) is None


def test_labels_and_min_trades():
    rid2name = {1: "alpha", 2: "beta"}
    buys = [
        _trade(f"t{i}", REF + i, adds={"100": 1}, drops={"100": 2}, picks=[_pick(owner=2, prev=1)])
        for i in range(3)
    ]
    out = ps.classify_postures(buys, rid2name)
    assert out["alpha"]["label"] == ps.BUYER and out["alpha"]["bought"] == 3
    assert out["beta"]["label"] == ps.SELLER and out["beta"]["sold"] == 3
    # one classifying trade only -> not enough for a label (bought >= 2 required)
    out1 = ps.classify_postures(buys[:2], rid2name)
    assert out1["alpha"]["label"] == ps.BUYER  # 2 buys, 0 sells
    out2 = ps.classify_postures(buys[:1], rid2name)
    assert out2["alpha"]["label"] == ps.NEUTRAL
    assert "inactive" in out2["alpha"]["note"]  # < 2 trades in window


def test_window_excludes_old_trades():
    rid2name = {1: "alpha", 2: "beta"}
    old = _trade("old", REF - 400 * DAY_MS, adds={"1": 1}, drops={"1": 2}, picks=[_pick(owner=2, prev=1)])
    new = [
        _trade(f"n{i}", REF + i, adds={"9": 1}, drops={"9": 2}, picks=[_pick(owner=2, prev=1)])
        for i in range(2)
    ]
    trades = ps.window_trades([old] + new, window_days=365)
    assert [t["transaction_id"] for t in trades] == ["n0", "n1"]
    out = ps.classify_postures([old] + new, rid2name)
    assert out["alpha"]["bought"] == 2  # the 400-day-old buy does not count


def test_incomplete_and_non_trades_ignored():
    rid2name = {1: "alpha", 2: "beta"}
    txs = [
        _trade("w1", REF, type="waiver", adds={"1": 1}),
        _trade("f1", REF, status="failed", adds={"1": 1}, drops={"1": 2}, picks=[_pick(owner=2, prev=1)]),
    ]
    out = ps.classify_postures(txs, rid2name)
    assert out["alpha"]["trades"] == 0 and out["alpha"]["label"] == ps.NEUTRAL


# ------------------------------------------------------ fixture-pinned labels


EXPECTED_LABELS = {
    "cmgaither43": "NEUTRAL",
    "jaketoppen": "NEUTRAL",
    "Jukinski": "NEUTRAL",
    "bengramling": "NEUTRAL",
    "trdouglas": "NEUTRAL",
    "millj": "SELLER",
    "joeydavis299": "NEUTRAL",
    "vishan": "NEUTRAL",
    "josbaski": "NEUTRAL",
    "NoahMoell": "NEUTRAL",
    "DrewR87": "NEUTRAL",
    "ronakpatel32": "BUYER",
}


def test_fixture_labels_deterministic(league):
    assert {n: p["label"] for n, p in league.postures.items()} == EXPECTED_LABELS
    # §11.4/§11.9: identical inputs -> identical output, twice
    rid2name = {t.rid: n for n, t in league.teams.items()}
    a = ps.classify_postures(league.snapshot.transactions, rid2name)
    b = ps.classify_postures(league.snapshot.transactions, rid2name)
    assert a == b
    assert {n: p["label"] for n, p in a.items()} == EXPECTED_LABELS


def test_fixture_evidence_millj_and_ronak(league):
    """The classifying trades ride with the label, human-readable."""
    millj = league.postures["millj"]
    assert (millj["bought"], millj["sold"], millj["trades"]) == (1, 3, 12)
    assert len(millj["evidence"]) == 4
    verdicts = [e["verdict"] for e in millj["evidence"]]
    assert verdicts.count("sold") == 3 and verdicts.count("bought") == 1
    jw_sale = next(e for e in millj["evidence"] if "Jameson Williams" in e["sent"])
    assert jw_sale["verdict"] == "sold"
    assert "2026 R1" in jw_sale["got"]
    ronak = league.postures["ronakpatel32"]
    assert (ronak["bought"], ronak["sold"]) == (3, 0)
    chubb = next(e for e in ronak["evidence"] if "Nick Chubb" in e["got"])
    assert chubb["verdict"] == "bought" and "2027 R4" in chubb["sent"]
    # every evidence entry is human-readable and JSON-plain
    for p in league.postures.values():
        for e in p["evidence"]:
            assert set(e) == {"transaction_id", "date", "verdict", "got", "sent", "summary"}
            assert e["verdict"] in ("bought", "sold")


def test_override_wins(snapshot, params, league):
    """§4/§11.4: the user override replaces the label, keeps the evidence."""
    rid2name = {t.rid: n for n, t in league.teams.items()}
    out = ps.classify_postures(
        snapshot.transactions, rid2name, overrides={"millj": "BUYER", "vishan": "SELLER"}
    )
    assert out["millj"]["label"] == "BUYER"
    assert out["millj"]["source"] == "override"
    assert out["millj"]["computed_label"] == "SELLER"
    assert len(out["millj"]["evidence"]) == 4  # evidence survives the override
    assert out["vishan"]["label"] == "SELLER"
    # unknown override values are ignored
    bad = ps.classify_postures(snapshot.transactions, rid2name, overrides={"millj": "WHALE"})
    assert bad["millj"]["label"] == "SELLER" and bad["millj"]["source"] == "trades"
    # end-to-end: the Snapshot field reaches league.postures
    league2 = md.build_league(
        dc_replace(snapshot, posture_overrides={"millj": "BUYER"}), params
    )
    assert league2.postures["millj"]["label"] == "BUYER"
    assert league2.postures["millj"]["source"] == "override"


def test_no_transactions_alert(snapshot, params):
    league2 = md.build_league(dc_replace(snapshot, transactions=()), params)
    assert all(p["label"] == "NEUTRAL" for p in league2.postures.values())
    assert any("posture defaults NEUTRAL" in a for a in league2.alerts)
