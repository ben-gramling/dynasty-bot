import type { Metadata } from "next";
import Link from "next/link";
import type { LeagueTableDoc, TradeRecsDoc } from "@/lib/queries";
import { getLeagueTable, getTradeRecs } from "@/lib/queries";
import { PairsBoard } from "@/components/trades/pairs-board";
import { marketStrip } from "@/components/trades/derive";

export const metadata: Metadata = {
  title: "Trades — Chicago Dynasty",
};

/**
 * Trades tab (scoring-system.md v3.4): the stratified stored PAIR space
 * behind the target-return RANGE, priced by the wealth ledger (starters +
 * picks, per side, never zero-sum). Pairs stay fully count-neutral (exactly
 * 0 players / 0 picks net for our side; a buy never goes out without its
 * exit); the range controls (min presets 1 / 2.5 / 5 / 10 / 20, default 5;
 * max presets 2.5 / 5 / 10 / 20 / no cap, default no cap) filter the stored
 * list client-side while the inventory line comes from the engine's honest
 * per-band `bands` counts. Unpaired legs and blocked buys stay in Mongo for
 * the trade-negotiator desk but do not render here (user: nothing without an
 * associated hedge). Reads Mongo only — every number is the engine's, never
 * recomputed here.
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

  const strip = marketStrip(league?.rows ?? [], doc.meta.my_team);

  return (
    <div className="space-y-8">
      <h1 className="sr-only">Trades</h1>

      <section aria-labelledby="pairs">
        <h2 id="pairs" className="display text-[22px]">
          Recommended trades
        </h2>
        <p className="mt-1 text-[12.5px] text-ink-muted">
          The recommendation unit is the count-neutral pair (§5 v3.3): a buy
          and its exit, distinct counterparties, no shared assets, netting
          exactly 0 players and 0 picks for your side — players count wherever
          they land, picks regardless of year. ΔW is the wealth ledger (§2
          v3.4): your starting lineup at raw KTC over active + taxi, plus picks
          at tranche — bench value is trade currency, not wealth. It is per
          side, so a good pair can lift both ledgers, and a buy leg on its own
          is normally negative; the pair number is both legs together. Every
          leg passes the fairness gate — literally the totals their KTC
          calculator shows — and respects posture (BUYERs receive players,
          SELLERs picks); the range sets the return window, on the inventory
          you send. Band ceilings on cards are negotiating room, not the opener.
        </p>
        <PairsBoard
          pairs={doc.pairs}
          presets={doc.presets}
          bands={doc.bands ?? []}
          computedAt={doc.computed_at}
        />
        {doc.notes.length ? (
          <ul className="mt-3 space-y-0.5 text-[11.5px] text-ink-muted">
            {doc.notes.map((n) => (
              <li key={n}>· {n}</li>
            ))}
          </ul>
        ) : null}
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
