"""The crosswalk must reproduce data/ktc_sleeper_map.json exactly — that file
is the committed ground truth built from the 2026-07-26 snapshots."""

from core.crosswalk import (
    MANUAL_OVERRIDES,
    TEAM_CODE_MAP_KTC_TO_SLEEPER,
    build_crosswalk,
    normalize_name,
)


def test_reproduces_committed_map_exactly(ktc_raw, players_trimmed, ktc_sleeper_map):
    crosswalk, unresolved = build_crosswalk(ktc_raw["players"], players_trimmed)
    assert unresolved == []
    assert len(crosswalk) == 464
    assert crosswalk == ktc_sleeper_map["crosswalk"]


def test_team_code_map_matches_committed(ktc_sleeper_map):
    assert TEAM_CODE_MAP_KTC_TO_SLEEPER == ktc_sleeper_map["team_code_map_ktc_to_sleeper"]


def test_manual_overrides_match_committed(ktc_sleeper_map):
    assert {str(k): v for k, v in MANUAL_OVERRIDES.items()} == ktc_sleeper_map["manual_overrides"]


def test_match_method_breakdown(ktc_raw, players_trimmed):
    crosswalk, _ = build_crosswalk(ktc_raw["players"], players_trimmed)
    methods = {}
    for entry in crosswalk.values():
        methods[entry["match_method"]] = methods.get(entry["match_method"], 0) + 1
    assert methods == {"unique name+pos": 457, "team tiebreak": 2, "manual_override": 5}


def test_known_hard_cases(ktc_raw, players_trimmed):
    crosswalk, _ = build_crosswalk(ktc_raw["players"], players_trimmed)
    assert crosswalk["365"]["sleeper_id"] == "4984"  # Josh Allen QB, not the LB
    assert crosswalk["1812"]["sleeper_id"] == "12547"  # Kyle Williams via team tiebreak
    assert crosswalk["1570"]["sleeper_id"] == "11573"  # Frank Gore Jr., not retired Frank Gore
    assert crosswalk["1186"]["sleeper_id"] == "8122"  # Bam -> Zonovan Knight (override)


def test_manual_override_target_missing_routes_to_unresolved(ktc_raw, players_trimmed):
    """A vanished override sleeper_id (retirement/rename) must land on the
    unresolved alert list, not raise KeyError."""
    gainwell = dict(MANUAL_OVERRIDES)[1032]
    dump = {pid: rec for pid, rec in players_trimmed.items() if pid != gainwell}
    crosswalk, unresolved = build_crosswalk(ktc_raw["players"], dump)
    assert 1032 in unresolved
    assert "1032" not in crosswalk
    assert len(crosswalk) == 463


def test_normalize_name():
    assert normalize_name("Ja'Marr Chase") == "jamarrchase"
    assert normalize_name("Frank Gore Jr.") == "frankgore"
    assert normalize_name("Amon-Ra St. Brown") == "amonrastbrown"
    assert normalize_name("Chris Brazzell II") == "chrisbrazzell"
    assert normalize_name("Kenneth Walker III") == "kennethwalker"
