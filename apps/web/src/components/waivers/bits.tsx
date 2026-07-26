import { fmtSigned } from "@/lib/format";

/**
 * Small shared pieces for the waivers tab: tags, carets, and cell formatters.
 * All server-renderable; ledger semantics (red = negative numbers only) come
 * from the .text-star class, never decoration.
 */

export { fmt1 } from "@/lib/format";

/** Tiny uppercase tag ("free", "Aug 15 cut"). emphasis = sky-deep border. */
export function Tag({
  children,
  emphasis = false,
  title,
}: {
  children: React.ReactNode;
  emphasis?: boolean;
  title?: string;
}) {
  return (
    <span className={`wv-tag${emphasis ? " wv-tag--em" : ""}`} title={title}>
      {children}
    </span>
  );
}

/** Row-expansion caret (same glyph as the decomposition sentence's). */
export function Caret() {
  return (
    <svg className="wv-caret" width="10" height="10" viewBox="0 0 10 10" aria-hidden>
      <path d="M3 1.5 7 5 3 8.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

/**
 * Right-aligned signed numeric grid cell. Zero renders unsigned and muted
 * (145 of 155 board rows are ≈0 — the eye should catch the nonzero ones);
 * negatives wear star red.
 */
export function SignedCell({ v, decimals = 1 }: { v: number; decimals?: number }) {
  if (v === 0) {
    return <span className="num wv-r text-ink-muted">{(0).toFixed(decimals)}</span>;
  }
  return (
    <span className={`num wv-r${v < 0 ? " text-star" : ""}`}>
      {fmtSigned(v, decimals)}
    </span>
  );
}

const INJURY_ABBR: Record<string, string> = {
  Questionable: "Q",
  Doubtful: "D",
  Out: "Out",
  IR: "IR",
  PUP: "PUP",
  Sus: "Sus",
  COV: "COV",
  NA: "NA",
  DNR: "DNR",
};

/** Compact injury marker ("Q", "IR") with the full status on hover. */
export function InjuryTag({ status }: { status: string | null }) {
  if (!status) return null;
  return <Tag title={status}>{INJURY_ABBR[status] ?? status.slice(0, 3)}</Tag>;
}
