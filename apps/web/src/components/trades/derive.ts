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
 * Legs of a pair in execution order: at the roster cap the sell-leg goes
 * first (the engine's sequencing note on the buy leg says so); otherwise
 * the engine's order stands. Ids missing from the board resolve to null.
 */
export function pairLegs(
  pair: TradePair,
  byId: Map<string, TradeRec>,
): (TradeRec | null)[] {
  const legs = pair.legs.map((id) => byId.get(id) ?? null);
  const buy = legs.find((l) => l?.leg_type === "buy");
  if (buy && buy.sequencing.startsWith("at the roster cap")) {
    return [...legs].sort((a, b) => {
      const w = (r: TradeRec | null) => (r?.leg_type === "sell" ? 0 : 1);
      return w(a) - w(b);
    });
  }
  return legs;
}

/** One compact "give → get" sentence for a pair-card leg row. */
export function assetSummary(rec: TradeRec): { give: string; get: string } {
  const names = (assets: TradeRec["give"]) => assets.map((a) => a.name).join(", ");
  return { give: names(rec.give), get: names(rec.get) };
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
