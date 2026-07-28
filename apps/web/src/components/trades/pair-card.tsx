import type { TradePair } from "@/lib/queries";
import { fmtPct, fmtSigned } from "@/lib/format";
import { ValueChip } from "@/components/value-chip";
import { TradeCard } from "./trade-card";
import { pairLegs } from "./derive";

/**
 * One §5 v3.2 count-neutral hedged pair — the board's PRIMARY unit: the buy
 * side and its hedge sell side as full embedded leg cards, listed in execution
 * order (sell first at the roster cap), with the pair ΔW (v3.4: the EXACT
 * combined ledger, both legs applied together — not the sum of the legs'
 * isolation ΔWs, which is why a negative buy leg is normal), the neutrality
 * badge (exactly 0 players / 0 picks net for you), the posture-fit summary,
 * and the agreement-first sequencing note.
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
            title="Return on inventory deployed (§5): the pair's exact combined ΔW(you) ÷ Σ face v of every asset you send across both legs — the range filter's ranking metric"
          >
            {fmtPct(pair.return_pct, 1)} return
          </span>
          <ValueChip label="pair ΔW" value={pair.dW_combined} emphasis />
          {pair.dW_combined_parts ? (
            <span
              className="text-[11.5px] text-ink-muted"
              title="Where the pair's wealth moves (§2 v3.4): starters = the max-Σv lineup at raw KTC over active + taxi; picks = tranche value"
            >
              starters{" "}
              <span className="num">{fmtSigned(pair.dW_combined_parts.dS)}</span> ·
              picks{" "}
              <span className="num">{fmtSigned(pair.dW_combined_parts.dP)}</span>
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
