"""KTC -> Sleeper player join (docs/ktc-sleeper-crosswalk.md).

Auto-join on (normalized name, position) with team then active-status as
tiebreakers only, plus 5 manual name-variant overrides. This is the
load-bearing bridge: KTC carries no Sleeper ID, and neither raw names nor
teams are safe join keys on their own.
"""

import re
from collections import Counter, defaultdict

TEAM_CODE_MAP_KTC_TO_SLEEPER = {
    "GBP": "GB",
    "JAC": "JAX",
    "KCC": "KC",
    "LVR": "LV",
    "NEP": "NE",
    "NOS": "NO",
    "SFO": "SF",
    "TBB": "TB",
    "FA": None,
}

MANUAL_OVERRIDES = {  # ktc playerID -> sleeper player_id (name variants, no auto hit)
    1032: "7567",  # Kenneth Gainwell -> Kenny Gainwell
    1320: "8210",  # Chigoziem Okonkwo -> Chig Okonkwo
    533: "6943",  # Gabriel Davis -> Gabe Davis
    1186: "8122",  # Bam Knight -> Zonovan Knight
    2020: "13324",  # Matthew Hibner -> Matt Hibner
}

SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_PUNCT_RE = re.compile(r"[.'\-,]")


class CrosswalkError(Exception):
    """Join integrity failure (sleeper_id collision)."""


def ktc_team_to_sleeper(team: str) -> str | None:
    return TEAM_CODE_MAP_KTC_TO_SLEEPER.get(team, team)


def normalize_name(name: str) -> str:
    parts = _PUNCT_RE.sub("", name.lower()).split()
    while parts and parts[-1] in _SUFFIXES:
        parts.pop()
    return "".join(parts)


def build_sleeper_index(sleeper_players: dict[str, dict]) -> dict[tuple[str, str], list[dict]]:
    """(normalized full_name, position) -> candidate records, positions taken
    from `position` union `fantasy_positions`, restricted to QB/RB/WR/TE."""
    idx: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for rec in sleeper_players.values():
        if not rec.get("full_name"):
            continue
        name = normalize_name(rec["full_name"])
        positions = set([rec["position"]] if rec.get("position") else [])
        positions |= set(rec.get("fantasy_positions") or [])
        for pos in positions & SKILL_POSITIONS:
            idx[(name, pos)].append(rec)
    return idx


def _pick(cands: list[dict], ktc_rec: dict) -> tuple[dict | None, str]:
    if len(cands) == 1:
        return cands[0], "unique name+pos"
    team = [c for c in cands if c.get("team") == ktc_team_to_sleeper(ktc_rec["team"])]
    if len(team) == 1:
        return team[0], "team tiebreak"
    active = [c for c in cands if c.get("status") == "Active"]
    if len(active) == 1:
        return active[0], "active-status tiebreak"
    return None, "ambiguous"


def build_crosswalk(
    ktc_assets: list[dict], sleeper_players: dict[str, dict]
) -> tuple[dict[str, dict], list[int]]:
    """Join every non-RDP KTC asset to a unique Sleeper player.

    Returns (crosswalk, unresolved_ktc_ids). Unresolved IDs are new-player
    alerts for the caller; sleeper_id collisions raise CrosswalkError.
    """
    idx = build_sleeper_index(sleeper_players)
    crosswalk: dict[str, dict] = {}
    unresolved: list[int] = []

    for kt in ktc_assets:
        if kt["position"] == "RDP":
            continue
        kid = kt["playerID"]
        if kid in MANUAL_OVERRIDES:
            # A vanished override target (retirement/rename) routes to the
            # unresolved alert list like any auto-join miss — never a KeyError.
            chosen, method = sleeper_players.get(MANUAL_OVERRIDES[kid]), "manual_override"
            if chosen is None:
                unresolved.append(kid)
                continue
        else:
            chosen, method = _pick(idx.get((normalize_name(kt["playerName"]), kt["position"]), []), kt)
            if chosen is None:
                unresolved.append(kid)
                continue
        crosswalk[str(kid)] = {
            "sleeper_id": chosen["player_id"],
            "ktc_name": kt["playerName"],
            "sleeper_name": chosen["full_name"],
            "position": kt["position"],
            "ktc_team": kt["team"],
            "sleeper_team": chosen.get("team"),
            "oneqb_value": kt["oneQBValues"]["value"],
            "rookie": kt["rookie"],
            "match_method": method,
        }

    collisions = {s: n for s, n in Counter(e["sleeper_id"] for e in crosswalk.values()).items() if n > 1}
    if collisions:
        raise CrosswalkError(f"sleeper_id collisions: {collisions}")
    return crosswalk, unresolved
