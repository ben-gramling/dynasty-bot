"""Every §10 parameter with its default. All knobs live here; nothing is hardcoded elsewhere."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

# §5.2 behavior-seeded opponent posture defaults (per-team editable in settings).
OMEGA_SEEDS: dict[str, float] = {
    "jaketoppen": 0.70,
    "NoahMoell": 0.65,
    "cmgaither43": 0.60,
    "joeydavis299": 0.60,
    "DrewR87": 0.60,
    "millj": 0.55,
    "trdouglas": 0.50,
    "josbaski": 0.40,
    "Jukinski": 0.35,
    "ronakpatel32": 0.35,
    "vishan": 0.25,
}

# §7.4 documented deal-count activity prior.
ACTIVITY_PRIOR: dict[str, str] = {
    "jaketoppen": "High",
    "cmgaither43": "High",
    "millj": "High",
    "trdouglas": "High",
    "vishan": "High",
    "Jukinski": "High",
    "ronakpatel32": "High",
    "NoahMoell": "Med",
    "DrewR87": "Med",
    "joeydavis299": "Low",
    "josbaski": "Low",
}


@dataclass(frozen=True)
class Params:
    # §5.2 contend/build knob
    omega_me: float = 0.60
    omega_seeds: Mapping[str, float] = field(default_factory=lambda: dict(OMEGA_SEEDS))
    # ω auto-refresh: clamp(base + rank_coef·(13 − rank_L)/12 + pickflow_coef·pickflow, lo, hi)
    omega_auto_base: float = 0.25
    omega_auto_rank_coef: float = 0.45
    omega_auto_pickflow_coef: float = 0.05
    omega_auto_clamp: tuple[float, float] = (0.20, 0.75)
    # ω in-season ramp/fade
    omega_ramp_seeded: float = 0.15  # seeds 1–6 get +ramp·week/11
    omega_fade_out: float = 0.10  # ≥3 games out get −fade

    # §2.2 weekly starter-absence priors
    q_qb: float = 0.06
    q_rb: float = 0.14
    q_wr: float = 0.11
    q_te: float = 0.10
    q_flex: float = 0.12

    # §2.3 replacement rule: KTC value of the Nth-best non-rookie FA per position
    replacement_fa_rank: int = 3

    # §9.5 availability multipliers
    u_healthy: float = 1.0
    u_out_short: float = 0.6  # OUT, expected return ≤ u_out_short_weeks
    u_out_long: float = 0.25  # OUT long-term / PUP
    u_out_short_weeks: int = 3

    # §3.3 rookie readiness
    rho_rook: float = 0.50

    # §7.2 market-realism layer
    consolidation: tuple[float, ...] = (1.00, 0.90, 0.80)
    fairness_rel: float = 0.20
    fairness_abs: float = 500.0
    fleece_ratio: float = 1.35

    # §7.2 / §7.3 / §7.4 trade thresholds
    g_min: float = 150.0  # my-side floor
    their_floor: float = 0.0
    tier_a: float = 300.0
    tier_b: float = 100.0
    contender_omega: float = 0.55
    rebuilder_omega: float = 0.40
    rebuilder_future_share: float = 0.50  # share of AdjV as picks + under-25 players
    under_age: float = 25.0
    mutual_weight: float = 0.30
    max_package: int = 3
    give_list_size: int = 8
    # §7.1: the give-list is surplus, not cornerstones — a team's top-N assets by
    # value never enter it (reproduces the spec's quoted list: Walker…Sutton, not
    # Jeanty/Hampton, whose raw σ⁰ would otherwise rank first).
    give_list_protect_top: int = 2
    anchor_ask_pct: float = 8.0
    dedup_variants: int = 2
    top_league_wide: int = 10
    top_per_opponent: int = 3
    # implementation bound (§13.10 erratum 8): joint evaluations are budgeted per
    # (give-size × get-size) bucket, best-first by the crunch-corrected additive
    # proxy — stratifying keeps the 1×1/2×1 bread-and-butter deals in play instead
    # of letting 3×3 consolidation monsters monopolize the budget.
    trade_eval_cap_per_bucket: int = 250

    # §7.6 market timing
    dip_threshold: float = 0.06  # −6% vs trailing-30-day max

    # §6 waivers
    n_min: float = 250.0  # claim threshold on raw NetClaim
    free_option_eps: float = 1.0  # NetClaim ≥ −ε still claimable at $0
    drop_floor: float = 2500.0  # RV⁰ above this requires explicit confirm
    rival_dl_threshold: float = 300.0

    # §6.4 bids
    kappa: float = 25.0  # KTC points per dollar (universal ceiling raw/κ)
    k_need: float = 6000.0
    g_contest: tuple[float, float, float] = (0.5, 1.0, 1.15)  # D=0 / D=1 / D≥2
    inseason_bid_clamp: float = 0.65
    offseason_bid_d1: int = 1
    offseason_bid_d2_cap: int = 3
    offseason_bid_d2_budget_pct: float = 0.06
    offseason_bid_d2_min_raw: float = 2000.0
    stash_bid_cap: int = 3

    # §9.3 taxi lock
    tau_lock: float = 400.0
    taxi_lock_week: int = 4

    # Taxi economics (errata 9-12)
    taxi_eligible_max_exp: int = 1  # house rule: only 1st/2nd-year players stashable
    # §2.2 extension (erratum 11): stashed players count as discounted backup
    # insurance. OFF by default — enabling moves every pinned L in the spec, so the
    # flip must ship together with a spec-table regeneration.
    taxi_insurance_mult: float = 0.0
    taxi_fill_top_n: int = 5  # erratum 12: waiver-tab "fill your taxi slot" nudge

    # §2.4 trade deadline (league setting mirrored here for the tab-disable rule)
    trade_deadline_week: int = 11

    def q(self, slot: str) -> float:
        return {
            "QB": self.q_qb,
            "RB": self.q_rb,
            "WR": self.q_wr,
            "TE": self.q_te,
            "FLEX": self.q_flex,
        }[slot]

    def omega_for(self, display_name: str, my_name: str) -> float:
        if display_name == my_name:
            return self.omega_me
        return float(self.omega_seeds.get(display_name, 0.50))


def omega_suggest(params: Params, rank_l: int, pickflow: int = 0) -> float:
    """§5.2 monthly auto-refresh suggestion (manual seed always wins)."""
    lo, hi = params.omega_auto_clamp
    raw = (
        params.omega_auto_base
        + params.omega_auto_rank_coef * (13 - rank_l) / 12
        + params.omega_auto_pickflow_coef * pickflow
    )
    return min(hi, max(lo, raw))


def omega_in_season(
    params: Params, omega: float, week: int, playoff_seed: int | None, games_back: float
) -> float:
    """§5.2 in-season ramp: weeks 1–11 seeds 1–6 ramp up; teams ≥3 games out fade."""
    if not 1 <= week <= params.trade_deadline_week:
        return omega
    if playoff_seed is not None and playoff_seed <= 6:
        omega = omega + params.omega_ramp_seeded * week / 11
    if games_back >= 3:
        omega = omega - params.omega_fade_out
    return omega
