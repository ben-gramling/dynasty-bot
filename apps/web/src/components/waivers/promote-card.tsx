import type { TaxiPromotion } from "@/lib/queries";
import { fmtValue } from "@/lib/format";
import { Decomposition } from "@/components/decomposition";

/**
 * A taxi-promotion suggestion (§9.3): promote a stashed player onto the
 * active roster, with the attached drop and the §12 decomposition.
 */
export function PromoteCard({ p }: { p: TaxiPromotion }) {
  return (
    <article className="rounded-md border border-line bg-surface px-4 py-3">
      <div className="wv-card-head">
        <span className="wv-verdict">Promote</span>
        <span className="wv-player">{p.player}</span>
        <span className="text-[12.5px] text-ink-muted">from taxi</span>
      </div>
      <p className="wv-plan">
        Promote {p.player}
        {p.attached_drop ? ` · drop ${p.attached_drop}` : " · a roster slot is open"}
        {p.lock_penalty > 0 ? (
          <span className="num">
            {" "}
            · lock penalty <span className="text-star">−{fmtValue(p.lock_penalty)}</span>
          </span>
        ) : null}
      </p>
      <div className="mt-2">
        <Decomposition side={p.sides.me} tables={p.audit.lineup_tables} />
      </div>
    </article>
  );
}
