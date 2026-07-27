"use client";

import { useState } from "react";
import type { BandInfo, TradePair } from "@/lib/queries";
import { fmtDateTime } from "@/lib/format";
import { PairCard } from "./pair-card";

const RENDER_CAP = 50;
const DEFAULT_MIN = 5;

/**
 * §5 v3.3.1 target-return RANGE over the STORED pair list: a min selector
 * (presets 1 / 2.5 / 5 / 10 / 20, default 5) and a max selector (2.5 / 5 / 10
 * / 20 / "No cap", default no cap), min < max enforced by disabling invalid
 * combos. Filtering is client-side on return_pct ∈ [min, max); the engine's
 * stratified per-band storage guarantees every such range has whatever
 * inventory exists. The inventory line comes from the doc's `bands` — exact
 * counts, or verified floors rendered "≥ N" when a band is saturated.
 */
export function PairsBoard({
  pairs,
  presets,
  bands,
  computedAt,
}: {
  pairs: TradePair[];
  presets: number[];
  bands: BandInfo[];
  computedAt: string;
}) {
  const [min, setMin] = useState<number>(
    presets.includes(DEFAULT_MIN) ? DEFAULT_MIN : presets[0],
  );
  const [max, setMax] = useState<number | null>(null); // null = no cap

  const bandList = bands ?? [];
  const maxOptions: (number | null)[] = [...presets.slice(1), null];

  const fmtPct = (p: number): string => `${p}%`;
  const rangeLabel = max === null ? `${min}%+` : `${min}–${max}%`;
  const bandLabel = (b: BandInfo): string =>
    b.hi === null ? `${b.lo}%+` : `${b.lo}–${b.hi}%`;

  const filtered = [...pairs]
    .filter((p) => p.return_pct >= min && (max === null || p.return_pct < max))
    .sort((a, b) => b.return_pct - a.return_pct);
  const shown = filtered.slice(0, RENDER_CAP);

  // inventory over the selected range: min/max are band edges, so the range
  // is a union of whole bands
  const inRange = bandList.filter(
    (b) => b.lo >= min && (max === null || (b.hi !== null && b.hi <= max)),
  );
  const invStored = inRange.reduce((n, b) => n + b.stored, 0);
  const invCount = inRange.reduce((n, b) => n + b.count, 0);
  const invSat = inRange.some((b) => b.saturated);

  // empty-state honesty: name the nearest band outside the range that still
  // holds stored pairs (below first, then above)
  const below = bandList
    .filter((b) => b.stored > 0 && b.lo < min)
    .sort((a, b) => b.lo - a.lo)[0];
  const above = bandList
    .filter((b) => b.stored > 0 && max !== null && b.lo >= max)
    .sort((a, b) => a.lo - b.lo)[0];
  const fallback = below ?? above;

  return (
    <div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex items-center gap-1.5">
          <span className="text-[11.5px] text-ink-muted">Min</span>
          <div
            role="group"
            aria-label="Minimum return"
            className="inline-flex overflow-hidden rounded-md border border-line"
          >
            {presets.map((p) => {
              const invalid = max !== null && p >= max;
              return (
                <button
                  key={p}
                  type="button"
                  aria-pressed={p === min}
                  disabled={invalid}
                  onClick={() => setMin(p)}
                  className={`num px-2.5 py-1 text-[12px] transition-colors ${
                    p === min
                      ? "bg-sky-deep font-medium text-white"
                      : invalid
                        ? "cursor-not-allowed bg-surface text-ink-muted/40"
                        : "bg-surface text-ink-muted hover:bg-chip"
                  }`}
                >
                  {fmtPct(p)}
                </button>
              );
            })}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[11.5px] text-ink-muted">Max</span>
          <div
            role="group"
            aria-label="Maximum return"
            className="inline-flex overflow-hidden rounded-md border border-line"
          >
            {maxOptions.map((m) => {
              const invalid = m !== null && m <= min;
              const active = m === max;
              return (
                <button
                  key={m === null ? "nocap" : m}
                  type="button"
                  aria-pressed={active}
                  disabled={invalid}
                  onClick={() => setMax(m)}
                  className={`num px-2.5 py-1 text-[12px] transition-colors ${
                    active
                      ? "bg-sky-deep font-medium text-white"
                      : invalid
                        ? "cursor-not-allowed bg-surface text-ink-muted/40"
                        : "bg-surface text-ink-muted hover:bg-chip"
                  }`}
                >
                  {m === null ? "No cap" : fmtPct(m)}
                </button>
              );
            })}
          </div>
        </div>
        <p className="num text-[11.5px] text-ink-muted">
          {filtered.length.toLocaleString("en-US")} shown in {rangeLabel} ·
          band inventory: {invStored.toLocaleString("en-US")} stored of{" "}
          {invSat ? "≥ " : ""}
          {invCount.toLocaleString("en-US")} legal · ranked by return ·
          computed {fmtDateTime(computedAt)}
        </p>
      </div>

      {invSat ? (
        <p className="mt-2 text-[11.5px] text-ink-muted">
          Inventory marked ≥ is a verified floor — the legal pair space in
          this range runs deeper than the collection budget; only each
          band&apos;s stored top is listed.
        </p>
      ) : null}

      {shown.length ? (
        <>
          {filtered.length > RENDER_CAP ? (
            <p className="mt-2 text-[11.5px] text-ink-muted">
              Showing the top {RENDER_CAP} of {filtered.length} stored pairs in
              this range.
            </p>
          ) : null}
          <div className="mt-3 space-y-3">
            {shown.map((pair) => (
              <PairCard key={pair.id} pair={pair} />
            ))}
          </div>
        </>
      ) : (
        <div className="card mt-3">
          <p className="text-ink-muted">
            No stored pairs in {rangeLabel} today
            {fallback ? (
              <>
                {" "}
                — the {bandLabel(fallback)} band holds{" "}
                {fallback.stored.toLocaleString("en-US")} (of{" "}
                {fallback.saturated ? "≥ " : ""}
                {fallback.count.toLocaleString("en-US")} legal). Widen the
                range, or hold.
              </>
            ) : (
              <>
                {" "}
                — and no band holds any stored pairs either. Holding is the
                move; the board recomputes nightly.
              </>
            )}
          </p>
        </div>
      )}
    </div>
  );
}
