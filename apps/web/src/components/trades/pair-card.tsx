import type { TradePair } from "@/lib/queries";
import { fmtPct, fmtSigned } from "@/lib/format";
import { ValueChip } from "@/components/value-chip";
import { TradeCard } from "./trade-card";
import { pairLegs } from "./derive";

/**
 * One §5 v3.2 count-neutral hedged pair — the board's PRIMARY unit: the buy
 * side and its hedge sell side as full embedded leg cards, listed in execution
 * order (sell first at the roster cap), with the pair's GUARANTEED floor (§2
 * v4: min of the exact combined coordinates, both legs applied together — a
 * floor-negative leg is normal, the pair's verdict is what is constrained),
 * the interval up to the ceiling, the combined "starters · face" coordinates,
 * each leg's market return (v3.4.1 — the leg-cap dial's input), the
 * neutrality badge (exactly 0 players / 0 picks net for you), the posture-fit
 * summary, and the agreement-first sequencing note. Pre-v4 docs fall back to
 * the stored pair ΔW.
 */
export function PairCard({ pair }: { pair: TradePair }) {
  const legs = pairLegs(pair);
  return (
    <article className="rounded-lg border border-line bg-surface p-3 sm:p-4">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="display text-[15px]">Buy + sell</h3>
        <span className="num text-[11px] text-ink-muted">{pair.id}</span>
        <span
          className="rounded border border-sky-deep px-1.5 py-0.5 text-[10px] uppercase tracking-[0.08em] text-sky-deep"
          title="§5 v3.2 strict: the pair leaves you with exactly the same number of players and picks — players count wherever they land (active or taxi); picks regardless of year"
        >
          0 players / 0 picks net
        </span>
        <span className="text-[11.5px] text-ink-muted">{pair.fit_summary}</span>
        <span className="ml-auto flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span
            className="num text-[13px] font-medium text-sky-deep"
            title="TOTAL return on inventory deployed (§5 v4): the pair's guaranteed floor min(ΔS, ΔF) ÷ Σ face v of every asset you send across both legs — the floor dial's key and the primary sort key (ceiling breaks ties)"
          >
            {fmtPct(pair.return_pct, 1)} return
          </span>
          {pair.leg_returns ? (
            <span
              className="text-[11.5px] text-ink-muted"
              title="Each leg's market return (§5 v3.4.1): face ΔF(you) ÷ face Σv you send on that leg — the skim that leg's counterparty sees; the leg-cap dial filters on the larger of the two"
            >
              legs: buy <span className="num">{fmtSigned(pair.leg_returns.buy, 1)}%</span>{" "}
              · sell <span className="num">{fmtSigned(pair.leg_returns.sell, 1)}%</span>{" "}
              market
            </span>
          ) : null}
          {pair.floor !== undefined ? (
            <ValueChip label="guaranteed ΔW" value={pair.floor} emphasis />
          ) : pair.dW_combined !== undefined ? (
            <ValueChip label="pair ΔW" value={pair.dW_combined} emphasis />
          ) : null}
          {pair.ceiling !== undefined ? (
            <span
              className="text-[11.5px] text-ink-muted"
              title="The §2 v4 interval: with both legs executed your gain lies between the guaranteed floor and this ceiling, whatever your stored-value preference — every stored pair is objectively good (both coordinates positive)"
            >
              up to <span className="num">{fmtSigned(pair.ceiling)}</span>
            </span>
          ) : null}
          {pair.coords ? (
            <span
              className="text-[11.5px] text-ink-muted"
              title="The pair's combined coordinates (§2 v4): starters = ΔS, the max-Σv lineup at raw KTC over active + taxi, both legs applied together; face = ΔF, the total face you gain across both legs. The gain interval runs between them."
            >
              starters <span className="num">{fmtSigned(pair.coords.dS)}</span> ·
              face <span className="num">{fmtSigned(pair.coords.dF)}</span>
            </span>
          ) : pair.dW_combined_parts?.dS !== undefined &&
            pair.dW_combined_parts?.dT !== undefined ? (
            <span className="text-[11.5px] text-ink-muted">
              starters{" "}
              <span className="num">{fmtSigned(pair.dW_combined_parts.dS)}</span> ·
              stored{" "}
              <span className="num">{fmtSigned(pair.dW_combined_parts.dT)}</span>
            </span>
          ) : null}
          <span
            className="text-[11.5px] text-ink-muted"
            title="Δ(active roster) across both legs — sequencing context only; count-neutrality is the badge (§5 v3.2)"
          >
            net roster{" "}
            <span className={`num${pair.net_roster > 0 ? " font-medium text-ink" : ""}`}>
              {fmtSigned(pair.net_roster)}
            </span>
          </span>
        </span>
      </header>

      <div className="mt-3 space-y-3">
        {legs.map((leg, i) => (
          <div key={leg.id} className="flex gap-2">
            <span
              className="num mt-1 w-4 shrink-0 text-right text-[12px] text-ink-muted"
              title="Execution order — sell first at the roster cap (§5)"
            >
              {i + 1}
            </span>
            <div className="min-w-0 grow">
              <TradeCard rec={leg} compact />
            </div>
          </div>
        ))}
      </div>

      <p className="mt-3 border-t border-line pt-2 text-[11.5px] text-ink-muted">
        {pair.sequencing} · after both execute, the whole board recomputes from
        fresh rosters
      </p>
    </article>
  );
}
