"""KTC's numbered current-year picks — the port pinned to a live capture.

The calculator GENERATES the 48 numbered picks client-side; they are in no
payload we scrape. `data/fixtures/ktc/tc_capture_2026-08-02.json` is a one-shot
capture of `rawPlayers` taken from the running page, so its 500 inputs and its
48 `calculated: true` outputs are self-consistent — which is the only way this
port can be pinned at all, since the board moves daily. Two of the 48 are
independently corroborated by the user's own browser (2026 Pick 3.02, 4.01).

Everything here is exact-match, never `approx`: a port that is "close" to an
external calculator is a port that will disagree with the counterparty's screen,
which is the exact failure this module exists to remove.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.scoring import ktc_link as kl
from core.scoring import ktc_picks as kp

CAPTURE = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "fixtures"
    / "ktc"
    / "tc_capture_2026-08-02.json"
)


@pytest.fixture(scope="module")
def capture() -> dict:
    return json.loads(CAPTURE.read_text())


@pytest.fixture(scope="module")
def inputs(capture) -> list[dict]:
    """The 500 records KTC had BEFORE addNumberedPicks ran — the same shape our
    own `data/ktc_raw.json` carries."""
    return [a for a in capture["rawPlayers"] if not a.get("calculated")]


@pytest.fixture(scope="module")
def truth(capture) -> dict[str, dict]:
    """The 48 KTC computed, by name."""
    return {
        a["playerName"]: a for a in capture["rawPlayers"] if a.get("calculated")
    }


def test_capture_is_the_shape_the_port_expects(capture, inputs, truth):
    assert capture["draftYear"] == 2026 and capture["phase"] == 2
    assert len(capture["rawPlayers"]) == 548
    assert len(inputs) == 500 and len(truth) == 48
    assert sum(1 for a in inputs if a.get("position") == "RDP") == 36
    assert sum(1 for a in inputs if a.get("rookie")) == 61


def test_all_48_numbered_picks_are_exact_in_both_columns(inputs, truth):
    """The acceptance test. Every slot, both formats, integer-exact — including
    the two non-integer ones KTC derives off the rookies rather than a tranche
    (1.01 = 7897.01, 1.02 = 6597.36), which are the tell that the special-cased
    top-of-round branch is ported and not approximated."""
    for sf, col in ((False, "oneQBValues"), (True, "superflexValues")):
        got = kp.numbered_pick_values(
            inputs, draft_year=2026, phase=2, site_draft_year=2026, sf=sf
        )
        assert len(got) == 48
        for (rnd, slot), value in got.items():
            name = kp.numbered_pick_name(2026, rnd, slot)
            assert value == truth[name][col]["value"], (name, col)
    one = kp.numbered_pick_values(inputs, draft_year=2026, phase=2)
    assert one[(1, 1)] == 7897.01 and one[(1, 2)] == 6597.36
    assert one[(3, 2)] == 2912 and one[(4, 1)] == 2181  # the browser-corroborated pair


def test_ids_and_names_match_ktcs_own_records(inputs, truth):
    """`parseInt(DRAFTYEAR + round + slot)` — slot UNPADDED in the id, zero-padded
    in the name. One implementation, shared with the deep-link builder."""
    for name, rec in truth.items():
        _, _, dotted = name.partition(" Pick ")
        rnd, slot = (int(x) for x in dotted.split("."))
        assert kp.numbered_pick_id(2026, rnd, slot) == rec["playerID"]
        assert kp.numbered_pick_name(2026, rnd, slot) == name
    assert kl.numbered_pick_id is kp.numbered_pick_id  # no second copy to drift
    assert kp.numbered_pick_id(2026, 1, 1) == 202611
    assert kp.numbered_pick_id(2026, 1, 12) == 2026112  # unpadded: not 20261012


def test_the_result_is_order_insensitive(inputs):
    """The JS sorts DESC inside the generator, twice. Our snapshot's natural
    order is NOT value-descending, so a port that only sorted in the wrapper
    would be one refactor away from moving 44 of 48 prices."""
    base = kp.numbered_pick_values(inputs, draft_year=2026, phase=2)
    shuffled = list(reversed(inputs))
    assert kp.numbered_pick_values(shuffled, draft_year=2026, phase=2) == base
    rookies = sorted((a["oneQBValues"]["value"] for a in inputs if a.get("rookie")))
    tranches = sorted(
        a["oneQBValues"]["value"]
        for a in inputs
        if a.get("position") == "RDP" and a["playerName"].startswith("2026 ")
    )
    # ascending in, same answer out
    assert kp.calc_picks_rookies_single_mode(
        rookies, sorted(tranches, reverse=True)
    ) == kp.calc_picks_rookies_single_mode(
        sorted(rookies, reverse=True), sorted(tranches, reverse=True)
    )


# --------------------------------------------------- refuse, never degrade


def test_a_short_rookie_ladder_refuses_instead_of_degrading(inputs):
    """The curvature term is indexed by PICK number and spans all 48, so a
    shorter rookie list silently routes the tail into the plain-eighths branch
    and returns a full, monotone, plausible, WRONG board. Measured before the
    guard: 47 rookies moved 1 slot, 40 moved 8, 20 moved 26 — no signal."""
    keep = 0
    trimmed = []
    for a in inputs:
        if a.get("rookie"):
            keep += 1
            if keep > 40:
                continue
        trimmed.append(a)
    with pytest.raises(ValueError, match="rookies on the board"):
        kp.numbered_pick_values(trimmed, draft_year=2026, phase=2)


def test_a_thirteenth_tranche_refuses(inputs):
    """13 same-year tranches make the ladder emit 52 and shift the tail block,
    re-pricing 4.11/4.12 while still returning a full 48."""
    extra = dict(
        playerName="2026 Early 5th", position="RDP", rookie=False,
        oneQBValues={"value": 1500}, superflexValues={"value": 1400},
    )
    with pytest.raises(ValueError, match="exactly 12"):
        kp.numbered_pick_values([*inputs, extra], draft_year=2026, phase=2)


def test_a_year_ktc_does_not_number_refuses(inputs):
    """KTC numbers only its DRAFTYEAR. Asking for 2027 used to return a clean
    monotone 48 built from 2027 tranches against the 2026 rookie class — numbers
    KTC never shows, wearing the shape of scraped truth."""
    with pytest.raises(ValueError, match="DRAFTYEAR"):
        kp.numbered_pick_values(
            inputs, draft_year=2027, phase=2, site_draft_year=2026
        )
    # and a substring year can no longer match three years of tranches at once
    with pytest.raises(ValueError, match="exactly 12"):
        kp.numbered_pick_values(inputs, draft_year=202, phase=2)


def test_an_unported_phase_refuses(inputs):
    """`phase` is required and unguessable from our payload — the collector
    scrapes it. Phase 1 runs calcPicksDevy (different arithmetic, unported);
    any other phase means the calculator generates no numbered picks at all."""
    with pytest.raises(NotImplementedError, match="calcPicksDevy"):
        kp.numbered_pick_values(inputs, draft_year=2026, phase=1)
    with pytest.raises(ValueError, match="no numbered"):
        kp.numbered_pick_values(inputs, draft_year=2026, phase=0)


def test_the_numbered_board_is_monotone_and_beats_the_tranche(inputs):
    """Sanity that survives a board move: prices fall monotonically down the
    board, and the numbered price for an EARLY slot sits above its own tranche
    (which is the whole reason the gate disagreed with the screen)."""
    got = kp.numbered_pick_values(inputs, draft_year=2026, phase=2)
    flat = [got[(r, s)] for r in range(1, 5) for s in range(1, 13)]
    assert flat == sorted(flat, reverse=True)
    tranche = {
        a["playerName"]: a["oneQBValues"]["value"]
        for a in inputs
        if a.get("position") == "RDP"
    }
    assert got[(3, 2)] > tranche["2026 Early 3rd"]
    assert got[(4, 1)] > tranche["2026 Early 4th"]
