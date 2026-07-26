"""§8 league tab — every cell of the published table — and §11.3 my-team detail."""

from __future__ import annotations

from .conftest import by_name

# team: (QB, RB, WR, TE, FLEX, L, rk, omega, Picks, Taxi, F, Frk, cuts, C, FAAB)
EXPECTED_ROWS = {
    "DrewR87":      (6544, 13077, 20327, 3803, 10500, 52418.8, 1, 0.60, 40931, 4167, 45098, 9, 3, 2900, 50),
    "NoahMoell":    (5382, 10311, 19947, 5586, 11812, 51546.0, 2, 0.65, 31878, 3317, 35195, 11, 3, 2764, 50),
    "cmgaither43":  (6181, 12201, 17953, 8376, 8959, 50970.9, 3, 0.60, 42730, 4472, 47202, 7, 3, 2138, 0),
    "joeydavis299": (4048, 10554, 23854, 6648, 8397, 50491.1, 4, 0.60, 38034, 7750, 45784, 8, 4, 3953, 50),
    "bengramling":  (5744, 15434, 13718, 5195, 11741, 49598.8, 5, 0.60, 41153, 7433, 48586, 4, 3, 1401, 50),
    "jaketoppen":   (4038, 15143, 14041, 7615, 9040, 47214.1, 6, 0.70, 38165, 0, 38165, 10, 0, 0, 0),
    "trdouglas":    (5480, 16718, 12971, 6460, 7213, 46552.0, 7, 0.50, 51072, 4742, 55814, 1, 6, 6379, 50),
    "ronakpatel32": (6256, 8459, 18660, 4313, 9874, 46217.9, 8, 0.35, 31242, 0, 31242, 12, 0, 0, 45),
    "millj":        (5412, 11661, 16234, 5455, 9299, 45926.6, 9, 0.55, 41181, 9890, 51071, 3, 6, 6571, 0),
    "josbaski":     (4937, 13029, 20508, 3263, 6543, 44975.3, 10, 0.40, 47522, 7246, 54768, 2, 2, 1034, 44),
    "Jukinski":     (5707, 7707, 18712, 3888, 7607, 42140.3, 11, 0.35, 44453, 4031, 48484, 5, 4, 5073, 50),
    "vishan":       (7663, 7648, 14148, 5123, 6712, 40315.7, 12, 0.25, 45290, 2365, 47655, 6, 2, 3560, 50),
}


def test_full_league_table(result):
    table = result["league_table"]
    assert table["L_mean"] == 47363.9
    assert table["L_sigma"] == 3623.5
    rows = {r["team"]: r for r in table["rows"]}
    assert len(rows) == 12
    for name, (qb, rb, wr, te, flex, l, rk, om, picks, taxi, f, frk, cuts, c, faab) in EXPECTED_ROWS.items():
        r = rows[name]
        lu = r["lineup"]
        assert (lu["QB"]["sum"], lu["RB"]["sum"], lu["WR"]["sum"], lu["TE"]["sum"], lu["FLEX"]["sum"]) == (
            qb, rb, wr, te, flex,
        ), name
        assert r["L"] == l and r["L_rank"] == rk, name
        assert r["omega"] == om, name
        assert r["future"]["picks"] == picks and r["future"]["taxi"] == taxi, name
        assert r["future"]["F"] == f and r["future"]["F_rank"] == frk, name
        assert r["market"]["cuts"] == cuts and round(r["market"]["C"]) == c, name
        assert r["market"]["faab"] == faab, name
    # rows are ordered by L rank
    assert [r["team"] for r in table["rows"]] == sorted(EXPECTED_ROWS, key=lambda n: EXPECTED_ROWS[n][6])


def test_my_row_z_score(result):
    me_row = next(r for r in result["league_table"]["rows"] if r["team"] == "bengramling")
    assert me_row["L_z"] == 0.62  # §11.3: L 49,598.8 (5th, z +0.62)


def test_cells_expand_to_players(result):
    """§8: clicking any cell lists the players/picks behind it."""
    rows = {r["team"]: r for r in result["league_table"]["rows"]}
    me = rows["bengramling"]
    assert [p["player"] for p in me["lineup"]["RB"]["players"]] == ["Ashton Jeanty", "Omarion Hampton"]
    assert {p["player"] for p in me["future"]["taxi_detail"]} == {"Cam Ward", "Elijah Arroyo"}
    labels = {d["label"] for d in me["future"]["picks_detail"]}
    assert "2026 1.01" in labels and "2027 R1 (own)" in labels
    jt = rows["jaketoppen"]
    assert jt["future"]["taxi_detail"] == []
    assert "George Kittle" in {p["player"] for grp in ("TE",) for p in jt["lineup"][grp]["players"]} or (
        "George Kittle" in {p["player"] for p in jt["lineup"]["FLEX"]["players"]}
    )  # §8: IR fix — Kittle counts in the July lineup


def test_my_team_detail(result):
    """§11.3 block: picks by year, crunch line, FAAB."""
    d = result["my_team_detail"]
    assert d["team"] == "bengramling"
    assert d["market"] == {
        "cuts": 3,
        "C": 1400.9,
        "cut_list": ["Darren Waller", "Joe Flacco", "Stefon Diggs"],
        "faab": 50,
    }
    y26 = d["picks_by_year"]["2026"]
    assert [(p["label"], p["p"]) for p in y26] == [
        ("2026 1.01", 7762), ("2026 2.09", 3236), ("2026 3.03", 2927), ("2026 4.01", 1922),
    ]
    assert sum(p["p"] for p in d["picks_by_year"]["2027"]) == 12293
    assert sum(p["p"] for p in d["picks_by_year"]["2028"]) == 13013
    assert d["crunch_due"] == "rookie draft"


def test_rank_l_feeds_pick_bands(league):
    """§8: the table's rank_L is what §3.2 band projection consumes."""
    assert league.rank_l == {
        "DrewR87": 1, "NoahMoell": 2, "cmgaither43": 3, "joeydavis299": 4,
        "bengramling": 5, "jaketoppen": 6, "trdouglas": 7, "ronakpatel32": 8,
        "millj": 9, "josbaski": 10, "Jukinski": 11, "vishan": 12,
    }
