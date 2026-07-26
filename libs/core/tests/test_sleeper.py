"""Sleeper client tests against the recorded fixtures in data/fixtures/sleeper/
via a monkeypatched httpx transport — no live calls ever."""

import httpx
import pytest

from core.sleeper import (
    LEAGUE_ID_2025,
    LEAGUE_ID_2026,
    MY_ROSTER_ID,
    MY_USER_ID,
    SleeperClient,
)
from tests.conftest import FIXTURES, load_json

SLEEPER = FIXTURES / "sleeper"
DRAFT_ID = "1327016687945392128"

ROUTES = {
    f"/v1/league/{LEAGUE_ID_2026}": SLEEPER / "league26.json",
    f"/v1/league/{LEAGUE_ID_2026}/rosters": SLEEPER / "rosters26.json",
    f"/v1/league/{LEAGUE_ID_2026}/users": SLEEPER / "users26.json",
    f"/v1/league/{LEAGUE_ID_2026}/traded_picks": SLEEPER / "traded_picks_26.json",
    f"/v1/draft/{DRAFT_ID}": SLEEPER / "draft26.json",
    f"/v1/draft/{DRAFT_ID}/traded_picks": SLEEPER / "draft26_traded_picks.json",
    "/v1/players/nfl/trending/add": SLEEPER / "trending_add.json",
    "/v1/state/nfl": SLEEPER / "state.json",
    "/v1/players/nfl": SLEEPER / "players_trimmed.json",
}

INLINE = {
    f"/v1/league/{LEAGUE_ID_2026}/drafts": [{"draft_id": DRAFT_ID, "status": "pre_draft"}],
    f"/v1/draft/{DRAFT_ID}/picks": [],
    f"/v1/league/{LEAGUE_ID_2026}/transactions/1": [
        {"transaction_id": "t1", "type": "waiver", "status": "complete"}
    ],
    "/v1/players/nfl/trending/drop": [{"player_id": "1234", "count": 99}],
}


@pytest.fixture
def client():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path in ROUTES:
            return httpx.Response(200, text=ROUTES[path].read_text())
        if path in INLINE:
            return httpx.Response(200, json=INLINE[path])
        return httpx.Response(404, json=None)

    with SleeperClient(transport=httpx.MockTransport(handler)) as c:
        c.requests = requests
        yield c


def test_league(client):
    league = client.league()
    assert league["name"] == "Chicago Dynasty"
    assert league["total_rosters"] == 12
    assert league["settings"]["waiver_budget"] == 50


def test_rosters(client):
    rosters = client.rosters()
    assert len(rosters) == 12
    mine = next(r for r in rosters if r["roster_id"] == MY_ROSTER_ID)
    assert mine["owner_id"] == MY_USER_ID
    assert isinstance(mine["roster_id"], int)


def test_users(client):
    users = client.users()
    assert len(users) == 12
    assert any(u["user_id"] == MY_USER_ID for u in users)


def test_traded_picks(client):
    picks = client.traded_picks()
    assert all({"season", "round", "roster_id", "owner_id"} <= set(p) for p in picks)


def test_drafts_and_draft(client):
    drafts = client.drafts()
    assert drafts[0]["draft_id"] == DRAFT_ID
    draft = client.draft(DRAFT_ID)
    assert draft["draft_id"] == DRAFT_ID
    assert draft["settings"]["rounds"] == 4
    assert client.draft_picks(DRAFT_ID) == []
    assert len(client.draft_traded_picks(DRAFT_ID)) > 0


def test_transactions(client):
    txs = client.transactions(LEAGUE_ID_2026, 1)
    assert txs[0]["transaction_id"] == "t1"


def test_players_nfl(client):
    players = client.players_nfl()
    assert players["4984"]["full_name"] == "Josh Allen"
    assert players["4984"]["position"] == "QB"


def test_trending_params(client):
    add = client.trending("add", lookback_hours=48, limit=50)
    assert add[0]["count"] > 0
    drop = client.trending("drop")
    assert drop == INLINE["/v1/players/nfl/trending/drop"]
    add_req = next(r for r in client.requests if "trending/add" in r.url.path)
    assert add_req.url.params["lookback_hours"] == "48"
    assert add_req.url.params["limit"] == "50"


def test_state(client):
    state = client.state()
    assert state["season"] == "2026"
    assert state["league_season"] == "2026"


def test_bad_league_raises(client):
    with pytest.raises(httpx.HTTPStatusError):
        client.league(LEAGUE_ID_2025)  # not routed -> 404


def test_constants():
    assert LEAGUE_ID_2026 == "1312124603224555520"
    assert LEAGUE_ID_2025 == "1251359014202114048"
    assert MY_USER_ID == "1095425159290331136"
    assert MY_ROSTER_ID == 4
