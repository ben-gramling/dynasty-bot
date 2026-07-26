import type { LeagueRow, TradeRec, TradeZoneRow } from "@/lib/queries";

/**
 * Pure helpers for the Trades tab. Everything here is a typed view or a
 * restatement of facts already in the collector's output (scoring-system.md
 * §7) — never a recomputation of scores.
 */

// ---- typed views over fields the shared interfaces leave loose ----

/** §7.6 pick-anchor entries (typed view over TradeRec.pick_anchor). */
export interface PickAnchor {
  side: "give" | "get";
  pick: string;
  concrete: number;
  tranche: number;
  sell_floor: number;
}

export function pickAnchors(rec: TradeRec): PickAnchor[] {
  return (rec.pick_anchor ?? []) as PickAnchor[];
}

/** §7.3 rank score H = my score + 0.3 · clipped their score (on the doc). */
export function hScore(rec: TradeRec): number | null {
  const h = (rec as TradeRec & { rank_score_H?: number }).rank_score_H;
  return typeof h === "number" ? h : null;
}

/** trade_zone.zone is null in the data when their floor clears my ceiling. */
export function zoneValue(row: TradeZoneRow): number | null {
  const z = (row as Omit<TradeZoneRow, "zone"> & { zone: number | null }).zone;
  return typeof z === "number" ? z : null;
}

/** DIP entries are empty in current data; render whatever shape shows up. */
export function describeDip(entry: unknown): string {
  if (typeof entry === "string") return entry;
  if (entry && typeof entry === "object") {
    const e = entry as Record<string, unknown>;
    const name = [e.player, e.name, e.target, e.pick].find(
      (x) => typeof x === "string",
    );
    if (name) return name as string;
  }
  return JSON.stringify(entry);
}

// ---- acceptance layer labels (§7.4) ----

export function tierLabel(rec: TradeRec): string {
  if (rec.tier === "A") return "should accept";
  if (rec.tier === "B") return rec.posture_fit ? "worth asking" : "needs selling";
  return rec.posture_fit ? "thin for them" : "thin for them · misfit";
}

// ---- posture + "what they want" (§7.4 thresholds over league-table facts) ----

export function posture(omega: number): "Contender" | "On the fence" | "Rebuilder" {
  if (omega >= 0.55) return "Contender";
  if (omega <= 0.4) return "Rebuilder";
  return "On the fence";
}

export function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] ?? s[v] ?? s[0]}`;
}

/** Two weakest lineup groups by within-column rank (higher rank = weaker). */
function weakestSlots(row: LeagueRow): string {
  return Object.entries(row.lineup)
    .map(([slot, g]) => ({ slot, rank: g.rank }))
    .sort((a, b) => b.rank - a.rank)
    .slice(0, 2)
    .map((w) => `${w.slot} (${ordinal(w.rank)})`)
    .join(" and ");
}

function cutsClause(row: LeagueRow): string {
  const cuts = row.market.cuts;
  if (cuts === 0) return "No cuts due — room to take on bodies";
  if (cuts >= 4) return `${cuts} cuts due Aug 15 — motivated to shed bodies`;
  return `${cuts} cuts due Aug 15`;
}

/**
 * One honest sentence per opponent, derived from their ω posture and their
 * league-table row — weakest slot groups, futures rank, crunch pressure.
 */
export function wantsLine(row: LeagueRow): string {
  const p = posture(row.omega);
  if (p === "Contender")
    return `Wants now-help — players over picks; thinnest at ${weakestSlots(row)}. ${cutsClause(row)}.`;
  if (p === "Rebuilder")
    return `Wants futures — at least half the package in picks and under-25s (futures rank ${ordinal(row.future.F_rank)}). ${cutsClause(row)}.`;
  return `Takes either side of a fair deal; thinnest at ${weakestSlots(row)}. ${cutsClause(row)}.`;
}

// ---- opponent ordering: best available deal first, dealless teams last ----

const TIER_ORDER: Record<string, number> = { A: 0, B: 1, C: 2 };

export function opponentOrder(
  perOpp: Record<string, TradeRec[]>,
  rows: LeagueRow[],
  myTeam: string,
): string[] {
  const names = new Set<string>([
    ...Object.keys(perOpp),
    ...rows.map((r) => r.team).filter((t) => t !== myTeam),
  ]);
  const lRank = new Map(rows.map((r) => [r.team, r.L_rank] as const));
  return [...names].sort((a, b) => {
    const da = perOpp[a]?.[0];
    const db = perOpp[b]?.[0];
    const t =
      (da ? (TIER_ORDER[da.tier] ?? 3) : 4) - (db ? (TIER_ORDER[db.tier] ?? 3) : 4);
    if (t !== 0) return t;
    const h = (db ? (hScore(db) ?? 0) : -Infinity) - (da ? (hScore(da) ?? 0) : -Infinity);
    if (h !== 0) return h;
    return (lRank.get(a) ?? 99) - (lRank.get(b) ?? 99);
  });
}
