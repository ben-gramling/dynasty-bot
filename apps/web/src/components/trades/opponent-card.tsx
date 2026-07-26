import type { LeagueRow, TradeRec, TradeZoneRow } from "@/lib/queries";
import { fmtFaab, fmtSigned, fmtValue } from "@/lib/format";
import { TradeCard } from "./trade-card";
import { ordinal, posture, wantsLine, zoneValue } from "./derive";

/**
 * One opponent block: posture (ω seed) + an honest "what they want" line
 * derived from their league-table row, the best available deal (top-3
 * variants behind a details toggle) or a "no deal clears" state, and the
 * §7.5 trade-zone diagnostic where targets exist on that roster.
 */
export function OpponentCard({
  team,
  row,
  deals,
  zone,
  omegaMe,
  myCuts,
}: {
  team: string;
  /** Their league-table row; undefined only if the league doc is missing. */
  row?: LeagueRow;
  deals: TradeRec[];
  zone: TradeZoneRow[];
  omegaMe: number;
  myCuts: string[];
}) {
  const [best, ...rest] = deals;
  return (
    <article className="card">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="display text-[17px]">{team}</h3>
        {row ? (
          <>
            <span className="text-[11px] uppercase tracking-[0.08em] text-ink-muted">
              {posture(row.omega)}
            </span>
            <span className="num ml-auto text-[11.5px] text-ink-muted">
              ω {row.omega.toFixed(2)} · L {ordinal(row.L_rank)} · F{" "}
              {ordinal(row.future.F_rank)} · cuts {row.market.cuts} ·{" "}
              {fmtFaab(row.market.faab)} faab
            </span>
          </>
        ) : null}
      </header>
      {row ? (
        <p className="mt-1.5 text-[12.5px] text-ink-muted">{wantsLine(row)}</p>
      ) : null}

      {best ? (
        <div className="mt-3">
          <h4 className="text-[10.5px] font-medium uppercase tracking-[0.08em] text-ink-muted">
            Best available deal
          </h4>
          <div className="mt-1">
            <TradeCard
              rec={best}
              omegaMe={omegaMe}
              myCuts={myCuts}
              frame="inset"
              showCounterparty={false}
            />
          </div>
          {rest.length ? (
            <details className="mt-2">
              <summary className="cursor-pointer list-none text-[12px] text-sky-deep [&::-webkit-details-marker]:hidden">
                + {rest.length} more variant{rest.length > 1 ? "s" : ""}
              </summary>
              <div className="mt-2 space-y-2">
                {rest.map((r, i) => (
                  <TradeCard
                    key={i}
                    rec={r}
                    omegaMe={omegaMe}
                    myCuts={myCuts}
                    frame="inset"
                    showCounterparty={false}
                  />
                ))}
              </div>
            </details>
          ) : null}
        </div>
      ) : (
        <p className="mt-3 text-[12.5px] text-ink-muted">
          No deal clears — no 1–3 for 1–3 package passes the fairness band, the
          anti-fleece cap, and two-sided value against this roster.
        </p>
      )}

      {zone.length ? <ZoneTable rows={zone} /> : null}
    </article>
  );
}

function ZoneTable({ rows }: { rows: TradeZoneRow[] }) {
  return (
    <div className="mt-3">
      <h4 className="text-[10.5px] font-medium uppercase tracking-[0.08em] text-ink-muted">
        Buy zone{" "}
        <span className="font-normal normal-case tracking-normal">
          — what a straight 1-for-1 would clear (§7.5)
        </span>
      </h4>
      <div className="card-scroll mt-1">
        <table className="data-table">
          <thead>
            <tr>
              <th>Target</th>
              <th className="num">Value</th>
              <th className="num">Their floor</th>
              <th className="num">My ceiling</th>
              <th className="num">Zone</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const z = zoneValue(r);
              return (
                <tr key={r.target}>
                  <td>{r.target}</td>
                  <td className="num">{fmtValue(r.v)}</td>
                  <td className="num">{fmtValue(r.their_floor)}</td>
                  <td className="num">{fmtValue(r.my_ceiling)}</td>
                  <td className="num">
                    {z === null ? (
                      <span className="text-ink-muted">none</span>
                    ) : (
                      fmtSigned(z)
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
