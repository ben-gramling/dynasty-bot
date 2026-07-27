import type { LeagueRow, LeagueTableDoc } from "@/lib/queries";
import { Star } from "@/components/star";
import { fmtFaab, fmtValue } from "@/lib/format";
import { POSITIONS } from "@/components/league/chart-data";
import { ord, slugFor } from "@/components/league/util";

/**
 * The headline strength map: one row per team, three strictly separated
 * column groups (scoring-system.md v3 §7) — starting lineup (L + per-position
 * sums), future assets (F), market (posture / holes / pick inventory / FAAB —
 * the targeting console). Strength cells are heat-tinted by within-column
 * rank with the sanctioned sequential ramp (sky-deep light→dark,
 * docs/web-design.md §5); my row is anchored with the six-pointed star.
 * Team names link to the front-office cards below.
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

/** Hover: the evidence trades behind the posture label, human-readably (§4). */
function postureTitle(row: LeagueRow): string {
  const m = row.market;
  const head = `${m.posture} — bought ${m.bought} / sold ${m.sold} of ${m.trades_12mo} trades in 12 months`;
  if (!m.evidence.length) return head;
  const lines = m.evidence.map((e) => `${e.date} — ${e.summary}`);
  return `${head}\n${lines.join("\n")}`;
}

function holesTitle(row: LeagueRow, teams: number): string {
  const holes = row.market.holes;
  if (!holes.length) return "No starting-lineup group ranked in the league's bottom quarter";
  return holes.map((h) => `${h.pos} ${ord(h.rank)} of ${teams}`).join(" · ");
}

function picksTitle(row: LeagueRow): string {
  const inv = row.market.pick_inventory;
  const byYear = Object.entries(inv.by_year)
    .map(([y, n]) => `${y}: ${n}`)
    .join(" · ");
  return `${inv.count} picks worth ${fmtValue(inv.value)} at tranche — ${byYear}`;
}

export function StrengthTable({ table }: { table: LeagueTableDoc }) {
  const rows = [...table.rows].sort((a, b) => a.L_rank - b.L_rank);
  const n = rows.length;
  const my = table.meta.my_team;

  return (
    <div className="card-scroll">
      <table className="data-table min-w-[960px]">
        <thead>
          <tr>
            <th colSpan={2} aria-hidden />
            <th colSpan={6} style={groupEdge} className="pl-2">
              Starting lineup
            </th>
            <th colSpan={2} style={groupEdge} className="pl-2">
              Future assets
            </th>
            <th colSpan={5} style={groupEdge} className="pl-2">
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
            <th className="pl-2" style={groupEdge}>
              Posture
            </th>
            <th>Holes</th>
            <th className="num">Picks</th>
            <th className="num">Pick Σv</th>
            <th className="num">FAAB</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const me = r.team === my;
            const m = r.market;
            const neutral = m.posture === "NEUTRAL";
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
                <td
                  className={`pl-2 whitespace-nowrap ${neutral ? "text-ink-muted" : "font-medium"}`}
                  style={groupEdge}
                  title={postureTitle(r)}
                >
                  {m.posture.toLowerCase()}
                  {m.evidence.length ? (
                    <span className="num text-ink-muted"> ·{m.evidence.length}</span>
                  ) : null}
                </td>
                <td
                  className="whitespace-nowrap text-ink-muted"
                  title={holesTitle(r, n)}
                >
                  {m.holes.length ? m.holes.map((h) => h.pos).join(" ") : "—"}
                </td>
                <td className="num text-ink-muted" title={picksTitle(r)}>
                  {m.pick_inventory.count}
                </td>
                <td className="num text-ink-muted" title={picksTitle(r)}>
                  {fmtValue(m.pick_inventory.value)}
                </td>
                <td className="num text-ink-muted">{fmtFaab(m.faab)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
