"""§7 league tab — strength map + future assets (current-year picks at their
exact numbered KTC slot, future years at the face tranche) and the market map.
Every cell pinned to the committed fixtures.

v7.4 moved every Picks(mv)/F cell below. The 2026 picks used to be priced at
KTC's generic tranche ("2026 Early 1st" = 6,243 for everyone holding a 1.0x);
`core/scoring/ktc_picks.py` now ports KTC's own client-side generator, so each
current-year pick is priced at its exact numbered slot ("2026 Pick 1.01" =
7,994.86). That is a re-price, not a re-scale: teams holding early slots gained
(DrewR87 41,746 -> 42,001) and teams holding the back of a tranche lost
(NoahMoell 33,933 -> 33,746). L is untouched — no roster player moved."""

from __future__ import annotations

# team: (QB, RB, WR, TE, FLEX, L, rk, Picks(mv), Taxi, F, Frk, posture, FAAB)
EXPECTED_ROWS = {
    "DrewR87":      (6544, 13077, 20327, 3803, 10500, 52418.8, 1, 42001, 4167, 46168, 9, "NEUTRAL", 50),
    "NoahMoell":    (5382, 10311, 19947, 5586, 11812, 51546.0, 2, 33746, 3317, 37063, 11, "NEUTRAL", 50),
    "cmgaither43":  (6181, 12201, 17953, 8376, 8959, 50970.9, 3, 43453, 4472, 47925, 7, "NEUTRAL", 0),
    "joeydavis299": (4048, 10554, 23854, 6648, 8397, 50491.1, 4, 39609, 7750, 47359, 8, "NEUTRAL", 50),
    "bengramling":  (5744, 15434, 13718, 5195, 11741, 49598.8, 5, 41870, 7433, 49303, 5, "NEUTRAL", 50),
    "jaketoppen":   (4038, 15143, 14041, 7615, 9040, 47214.1, 6, 38635, 0, 38635, 10, "NEUTRAL", 0),
    "trdouglas":    (5480, 16718, 12971, 6460, 7213, 46552.0, 7, 53491, 4742, 58233, 1, "NEUTRAL", 50),
    "ronakpatel32": (6256, 8459, 18660, 4313, 9874, 46217.9, 8, 32065, 0, 32065, 12, "BUYER", 45),
    "millj":        (5412, 11661, 16234, 5455, 9299, 45926.6, 9, 42313, 9890, 52203, 3, "SELLER", 0),
    "josbaski":     (4937, 13029, 20508, 3263, 6543, 44975.3, 10, 48365, 7246, 55611, 2, "NEUTRAL", 44),
    "Jukinski":     (5707, 7707, 18712, 3888, 7607, 42140.3, 11, 45853, 4031, 49884, 4, "NEUTRAL", 50),
    "vishan":       (7663, 7648, 14148, 5123, 6712, 40315.7, 12, 46329, 2365, 48694, 6, "NEUTRAL", 50),
}
# The re-price also reordered the F standings around my own team: holding 1.01
# lifted me 47,354 -> 49,303, which is F_rank 7 -> 5, pushing vishan to 6 and
# cmgaither43 (48,183 -> 47,925, a mid/late-tranche holder) from 5 to 7.


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
        # v7.4: 39,921 -> 41,870. Same 11 picks; my four 2026 slots are now
        # priced at their exact numbered KTC values instead of their tranche,
        # and 1.01 alone is worth 7,995 against the 6,243 "Early 1st" it used
        # to carry. round(picks_mv) — the underlying total is 41,869.86,
        # because KTC derives 1.01 off the rookie ladder unrounded.
        "value": 41870,
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
    """Picks by year: the current year at KTC's exact numbered slot price — one
    lens, no annotation — the future years still at the face tranche with the
    my-lens `v_me` beside them.

    v7.4 collapsed the two lenses in the current year. `v` used to be the
    generic tranche and `concrete` the rookie-board proxy that ΔF actually
    booked — 1.01 showed 6,243 with a 7,762 annotation. Both are now the single
    number KTC's calculator publishes for the numbered slot (7,995), so
    `p == mv == p_me`, and `league._pick_detail` only emits a second lens when
    `p_me != mv`. The current-year rows therefore lose BOTH `concrete` and
    `v_me` — asserted below on the key set, so a silently reappearing proxy
    fails here rather than passing as an equal number."""
    d = result["my_team_detail"]
    assert d["team"] == "bengramling"
    y26 = d["picks_by_year"]["2026"]
    assert [(p["label"], p["v"]) for p in y26] == [
        ("2026 1.01", 7995),  # displayed round() of KTC's 7,994.86
        ("2026 2.09", 3560),
        ("2026 3.03", 2804),
        ("2026 4.01", 2205),
    ]
    assert all(not {"concrete", "v_me", "band_me"} & set(p) for p in y26)
    # Future years are untouched: KTC publishes nothing finer than Early/Mid/
    # Late beyond the current draft, so the tranche price and the two-lens
    # split both survive there and these sums are the same as pre-v7.4.
    y27, y28 = d["picks_by_year"]["2027"], d["picks_by_year"]["2028"]
    assert sum(p["v"] for p in y27) == 12293
    assert sum(p["v"] for p in y28) == 13013
    assert all(p["v_me"] > p["v"] for p in y27 + y28)  # own future pick => Early lens
    assert d["unvalued"] == ["Darren Waller"]
    assert "crunch_due" not in d  # v1 concept, deleted


def test_rank_l_feeds_pick_bands(league):
    """The table's rank_L is what the 2027 band projection consumes."""
    assert league.rank_l == {
        "DrewR87": 1, "NoahMoell": 2, "cmgaither43": 3, "joeydavis299": 4,
        "bengramling": 5, "jaketoppen": 6, "trdouglas": 7, "ronakpatel32": 8,
        "millj": 9, "josbaski": 10, "Jukinski": 11, "vishan": 12,
    }
