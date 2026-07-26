import type { BeforeAfter, SideDecomp } from "@/lib/queries";
import { fmtSigned, fmtValue } from "@/lib/format";
import { ValueChip } from "@/components/value-chip";

/**
 * The signature element (docs/web-design.md §4): every recommendation's §12
 * breakdown as one readable sentence of value chips that expands to the full
 * audit. Native details/summary — server-renderable, works without JS.
 *
 * Chips come straight from the side decomposition (lineup_weighted +
 * wealth_weighted + crunch_term = score, guaranteed ±0.1 by the engine) —
 * never recomputed here, never hand-written.
 */
export function Decomposition({
  side,
  tables,
  scoreLabel = "score",
  lead,
  defaultOpen = false,
}: {
  side: SideDecomp;
  /** Before/after lineup tables from the card's audit block, if rendered. */
  tables?: BeforeAfter;
  scoreLabel?: string;
  /** Optional chips prepended to the sentence (e.g. a bid chip). */
  lead?: React.ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details className="decomp" open={defaultOpen || undefined}>
      <summary>
        {lead}
        <ValueChip label="lineup" value={side.lineup_weighted} decimals={1} />
        <span className="decomp-dot">·</span>
        <ValueChip label="wealth" value={side.wealth_weighted} decimals={1} />
        <span className="decomp-dot">·</span>
        <ValueChip label="crunch" value={side.crunch_term} decimals={1} />
        <span className="decomp-eq">=</span>
        <ValueChip label={scoreLabel} value={side.score} decimals={1} emphasis />
        <svg
          className="decomp-caret"
          width="10"
          height="10"
          viewBox="0 0 10 10"
          aria-hidden
        >
          <path d="M3 1.5 7 5 3 8.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </summary>
      <div className="decomp-audit space-y-3">
        <DLTerms side={side} />
        <CrunchLine side={side} />
        {tables ? <LineupTables tables={tables} /> : null}
        <p className="num text-[11.5px] text-ink-muted">
          {fmtSigned(side.lineup_weighted, 1)} {fmtSigned(side.wealth_weighted, 1)}{" "}
          {fmtSigned(side.crunch_term, 1)} = {fmtSigned(side.score, 1)}
        </p>
      </div>
    </details>
  );
}

function DLTerms({ side }: { side: SideDecomp }) {
  if (!side.dL_terms.length) {
    return (
      <p className="text-ink-muted">
        No lineup change — the value moves through wealth and crunch only.
      </p>
    );
  }
  return (
    <div className="card-scroll">
      <table className="data-table data-table--auto">
        <thead>
          <tr>
            <th>Change</th>
            <th>Slot</th>
            <th>Out</th>
            <th>In</th>
            <th className="num">ΔL</th>
          </tr>
        </thead>
        <tbody>
          {side.dL_terms.map((t, i) => (
            <tr key={i}>
              <td>{t.kind}</td>
              <td>{t.slot}</td>
              <td>{t.out}</td>
              <td>{t.in}</td>
              <td className={`num${t.delta < 0 ? " text-star" : ""}`}>
                {fmtSigned(t.delta, 1)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CrunchLine({ side }: { side: SideDecomp }) {
  const c = side.crunch;
  if (!c) return null;
  return (
    <p>
      Cuts {c.cuts_before} → {c.cuts_after}
      {c.rescued.length ? ` · rescued ${c.rescued.join(", ")}` : ""}
    </p>
  );
}

function LineupTables({ tables }: { tables: BeforeAfter }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {(["before", "after"] as const).map((which) => (
        <div key={which} className="card-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th colSpan={2}>{which === "before" ? "Lineup before" : "Lineup after"}</th>
                <th className="num">Value</th>
              </tr>
            </thead>
            <tbody>
              {tables[which].map((r) => (
                <tr key={`${which}-${r.slot}`}>
                  <td className="text-ink-muted">{r.slot}</td>
                  <td>{r.player}</td>
                  <td className="num">{fmtValue(r.v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
