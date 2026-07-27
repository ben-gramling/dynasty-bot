import type { Metadata } from "next";
import Link from "next/link";
import type { LeagueTableDoc, TradeRecsDoc } from "@/lib/queries";
import { getLeagueTable, getTradeRecs } from "@/lib/queries";
import { fmtDateTime, fmtSigned, fmtValue } from "@/lib/format";
import { PairCard } from "@/components/trades/pair-card";
import { TradeCard } from "@/components/trades/trade-card";
import { marketStrip } from "@/components/trades/derive";

export const metadata: Metadata = {
  title: "Trades — Chicago Dynasty",
};

/**
 * Trades tab (scoring-system.md v3.1): the hedged PAIRS first (the §5 v3.1
 * recommendation unit — a buy never goes out without its exit), then the
 * labeled sell-side legs, the watch list of blocked buys, and a pointer into
 * the League tab's market map (§7 targeting console). Reads Mongo only —
 * every number is the engine's, never recomputed here.
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
  const strip = marketStrip(league?.rows ?? [], doc.meta.my_team);

  return (
    <div className="space-y-8">
      <h1 className="sr-only">Trades</h1>

      <section aria-labelledby="pairs">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 id="pairs" className="display text-[22px]">
            Recommended trades
          </h2>
          <p className="num text-[11.5px] text-ink-muted">
            {doc.pairs.length} hedged pair{doc.pairs.length === 1 ? "" : "s"} ·
            ranked fit, then combined ΔW(you) · floor {fmtValue(doc.meta.w_min)} ·
            computed {fmtDateTime(doc.computed_at)}
          </p>
        </div>
        <p className="mt-1 text-[12.5px] text-ink-muted">
          The recommendation unit is the hedged pair (§5 v3.1): a buy and its
          exit, no shared assets, net Δ(roster) ≤ 0. Every leg passes the
          fairness gate at the smallest in-band gap clearing the floor — the
          band ceiling on each card is negotiating room, not the opener.
        </p>
        {doc.pairs.length ? (
          <div className="mt-3 space-y-3">
            {doc.pairs.map((pair) => (
              <PairCard key={pair.id} pair={pair} />
            ))}
          </div>
        ) : (
          <div className="card mt-3">
            <p className="text-ink-muted">
              No hedged pair clears today — nothing beats the{" "}
              {fmtValue(doc.meta.w_min)} noise floor inside the fairness band
              with a clean exit attached. Holding is the move.
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

      <section aria-labelledby="sell-legs">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 id="sell-legs" className="display text-[22px]">
            Sell-side legs (no hedge needed)
          </h2>
          <p className="text-[11.5px] text-ink-muted">
            Standalone sells and roster-neutral legs — they free space; never a
            standalone buy
          </p>
        </div>
        {recs.length ? (
          <div className="mt-3 space-y-3">
            {recs.map((rec) => (
              <TradeCard key={rec.id} rec={rec} />
            ))}
          </div>
        ) : (
          <div className="card mt-3">
            <p className="text-ink-muted">
              No standalone sell clears today — the pairs above carry the whole
              board.
            </p>
          </div>
        )}
      </section>

      {doc.watch.length ? (
        <section aria-labelledby="watch" className="card">
          <h2 id="watch" className="display text-[17px]">
            Watch — buys with no clean exit
          </h2>
          <p className="mt-1 text-[12.5px] text-ink-muted">
            Worth wanting, not worth proposing (§5 v3.1): a buy without an
            identified exit never goes out.
          </p>
          <ul className="mt-2 space-y-1 text-[12.5px]">
            {doc.watch.map((w) => (
              <li key={`${w.counterparty}-${w.get.join("+")}`}>
                <span className="font-medium">{w.counterparty}</span>:{" "}
                {w.get.join(", ")} for {w.give.join(", ")}{" "}
                <span className="num">({fmtSigned(w.dW)})</span>{" "}
                <span className="text-ink-muted">— {w.blocker}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

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
