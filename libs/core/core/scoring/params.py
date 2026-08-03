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
    # crossings per query; saturation → verified floors. v5.1 raised this from
    # 2,000,000: the sound key ΔF gives up later than the retired isolation
    # floor, so a TRUNCATED robust walk keeps different (measurably worse for
    # the floor objective) crossings — on the measured market query the 2M walk
    # returned best 13.18% and none of the exhaustive top-20, where the same
    # query crossed COMPLETELY at 10.3M (best 16.25%, exact=True, 34.5s).
    # v7.5 raised 16M → 20M: its pessimistic pricing broadened the §3 fair
    # band and the largest per-counterparty dashboard crossing measured
    # 16,110,117 on the fixtures (jaketoppen — 16M truncated it by 0.7%).
    # v7.6's flat Mid shrank that max back to 10,358,086, but the 20M ceiling
    # stays: a budget only bites on queries that would saturate anyway, and
    # the headroom is what keeps the per-counterparty board exhaustive across
    # re-pricings. ~576k crossings/s; unconstrained queries (space 4.6e9)
    # stay truncated honest floors either way. The finder is the interactive
    # CLI/skill path — it never runs on the collector Lambda, so this does not
    # touch the §11.10 board budget (§9, v5.1).
    finder_cross_budget: int = 20_000_000
    # §4a v6 the COMPLETE fair-band pool. `pool_favor_band` bounds the whole
    # enumeration to |leg favor| ≤ β — the band the desk actually trades in —
    # and in exchange the v3.4/v5 SAMPLING is retired: every gate-passer inside
    # the band is kept, not the best 2 of the first 3 scanned. That sampling was
    # the engine's central unsoundness (disclosed since v5): it retained 0.449%
    # of the fair inventory, and because the bracket was scanned Σv-DESCENDING
    # the survivors skewed hard to the me-favorable end (pool favor median
    # −9.40 against a true population median +0.10) — i.e. it was worst at
    # exactly the counterparty-friendly trades a spread needs. Set to None to
    # enumerate the whole §3.1 gate band instead (26.2M legs / 1,043 MB on the
    # live snapshot — it does NOT fit the collector Lambda; see §9).
    #
    # DEFAULT IS None PENDING THE LEG REPRESENTATION. The complete |favor| ≤ 5
    # pool is 11,911,255 legs and MEASURES 3,904 MB peak RSS as Python tuples
    # holding Package objects (~330 B/leg). The design study's 479 MB figure was
    # for a columnar layout it never had to integrate with the walks, the sinks
    # or `pair_eval`. Until the legs are columnar this cannot run on the
    # collector, so the band stays opt-in (`build_pair_pool(..., favor_band=5)`)
    # and the board keeps the sampled scan with a budget that no longer starves
    # it (see `pair_collect_budget`).
    pool_favor_band: float | None = None
    # §4a v6 the FINDER's band. The finder is interactive and local, so it takes
    # the complete pool the collector cannot afford: every gate-passer inside
    # |favor| ≤ 5 is kept. This is where the coverage actually pays — measured
    # on the live snapshot, the complete pool lifts the best guaranteed floor by
    # +10.9% to +16.8% for EVERY counterparty (ronakpatel32 2,997 → 3,338), and
    # moves the pool favor median −9.40 → +0.10 so the counterparty-friendly end
    # is represented at all. Constraint push-down runs BEFORE the gate scan, so a
    # real negotiator query builds a small fraction of the ~3.9 GB unconstrained
    # band-5 pool; set to None to fall back to v5's sampled scan.
    finder_favor_band: float | None = None
    # The Σv-descending scan and its caps, kept ONLY for `pool_favor_band=None`
    # (the wide-band path, which is still infeasible to drain). Inside a favor
    # band the scan drains the bracket and these are unused.
    variants_per_signature: int = 2  # gets kept per (opponent, give, count-signature), isolation floor desc
    variant_scan_cap: int = 3
    # §3.1 v6 screen slack. The raw-adjustment-gap screen rejects candidates
    # whose adjusted gap provably cannot clear the target band. Evaluating
    # processV at nerf 0 and at r_max (rather than reverseAdjust's rescaled max)
    # already pushes the threshold UP; this multiplier covers reverse_adjust's
    # 2.5% tolerance, which the port does not always honour (it is non-monotone).
    # Calibration, not proof: the minimum factor that admits every fair leg on
    # the live snapshot measures 1.0308, so 1.15 carries ~11.6% headroom.
    screen_slack: float = 1.15
    pair_scan_budget: int = 40_000  # pair visits per COUNTING pass; counters saturate honestly
    # §5 v6 raised 400,000 → 4,000,000. `canonical_sig` restored the Δplayers==0
    # crossing family (+6.1% of the space), and a FIXED collection budget spread
    # over a larger space stores FEWER pairs, not more — measured on the live
    # snapshot with the fix in: 400k → 619 stored / 19 both-legs-fair, 1.6M →
    # 1,101 / 478, 4M → 1,133 / 528. The old budget turned a coverage fix into a
    # regression. 4M costs 61.0 s and 236 MB peak against the collector's 900 s
    # / 2048 MB, and is what makes the fair band actually populated (v5.1 stored
    # 1,079 pairs total). This is a mitigation, not the cure — the budget is a
    # walk cutoff, so it still certifies nothing; `pool_favor_band` plus a
    # per-cell exact top-K is the real fix and is blocked on the leg layout.
    pair_collect_budget: int = 4_000_000  # pair visits for the stored-pair collection walk
    # §12 v8 the hedge database (core.scoring.hedgedb — CLI-only, never the
    # collector). The DB stores the COMPLETE |favor| <= hedgedb_band leg pool
    # columnar and serves exact seeded-walk searches over it; measured on the
    # live snapshot the band-5 pool is 13,490,657 legs and its >= 1%-floor
    # crossing region is ~2.5e12 pairs — which is why the DB stores legs, not
    # pairs. `hedgedb_store_top` is the stored search depth per counterparty
    # (the board shows 5); `hedgedb_search_budget` guards a single search's
    # walk — saturation is disclosed per search, never expected for filtered
    # queries.
    hedgedb_band: float = 5.0
    hedgedb_store_top: int = 50
    hedgedb_search_budget: int = 40_000_000
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
