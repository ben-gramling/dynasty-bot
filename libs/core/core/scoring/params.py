"""Every §9 parameter with its default. All knobs live here; nothing is hardcoded elsewhere.

v3: one score (ΔW), one gate (§3), qualitative posture targeting (§4). The lineup
q/replacement/availability knobs survive only for the league-tab strength map and
the in-season FAAB bid formula — they never touch the trade path (§11.2).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Params:
    # §2 the score
    w_min: float = 150.0  # surface floor — below is noise inside KTC error bars

    # §3 fairness gate (measured from this league's ~33 completed trades)
    consolidation: tuple[float, ...] = (1.00, 0.90, 0.80)
    fairness_rel: float = 0.20
    fairness_abs: float = 500.0
    fleece_ratio: float = 1.35  # never exempted
    anchor_ask_pct: float = 8.0  # observed negotiation convention; display only

    # §4 posture
    posture_window_days: int = 365
    posture_min_trades: int = 2

    # §5 enumeration bounds (implementation, not scoring)
    max_package: int = 3
    give_list_protect_top: int = 2  # cornerstones never enter the give-list
    per_give_keep: int = 4  # smallest-gap in-band gets kept per give-package (§3 v3.1)
    dedup_variants: int = 2  # variants kept per (top-give, top-get) asset pair
    top_league_wide: int = 10
    legality_budget: int = 400  # full apply_tx legality checks per board build
    max_pairs: int = 8  # hedged pairs kept on the board (§5 v3.1)
    watch_max: int = 5  # unpaired buys surfaced as watch-list notes (§5 v3.1)

    # §2.2-style lineup strength (league tab + waiver ΔL only; never trades)
    q_qb: float = 0.06
    q_rb: float = 0.14
    q_wr: float = 0.11
    q_te: float = 0.10
    q_flex: float = 0.12
    replacement_fa_rank: int = 3  # KTC value of the Nth-best non-rookie FA per position

    # availability multipliers (lineup display only — never wealth, never ΔW)
    u_healthy: float = 1.0
    u_out_short: float = 0.6  # OUT, expected return ≤ u_out_short_weeks
    u_out_long: float = 0.25  # OUT long-term / PUP
    u_out_short_weeks: int = 3

    # §6 waivers (v1 §6.4 mechanics, backtested on the league's 2025 bid tape)
    kappa: float = 25.0  # KTC points per dollar (universal ceiling raw/κ)
    k_need: float = 6000.0
    g_contest: tuple[float, float, float] = (0.5, 1.0, 1.15)  # D=0 / D=1 / D≥2
    inseason_bid_clamp: float = 0.65
    offseason_bid_d1: int = 1
    offseason_bid_d2_cap: int = 3
    offseason_bid_d2_budget_pct: float = 0.06
    offseason_bid_d2_min_raw: float = 2000.0
    stash_bid_cap: int = 3
    rival_dl_threshold: float = 300.0  # D(a): rival lineup need to count as demand

    # taxi errata 9-12 mechanics (§8 — legality and sequencing only)
    taxi_eligible_max_exp: int = 1  # house rule: only 1st/2nd-year players stashable
    taxi_insurance_mult: float = 0.0  # erratum 11 backup-insurance shadows (off)
    taxi_lock_week: int = 4
    taxi_fill_top_n: int = 5

    # §8 trade deadline (league setting mirrored here for the tab-disable rule)
    trade_deadline_week: int = 11

    # display-only dip note: value down vs our own trailing-30-day archive
    dip_threshold: float = 0.06

    def q(self, slot: str) -> float:
        return {
            "QB": self.q_qb,
            "RB": self.q_rb,
            "WR": self.q_wr,
            "TE": self.q_te,
            "FLEX": self.q_flex,
        }[slot]
