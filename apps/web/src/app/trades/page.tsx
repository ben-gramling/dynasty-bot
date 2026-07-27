import type { Metadata } from "next";
import Link from "next/link";
import type { LeagueTableDoc, TradeRecsDoc } from "@/lib/queries";
import { getLeagueTable, getTradeRecs } from "@/lib/queries";
import { fmtDateTime, fmtValue } from "@/lib/format";
import { PairCard } from "@/components/trades/pair-card";
import { TradeCard } from "@/components/trades/trade-card";
import { marketStrip } from "@/components/trades/derive";

export const metadata: Metadata = {
  title: "Trades — Chicago Dynasty",
};

/**
 * Trades tab (scoring-system.md v3): the ranked gated legs ("the book", §5),
 * the roster-neutral pairings, and a pointer into the League tab's market
 * map (§7 targeting console). Reads Mongo only — every number is the
 * engine's, never recomputed here.
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

  const recs = doc.recommendations;
  const byId = new Map(recs.map((r) => [r.id, r] as const));
  const strip = marketStrip(league?.rows ?? [], doc.meta.my_team);

  return (
    <div className="space-y-8">
      <h1 className="sr-only">Trades</h1>

      <section aria-labelledby="best-trades">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 id="best-trades" className="display text-[22px]">
            Best trades
          </h2>
          <p className="num text-[11.5px] text-ink-muted">
            {recs.length} gated legs · ranked by ΔW(you) · floor{" "}
            {fmtValue(doc.meta.w_min)} · computed {fmtDateTime(doc.computed_at)}
          </p>
        </div>
        <p className="mt-1 text-[12.5px] text-ink-muted">
          Every leg passes the fairness gate: inside the observed band, under the
          1.35× anti-fleece cap, legal on both rosters. Value at the favorable
          band edge is the whole edge — harvested repeatedly, never past it.
        </p>
        {recs.length ? (
          <div className="mt-3 space-y-3">
            {recs.map((rec) => (
              <TradeCard key={rec.id} rec={rec} />
            ))}
          </div>
        ) : (
          <div className="card mt-3">
            <p className="text-ink-muted">
              No trade clears today — nothing beats the {fmtValue(doc.meta.w_min)}{" "}
              noise floor inside the fairness band and the anti-fleece cap.
              Holding is the move.
            </p>
          </div>
        )}
        {doc.notes.length ? (
          <ul className="mt-3 space-y-0.5 text-[11.5px] text-ink-muted">
            {doc.notes.map((n) => (
              <li key={n}>· {n}</li>
            ))}
          </ul>
        ) : null}
      </section>

      <section aria-labelledby="pairs">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 id="pairs" className="display text-[22px]">
            Roster-neutral pairs
          </h2>
          <p className="text-[11.5px] text-ink-muted">
            Buy-legs bundled with their hedge sell-legs — plans net Δ(roster) ≤ 0
          </p>
        </div>
        {doc.pairs.length ? (
          <div className="mt-3 space-y-3">
            {doc.pairs.map((pair) => (
              <PairCard key={pair.legs.join("+")} pair={pair} byId={byId} />
            ))}
          </div>
        ) : (
          <div className="card mt-3">
            <p className="text-ink-muted">
              No pairings needed — every recommended leg is a standalone sell or
              already roster-neutral.
            </p>
          </div>
        )}
      </section>

      <section aria-labelledby="market-map" className="card">
        <h2 id="market-map" className="display text-[17px]">
          Market map
        </h2>
        <p className="mt-1.5 text-[12.5px]">
          {strip.length ? (
            <>
              {strip.map((e, i) => (
                <span key={e.team}>
                  {i > 0 ? " · " : ""}
                  <span className="font-medium">{e.team}</span>{" "}
                  <span className="text-ink-muted">
                    {e.posture} ({e.count}{" "}
                    {e.posture === "BUYER" ? "buy" : "sell"}
                    {e.count > 1 ? "s" : ""} on record)
                  </span>
                </span>
              ))}
              <span className="text-ink-muted"> — everyone else NEUTRAL.</span>
            </>
          ) : (
            <span className="text-ink-muted">
              No BUYER or SELLER classifications in the trailing 12 months —
              the whole league reads NEUTRAL.
            </span>
          )}
        </p>
        <p className="mt-1.5 text-[12.5px] text-ink-muted">
          Postures, evidence trades, holes, pick inventories, and FAAB live on
          the{" "}
          <Link href="/league" className="text-sky-deep hover:underline">
            League tab&apos;s market map
          </Link>{" "}
          — the targeting console behind these cards.
        </p>
      </section>
    </div>
  );
}
