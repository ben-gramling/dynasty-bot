"use client";

import { useMemo, useState } from "react";
import { Star } from "@/components/star";
import { fmtSigned, fmtValue } from "@/lib/format";
import {
  POSITIONS,
  type ChartTeam,
  type Metric,
  type Position,
} from "@/components/league/chart-data";
import { ord, slugFor } from "@/components/league/util";

/**
 * Per-position comparative bars (docs/web-design.md §5). Single series:
 * every bar is sky-deep; my team gets the red six-pointed star and a deeper
 * step of the same hue — never 12 hues. Magnitude from a zero baseline, one
 * axis, thin marks with rounded data-ends, hover/focus tooltips. The headline
 * table above the chart is the always-present table view.
 */

const METRICS: Metric[] = ["L", ...POSITIONS, "F"];

const METRIC_LABEL: Record<Metric, string> = {
  L: "Strength",
  QB: "QB",
  RB: "RB",
  WR: "WR",
  TE: "TE",
  FLEX: "Flex",
  F: "Future",
};

const BAR = "var(--color-sky-deep)"; // series hue (#1877B8)
const BAR_ME = "#0f5a8c"; // same hue, one step deeper — the my-team mark

function metricValue(t: ChartTeam, m: Metric): number {
  if (m === "L") return t.L;
  if (m === "F") return t.F;
  return t.pos[m].sum;
}

function metricRank(t: ChartTeam, m: Metric): number {
  if (m === "L") return t.L_rank;
  if (m === "F") return t.F_rank;
  return t.pos[m].rank;
}

/** Zero-based axis with a 1/2/2.5/5×10^k step and ≤ 6 divisions. */
function axisFor(max: number): { max: number; ticks: number[] } {
  if (max <= 0) return { max: 1, ticks: [0, 1] };
  const pow = Math.pow(10, Math.floor(Math.log10(max / 4.5)));
  const step =
    [1, 2, 2.5, 5, 10].map((s) => s * pow).find((s) => max / s <= 6) ?? 10 * pow;
  const niceMax = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let v = 0; v <= niceMax + step / 2; v += step) ticks.push(v);
  return { max: niceMax, ticks };
}

function fmtTick(v: number): string {
  if (v === 0) return "0";
  const k = v / 1000;
  return k >= 1 ? `${Number.isInteger(k) ? k : k.toFixed(1)}k` : fmtValue(v);
}

function tooltipLines(t: ChartTeam, m: Metric): { text: string; v: number }[] {
  if (m === "L")
    return POSITIONS.map((p) => ({
      text: `${p} ${ord(t.pos[p].rank)}`,
      v: t.pos[p].sum,
    }));
  if (m === "F")
    return [
      { text: `Picks (${t.picksCount} owned)`, v: t.picks },
      { text: `Taxi (${t.taxiCount} players)`, v: t.taxi },
    ];
  return t.pos[m as Position].players.map((p) => ({ text: p.player, v: p.v }));
}

export function StrengthChart({ teams }: { teams: ChartTeam[] }) {
  const [metric, setMetric] = useState<Metric>("L");
  const [active, setActive] = useState<string | null>(null);

  const sorted = useMemo(
    () => [...teams].sort((a, b) => metricValue(b, metric) - metricValue(a, metric)),
    [teams, metric],
  );
  const axis = useMemo(
    () => axisFor(Math.max(...sorted.map((t) => metricValue(t, metric)))),
    [sorted, metric],
  );

  const grid = "minmax(96px, 140px) 1fr 60px";

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1" role="group" aria-label="Chart metric">
        {METRICS.map((m) => (
          <button
            key={m}
            type="button"
            aria-pressed={metric === m}
            onClick={() => {
              setMetric(m);
              setActive(null);
            }}
            className={`rounded border px-2.5 py-1 text-[12px] leading-none transition-colors ${
              metric === m
                ? "border-sky-deep bg-chip text-ink"
                : "border-line text-ink-muted hover:text-ink"
            }`}
          >
            {METRIC_LABEL[m]}
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-[7px]">
        {sorted.map((t, i) => {
          const v = metricValue(t, metric);
          const rank = metricRank(t, metric);
          const pct = Math.max(0, (v / axis.max) * 100);
          const slug = slugFor(t.team);
          const isActive = active === t.team;
          const label = `${t.team} — ${METRIC_LABEL[metric]} ${fmtValue(v)}, ${ord(
            rank,
          )} of ${teams.length}. Open team detail.`;
          return (
            <a
              key={t.team}
              href={`#${slug}`}
              aria-label={label}
              onMouseEnter={() => setActive(t.team)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(t.team)}
              onBlur={() => setActive(null)}
              className="grid items-center gap-x-3 no-underline"
              style={{ gridTemplateColumns: grid }}
            >
              <span
                aria-hidden
                className={`flex min-w-0 items-center justify-end gap-1 text-right text-[12.5px] ${
                  t.me ? "font-semibold text-ink" : "text-ink-muted"
                }`}
              >
                <span className="truncate">{t.team}</span>
                {t.me ? <Star size={9} title="Your team" /> : null}
              </span>

              <span aria-hidden className="relative block h-[18px]">
                {/* gridlines */}
                {axis.ticks.slice(1).map((tick) => (
                  <span
                    key={tick}
                    className="absolute inset-y-0 w-px bg-line"
                    style={{ left: `${(tick / axis.max) * 100}%` }}
                  />
                ))}
                <span className="absolute inset-y-0 left-0 w-px bg-line" />
                {/* the mark: thin, zero-anchored, rounded data-end */}
                <span
                  className="absolute top-1/2 h-[13px] -translate-y-1/2"
                  style={{
                    left: 0,
                    width: `${pct}%`,
                    background: t.me ? BAR_ME : BAR,
                    borderRadius: "0 4px 4px 0",
                  }}
                />
                {isActive ? (
                  <span
                    className="pointer-events-none absolute z-20 w-[230px] rounded-md border border-line bg-surface p-2.5 shadow-sm"
                    style={{
                      left: `min(${Math.min(pct, 55)}%, calc(100% - 232px))`,
                      ...(i >= sorted.length / 2
                        ? { bottom: "calc(100% + 5px)" }
                        : { top: "calc(100% + 5px)" }),
                    }}
                  >
                    <span className="flex items-baseline justify-between gap-2">
                      <span className="text-[12px] font-semibold text-ink">{t.team}</span>
                      <span className="num text-[12px] text-ink">
                        {fmtValue(v)}
                        <span className="text-ink-muted"> · {ord(rank)}</span>
                      </span>
                    </span>
                    {metric === "L" ? (
                      <span className="num mt-0.5 block text-[10.5px] text-ink-muted">
                        z {fmtSigned(t.L_z, 2)}
                      </span>
                    ) : null}
                    <span className="mt-1.5 block border-t border-line pt-1.5">
                      {tooltipLines(t, metric).map((l) => (
                        <span
                          key={l.text}
                          className="flex items-baseline justify-between gap-3 py-px"
                        >
                          <span className="truncate text-[11.5px] text-ink-muted">
                            {l.text}
                          </span>
                          <span className="num text-[11.5px] text-ink">{fmtValue(l.v)}</span>
                        </span>
                      ))}
                    </span>
                  </span>
                ) : null}
              </span>

              <span aria-hidden className="num text-right text-[12px] text-ink">
                {fmtValue(v)}
              </span>
            </a>
          );
        })}
      </div>

      {/* the one axis */}
      <div
        className="mt-1 grid gap-x-3"
        aria-hidden
        style={{ gridTemplateColumns: grid }}
      >
        <span />
        <span className="relative block h-4">
          {axis.ticks.map((tick, i) => (
            <span
              key={tick}
              // narrow screens keep only the 0 and max labels — no collisions
              className={`num absolute top-0 -translate-x-1/2 text-[10.5px] text-ink-muted ${
                i === 0 || i === axis.ticks.length - 1 ? "" : "hidden sm:block"
              }`}
              style={{ left: `${(tick / axis.max) * 100}%` }}
            >
              {fmtTick(tick)}
            </span>
          ))}
        </span>
        <span />
      </div>

      <p className="mt-2 text-[11.5px] text-ink-muted">
        KTC value from a zero baseline · <Star size={8} className="inline" /> your team ·
        click a bar for the front-office card · the table above is the same data.
      </p>
    </div>
  );
}
