"""Unit tests for core.store's pure document builders. The Mongo-touching
writers are deliberately not stubbed here (no mongomock); they are covered by
the integration stage's seed run against the real dynasty-bot database."""

from datetime import datetime, timezone

from core import store


def test_trim_player_keeps_only_subset_fields():
    rec = {
        "player_id": "4984",
        "full_name": "Josh Allen",
        "position": "QB",
        "fantasy_positions": ["QB"],
        "team": "BUF",
        "status": "Active",
        "espn_id": 3918298,  # dropped
        "hashtag": "#JoshAllen-NFL-BUF-17",  # dropped
    }
    trimmed = store.trim_player(rec)
    assert trimmed["full_name"] == "Josh Allen"
    assert "espn_id" not in trimmed
    assert "hashtag" not in trimmed
    assert set(trimmed) <= set(store.PLAYER_FIELDS)


def test_player_subset_filters_to_named_skill_players(players_trimmed):
    dump = {
        "4984": {"player_id": "4984", "full_name": "Josh Allen", "position": "QB"},
        "9509": {"player_id": "9509", "full_name": "Kicker Guy", "position": "K"},
        "CHI": {"player_id": "CHI", "position": "DEF"},  # team DEF, no full_name
        "111": {"player_id": "111", "position": "RB"},  # no full_name
        "222": {
            "player_id": "222",
            "full_name": "Taysom Hill",
            "position": "TE",
            "fantasy_positions": ["TE", "QB"],
        },
    }
    subset = store.player_subset(dump)
    assert set(subset) == {"4984", "222"}
    # the committed trimmed fixture is exactly a player_subset of the full dump
    assert store.player_subset(players_trimmed) == players_trimmed


def test_pick_id():
    assert store.pick_id({"season": "2026", "round": 1, "roster_id": 7}) == "2026-1-7"


def test_ktc_history_rows(ktc_raw):
    rows = store.ktc_history_rows(ktc_raw["players"][:2], "2026-07-26")
    josh = rows[0]
    assert josh == {
        "_id": "365:2026-07-26",
        "playerID": 365,
        "date": "2026-07-26",
        "value_1qb": 7663,
        "value_sf": 9999,
        "rank_1qb": 11,
    }
    assert len(rows) == 2


def test_scoring_docs_one_singleton_per_tab_collection():
    outputs = {
        "meta": {"mode": "offseason", "alerts": []},
        "waiver_board": {"targets": [{"player": "X"}], "mode": "offseason"},
        "league_table": {"rows": [{"team": "me"}], "L_mean": 0.0},
        "my_team_detail": {"team": "me", "L_rank": 1},
    }
    when = datetime(2026, 7, 26, tzinfo=timezone.utc)
    docs = store.scoring_docs(outputs, when)
    # v7.1: two collections, not three — no `trade-recs` document is written
    assert set(docs) == {"waiver-board", "league-table"}
    for doc in docs.values():
        assert doc["_id"] == "latest"
        assert doc["computed_at"] == when
        assert doc["meta"] == outputs["meta"]
    assert docs["waiver-board"]["targets"] == [{"player": "X"}]
    assert docs["league-table"]["rows"] == [{"team": "me"}]
    assert docs["league-table"]["my_team"]["L_rank"] == 1
