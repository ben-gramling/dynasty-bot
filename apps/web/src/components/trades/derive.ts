import type { LeagueRow, TradePair, TradeRec } from "@/lib/queries";

/**
 * Pure helpers for the Trades tab. Everything here is a typed view or a
 * restatement of facts already in the collector's output (scoring-system.md
 * v3 §4–§5) — never a recomputation of scores.
 */

export { ord } from "@/components/league/util";

/** "BUY LEG" / "SELL LEG" / "NEUTRAL" badge text. */
export function legLabel(rec: TradeRec): string {
  if (rec.leg_type === "buy") return "buy leg";
  if (rec.leg_type === "sell") return "sell leg";
  return "roster-neutral";
}

/**
 * §4a v5 leg favor chip text, in KTC's own calculator terms: |favor| ≤ 5 is
 * literally the calculator's FAIR verdict at default variance (the engine
 * quantizes favor exactly as the calculator does, so the boundary is exact);
 * beyond it the chip names the beneficiary — favor > 0 skews to the
 * counterparty ("them"), favor < 0 to you (shown as a magnitude).
 */
export function favorLabel(favor: number): string {
  if (Math.abs(favor) <= 5) return "their calculator: FAIR";
  return favor > 0
    ? `favors them +${favor.toFixed(1)}`
    : `favors you ${Math.abs(favor).toFixed(1)}`;
}

/**
 * §4 posture sentence: what the counterparty receives, aimed at their
 * observed posture — "players → BUYER ronakpatel32 (3 trades on record)".
 */
export function postureEvidenceNote(rec: TradeRec): string {
  const n = rec.posture.evidence_count;
  if (rec.posture.source !== "trades") return "user override";
  if (n === 0) return "no posture trades in window";
  return `${n} trade${n > 1 ? "s" : ""} on record`;
}

/**
 * A pair's embedded legs in execution order (§5 v3.1): at the roster cap the
 * sell executes first (the engine's pair sequencing note says so); with open
 * roster space the buy may go first — agreement-first either way.
 */
export function pairLegs(pair: TradePair): [TradeRec, TradeRec] {
  return pair.sequencing.startsWith("at the roster cap")
    ? [pair.sell, pair.buy]
    : [pair.buy, pair.sell];
}

// ---- market strip (league-table market blocks, §7 targeting console) ----

export interface MarketStripEntry {
  team: string;
  posture: string;
  count: number;
}

/** BUYERs and SELLERs with their evidence tallies, for the trades-tab strip. */
export function marketStrip(rows: LeagueRow[], myTeam: string): MarketStripEntry[] {
  return rows
    .filter((r) => r.team !== myTeam && r.market.posture !== "NEUTRAL")
    .map((r) => ({
      team: r.team,
      posture: r.market.posture,
      count:
        r.market.posture === "BUYER" ? r.market.bought : r.market.sold,
    }))
    .sort((a, b) => a.posture.localeCompare(b.posture) || b.count - a.count);
}
