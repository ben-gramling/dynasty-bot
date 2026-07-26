"""Taxi economics — errata 9-12 (reviewer bug fix + house-rule model).

House rules: taxi stashable by 1st/2nd-year players only, adds legal until the
lock after week 4, promote-out any time, vacated slots not refillable post-lock.
"""

from dataclasses import replace

import pytest

from core.scoring import Params, model as md, transactions as tx, waivers as wv


def _by_name(players, name):
    return next(p for p in players if p.name == name)


@pytest.fixture(scope="module")
def ward(me):
    return _by_name(me.taxi, "Cam Ward")


@pytest.fixture(scope="module")
def shedeur(league):
    return _by_name(league.teams["vishan"].taxi, "Shedeur Sanders")


class TestErratum9WealthDebit:
    def test_taxi_departure_debits_everything(self, league, me, ward):
        t2 = md.apply_tx(league, me, remove_ids=[ward.sid])
        assert t2.players_v_sum == pytest.approx(me.players_v_sum - ward.v)
        assert t2.a == pytest.approx(me.a - ward.v)  # wealth debited (the bug)
        assert t2.f == pytest.approx(me.f - ward.v)  # future assets debited
        assert ward.sid not in {p.sid for p in t2.taxi}
        assert t2.free_taxi == me.free_taxi + 1  # pre-lock: slot refillable

    def test_taxi_swap_wealth_is_zero_sum(self, league, me, ward, shedeur):
        vishan = league.teams["vishan"]
        res_me = tx.score_transaction(
            league, me, add_players=[shedeur], remove_ids=[ward.sid]
        )
        res_them = tx.score_transaction(
            league, vishan, add_players=[ward], remove_ids=[shedeur.sid]
        )
        # pre-fix both sides came out positive (+2368 / +4426)
        assert res_me.da == pytest.approx(shedeur.v - ward.v)
        assert res_them.da == pytest.approx(ward.v - shedeur.v)
        assert res_me.da + res_them.da == pytest.approx(0.0)

    def test_post_lock_departure_slot_is_dead(self, snapshot, params, me, ward):
        wk6 = replace(
            snapshot, state={**dict(snapshot.state), "season_type": "regular", "week": 6}
        )
        lg6 = md.build_league(wk6, params)
        me6 = lg6.teams[lg6.me]
        ward6 = _by_name(me6.taxi, "Cam Ward")
        t2 = md.apply_tx(lg6, me6, remove_ids=[ward6.sid])
        assert t2.a == pytest.approx(me6.a - ward6.v)
        assert t2.free_taxi == me6.free_taxi  # post-lock: freed slot unusable


class TestErratum10Routing:
    def test_eligible_arrival_routes_to_surplus_slot(self, league):
        """jaketoppen: zero crunch, surplus taxi slots — a young non-starter stashes."""
        jake = league.teams["jaketoppen"]
        arroyo = _by_name(league.teams[league.me].taxi, "Elijah Arroyo")
        assert md.taxi_eligible(league, arroyo)
        assert jake.free_taxi - md.taxi_slot_demand(league, jake) > 0
        t2 = md.apply_tx(league, jake, add_players=[arroyo])
        assert arroyo.sid in {p.sid for p in t2.taxi}
        assert len(t2.act) == len(jake.act)  # no active spot consumed
        assert t2.cuts == jake.cuts  # no crunch charged
        assert t2.free_taxi == jake.free_taxi - 1
        assert t2.a == pytest.approx(jake.a + arroyo.v)  # still full wealth credit

    def test_earmarked_slots_are_never_consumed(self, league, me, shedeur):
        """My one free slot is crunch absorption for the incoming picks — an
        arriving stash candidate must go active + drop, not eat the slot."""
        assert md.taxi_slot_demand(league, me) >= me.free_taxi
        to_active, to_taxi = md.routed_split(league, me, [shedeur])
        assert to_taxi == [] and to_active == [shedeur]

    def test_ineligible_veteran_never_routes(self, league):
        jake = league.teams["jaketoppen"]
        evans = _by_name(league.teams[league.me].act, "Mike Evans")
        assert not md.taxi_eligible(league, evans)
        to_active, to_taxi = md.routed_split(league, jake, [evans])
        assert to_taxi == []

    def test_post_lock_everyone_is_active(self, snapshot, params):
        wk6 = replace(
            snapshot, state={**dict(snapshot.state), "season_type": "regular", "week": 6}
        )
        lg6 = md.build_league(wk6, params)
        jake6 = lg6.teams["jaketoppen"]
        arroyo6 = _by_name(lg6.teams[lg6.me].taxi, "Elijah Arroyo")
        t2 = md.apply_tx(lg6, jake6, add_players=[arroyo6])
        assert arroyo6.sid in {p.sid for p in t2.act}
        assert len(t2.taxi) == len(jake6.taxi)

    def test_route_taxi_false_forces_active(self, league):
        """The promote path passes route_taxi=False — an add must land active even
        when a surplus slot and eligibility would otherwise stash it."""
        jake = league.teams["jaketoppen"]
        arroyo = _by_name(league.teams[league.me].taxi, "Elijah Arroyo")
        t2 = md.apply_tx(league, jake, add_players=[arroyo], route_taxi=False)
        assert arroyo.sid in {p.sid for p in t2.act}
        assert len(t2.taxi) == len(jake.taxi)

    def test_promotion_is_wealth_neutral(self, league, me, ward):
        card = tx.promote_score(league, me, ward)
        assert card["action"] == "PROMOTE"
        assert card["sides"]["me"]["wealth_weighted"] == pytest.approx(0.0, abs=0.05)


class TestErratum11InsuranceShadows:
    def test_default_off_matches_pinned_model(self, snapshot, params, league):
        assert params.taxi_insurance_mult == 0.0
        assert not any(p.sid.endswith(":taxi") for t in league.teams.values() for p in t.pool)

    def test_mult_raises_L_via_stash_backups(self, snapshot, league):
        lg75 = md.build_league(snapshot, Params(taxi_insurance_mult=0.75))
        # Cam Ward (QB, taxi) at 0.75x beats Flacco as my QB insurance
        assert lg75.teams[lg75.me].lineup.L > league.teams[league.me].lineup.L
        # shadows never leak real wealth: A and F identical under both params
        assert lg75.teams[lg75.me].a == pytest.approx(league.teams[league.me].a)
        assert lg75.teams[lg75.me].f == pytest.approx(league.teams[league.me].f)

    def test_shadow_removed_with_departing_taxi_player(self, snapshot, me, ward):
        lg75 = md.build_league(snapshot, Params(taxi_insurance_mult=0.75))
        me75 = lg75.teams[lg75.me]
        t2 = md.apply_tx(lg75, me75, remove_ids=[ward.sid])
        assert not any(p.sid == f"{ward.sid}:taxi" for p in t2.pool)


class TestErratum12TaxiFill:
    def test_earmarked_slot_produces_no_nudge(self, league, me):
        board = wv.waiver_board(league, me)
        tf = board["taxi_fill"]
        assert tf["free_slots"] == me.free_taxi
        assert tf["surplus_slots"] == 0  # my slot is pick-absorption, not surplus
        assert tf["candidates"] == []

    def test_surplus_slot_lists_eligible_stashes(self, league):
        jake = league.teams["jaketoppen"]
        board = wv.waiver_board(league, jake)
        tf = board["taxi_fill"]
        assert tf["surplus_slots"] > 0
        assert 0 < len(tf["candidates"]) <= league.params.taxi_fill_top_n
        for c in tf["candidates"]:
            p = next(x for x in league.fa_vets if x.name == c["player"])
            assert md.taxi_eligible(league, p)
