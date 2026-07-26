"""Typed read-only client for the Sleeper API (docs/sleeper-api.md)."""

from typing import Any, Literal

import httpx

BASE_URL = "https://api.sleeper.app/v1"

LEAGUE_ID_2026 = "1312124603224555520"
LEAGUE_ID_2025 = "1251359014202114048"
MY_USER_ID = "1095425159290331136"
MY_ROSTER_ID = 4

Json = dict[str, Any]


class SleeperClient:
    """Thin httpx wrapper; pass a transport to mock in tests (never hit live APIs)."""

    def __init__(self, *, timeout: float = 30.0, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(base_url=BASE_URL, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "SleeperClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = self._http.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def league(self, league_id: str = LEAGUE_ID_2026) -> Json:
        return self._get(f"/league/{league_id}")

    def rosters(self, league_id: str = LEAGUE_ID_2026) -> list[Json]:
        return self._get(f"/league/{league_id}/rosters")

    def users(self, league_id: str = LEAGUE_ID_2026) -> list[Json]:
        return self._get(f"/league/{league_id}/users")

    def traded_picks(self, league_id: str = LEAGUE_ID_2026) -> list[Json]:
        return self._get(f"/league/{league_id}/traded_picks")

    def drafts(self, league_id: str = LEAGUE_ID_2026) -> list[Json]:
        return self._get(f"/league/{league_id}/drafts")

    def draft(self, draft_id: str) -> Json:
        return self._get(f"/draft/{draft_id}")

    def draft_picks(self, draft_id: str) -> list[Json]:
        return self._get(f"/draft/{draft_id}/picks")

    def draft_traded_picks(self, draft_id: str) -> list[Json]:
        return self._get(f"/draft/{draft_id}/traded_picks")

    def transactions(self, league_id: str, week: int) -> list[Json]:
        """All offseason activity lands in week ("round") 1."""
        return self._get(f"/league/{league_id}/transactions/{week}")

    def players_nfl(self) -> dict[str, Json]:
        """Full ~15MB dump keyed by player_id. Call at most once per day."""
        return self._get("/players/nfl")

    def trending(
        self,
        kind: Literal["add", "drop"],
        *,
        lookback_hours: int = 24,
        limit: int = 25,
    ) -> list[Json]:
        return self._get(
            f"/players/nfl/trending/{kind}",
            params={"lookback_hours": lookback_hours, "limit": limit},
        )

    def state(self) -> Json:
        return self._get("/state/nfl")
