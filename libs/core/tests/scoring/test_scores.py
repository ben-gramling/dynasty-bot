"""§5 core scores, §9 edge cases, ω machinery."""

from __future__ import annotations

import pytest

from core.scoring import model as md
from core.scoring import transactions as tx
from core.scoring.params import Params, omega_in_season, omega_suggest

from .conftest import by_name, pick_of


def test_omega_seeds(league):
    """§5.2: the 11 behavior-seeded opponent ω values + mine at 0.60."""
    want = {
        "bengramling": 0.60, "jaketoppen": 0.70, "NoahMoell": 0.65, "cmgaither43": 0.60,
        "joeydavis299": 0.60, "DrewR87": 0.60, "millj": 0.55, "trdouglas": 0.50,
        "josbaski": 0.40, "Jukinski": 0.35, "ronakpatel32": 0.35, "vishan": 0.25,
    }
    assert {n: t.omega for n, t in league.teams.items()} == want


def test_omega_auto_refresh_formula():
    p = Params()
    assert omega_suggest(p, rank_l=6) == pytest.approx(0.5125)  # jaketoppen: seed 0.70 wins
    assert omega_suggest(p, rank_l=1) == pytest.approx(0.70)
    assert omega_suggest(p, rank_l=12, pickflow=1) == pytest.approx(0.3375)
    assert omega_suggest(p, rank_l=12, pickflow=-1) == pytest.approx(0.2375)
    assert omega_suggest(p, rank_l=13, pickflow=-1) == 0.20  # clamp floor


def test_omega_in_season_ramp():
    p = Params()
    assert omega_in_season(p, 0.60, week=11, playoff_seed=3, games_back=0) == pytest.approx(0.75)
    assert omega_in_season(p, 0.60, week=0, playoff_seed=3, games_back=0) == 0.60
    assert omega_in_season(p, 0.40, week=8, playoff_seed=None, games_back=4) == pytest.approx(0.30)


def test_flacco_qb2_insurance(league, me):
    """§9.1: Flacco is worse than free insurance — keeping him costs 38.6 L-points,
    RV(Flacco) is only 11.6, and streaming Richardson adds +75.5."""
    flacco = by_name(league, "Joe Flacco")
    res = tx.score_transaction(league, me, remove_ids=[flacco.sid])
    assert round(res.dl, 1) == 38.6  # removal RAISES L: FA line 1,562 > 919
    assert round(-res.score, 1) == pytest.approx(11.6, abs=0.05)
    richardson = by_name(league, "Anthony Richardson")
    add = tx.score_transaction(league, me, add_players=[richardson], include_nc=False, include_crunch=False)
    assert round(add.dl, 1) == 75.5


def test_taxi_not_qb_insurance(league, me):
    """§9.1/§9.3: taxi players are lineup-ineligible — Cam Ward is in F, not L."""
    assert "Cam Ward" in {p.name for p in me.taxi}
    assert "Cam Ward" not in {p.name for p in me.pool}
    assert me.lineup.backups["QB"][0] == 919  # Flacco, not Ward


def test_flex_bars_differ_by_position(league, me):
    """§9.2: a new WR enters over Evans 4,125; a new RB must clear Javonte 5,460."""
    from core.scoring.lineup import PlayerV, solve

    wr = PlayerV(sid="s1", name="s", pos="WR", v=4500)
    rb = PlayerV(sid="s2", name="s", pos="RB", v=4500)
    aug_wr = solve(me.pool + [wr], league.replacement, league.params)
    aug_rb = solve(me.pool + [rb], league.replacement, league.params)
    assert "s1" in {p.sid for g in ("WR", "FLEX") for p in aug_wr.starters[g]}
    assert "s2" not in {p.sid for g in ("RB", "FLEX") for p in aug_rb.starters[g]}


def test_promote_cam_ward(league, me):
    """§9.3: PromoScore — ω·ΔL = +126.5 against a free drop; no lock charge pre-week-4."""
    ward = next(p for p in me.taxi if p.name == "Cam Ward")
    promo = tx.promote_score(league, me, ward, week=0)
    assert promo["omega_dl"] == 126.5
    assert promo["attached_drop"] == "Darren Waller"
    assert promo["lock_penalty"] == 0.0
    late = tx.promote_score(league, me, ward, week=5)
    assert late["lock_penalty"] == 400.0
    assert late["score"] == pytest.approx(promo["score"] - 400.0, abs=0.1)


def test_sell_101_now_vs_after_shedding(league, me):
    """§9.7: selling the 1.01 at full concrete price scores +212.6 today, −860.5
    after the body-shedding trade lands — the engine sequences hold-vs-sell itself."""
    p101 = pick_of(me, 2026, 1)
    # "full concrete price" = wealth-neutral return of 7,762 (e.g. pick capital):
    # model as removing the pick and crediting its truth value via a synthetic
    # equal-value future pick — ΔA = 0 by construction.
    res = tx.score_transaction(league, me, remove_pick_keys=[p101.key])
    score_full_price = res.score + (1 - me.omega) * p101.p  # add the sale proceeds
    assert round(score_full_price, 1) == 212.6
    assert round(me.omega * -res.dnc, 1) == 843.8  # lost now-credit
    assert round(-res.dc, 1) == 1056.4  # crunch relief

    # after Sutton + Evans → jaketoppen 2027 R1 (§11.2):
    sutton = by_name(league, "Courtland Sutton")
    evans = by_name(league, "Mike Evans")
    jt_r1 = pick_of(league.teams["jaketoppen"], 2027, 1, origin_rid=2)
    after = md.apply_tx(
        league, me, remove_ids=[sutton.sid, evans.sid], add_picks=[jt_r1]
    )
    res2 = tx.score_transaction(league, after, remove_pick_keys=[p101.key])
    score2 = res2.score + (1 - me.omega) * p101.p
    assert round(score2, 1) == -860.5


def test_401_is_a_liability(league, me):
    """§9.8: RV(4.01) = −287.6; swapping it for a 2028 Mid 4th scores +991.2."""
    p401 = pick_of(me, 2026, 4)
    res = tx.score_transaction(league, me, remove_pick_keys=[p401.key])
    assert round(-res.score, 1) == -287.6
    synth_2028_m4 = pick_of(league.teams["jaketoppen"], 2028, 4)
    swap = tx.score_transaction(
        league, me, remove_pick_keys=[p401.key], add_picks=[synth_2028_m4]
    )
    assert round(swap.score, 1) == 991.2


def test_availability_never_overrides_value(league, me):
    """§9.5 locked decision 1: u scales the lineup solver only — A(T) uses full v."""
    from core.scoring.lineup import PlayerV

    hurt = PlayerV(sid="syn:hurt", name="hurt", pos="WR", v=6000, u=0.25)
    t2 = md.apply_tx(league, me, add_players=[hurt])
    assert t2.a - me.a == 6000  # full v banked
    assert t2.L - me.L < 1000  # but the lineup sees 1,500 effective


def test_unvalued_player(league, me):
    """§9.6: Waller v = 0, flagged, never imputed; exactly one such player (§13.2)."""
    waller = by_name(league, "Darren Waller")
    assert waller.v == 0 and waller.unvalued
    all_unvalued = [
        p for t in league.teams.values() for p in t.pool + t.taxi if p.unvalued
    ]
    assert len(all_unvalued) == 1
