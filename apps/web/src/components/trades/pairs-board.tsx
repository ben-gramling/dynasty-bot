"use client";

import { useState } from "react";
import type { ThresholdCount, TradePair, TruncationInfo } from "@/lib/queries";
import { fmtDateTime } from "@/lib/format";
import { PairCard } from "./pair-card";

const RENDER_CAP = 50;
const DEFAULT_TARGET = 5;

/**
 * §5 v3.3 target-return dial over the STORED pair list. The dial filters
 * client-side (the doc already holds the top pairs by return); the header
 * counts come from the engine's counts_by_threshold so they stay honest even
 * when storage truncates — saturated counters render as "≥ N" (verified
 * floors, never estimates).
 */
export function PairsBoard({
  pairs,
  presets,
  counts,
  truncated,
  computedAt,
}: {
  pairs: TradePair[];
  presets: number[];
  counts: ThresholdCount[];
  truncated: TruncationInfo | null;
  computedAt: string;
}) {
  const [target, setTarget] = useState<number>(
    presets.includes(DEFAULT_TARGET) ? DEFAULT_TARGET : presets[0],
  );

  const countAt = (t: number): ThresholdCount | undefined =>
    counts.find((e) => e.threshold === t);
  const fmtCount = (e: ThresholdCount | undefined): string =>
    e ? `${e.saturated ? "≥ " : ""}${e.count.toLocaleString("en-US")}` : "—";

  const floor = presets[0];
  const atTarget = countAt(target);
  const atFloor = countAt(floor);
  const filtered = pairs.filter((p) => p.return_pct >= target);
  const shown = filtered.slice(0, RENDER_CAP);

  // empty-state honesty: name the deepest preset below the target that still
  // has pairs ("No pairs clear 10% today — 12 clear 2.5%")
  const fallback = counts
    .filter((e) => e.threshold < target && e.count > 0)
    .sort((a, b) => b.threshold - a.threshold)[0];

  return (
    <div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <div
          role="group"
          aria-label="Target return"
          className="inline-flex overflow-hidden rounded-md border border-line"
        >
          {presets.map((p) => (
            <button
              key={p}
              type="button"
              aria-pressed={p === target}
              onClick={() => setTarget(p)}
              className={`num px-2.5 py-1 text-[12px] transition-colors ${
                p === target
                  ? "bg-sky-deep font-medium text-white"
                  : "bg-surface text-ink-muted hover:bg-chip"
              }`}
            >
              {p}%
            </button>
          ))}
        </div>
        <p className="num text-[11.5px] text-ink-muted">
          {fmtCount(atTarget)} pair{atTarget?.count === 1 && !atTarget.saturated ? "" : "s"} ≥{" "}
          {target}% (of {fmtCount(atFloor)} ≥ {floor}%) · ranked by return ·
          computed {fmtDateTime(computedAt)}
        </p>
      </div>

      {truncated ? (
        <p className="mt-2 text-[11.5px] text-ink-muted">
          Storage cap: the top {truncated.stored.toLocaleString("en-US")} pairs
          by return are stored here, of{" "}
          {truncated.total_saturated ? "at least " : ""}
          {truncated.total.toLocaleString("en-US")} clearing the {floor}% floor
          — counts above stay honest; deeper pairs are not listed.
        </p>
      ) : null}

      {shown.length ? (
        <>
          {filtered.length > RENDER_CAP ? (
            <p className="mt-2 text-[11.5px] text-ink-muted">
              Showing the top {RENDER_CAP} of {filtered.length} stored pairs at
              this target.
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
            No pairs clear {target}% today
            {fallback ? (
              <>
                {" "}
                — {fmtCount(fallback)} clear {fallback.threshold}%. Drop the
                dial, or hold.
              </>
            ) : (
              <>
                {" "}
                — and none clear any lower preset either. Holding is the move;
                the board recomputes nightly.
              </>
            )}
          </p>
        </div>
      )}
    </div>
  );
}
