import type { TradePair, TradeRec } from "@/lib/queries";
import { fmtSigned } from "@/lib/format";
import { ValueChip } from "@/components/value-chip";
import { assetSummary, pairLegs } from "./derive";

/**
 * One §5 roster-neutral bundle: the buy-leg with its hedge sell-leg, listed
 * in execution order (sell first at the roster cap), the combined ΔW, and
 * the agreement-first protocol note. Legs reference the ranked cards above
 * by id. A one-leg "pair" is a buy still waiting for its hedge.
 */
export function PairCard({
  pair,
  byId,
}: {
  pair: TradePair;
  byId: Map<string, TradeRec>;
}) {
  const legs = pairLegs(pair, byId);
  const hedged = legs.filter((l) => l !== null).length > 1;
  return (
    <article className="card">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="display text-[15px]">
          {hedged ? "Buy + sell" : "Buy — hedge missing"}
        </h3>
        <span className="num text-[11px] text-ink-muted">{pair.legs.join(" + ")}</span>
        <span className="ml-auto flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <ValueChip label="pair ΔW" value={pair.dW} emphasis />
          <span
            className="text-[11.5px] text-ink-muted"
            title="Recommended plans net Δ(roster count) ≤ 0 overall (§5)"
          >
            net roster{" "}
            <span className={`num${pair.net_roster > 0 ? " font-medium text-ink" : ""}`}>
              {fmtSigned(pair.net_roster)}
            </span>
          </span>
        </span>
      </header>

      <ol className="mt-2 space-y-1.5">
        {legs.map((leg, i) =>
          leg ? (
            <li key={leg.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[12.5px]">
              <span className="num w-4 text-right text-ink-muted">{i + 1}</span>
              <span className="rounded border border-line bg-surface px-1 text-[9.5px] uppercase tracking-[0.08em] text-ink-muted">
                {leg.leg_type}
              </span>
              <a href={`#leg-${leg.id}`} className="num text-sky-deep hover:underline">
                {leg.id}
              </a>
              <span className="text-ink-muted">with</span>
              <span className="font-medium">{leg.counterparty}</span>
              <span className={`num${leg.dW.me < 0 ? " text-star" : ""}`}>
                {fmtSigned(leg.dW.me)}
              </span>
              <span className="min-w-0 basis-full pl-6 text-[12px] text-ink-muted sm:basis-auto sm:pl-0">
                {assetSummary(leg).give} → {assetSummary(leg).get}
              </span>
            </li>
          ) : (
            <li key={pair.legs[i]} className="pl-6 text-[12.5px] text-ink-muted">
              <span className="num">{pair.legs[i]}</span> — leg no longer on the board
            </li>
          ),
        )}
      </ol>

      <p className="mt-2 border-t border-line pt-2 text-[11.5px] text-ink-muted">
        {pair.note}
        {hedged
          ? " · after both execute, the whole board recomputes from fresh rosters"
          : null}
      </p>
    </article>
  );
}
