"""Every §9 parameter with its default. All knobs live here; nothing is hardcoded elsewhere.

v4: the score has ZERO parameters — two objective coordinates (ΔS, ΔF) plus
maximin, §2. `stored_delta` is RETIRED: δ survives only as the derived,
per-trade breakeven the CLI reports on preference trades. One gate (the exact
KTC calculator adjustment + the fleece cap + legality, §3), qualitative posture
targeting (§4). The lineup q/replacement/availability knobs survive only for the
league-tab strength map and the in-season FAAB bid formula — they never touch
the trade path (§11.2). The gate itself has ZERO fitted parameters: the
consolidation coefficients `c` are retired with v3.4.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Params:
    # §2 the score (v4: two objective coordinates ΔS/ΔF, no blend, no δ).
    # v3.3: W_min is RETIRED as a gate — kept only as the display-level noise
    # floor, applied to the guaranteed FLOOR min(ΔS, ΔF) (a positive floor
    # inside KTC's own error bars gets flagged, never hidden)
    w_min: float = 150.0

    # §3 fairness gate. The band tolerances are measured from this league's ~33
    # completed trades; the adjustment they are applied to is the EXACT KTC
    # calculator port (core.scoring.ktc_adjust — zero free parameters). v3.4
    # retired the fitted consolidation coefficients c = (1.00, 0.90, 0.80):
    # they approximated this algorithm, and the real one provably does not
    # cancel across roster-neutral pairs.
    fairness_rel: float = 0.20
    fairness_abs: float = 500.0
    fleece_ratio: float = 1.35  # never exempted
    anchor_ask_pct: float = 8.0  # observed negotiation convention; display only

    # §4 posture
    posture_window_days: int = 365
    posture_min_trades: int = 2

    # §5 v3.3 target-return range + enumerate-then-filter bounds
    # v3.4: the per-leg return floor is RETIRED — a pair's buy leg is legitimately
    # negative in isolation, so legs are no longer required to earn on their own.
    max_package: int = 3
    give_list_protect_top: int = 2  # cornerstones never enter the give-list
    # total-return floor presets, percent (the min dial + the by_total grid bands)
    return_presets: tuple[float, ...] = (1.0, 2.5, 5.0, 10.0, 20.0)
    # §9 v5 counterparty-favorability presets (KTC's own variance units; ±5 is
    # the calculator's FAIR window at default variance). The favor dial is a
    # FLOOR on pair favorability min(f_buy, f_sell); an optional ceiling stops
    # giving edge away. Replaces the v3.4.1 raw-skim leg cap: the raw skim
    # provably diverges from the counterparty's own calculator by up to 14 pts.
    favor_presets: tuple[float, ...] = (-10.0, -5.0, 0.0, 2.5, 5.0)
    # §5 v5 storage strata: pair favor min(f_buy, f_sell) buckets
    # (−∞,−10), [−10,−5), [−5,0), [0,+5), [+5,∞) — the +2.5 preset is a DIAL
    # position served from the [0,+5) bucket's stored inventory (every stored
    # pair carries its exact favor, so the client filter is O(stored))
    favor_band_edges: tuple[float, ...] = (-10.0, -5.0, 0.0, 5.0)
    # §9 v5 δ-slider presets — labeled preference VIEWS over the stored (ΔS, ΔF)
    # coordinates, never score parameters (§2/§4a); robust (all-δ) is the default
    delta_presets: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)
    # §5 v5 stratified storage: PER favor bucket the deduped UNION of the top-N
    # by robust floor-return, by ΔS, and by ΔF — so both δ-slider extremes have
    # inventory; per-bucket honesty + the bucket × robust-return-band grid via
    # `bands`.
    pairs_per_band: int = 100
    # §4a/§9 the spread finder
    finder_top: int = 20  # query result size
    finder_cross_budget: int = 2_000_000  # crossings per query; saturation → verified floors
    variants_per_signature: int = 2  # gets kept per (opponent, give, count-signature), isolation floor desc
    # v3.4 scan bound: gate-passers evaluated per (opponent, give, count-signature)
    # before the top-`variants_per_signature` are taken. The exact KTC gate and the
    # starter-sum re-solve are ~30× the retired adjv comparison, so the bracket is
    # sampled from its Σv-desc top rather than drained (disclosed in the board notes).
    variant_scan_cap: int = 3
    pair_scan_budget: int = 40_000  # pair visits per COUNTING pass; counters saturate honestly
    pair_collect_budget: int = 400_000  # pair visits for the stored-pair collection walk
    top_league_wide: int = 10  # unpaired sell/neutral legs kept as `recommendations` (isolation floor desc)
    watch_max: int = 5  # unpaired buys surfaced as watch-list notes

    # §2.2-style lineup strength (league tab + waiver ΔL only; never trades)
    q_qb: float = 0.06
    q_rb: float = 0.14
    q_wr: float = 0.11
    q_te: float = 0.10
    q_flex: float = 0.12
    replacement_fa_rank: int = 3  # KTC value of the Nth-best non-rookie FA per position

    # availability multipliers (lineup display only — never the trade coordinates)
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
