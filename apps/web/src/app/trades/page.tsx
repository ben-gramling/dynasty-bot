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
 * Trades tab (scoring-system.md v5): the favor-stratified stored PAIR space
 * behind the finder's THREE dials (§4a/§5) — a δ SELECTOR (robust default +
 * presets 0/0.25/0.5/0.75/1; return(δ) re-scored client-side from each stored
 * pair's exact coordinates, a labeled preference view — the §2 objective
 * verdict never moves), a floor on TOTAL return(δ) (robust = the GUARANTEED
 * floor min(ΔS, ΔF) over face sent; presets 1/2.5/5/10/20, default 5), and a
 * counterparty-favorability FLOOR on min(f_buy, f_sell) (presets −10/−5/0/
 * +2.5/+5/no floor, KTC's own calculator variance units — ±5 = their
 * calculator literally says FAIR; replaces the v3.4.1 per-leg market-return
 * cap). Every stored pair is objectively good (both coordinates positive —
 * §11.8b(d)/§11.12(g) hard constraint) and fully count-neutral (exactly 0
 * players / 0 picks net for our side; a buy never goes out without its exit);
 * the dials filter/re-sort the stored list client-side while the inventory
 * line comes from the engine's honest favor-bucket × robust-return `bands`
 * grid. Unpaired legs and blocked buys stay in Mongo for the trade-negotiator
 * desk but do not render here (user: nothing without an associated hedge);
 * deep or constrained queries beyond stored inventory belong to the finder
 * (§4a), not this board. Reads Mongo only — every number is the engine's,
 * never recomputed here (return(δ) is arithmetic on stored numbers).
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
          The recommendation unit is the count-neutral pair (§5): a buy and
          its exit, distinct counterparties, no shared assets, netting exactly
          0 players and 0 picks for your side — players count wherever they
          land, picks regardless of year. The score is two objective
          coordinates (§2 v4), no blend, no parameter: starters (ΔS, your
          max-Σv lineup at raw KTC over active + taxi) and face (ΔF, the
          total KTC you own, players and picks alike). Every pair here is
          objectively good — both coordinates rise — so your gain is
          guaranteed between the floor and the ceiling whatever you think
          stored future capital is worth; the chip is the guaranteed ΔW, and
          the shipped ranking is maximin: best guaranteed floor first, ceiling
          as the tie-break. Coordinates are per side (face is zero-sum on a
          leg, starters are not), so a trade can be genuinely good for both
          parties, and a buy leg on its own can be floor-negative; the pair
          numbers are both legs together. Every leg passes the fairness gate —
          literally the totals their KTC calculator shows — and respects
          posture (BUYERs receive players, SELLERs picks). v5 gives the board
          the finder&apos;s three dials (§4a): a δ selector (a labeled
          preference view between win-now δ=0 and win-later δ=1 — return(δ)
          re-scored from stored coordinates, robust default = the guaranteed
          floor), a floor on total return(δ), and a counterparty-favorability
          floor in KTC&apos;s own variance units — per leg, favor is the
          signed skew their own calculator shows (±5 = it literally says
          FAIR), and the floor applies to the least-happy counterparty,
          min(f_buy, f_sell) — replacing the per-leg market-return cap (the
          raw skim diverges from their calculator by up to 14 pts). The
          inventory count under the dials is the engine&apos;s own and says
          which kind it is (v5.1): an exact count where the nightly collection
          walk ran to completion — so &ldquo;none&rdquo; there means none
          exists among the legs that run pooled — and a ≥ verified floor only
          where it saturated. Band
          ceilings on cards are negotiating room, not the opener.
        </p>
        <PairsBoard
          pairs={doc.pairs}
          presets={doc.presets}
          favorPresets={doc.favor_presets}
          deltaPresets={doc.delta_presets}
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
