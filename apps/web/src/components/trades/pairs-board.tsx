"use client";

import { useState } from "react";
import type { BandInfo, TradePair } from "@/lib/queries";
import { fmtDateTime } from "@/lib/format";
import { PairCard } from "./pair-card";

const RENDER_CAP = 50;
const DEFAULT_MIN = 5;
const LEG_CAP_PRESETS = [2.5, 5, 10, 20];

/**
 * §5 v3.4.1 two-dial filter over the STORED pair list: a floor on TOTAL pair
 * return (presets 1 / 2.5 / 5 / 10 / 20, default 5) and a cap on EACH LEG's
 * market return (presets 2.5 / 5 / 10 / 20 / "No cap", default no cap). The
 * dials are independent dimensions — floor 5% with a 2.5% leg cap is the
 * balanced-legs/high-total query, so no combination is disabled. Filtering is
 * client-side (return_pct ≥ min AND max_leg_return_pct < cap); the list always
 * sorts by TOTAL return desc. The inventory line reads the doc's per-bucket
 * `by_total` grid — verified floors rendered "≥ N" (v3.4: every count is one,
 * by construction — see the note under the inventory line).
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
  const [cap, setCap] = useState<number | null>(null); // null = no leg cap

  const bucketList = bands ?? [];
  const capOptions: (number | null)[] = [
    ...(bucketList.length
      ? bucketList.filter((b) => b.hi !== null).map((b) => b.hi as number)
      : LEG_CAP_PRESETS),
    null,
  ];

  const fmtPct = (p: number): string => `${p}%`;
  const filterLabel =
    cap === null ? `total ${min}%+, no leg cap` : `total ${min}%+, legs < ${cap}%`;

  const filtered = [...pairs]
    .filter(
      (p) =>
        p.return_pct >= min &&
        (cap === null || (p.max_leg_return_pct ?? Infinity) < cap),
    )
    .sort((a, b) => b.return_pct - a.return_pct); // ALWAYS total return desc
  const shown = filtered.slice(0, RENDER_CAP);

  // inventory from the bucket × total-band grid: a cap preset selects the
  // buckets with hi ≤ cap; the floor selects the grid columns with lo ≥ min
  // (floor presets coincide with the total-band los)
  const selected = bucketList.filter(
    (b) => cap === null || (b.hi !== null && b.hi <= cap),
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
  const invSat = selected.some((b) => b.saturated);

  // empty-state honesty: how many stored pairs each loosening would expose
  const withoutCap = pairs.filter((p) => p.return_pct >= min).length;
  const withoutFloor = pairs.filter(
    (p) => cap === null || (p.max_leg_return_pct ?? Infinity) < cap,
  ).length;

  return (
    <div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex items-center gap-1.5">
          <span className="text-[11.5px] text-ink-muted">Min total</span>
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
            title="v3.4.1: caps EACH leg's market return — the face skim that leg's counterparty sees. Independent of the total floor: a low cap with a high floor is the balanced-legs query."
          >
            Leg cap
          </span>
          <div
            role="group"
            aria-label="Max per-leg return"
            className="inline-flex overflow-hidden rounded-md border border-line"
          >
            {capOptions.map((c) => {
              const active = c === cap;
              return (
                <button
                  key={c === null ? "nocap" : c}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setCap(c)}
                  className={`num px-2.5 py-1 text-[12px] transition-colors ${
                    active
                      ? "bg-sky-deep font-medium text-white"
                      : "bg-surface text-ink-muted hover:bg-chip"
                  }`}
                >
                  {c === null ? "No cap" : fmtPct(c)}
                </button>
              );
            })}
          </div>
        </div>
        <p className="num text-[11.5px] text-ink-muted">
          {filtered.length.toLocaleString("en-US")} stored shown ({filterLabel})
          · inventory: {invSat ? "≥ " : ""}
          {invCount.toLocaleString("en-US")} legal · sorted by total return ·
          computed {fmtDateTime(computedAt)}
        </p>
      </div>

      {invSat ? (
        <p className="mt-2 text-[11.5px] text-ink-muted">
          Inventory marked ≥ is a verified floor — the legal pair space behind
          this filter runs deeper than the collection budget, and the walk
          crosses legs by their isolation ΔW while pairs are priced by the
          exact combined ledger, so completeness above a cutoff cannot be
          certified (§5 v3.4). Only each max-leg bucket&apos;s stored top (by
          total return) is listed.
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
            {shown.map((pair) => (
              <PairCard key={pair.id} pair={pair} />
            ))}
          </div>
        </>
      ) : (
        <div className="card mt-3">
          <p className="text-ink-muted">
            No stored pairs with {filterLabel} today —{" "}
            {withoutCap > 0 || withoutFloor > 0 ? (
              <>
                removing the leg cap exposes {withoutCap.toLocaleString("en-US")}{" "}
                stored, dropping the floor to {presets[0]}% exposes{" "}
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
