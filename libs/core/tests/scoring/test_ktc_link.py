"""KTC trade-calculator deep links.

Pinned against the committed 2026-07-26 snapshot. A link that resolves to the WRONG
asset is worse than no link — the user pastes these to real league-mates — so the
load-bearing test here is `test_every_rostered_asset_round_trips`, which walks EVERY
tradeable asset in the league and asserts the resolved id maps back to the right KTC
record. Its counts are exact and split by kind on purpose: a single loose `>=`
threshold would pass even if every pick were skipped, which is precisely the
population where tranche mis-mapping lives.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.scoring import ktc_link as kl
from core.scoring import ktc_picks as kp
from core.scoring import trades as tr

REPO = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="session")
def ids(league):
    return kl.rdp_ids(league)


@pytest.fixture(scope="session")
def names(league):
    return kl.ktc_names(league)


@pytest.fixture(scope="session")
def ktc_raw():
    with open(REPO / "data" / "ktc_raw.json") as fh:
        return json.load(fh)


# ----------------------------------------------------------------- tranche table


def test_rdp_table_is_complete(ids):
    """3 years x 3 bands x 4 rounds, derived from the snapshot, never hardcoded."""
    assert len(ids) == 36
    for year in (2026, 2027, 2028):
        for band in ("Early", "Mid", "Late"):
            for rnd in (1, 2, 3, 4):
                assert (year, band, rnd) in ids


def test_pinned_tranche_ids(ids):
    """The ids the desk actually emits, verified against ktc_raw playerNames."""
    assert ids[(2026, "Early", 1)] == 1527
    assert ids[(2026, "Mid", 1)] == 1528
    assert ids[(2026, "Late", 1)] == 1529
    assert ids[(2027, "Early", 1)] == 1702
    assert ids[(2027, "Mid", 1)] == 1703
    assert ids[(2027, "Late", 1)] == 1704
    assert ids[(2028, "Early", 1)] == 1882
    assert ids[(2028, "Mid", 1)] == 1883
    assert ids[(2027, "Early", 4)] == 1711
    assert ids[(2027, "Mid", 4)] == 1712


def test_every_tranche_id_names_its_own_key(ids, names):
    """(year, band, round) -> id -> playerName must reconstruct the key exactly."""
    word = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
    for (year, band, rnd), kid in ids.items():
        assert names[kid] == f"{year} {band} {word[rnd]}"


def test_rdp_ids_ignores_malformed_names(league, monkeypatch):
    """A rolled-forward / renamed RDP record must degrade one pick, not crash."""
    bad = [
        {"position": "RDP", "playerName": "2026 Early 1st", "playerID": 1527},
        {"position": "RDP", "playerName": "2029 Rookie Pick Round One", "playerID": 999},
        {"position": "RDP", "playerName": "malformed", "playerID": 998},
        {"position": "WR", "playerName": "Chris Godwin", "playerID": 299},
    ]

    class FakeSnap:
        ktc_assets = bad

    class FakeLeague:
        snapshot = FakeSnap()

    got = kl.rdp_ids(FakeLeague())
    assert got == {(2026, "Early", 1): 1527}


# ------------------------------------------------------------- the real S1 trade


def _asset(league, team_name, asset_name):
    t = league.teams[team_name]
    return tr.team_assets(league, t)[asset_name]


def test_s1_trade_resolves_exactly(league, ids, names):
    """The trade the desk actually recommended. Every id verified by name."""
    give = [
        _asset(league, league.me, "Chris Godwin"),
        _asset(league, league.me, "2026 1.01"),
        _asset(league, league.me, "2027 R1 (own)"),
    ]
    get = [
        _asset(league, "NoahMoell", "Luther Burden"),
        _asset(league, "NoahMoell", "Rashee Rice"),
        _asset(league, "NoahMoell", "2028 R1 (own)"),
    ]
    link = kl.tc_link(give, get, ids, current_year=league.current_year)

    assert link.complete
    assert link.dropped == ()
    # v7.4: the 2026 1.01 links at KTC's NUMBERED id, because that is the price
    # the gate now uses. A future pick still links its tranche — that IS its
    # price, KTC publishes nothing finer.
    assert link.one == (299, 202611, 1703)
    assert link.two == (1770, 1447, 1883)
    assert names[link.one[0]] == "Chris Godwin"
    assert link.one[1] == kp.numbered_pick_id(2026, 1, 1)  # "2026 Pick 1.01"
    assert names[link.one[2]] == "2027 Mid 1st"
    assert [names[i] for i in link.two] == [
        "Luther Burden", "Rashee Rice", "2028 Mid 1st",
    ]
    assert link.url == (
        "https://keeptradecut.com/trade-calculator"
        "?var=5&pickVal=0&teamOne=299%7C202611%7C1703&teamTwo=1770%7C1447%7C1883"
        "&format=1&isStartup=0&tep=0"
    )


def test_link_side_totals_match_the_gate(league, ids, names):
    """teamOne must be the side the gate calls `give` — otherwise the page shows
    the trade backwards and `favor` reads with the wrong sign."""
    give = [
        _asset(league, league.me, "Chris Godwin"),
        _asset(league, league.me, "2026 1.01"),
        _asset(league, league.me, "2027 R1 (own)"),
    ]
    get = [
        _asset(league, "NoahMoell", "Luther Burden"),
        _asset(league, "NoahMoell", "Rashee Rice"),
        _asset(league, "NoahMoell", "2028 R1 (own)"),
    ]
    link = kl.tc_link(give, get, ids, current_year=league.current_year)

    # v7.4: the page's own value for every linked id — scraped records for
    # players and future picks, KTC's generated table for the numbered ones.
    # This is the assertion that actually matters: it says the number on the
    # counterparty's screen is the number our gate priced, id for id.
    by_id = {int(a["playerID"]): float(a["oneQBValues"]["value"])
             for a in league.snapshot.ktc_assets}
    for (rnd, slot), v in kp.numbered_pick_values(
        league.snapshot.ktc_assets, draft_year=league.current_year, phase=2,
        site_draft_year=league.current_year,
    ).items():
        by_id[kp.numbered_pick_id(league.current_year, rnd, slot)] = v
    one_sum = sum(by_id[i] for i in link.one)
    two_sum = sum(by_id[i] for i in link.two)

    # raw (pre-adjustment) sums, as multisets of the engine's own face values
    assert one_sum == pytest.approx(sum(a.v for a in give))
    assert two_sum == pytest.approx(sum(a.v for a in get))
    # v7.4 FLIPPED this leg's direction, which is the change in one number: the
    # 1.01 went 6,243 (a generic "Early 1st") to 7,994.86 (KTC's own price for
    # that exact slot), so we are now sending MORE raw face than we receive on a
    # trade the old pricing read the other way round.
    assert one_sum > two_sum
    assert one_sum - two_sum == pytest.approx(737.86, abs=0.01)


# --------------------------------------------------------- league-wide round trip


def test_every_rostered_asset_round_trips(league, ids, names):
    """EVERY tradeable asset in all 12 teams resolves to a KTC record of the right
    identity. Counts asserted exactly and split by kind — see module docstring."""
    by_id = {int(a["playerID"]): a for a in league.snapshot.ktc_assets}
    numbered = {
        kp.numbered_pick_id(league.current_year, rnd, slot): (rnd, slot, v)
        for (rnd, slot), v in kp.numbered_pick_values(
            league.snapshot.ktc_assets, draft_year=league.current_year, phase=2,
            site_draft_year=league.current_year,
        ).items()
    }
    word = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}

    players = picks = unresolved = 0
    for team in league.teams.values():
        for asset in tr.team_assets(league, team).values():
            kid = kl.ktc_id_of(asset, ids)
            if kid is None:
                assert asset.unvalued, f"{asset.name} unresolved but not unvalued"
                unresolved += 1
                continue
            if kid in numbered:  # v7.4 current-year pick: KTC's generated entry
                picks += 1
                rnd, slot, v = numbered[kid]
                assert asset.name == f"{league.current_year} {rnd}.{slot:02d}"
                assert float(v) == pytest.approx(asset.v)
                continue
            rec = by_id[kid]
            if asset.kind == "player":
                players += 1
                assert rec["playerName"] == asset.name
                assert float(rec["oneQBValues"]["value"]) == pytest.approx(asset.v)
            else:
                picks += 1
                p = asset.pick
                assert rec["position"] == "RDP"
                assert rec["playerName"] == f"{p.year} {p.band} {word[p.round]}"
                # the linked tranche must be the value the gate priced (Pick.mv)
                assert float(rec["oneQBValues"]["value"]) == pytest.approx(asset.v)

    assert players == 247
    assert picks == 144
    assert unresolved == 1  # Darren Waller, the sole unvalued rostered asset
    assert players + picks + unresolved == 392


# --------------------------------------------------------------------- edge cases


def test_band_follows_origin_not_holder(league, ids):
    """millj holds three 2027 R4s; they do NOT all share an id. Keying on
    (year, round) alone — ignoring the origin team's band — would break this."""
    assets = tr.team_assets(league, league.teams["millj"])
    trio = {n: a for n, a in assets.items() if n.startswith("2027 R4")}
    assert len(trio) == 3, sorted(trio)

    resolved = {n: kl.ktc_id_of(a, ids) for n, a in trio.items()}
    assert resolved["2027 R4 (own)"] == 1711
    assert resolved["2027 R4 (from vishan)"] == 1711
    assert resolved["2027 R4 (from ronakpatel32)"] == 1712
    assert len(set(resolved.values())) == 2


def test_unvalued_player_is_dropped_and_disclosed(league, ids):
    waller = _asset(league, league.me, "Darren Waller")
    assert waller.unvalued
    assert kl.ktc_id_of(waller, ids) is None

    give = [_asset(league, league.me, "Chris Godwin"), waller]
    get = [_asset(league, "NoahMoell", "Rashee Rice")]
    link = kl.tc_link(give, get, ids, current_year=league.current_year)

    assert link.complete
    assert link.dropped == ("Darren Waller",)
    assert str(kl.NO_KTC_ID) not in (link.url or "")
    # pairs is one entry per INPUT asset so a renderer can zip it safely
    assert link.pairs == (
        ("Chris Godwin", 299),
        ("Darren Waller", None),
        ("Rashee Rice", 1447),
    )


def test_side_emptied_by_drops_yields_no_url(league, ids):
    """KTC reads `teamOne=` as absent and would render a pure giveaway."""
    give = [_asset(league, league.me, "Darren Waller")]
    get = [_asset(league, "NoahMoell", "Rashee Rice")]
    link = kl.tc_link(give, get, ids, current_year=league.current_year)

    assert not link.complete
    assert link.url is None
    assert link.numbered_url is None
    assert link.dropped == ("Darren Waller",)


def test_two_picks_in_one_tranche_are_two_entries(league, ids):
    """Two entries, never deduped. v7.4 makes the current-year case stronger:
    1.07 and 1.08 used to collapse to the same tranche id (1528, "2026 Mid 1st")
    and now carry their own distinct numbered ids and their own distinct
    prices — which is the whole point of the change."""
    assets = tr.team_assets(league, league.teams["trdouglas"])
    a, b = assets["2026 1.07"], assets["2026 1.08"]
    assert a.pick.band == b.pick.band == "Mid"  # same tranche, different picks
    assert a.v != b.v
    link = kl.tc_link([a, b], [_asset(league, "NoahMoell", "Rashee Rice")], ids)
    assert link.one == (202617, 202618)

    # a FUTURE pair in one tranche still collapses — KTC publishes nothing finer
    fut = [p for p in league.teams["millj"].picks if p.year == 2027 and p.round == 4]
    assert len(fut) >= 2
    ids_fut = {kl.ktc_id_of(tr.pick_asset(league, p), ids) for p in fut}
    assert len(ids_fut) < len(fut)


def test_asset_cap_is_counted_on_inputs_and_ids(league, ids):
    """KTC holds 12 across both sides. A 13th asset must raise even if one asset
    drops out for an unrelated reason (which would leave only 12 ids)."""
    waller = _asset(league, league.me, "Darren Waller")
    mine = [
        a
        for a in tr.team_assets(league, league.teams[league.me]).values()
        if not a.unvalued
    ]
    assert len(mine) >= 13
    with pytest.raises(ValueError, match="12 assets"):
        kl.tc_link(mine[:13], [], ids)

    # 13 inputs but only 12 resolvable ids: must still raise on the input count
    give13 = mine[:12] + [waller]
    assert len(kl.tc_link(mine[:12], [], ids).one) == 12
    with pytest.raises(ValueError, match="12 assets"):
        kl.tc_link(give13, [], ids)


# ------------------------------------------------- numbered-pick gap disclosure


def test_numbered_pick_id_encoding():
    assert kl.numbered_pick_id(2026, 1, 1) == 202611
    assert kl.numbered_pick_id(2026, 1, 12) == 2026112
    assert kl.numbered_pick_id(2026, 4, 3) == 202643


def test_there_is_nothing_left_to_disclose(league, ids):
    """Through v7.3 a current-year pick was linked at its tranche while KTC also
    carried a numbered entry at a different price, so the link shipped a
    `numbered_url` alternative and a note. v7.4 prices the numbered entry, links
    it, and the gap closes: one price, one link, no disclosure."""
    give = [_asset(league, league.me, "2026 1.01")]
    get = [_asset(league, "NoahMoell", "Rashee Rice")]
    link = kl.tc_link(give, get, ids, current_year=league.current_year)

    assert link.numbered == () and link.numbered_url is None
    assert "202611" in (link.url or "")  # the numbered id IS the primary link
    assert "1527" not in (link.url or "")  # the tranche is gone from the trade


def test_tranche_only_picks_have_no_numbered_entry(league, ids):
    """Future-year picks have no slot, so no numbered KTC entry exists."""
    give = [_asset(league, league.me, "2027 R1 (own)")]
    get = [_asset(league, "NoahMoell", "Rashee Rice")]
    link = kl.tc_link(give, get, ids, current_year=league.current_year)
    assert link.numbered == ()
    assert link.numbered_url is None


def test_fixed_params_match_the_gate_assumptions():
    """format=1 is load-bearing: without it KTC falls back to its Superflex
    cookie and every value on the page is the wrong column."""
    fixed = dict(kl.TC_PARAMS)
    assert fixed["format"] == "1"
    assert fixed["var"] == "5"
    assert fixed["pickVal"] == "0"
    assert fixed["isStartup"] == "0"
    assert fixed["tep"] == "0"
