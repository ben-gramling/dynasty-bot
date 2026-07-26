/**
 * Number/date formatters. KTC value is the currency of the page: grouped
 * integers in the data face (tabular numerals via the .num class). Negative
 * numbers always use the true minus sign (U+2212) and render in star red
 * (ledger semantics — see docs/web-design.md §1).
 */

const MINUS = "−";

const grouped = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

function groupedDp(decimals: number): Intl.NumberFormat {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** KTC value: "7,770". */
export function fmtValue(n: number): string {
  return grouped.format(Math.round(n)).replace("-", MINUS);
}

/** Unsigned 1-decimal magnitude ("1,087.2"); true minus; −0 → "0.0". */
export function fmt1(n: number): string {
  return groupedDp(1)
    .format(n === 0 ? 0 : n)
    .replace("-", MINUS);
}

/** Signed delta: "+1,240" / "−524". decimals > 0 keeps e.g. "+6.9". */
export function fmtSigned(n: number, decimals = 0): string {
  const body = (decimals > 0 ? groupedDp(decimals) : grouped)
    .format(decimals > 0 ? n : Math.round(n))
    .replace("-", "");
  // −0 renders as 0
  const sign = n > 0 ? "+" : n < 0 && body !== "0" && !/^0\.0*$/.test(body) ? MINUS : "+";
  return `${sign}${body}`;
}

/** Percentage: "17.7%". */
export function fmtPct(n: number, decimals = 1): string {
  return `${groupedDp(decimals).format(n).replace("-", MINUS)}%`;
}

/** FAAB / bids: "$0", "$63". */
export function fmtFaab(n: number): string {
  return `$${grouped.format(Math.round(n))}`;
}

/** Age of a timestamp: "just now", "4m ago", "2h ago", "3d ago". */
export function fmtAge(iso: string | Date, now: Date = new Date()): string {
  const then = typeof iso === "string" ? new Date(iso) : iso;
  const s = Math.max(0, Math.floor((now.getTime() - then.getTime()) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

/**
 * "Jul 26, 18:53" in league home time (America/Chicago). Pinned, not
 * inherited: this renders in server components, and the production server
 * runs in UTC — an unpinned toLocaleString would silently show UTC wall
 * time next to the pill's relative age. Pinning also keeps server and
 * client output identical (no hydration drift in title attributes).
 */
export function fmtDateTime(iso: string | Date): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  return d.toLocaleString("en-US", {
    timeZone: "America/Chicago",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
