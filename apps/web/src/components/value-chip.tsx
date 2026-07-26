import { fmtSigned, fmtValue } from "@/lib/format";

/**
 * Inline value chip — the atom of the decomposition sentence
 * (docs/web-design.md §4). Server-renderable; no client JS.
 *
 * signed (default) renders "+1,240" / "−524" with negatives in star red;
 * signed=false renders a plain magnitude ("7,770").
 */
export function ValueChip({
  label,
  value,
  decimals = 0,
  signed = true,
  emphasis = false,
  text,
}: {
  label: string;
  value?: number;
  decimals?: number;
  signed?: boolean;
  /** Score chip: adds the sky-deep border (the sentence's verb). */
  emphasis?: boolean;
  /** Non-numeric chip body (e.g. "Bid $0"); overrides value. */
  text?: string;
}) {
  const neg = (value ?? 0) < 0;
  const body =
    text ?? (value === undefined ? "—" : signed ? fmtSigned(value, decimals) : fmtValue(value));
  return (
    <span className={`chip${neg ? " is-neg" : ""}${emphasis ? " chip-score" : ""}`}>
      <span className="chip-k">{label}</span>
      <span className="chip-v">{body}</span>
    </span>
  );
}
