import type { LeagueTableDoc, TradeRecsDoc } from "@/lib/queries";
import { getLeagueTable, getTradeRecs } from "@/lib/queries";
import { fmtDateTime } from "@/lib/format";
import { OpponentCard } from "@/components/trades/opponent-card";
import { TradeCard } from "@/components/trades/trade-card";
import { opponentOrder } from "@/components/trades/derive";

/**
 * Trades tab (scoring-system.md §7): the ranked league-wide offers, then all
 * 11 opponents — posture, what they want, best available deal or an honest
 * "no deal clears", and the §7.5 buy-zone diagnostic. Reads Mongo only.
 */
export default async function TradesPage() {
  let doc: TradeRecsDoc | null;
  let league: LeagueTableDoc | null;
  try {
    [doc, league] = await Promise.all([getTradeRecs(), getLeagueTable()]);
  } catch {
    return (
      <section className="card">
        <h1 className="display text-[22px]">Trades</h1>
        <p className="mt-2 text-ink-muted">
          Can&apos;t reach the database — check MONGODB_URI and retry.
        </p>
      </section>
    );
  }

  if (!doc) {
    return (
      <section className="card">
        <h1 className="display text-[22px]">Trades</h1>
        <p className="mt-2 text-ink-muted">No collector run yet — hit Refresh.</p>
      </section>
    );
  }

  if (doc.disabled) {
    return (
      <section className="card">
        <h1 className="display text-[22px]">Trades</h1>
        <p className="mt-2 text-ink-muted">
          Trade deadline passed (week 11) — offers return with the new league year.
        </p>
      </section>
    );
  }

  const rows = league?.rows ?? [];
  const rowsByTeam = new Map(rows.map((r) => [r.team, r] as const));
  const myCuts = rowsByTeam.get(doc.meta.my_team)?.market.cut_list ?? [];
  const omegaMe = doc.meta.omega_me;
  const opponents = opponentOrder(doc.per_opponent ?? {}, rows, doc.meta.my_team);
  const zone = doc.trade_zone ?? [];

  return (
    <>
      <h1 className="sr-only">Trades</h1>

      <section aria-labelledby="best-offers">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 id="best-offers" className="display text-[22px]">
            Best offers
          </h2>
          <p className="text-[11.5px] text-ink-muted">
            Top {doc.recommendations.length} league-wide · acceptance tier first, then
            H · computed {fmtDateTime(doc.computed_at)}
          </p>
        </div>
        {doc.recommendations.length ? (
          <div className="mt-3 space-y-3">
            {doc.recommendations.map((rec, i) => (
              <TradeCard
                key={i}
                rec={rec}
                rank={i + 1}
                omegaMe={omegaMe}
                myCuts={myCuts}
              />
            ))}
          </div>
        ) : (
          <div className="card mt-3">
            <p className="text-ink-muted">
              No offer clears today — no package passes the fairness band, the
              anti-fleece cap, and two-sided value. Holding is the move.
            </p>
          </div>
        )}
      </section>

      <section aria-labelledby="by-opponent" className="mt-8">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 id="by-opponent" className="display text-[22px]">
            Opponent by opponent
          </h2>
          <p className="text-[11.5px] text-ink-muted">
            All {opponents.length} teams · sorted by best available deal · posture
            from ω seed
          </p>
        </div>
        <div className="mt-3 space-y-3">
          {opponents.map((team) => (
            <OpponentCard
              key={team}
              team={team}
              row={rowsByTeam.get(team)}
              deals={doc.per_opponent?.[team] ?? []}
              zone={zone.filter((z) => z.owner === team)}
              omegaMe={omegaMe}
              myCuts={myCuts}
            />
          ))}
        </div>
      </section>
    </>
  );
}
