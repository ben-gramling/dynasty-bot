import type { Metadata } from "next";
import { getLeagueTable } from "@/lib/queries";
import { fmtDateTime, fmtValue } from "@/lib/format";
import { toChartTeams } from "@/components/league/chart-data";
import { OpenOnHash } from "@/components/league/open-on-hash";
import { StrengthChart } from "@/components/league/strength-chart";
import { StrengthTable } from "@/components/league/strength-table";
import { TeamDetails } from "@/components/league/team-details";

export const metadata: Metadata = {
  title: "League — Chicago Dynasty",
};

export default async function LeaguePage() {
  let table = null;
  try {
    table = await getLeagueTable();
  } catch {
    return (
      <section className="card">
        <h1 className="display text-[22px]">League</h1>
        <p className="mt-2 text-ink-muted">
          Can&apos;t reach the database — check MONGODB_URI and retry.
        </p>
      </section>
    );
  }

  if (!table) {
    return (
      <section className="card">
        <h1 className="display text-[22px]">League</h1>
        <p className="mt-2 text-ink-muted">No collector run yet — hit Refresh.</p>
      </section>
    );
  }

  const { meta } = table;
  const chartTeams = toChartTeams(table.rows, meta.my_team);

  return (
    <div className="space-y-4">
      <OpenOnHash />

      <section className="card" aria-labelledby="strength-map">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h1 id="strength-map" className="display text-[22px]">
            Strength map
          </h1>
          <p className="num text-[11.5px] text-ink-muted">
            {table.rows.length} teams · {meta.mode} · {meta.draft_status.replace(/_/g, " ")}{" "}
            · L mean {fmtValue(table.L_mean)} · σ {fmtValue(table.L_sigma)} · computed{" "}
            {fmtDateTime(table.computed_at)}
          </p>
        </div>
        <StrengthTable table={table} />
        <p className="mt-2 text-[11.5px] text-ink-muted">
          Starting lineup and future assets are strictly separate: Strength (L) prices the
          expected starting lineup; F banks picks and taxi. Deeper cells rank higher in
          their column. Hover a cell for the players behind it; click a team for the full
          front office.
        </p>
      </section>

      <section className="card" aria-labelledby="position-chart">
        <h2 id="position-chart" className="display mb-3 text-[17px]">
          Position by position
        </h2>
        <StrengthChart teams={chartTeams} />
      </section>

      <TeamDetails table={table} />
    </div>
  );
}
