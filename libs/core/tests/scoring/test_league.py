"""§7 league tab — strength map + future assets (current-year picks at their
exact numbered KTC slot, future years at the pessimistic tranche) and the
market map. Every cell pinned to the committed fixtures.

v7.5 moved every future-pick cell below: the rank_L market band retired, so a
future pick prices Early when I own it and Late when anyone else does — the
league tab included. The F column is therefore MY seat's read of every
inventory, not a neutral market survey: my own picks re-priced Mid→Early
(41,870 → 44,689) while every other team's future picks dropped to Late,
which is why my F_rank jumps to 2 — the asymmetry is the point, not noise.
(v7.4 previously moved the 2026 cells from the generic tranche to KTC's exact
numbered slots.) L is untouched — no roster player moved."""

from __future__ import annotations

# team: (QB, RB, WR, TE, FLEX, L, rk, Picks(mv), Taxi, F, Frk, posture, FAAB)
EXPECTED_ROWS = {
    "DrewR87":      (6544, 13077, 20327, 3803, 10500, 52418.8, 1, 40759, 4167, 44926, 8, "NEUTRAL", 50),
    "NoahMoell":    (5382, 10311, 19947, 5586, 11812, 51546.0, 2, 32679, 3317, 35996, 10, "NEUTRAL", 50),
    "cmgaither43":  (6181, 12201, 17953, 8376, 8959, 50970.9, 3, 42102, 4472, 46574, 5, "NEUTRAL", 0),
    "joeydavis299": (4048, 10554, 23854, 6648, 8397, 50491.1, 4, 38542, 7750, 46292, 6, "NEUTRAL", 50),
    "bengramling":  (5744, 15434, 13718, 5195, 11741, 49598.8, 5, 44689, 7433, 52122, 2, "NEUTRAL", 50),
    "jaketoppen":   (4038, 15143, 14041, 7615, 9040, 47214.1, 6, 34394, 0, 34394, 11, "NEUTRAL", 0),
    "trdouglas":    (5480, 16718, 12971, 6460, 7213, 46552.0, 7, 51580, 4742, 56322, 1, "NEUTRAL", 50),
    "ronakpatel32": (6256, 8459, 18660, 4313, 9874, 46217.9, 8, 29983, 0, 29983, 12, "BUYER", 45),
    "millj":        (5412, 11661, 16234, 5455, 9299, 45926.6, 9, 40329, 9890, 50219, 4, "SELLER", 0),
    "josbaski":     (4937, 13029, 20508, 3263, 6543, 44975.3, 10, 43945, 7246, 51191, 3, "NEUTRAL", 44),
    "Jukinski":     (5707, 7707, 18712, 3888, 7607, 42140.3, 11, 41717, 4031, 45748, 7, "NEUTRAL", 50),
    "vishan":       (7663, 7648, 14148, 5123, 6712, 40315.7, 12, 42258, 2365, 44623, 9, "NEUTRAL", 50),
}


def test_full_league_table(result):
    table = result["league_table"]
    assert table["L_mean"] == 47363.9
    assert table["L_sigma"] == 3623.5
    rows = {r["team"]: r for r in table["rows"]}
    assert len(rows) == 12
    for name, (qb, rb, wr, te, flex, l, rk, picks, taxi, f, frk, posture, faab) in EXPECTED_ROWS.items():
        r = rows[name]
        lu = r["lineup"]
        assert (lu["QB"]["sum"], lu["RB"]["sum"], lu["WR"]["sum"], lu["TE"]["sum"], lu["FLEX"]["sum"]) == (
            qb, rb, wr, te, flex,
        ), name
        assert r["L"] == l and r["L_rank"] == rk, name
        assert r["future"]["picks"] == picks and r["future"]["taxi"] == taxi, name
        assert r["future"]["F"] == f and r["future"]["F_rank"] == frk, name
        assert r["market"]["posture"] == posture, name
        assert r["market"]["faab"] == faab, name
        # v3: the ω/cuts/crunch columns are gone from the market block
        assert not {"cuts", "C", "cut_list", "omega"} & set(r["market"]), name
        assert "omega" not in r and "omega_suggest" not in r, name
    # rows are ordered by L rank
    assert [r["team"] for r in table["rows"]] == sorted(EXPECTED_ROWS, key=lambda n: EXPECTED_ROWS[n][6])


def test_market_map_contents(result):
    """§7: posture + evidence, positional holes, pick inventory, FAAB — the
    targeting console."""
    rows = {r["team"]: r for r in result["league_table"]["rows"]}
    millj = rows["millj"]["market"]
    assert millj["posture"] == "SELLER" and millj["posture_source"] == "trades"
    assert (millj["bought"], millj["sold"], millj["trades_12mo"]) == (1, 3, 12)
    assert len(millj["evidence"]) == 4
    assert all("summary" in e for e in millj["evidence"])
    me = rows["bengramling"]["market"]
    assert me["holes"] == [{"pos": "WR", "rank": 11}]  # my thinnest room
    assert me["pick_inventory"] == {
        "count": 11,
        "by_year": {"2026": 4, "2027": 3, "2028": 4},
        # v7.5: 41,870 -> 44,689. Same 11 picks; my seven future picks now
        # price at the Early tranche (mine ⇒ I would send ⇒ dear end), the
        # rank_L Mid projection retired. round(picks_mv) — the underlying total
        # is 44,688.86, because KTC derives 1.01 off the rookie ladder
        # unrounded (v7.4).
        "value": 44689,
    }
    for r in rows.values():
        m = r["market"]
        for h in m["holes"]:
            assert h["rank"] >= 9  # holes = bottom-third rooms only


def test_my_row_z_score(result):
    me_row = next(r for r in result["league_table"]["rows"] if r["team"] == "bengramling")
    assert me_row["L_z"] == 0.62  # L 49,598.8 (5th)


def test_cells_expand_to_players(result):
    """§7: clicking any cell lists the players/picks behind it."""
    rows = {r["team"]: r for r in result["league_table"]["rows"]}
    me = rows["bengramling"]
    assert [p["player"] for p in me["lineup"]["RB"]["players"]] == ["Ashton Jeanty", "Omarion Hampton"]
    assert {p["player"] for p in me["future"]["taxi_detail"]} == {"Cam Ward", "Elijah Arroyo"}
    labels = {d["label"] for d in me["future"]["picks_detail"]}
    assert "2026 1.01" in labels and "2027 R1 (own)" in labels
    jt = rows["jaketoppen"]
    assert jt["future"]["taxi_detail"] == []
    assert "George Kittle" in {p["player"] for p in jt["lineup"]["TE"]["players"]} or (
        "George Kittle" in {p["player"] for p in jt["lineup"]["FLEX"]["players"]}
    )  # IR players count in the July lineup


def test_my_team_detail(result):
    """Picks by year, ONE price each (v7.5): the current year at KTC's exact
    numbered slot price, future years at the pessimistic tranche (mine ⇒ Early).

    v7.4 collapsed the two lenses in the current year — `v` used to be the
    generic tranche and `concrete` the rookie-board proxy that ΔF actually
    booked (1.01 showed 6,243 with a 7,762 annotation); both became the single
    number KTC publishes for the numbered slot (7,995). v7.5 collapsed the
    future years the same way: the rank_L market band retired, `p == mv ==
    p_me` everywhere, and `league._pick_detail` only emits a second lens when
    `p_me != mv` — never, now. Asserted on the key set, so a silently
    reappearing proxy or forecast fails here rather than passing as an equal
    number."""
    d = result["my_team_detail"]
    assert d["team"] == "bengramling"
    y26 = d["picks_by_year"]["2026"]
    assert [(p["label"], p["v"]) for p in y26] == [
        ("2026 1.01", 7995),  # displayed round() of KTC's 7,994.86
        ("2026 2.09", 3560),
        ("2026 3.03", 2804),
        ("2026 4.01", 2205),
    ]
    y27, y28 = d["picks_by_year"]["2027"], d["picks_by_year"]["2028"]
    assert all(
        not {"concrete", "v_me", "band_me"} & set(p) for p in y26 + y27 + y28
    )
    # my future picks at the Early tranche — dear, because I would be sending
    assert sum(p["v"] for p in y27) == 14085
    assert sum(p["v"] for p in y28) == 14040
    assert all(p["band"] == "Early" for p in y27 + y28)
    assert d["unvalued"] == ["Darren Waller"]
    assert "crunch_due" not in d  # v1 concept, deleted


def test_rank_l_is_standings_only(league):
    """The table's rank_L survives for standings/display; v7.5 retired it from
    pick pricing (see test_picks.test_rank_l_no_longer_prices_any_pick)."""
    assert league.rank_l == {
        "DrewR87": 1, "NoahMoell": 2, "cmgaither43": 3, "joeydavis299": 4,
        "bengramling": 5, "jaketoppen": 6, "trdouglas": 7, "ronakpatel32": 8,
        "millj": 9, "josbaski": 10, "Jukinski": 11, "vishan": 12,
    }
