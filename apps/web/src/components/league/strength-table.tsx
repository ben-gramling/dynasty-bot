import type { LeagueRow, LeagueTableDoc } from "@/lib/queries";
import { Star } from "@/components/star";
import { fmtFaab, fmtValue } from "@/lib/format";
import { POSITIONS } from "@/components/league/chart-data";
import { fmtOmega, ord, slugFor } from "@/components/league/util";

/**
 * The headline strength map: one row per team, three strictly separated
 * column groups (scoring-system.md §8) — starting lineup (L + per-position
 * sums), future assets (F), market (ω / cuts / FAAB). Strength cells are
 * heat-tinted by within-column rank with the sanctioned sequential ramp
 * (sky-deep light→dark, docs/web-design.md §5); my row is anchored with the
 * six-pointed star. Team names link to the front-office cards below.
 */

/** Sequential single-hue heat: rank 1 deepest, last rank ~white. */
function heat(rank: number, teams: number): string {
  if (!rank) return "transparent";
  const a = (0.3 * (teams - rank + 1)) / teams;
  return `rgba(24, 119, 184, ${a.toFixed(3)})`; // sky-deep #1877B8
}

const groupEdge = { borderLeft: "1px solid var(--color-line)" };

function posTitle(row: LeagueRow, pos: string, teams: number): string {
  const g = row.lineup[pos];
  if (!g) return "";
  const players = g.players.map((p) => `${p.player} ${fmtValue(p.v)}`).join(" · ");
  return `${ord(g.rank)} of ${teams} — ${players}`;
}

export function StrengthTable({ table }: { table: LeagueTableDoc }) {
  const rows = [...table.rows].sort((a, b) => a.L_rank - b.L_rank);
  const n = rows.length;
  const my = table.meta.my_team;

  return (
    <div className="card-scroll">
      <table className="data-table min-w-[860px]">
        <thead>
          <tr>
            <th colSpan={2} aria-hidden />
            <th colSpan={6} style={groupEdge} className="pl-2">
              Starting lineup
            </th>
            <th colSpan={2} style={groupEdge} className="pl-2">
              Future assets
            </th>
            <th colSpan={3} style={groupEdge} className="pl-2">
              Market
            </th>
          </tr>
          <tr>
            <th className="num">#</th>
            <th>Team</th>
            <th className="num pl-2" style={groupEdge}>
              Strength
            </th>
            {POSITIONS.map((p) => (
              <th key={p} className="num">
                {p}
              </th>
            ))}
            <th className="num pl-2" style={groupEdge}>
              F
            </th>
            <th className="num">Rk</th>
            {/* keep the lowercase omega — .data-table th uppercases text */}
            <th className="num pl-2" style={{ ...groupEdge, textTransform: "none" }}>
              ω
            </th>
            <th className="num">Cuts</th>
            <th className="num">FAAB</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const me = r.team === my;
            return (
              <tr key={r.team} style={me ? { background: "#eaf4fb" } : undefined}>
                <td className="num text-ink-muted">{r.L_rank}</td>
                <td>
                  <a
                    href={`#${slugFor(r.team)}`}
                    className={`inline-flex items-center gap-1.5 text-ink hover:underline ${
                      me ? "font-semibold" : ""
                    }`}
                  >
                    {r.team}
                    {me ? <Star size={9} title="Your team" /> : null}
                  </a>
                </td>
                <td
                  className="num pl-2"
                  style={{ ...groupEdge, background: heat(r.L_rank, n) }}
                  title={`${ord(r.L_rank)} of ${n} — z ${r.L_z >= 0 ? "+" : "−"}${Math.abs(
                    r.L_z,
                  ).toFixed(2)}`}
                >
                  {fmtValue(r.L)}
                </td>
                {POSITIONS.map((p) => (
                  <td
                    key={p}
                    className="num"
                    style={{ background: heat(r.lineup[p]?.rank ?? 0, n) }}
                    title={posTitle(r, p, n)}
                  >
                    {fmtValue(r.lineup[p]?.sum ?? 0)}
                  </td>
                ))}
                <td
                  className="num pl-2"
                  style={{ ...groupEdge, background: heat(r.future.F_rank, n) }}
                  title={`Picks ${fmtValue(r.future.picks)} · taxi ${fmtValue(r.future.taxi)}`}
                >
                  {fmtValue(r.future.F)}
                </td>
                <td className="num text-ink-muted">{r.future.F_rank}</td>
                <td className="num pl-2 text-ink-muted" style={groupEdge}>
                  {fmtOmega(r.omega)}
                </td>
                <td
                  className="num text-ink-muted"
                  title={
                    r.market.cuts
                      ? `C ${fmtValue(r.market.C)} — ${r.market.cut_list.join(", ")}`
                      : "No forced cuts"
                  }
                >
                  {r.market.cuts}
                </td>
                <td className="num text-ink-muted">{fmtFaab(r.market.faab)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
