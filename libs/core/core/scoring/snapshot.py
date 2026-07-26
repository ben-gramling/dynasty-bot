"""Snapshot: the single immutable input to the scoring engine (§0 data contract)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class Snapshot:
    """Everything the engine reads. Raw API/scrape payload shapes, no I/O here."""

    league: Mapping[str, Any]  # Sleeper league doc
    rosters: Sequence[Mapping[str, Any]]  # Sleeper rosters
    users: Sequence[Mapping[str, Any]]  # Sleeper users
    traded_picks: Sequence[Mapping[str, Any]]  # Sleeper league traded picks
    draft: Mapping[str, Any]  # current-year rookie draft doc
    state: Mapping[str, Any]  # Sleeper NFL state
    ktc_assets: Sequence[Mapping[str, Any]]  # ktc_raw["players"]: 464 players + 36 RDP
    crosswalk: Mapping[str, Mapping[str, Any]]  # ktc playerID -> {sleeper_id, ...}
    my_roster_id: int = 4
    # Optional: names/positions for rostered players absent from KTC (e.g. Darren Waller).
    player_names: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    # Optional: ktc playerID -> trailing-30-day max value from our own archive (§7.6 DIP).
    value_history_max: Mapping[str, float] = field(default_factory=dict)
    # Optional: display_name -> pickflow ∈ {−1, 0, +1} for the ω auto-refresh suggestion.
    pickflow: Mapping[str, int] = field(default_factory=dict)

    @property
    def offseason(self) -> bool:
        return self.state.get("season_type") in ("off", "pre")

    @property
    def week(self) -> int:
        return int(self.state.get("week") or 0)

    @property
    def draft_pre(self) -> bool:
        return self.draft.get("status") != "complete"


def validate_snapshot(snapshot: Snapshot) -> list[str]:
    """§13.9 scrape guards. Returns a list of alert strings (empty = clean)."""
    alerts: list[str] = []
    valued = [
        a
        for a in snapshot.ktc_assets
        if isinstance(a.get("oneQBValues"), dict) and "value" in a["oneQBValues"]
    ]
    if not 480 <= len(valued) <= 520:
        alerts.append(f"ktc asset count {len(valued)} outside guard band 480-520")
    rdp = [a for a in snapshot.ktc_assets if a.get("position") == "RDP"]
    if len(rdp) != 36:
        alerts.append(f"RDP tranche count {len(rdp)} != 36")
    else:
        names = {a["playerName"] for a in rdp}
        want = {
            f"{yr} {band} {rd}"
            for yr in ("2026", "2027", "2028")
            for band in ("Early", "Mid", "Late")
            for rd in ("1st", "2nd", "3rd", "4th")
        }
        if names != want:
            alerts.append(f"RDP tranche set drifted: missing {sorted(want - names)[:4]}")
    known = {str(a["playerID"]) for a in snapshot.ktc_assets if a.get("position") != "RDP"}
    mapped = set(snapshot.crosswalk)
    unmapped = known - mapped
    if unmapped:
        alerts.append(f"{len(unmapped)} ktc playerIDs missing from crosswalk: {sorted(unmapped)[:5]}")
    rookie_board = [
        a
        for a in snapshot.ktc_assets
        if a.get("rookie") and a.get("position") != "RDP" and a["oneQBValues"].get("rookieRank")
    ]
    if not rookie_board:
        alerts.append("rookie board empty (no rookieRank records)")
    for r in snapshot.rosters:
        players = set(r.get("players") or [])
        for grp in ("taxi", "reserve"):
            extra = set(r.get(grp) or []) - players
            if extra:
                alerts.append(f"roster {r['roster_id']}: {grp} not a subset of players: {sorted(extra)}")
    return alerts
