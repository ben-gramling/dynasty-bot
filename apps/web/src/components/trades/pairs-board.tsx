"use client";

import { useState } from "react";
import type { BandInfo, TradePair } from "@/lib/queries";
import { fmtDateTime } from "@/lib/format";
import { PairCard } from "./pair-card";

const RENDER_CAP = 50;
const DEFAULT_MIN = 5;
// Fallbacks for docs that predate the v5 preset fields (§9).
const FAVOR_PRESETS = [-10, -5, 0, 2.5, 5];
const DELTA_PRESETS = [0, 0.25, 0.5, 0.75, 1];

const MINUS = "−";

/** Favor preset label in KTC variance units: "−10", "0", "+2.5". */
function fmtFavor(f: number): string {
  const s = String(f).replace("-", MINUS);
  return f > 0 ? `+${s}` : s;
}

/**
 * §4a/§5 v5 view score, percent: return(δ) = (ΔS + δ·(ΔF − ΔS)) ÷ Σ face v
 * sent — re-scored client-side from each stored pair's exact coordinates
 * (never recomputed from rosters). δ = null is the robust view: the stored
 * guaranteed-floor return (§2 v4 maximin). Pre-v5 docs lack coords/sent and
 * always serve the robust figure. NOTE ΔW(δ) is bounded below by the floor
 * for every δ, so return(δ) ≥ the robust return on every pair — a δ view can
 * only widen the list past a given floor, never shrink it.
 */
function returnAt(p: TradePair, delta: number | null): number {
  if (delta !== null && p.coords && typeof p.sent === "number" && p.sent > 0) {
    const w = p.coords.dS + delta * (p.coords.dF - p.coords.dS);
    return (100 * w) / p.sent;
  }
  return p.return_pct;
}

/**
 * §5 v5: the finder's THREE dials over the STORED pair list — a δ SELECTOR
 * (robust default + presets 0/0.25/0.5/0.75/1; return(δ) re-scored instantly
 * from stored coordinates, a labeled preference VIEW — the objective verdict
 * on every card never changes), a floor on TOTAL return(δ) (robust mode =
 * guaranteed-floor return; presets 1/2.5/5/10/20%, default 5), and a
 * counterparty-favorability FLOOR on the pair's min(f_buy, f_sell) (presets
 * −10/−5/0/+2.5/+5/no floor, KTC's own calculator variance units — ±5 is
 * literally the calculator's FAIR window; replaces the v3.4.1 leg cap, whose
 * raw skim diverges from the calculator by up to 14 pts). Filtering and
 * sorting are client-side and O(stored): return(δ) desc, ceiling tie-break.
 * The inventory line reads the doc's favor-bucket × robust-return `by_total`
 * grid — verified floors rendered "≥ N"; a favor floor between bucket edges
 * (+2.5) counts only fully-covered buckets and a δ view counts on robust
 * return (a floor either way, see the note under the line).
 */
export function PairsBoard({
  pairs,
  presets,
  favorPresets,
  deltaPresets,
  bands,
  computedAt,
}: {
  pairs: TradePair[];
  presets: number[];
  favorPresets?: number[] | null;
  deltaPresets?: number[] | null;
  bands: BandInfo[];
  computedAt: string;
}) {
  const [min, setMin] = useState<number>(
    presets.includes(DEFAULT_MIN) ? DEFAULT_MIN : presets[0],
  );
  const [delta, setDelta] = useState<number | null>(null); // null = robust
  const [favorMin, setFavorMin] = useState<number | null>(null); // null = no floor

  const favorList = favorPresets?.length ? favorPresets : FAVOR_PRESETS;
  const deltaList = deltaPresets?.length ? deltaPresets : DELTA_PRESETS;
  const bucketList = bands ?? [];

  const fmtPct = (p: number): string => `${p}%`;
  const filterLabel = `total ${min}%+ ${
    delta === null ? "robust" : `at δ=${delta}`
  }, ${favorMin === null ? "no favor floor" : `favor ≥ ${fmtFavor(favorMin)}`}`;

  const passesFavor = (p: TradePair): boolean =>
    favorMin === null || (p.favor?.min ?? -Infinity) >= favorMin;

  const scored = pairs.map((p) => ({ p, r: returnAt(p, delta) }));
  const filtered = scored
    .filter(({ p, r }) => r >= min && passesFavor(p))
    // return(δ) desc, ceiling tie-break (§5 v5); robust δ = the shipped
    // maximin order (§2 v4)
    .sort((a, b) => b.r - a.r || (b.p.ceiling ?? 0) - (a.p.ceiling ?? 0));
  const shown = filtered.slice(0, RENDER_CAP);

  // inventory from the favor-bucket × robust-return grid: the favor floor
  // selects the buckets with lo ≥ floor (a floor strictly inside a bucket —
  // the +2.5 preset — leaves that bucket out, so the count stays a floor);
  // the return floor selects the grid columns with lo ≥ min (floor presets
  // coincide with the robust band los). In a δ view the same columns are a
  // floor for return(δ) ≥ min, since return(δ) ≥ robust return on every pair.
  const selected = bucketList.filter(
    (b) => favorMin === null || (b.lo !== null && b.lo >= favorMin),
  );
  const partialBucket =
    favorMin !== null &&
    bucketList.some(
      (b) => (b.lo ?? -Infinity) < favorMin && (b.hi === null || favorMin < b.hi),
    );
  const minIdx = presets.findIndex((p) => p >= min);
  const invCount = selected.reduce(
    (n, b) =>
      n +
      (b.by_total
        ? b.by_total.reduce((m, c, j) => (j >= minIdx ? m + c : m), 0)
        : b.count),
    0,
  );
  const invSat =
    selected.some((b) => b.saturated) || partialBucket || delta !== null;

  // empty-state honesty: how many stored pairs each loosening would expose
  const withoutFavor = scored.filter(({ r }) => r >= min).length;
  const withoutFloor = pairs.filter(passesFavor).length;

  return (
    <div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex items-center gap-1.5">
          <span
            className="text-[11.5px] text-ink-muted"
            title="δ is a stored-value preference (win-now 0 ↔ win-later 1), never a score parameter: return(δ) = (ΔS + δ·(ΔF − ΔS)) ÷ Σv sent, re-scored instantly from each stored pair's exact coordinates. A labeled preference VIEW — robust (default) is the v4 guaranteed-floor return, good at every δ; the objective verdict on every card is unchanged (§4a)."
          >
            δ view
          </span>
          <div
            role="group"
            aria-label="Delta view"
            className="inline-flex overflow-hidden rounded-md border border-line"
          >
            <button
              type="button"
              aria-pressed={delta === null}
              onClick={() => setDelta(null)}
              className={`px-2.5 py-1 text-[12px] transition-colors ${
                delta === null
                  ? "bg-sky-deep font-medium text-white"
                  : "bg-surface text-ink-muted hover:bg-chip"
              }`}
            >
              robust
            </button>
            {deltaList.map((d) => (
              <button
                key={d}
                type="button"
                aria-pressed={d === delta}
                onClick={() => setDelta(d)}
                className={`num px-2.5 py-1 text-[12px] transition-colors ${
                  d === delta
                    ? "bg-sky-deep font-medium text-white"
                    : "bg-surface text-ink-muted hover:bg-chip"
                }`}
              >
                {String(d)}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className="text-[11.5px] text-ink-muted"
            title="Floor on TOTAL pair return at the selected δ. Robust (default): the guaranteed-floor return — min(ΔS, ΔF) combined over Σv you send across both legs (§2 v4)."
          >
            Min total
          </span>
          <div
            role="group"
            aria-label="Minimum return"
            className="inline-flex overflow-hidden rounded-md border border-line"
          >
            {presets.map((p) => (
              <button
                key={p}
                type="button"
                aria-pressed={p === min}
                onClick={() => setMin(p)}
                className={`num px-2.5 py-1 text-[12px] transition-colors ${
                  p === min
                    ? "bg-sky-deep font-medium text-white"
                    : "bg-surface text-ink-muted hover:bg-chip"
                }`}
              >
                {fmtPct(p)}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className="text-[11.5px] text-ink-muted"
            title="Counterparty favorability floor (§4a v5), in KTC's own calculator VARIANCE UNITS: per leg, favor = the signed skew toward that counterparty, from the SAME adjusted totals as the fairness gate — ±5 means their calculator literally says FAIR at default variance, favor > 0 skews to them. The floor applies to the pair's min(f_buy, f_sell), the least-happy counterparty; it replaces the v3.4.1 per-leg market-return cap (the raw skim diverges from the calculator by up to 14 pts). The §3 band stays the hard outer bound — favor selects within it."
          >
            Favor floor
          </span>
          <div
            role="group"
            aria-label="Favorability floor"
            className="inline-flex overflow-hidden rounded-md border border-line"
          >
            {[...favorList, null].map((f) => {
              const active = f === favorMin;
              return (
                <button
                  key={f === null ? "nofloor" : f}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setFavorMin(f)}
                  className={`num px-2.5 py-1 text-[12px] transition-colors ${
                    active
                      ? "bg-sky-deep font-medium text-white"
                      : "bg-surface text-ink-muted hover:bg-chip"
                  }`}
                >
                  {f === null ? "No floor" : fmtFavor(f)}
                </button>
              );
            })}
          </div>
        </div>
        <p className="num text-[11.5px] text-ink-muted">
          {filtered.length.toLocaleString("en-US")} stored shown ({filterLabel})
          · inventory: {invSat ? "≥ " : ""}
          {invCount.toLocaleString("en-US")} legal ·{" "}
          {delta === null
            ? "sorted by guaranteed return"
            : `sorted by return(δ=${delta})`}{" "}
          · computed {fmtDateTime(computedAt)}
        </p>
      </div>

      {delta !== null ? (
        <p className="mt-2 text-[11.5px] font-medium text-ink">
          preference view at δ={delta} — return(δ) is re-scored from each
          stored pair&apos;s exact coordinates; the §2 objective verdict and
          the guaranteed floor on every card are unchanged (§4a).
        </p>
      ) : null}

      {invSat ? (
        <p className="mt-2 text-[11.5px] text-ink-muted">
          Inventory marked ≥ is a verified floor — the collection walk crosses
          legs by their isolation floors while pairs are priced by the exact
          combined coordinates, so completeness above a cutoff cannot be
          certified (§5); a favor floor between bucket edges (+2.5) counts
          only fully-covered favor buckets, and a δ view counts on robust
          return (return(δ) is never below it). Only each favor bucket&apos;s
          stored union (tops by robust return, ΔS, ΔF) is listed.
        </p>
      ) : null}

      {shown.length ? (
        <>
          {filtered.length > RENDER_CAP ? (
            <p className="mt-2 text-[11.5px] text-ink-muted">
              Showing the top {RENDER_CAP} of {filtered.length} stored pairs
              behind this filter.
            </p>
          ) : null}
          <div className="mt-3 space-y-3">
            {shown.map(({ p }) => (
              <PairCard key={p.id} pair={p} />
            ))}
          </div>
        </>
      ) : (
        <div className="card mt-3">
          <p className="text-ink-muted">
            No stored pairs with {filterLabel} today —{" "}
            {withoutFavor > 0 || withoutFloor > 0 ? (
              <>
                removing the favor floor exposes{" "}
                {withoutFavor.toLocaleString("en-US")} stored, dropping the
                return floor to {presets[0]}% exposes{" "}
                {withoutFloor.toLocaleString("en-US")}. Loosen a dial, or hold.
              </>
            ) : (
              <>
                and no stored pair survives either dial alone. Holding is the
                move; the board recomputes nightly.
              </>
            )}
          </p>
        </div>
      )}
    </div>
  );
}
