import type { LeagueRow, LeagueTableDoc, PickDetail } from "@/lib/queries";
import { Star } from "@/components/star";
import { fmtFaab, fmtValue } from "@/lib/format";
import { POSITIONS } from "@/components/league/chart-data";
import { fmtOmega, ord, slugFor } from "@/components/league/util";

/**
 * Front-office cards: one details/summary card per team (server-rendered,
 * works without JS). Roster by position with KTC values, owned picks priced,
 * omega posture, FAAB, forced-cut crunch. My card opens by default and adds
 * the my-team extras (sell floors, crunch due date, unvalued players).
 */

function SummaryStat({
  k,
  v,
  sub,
  keepCase = false,
}: {
  k: string;
  v: string;
  sub?: string;
  /** ω must stay lowercase — skip the uppercase transform. */
  keepCase?: boolean;
}) {
  return (
    <span className="inline-flex items-baseline gap-1 whitespace-nowrap">
      <span
        className={`text-[10.5px] font-medium tracking-[0.08em] text-ink-muted ${
          keepCase ? "" : "uppercase"
        }`}
      >
        {k}
      </span>
      <span className="num text-[12.5px]">{v}</span>
      {sub ? <span className="text-[11px] text-ink-muted">{sub}</span> : null}
    </span>
  );
}

function SectionH({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mb-1.5 text-[10.5px] font-medium uppercase tracking-[0.08em] text-ink-muted">
      {children}
    </h3>
  );
}

function PositionBlock({
  name,
  sum,
  rank,
  teams,
  players,
}: {
  name: string;
  sum: number;
  rank?: number;
  teams: number;
  players: { player: string; v: number }[];
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 border-b border-line pb-1">
        <span className="text-[10.5px] font-medium uppercase tracking-[0.08em] text-ink-muted">
          {name}
        </span>
        <span className="num text-[12px]">
          {fmtValue(sum)}
          {rank ? <span className="text-ink-muted"> · {ord(rank)} of {teams}</span> : null}
        </span>
      </div>
      {players.length ? (
        <ul className="mt-1 space-y-0.5">
          {players.map((p) => (
            <li key={p.player} className="flex items-baseline justify-between gap-2">
              <span className="truncate text-[12px]">{p.player}</span>
              <span className="num text-[12px] text-ink-muted">{fmtValue(p.v)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-[12px] text-ink-muted">Empty</p>
      )}
    </div>
  );
}

function PicksTable({
  picks,
  total,
  sellFloors,
}: {
  picks: PickDetail[];
  total: number;
  /** label → sell floor, my card only. */
  sellFloors?: Map<string, number>;
}) {
  if (!picks.length) return <p className="text-[12px] text-ink-muted">No picks owned.</p>;
  return (
    <div className="card-scroll">
      <table className="data-table data-table--auto">
        <thead>
          <tr>
            <th>Pick</th>
            <th>Band</th>
            <th className="num">Price</th>
            <th className="num">Market</th>
            {sellFloors ? <th className="num">Sell floor</th> : null}
          </tr>
        </thead>
        <tbody>
          {picks.map((p) => (
            <tr key={p.label}>
              <td className="whitespace-nowrap">
                <span className="num">{p.label}</span>
              </td>
              <td className="text-ink-muted" title={p.band_reason}>
                {p.band ?? "—"}
              </td>
              <td className="num">{fmtValue(p.p)}</td>
              <td className="num text-ink-muted">{fmtValue(p.mv)}</td>
              {sellFloors ? (
                <td className="num text-ink-muted">
                  {sellFloors.has(p.label) ? fmtValue(sellFloors.get(p.label)!) : "—"}
                </td>
              ) : null}
            </tr>
          ))}
          <tr>
            <td className="font-medium">Total</td>
            <td />
            <td className="num font-medium">{fmtValue(total)}</td>
            <td />
            {sellFloors ? <td /> : null}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function TeamCard({ row, table }: { row: LeagueRow; table: LeagueTableDoc }) {
  const my = table.my_team;
  const me = row.team === table.meta.my_team;
  const n = table.rows.length;
  const sellFloors = me
    ? new Map(
        Object.values(my.picks_by_year)
          .flat()
          .filter((p) => p.sell_floor !== undefined)
          .map((p) => [p.label, p.sell_floor!]),
      )
    : undefined;

  return (
    <details
      id={slugFor(row.team)}
      className="decomp card scroll-mt-20"
      open={me || undefined}
      style={me ? { borderColor: "var(--color-sky-deep)" } : undefined}
    >
      <summary>
        {me ? <Star size={11} title="Your team" /> : null}
        <span className={`text-[13.5px] ${me ? "font-semibold" : "font-medium"}`}>
          {row.team}
        </span>
        {me ? (
          <span className="text-[11.5px] text-ink-muted">what would it take</span>
        ) : null}
        <span className="mx-1 hidden flex-1 sm:block" />
        <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <SummaryStat k="L" v={fmtValue(row.L)} sub={ord(row.L_rank)} />
          <SummaryStat k="F" v={fmtValue(row.future.F)} sub={ord(row.future.F_rank)} />
          <SummaryStat k="ω" v={fmtOmega(row.omega)} keepCase />
          <SummaryStat k="FAAB" v={fmtFaab(row.market.faab)} />
          <SummaryStat k="Cuts" v={String(row.market.cuts)} />
        </span>
        <svg className="decomp-caret" width="10" height="10" viewBox="0 0 10 10" aria-hidden>
          <path d="M3 1.5 7 5 3 8.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </summary>

      <div className="mt-3 space-y-4 border-t border-line pt-3">
        <div>
          <SectionH>Starting lineup</SectionH>
          <div className="grid grid-cols-2 gap-x-5 gap-y-3 sm:grid-cols-3 lg:grid-cols-6">
            {POSITIONS.map((p) => {
              const g = row.lineup[p];
              return (
                <PositionBlock
                  key={p}
                  name={p}
                  sum={g?.sum ?? 0}
                  rank={g?.rank}
                  teams={n}
                  players={g?.players ?? []}
                />
              );
            })}
            <PositionBlock
              name="Taxi"
              sum={row.future.taxi}
              teams={n}
              players={row.future.taxi_detail}
            />
          </div>
        </div>

        <div>
          <SectionH>Picks</SectionH>
          <PicksTable
            picks={row.future.picks_detail}
            total={row.future.picks}
            sellFloors={sellFloors}
          />
        </div>

        <div>
          <SectionH>Market</SectionH>
          <p className="text-[12.5px]">
            Posture ω <span className="num">{fmtOmega(row.omega)}</span>
            <span className="text-ink-muted">
              {" "}
              · model suggests <span className="num">{fmtOmega(row.omega_suggest)}</span>
            </span>{" "}
            · FAAB <span className="num">{fmtFaab(row.market.faab)}</span>
          </p>
          <p className="mt-1 text-[12.5px]">
            {row.market.cuts ? (
              <>
                Forced cuts <span className="num">{row.market.cuts}</span> · C{" "}
                <span className="num">{fmtValue(row.market.C)}</span> —{" "}
                {row.market.cut_list.join(", ")}
                {me && my.crunch_due ? (
                  <span className="text-ink-muted"> · due at the {my.crunch_due}</span>
                ) : null}
              </>
            ) : (
              "No forced cuts."
            )}
          </p>
          {me && my.unvalued.length ? (
            <p className="mt-1 text-[12.5px] text-ink-muted">
              Unvalued rostered — {my.unvalued.join(", ")} (no KTC price; counts as a body,
              not value).
            </p>
          ) : null}
        </div>
      </div>
    </details>
  );
}

export function TeamDetails({ table }: { table: LeagueTableDoc }) {
  const rows = [...table.rows].sort((a, b) => a.L_rank - b.L_rank);
  return (
    <section aria-labelledby="front-offices">
      <h2 id="front-offices" className="display mb-2 text-[17px]">
        Front offices
      </h2>
      <div className="space-y-2">
        {rows.map((r) => (
          <TeamCard key={r.team} row={r} table={table} />
        ))}
      </div>
    </section>
  );
}
