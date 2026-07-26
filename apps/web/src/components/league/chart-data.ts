/**
 * Server-side mapper that slims league-table rows into the plain props the
 * client chart needs (keeps the RSC payload small — no pick band prose).
 */
import type { LeagueRow } from "@/lib/queries";

export const POSITIONS = ["QB", "RB", "WR", "TE", "FLEX"] as const;
export type Position = (typeof POSITIONS)[number];

/** What the chart can plot: total strength, one slot group, or future assets. */
export type Metric = "L" | Position | "F";

export interface ChartPlayer {
  player: string;
  v: number;
}

export interface ChartPosGroup {
  sum: number;
  rank: number;
  players: ChartPlayer[];
}

export interface ChartTeam {
  team: string;
  me: boolean;
  L: number;
  L_rank: number;
  L_z: number;
  pos: Record<Position, ChartPosGroup>;
  F: number;
  F_rank: number;
  picks: number;
  picksCount: number;
  taxi: number;
  taxiCount: number;
}

export function toChartTeams(rows: LeagueRow[], myTeam: string): ChartTeam[] {
  return rows.map((r) => {
    const pos = {} as Record<Position, ChartPosGroup>;
    for (const p of POSITIONS) {
      const g = r.lineup[p];
      pos[p] = g
        ? {
            sum: g.sum,
            rank: g.rank,
            players: g.players.map(({ player, v }) => ({ player, v })),
          }
        : { sum: 0, rank: 0, players: [] };
    }
    return {
      team: r.team,
      me: r.team === myTeam,
      L: r.L,
      L_rank: r.L_rank,
      L_z: r.L_z,
      pos,
      F: r.future.F,
      F_rank: r.future.F_rank,
      picks: r.future.picks,
      picksCount: r.future.picks_detail.length,
      taxi: r.future.taxi,
      taxiCount: r.future.taxi_detail.length,
    };
  });
}
