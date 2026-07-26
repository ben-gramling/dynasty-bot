import type { ReactNode } from "react";
import type { TradeAsset, TradeRec } from "@/lib/queries";
import { fmt1, fmtPct, fmtSigned, fmtValue } from "@/lib/format";
import { Decomposition } from "@/components/decomposition";
import {
  describeDip,
  hScore,
  pickAnchors,
  tierLabel,
  type PickAnchor,
} from "./derive";

/**
 * One ranked trade card (scoring-system.md §7): You send / You get columns,
 * both sides' gains as decomposition sentences side by side (two-sided is the
 * ethic), acceptance tier, fairness + anti-fleece status, ask anchor,
 * ω-sensitivity, and §7.6 market-timing flags. The row-per-asset columns keep
 * a 3-for-1 as scannable as a 1-for-1.
 */
export function TradeCard({
  rec,
  rank,
  omegaMe,
  myCuts,
  frame = "card",
  showCounterparty = true,
}: {
  rec: TradeRec;
  /** 1-based position in the league-wide list (best-offers section only). */
  rank?: number;
  /** meta.omega_me — marks the current row of the ω-sensitivity line. */
  omegaMe: number;
  /** My scheduled-cut names (league-table cut_list) — tags doomed inventory. */
  myCuts: string[];
  frame?: "card" | "inset";
  showCounterparty?: boolean;
}) {
  const h = hScore(rec);
  const anchors = pickAnchors(rec);
  const f = rec.fairness;
  const Heading = frame === "card" ? ("h3" as const) : ("h4" as const);
  return (
    <article className={frame === "card" ? "card" : "rounded-md border border-line p-3"}>
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {rank !== undefined ? (
          <span className="num text-[13px] text-ink-muted">{rank}</span>
        ) : null}
        {showCounterparty ? (
          <Heading className="display text-[17px]">
            <span className="text-ink-muted">With</span> {rec.counterparty}
          </Heading>
        ) : null}
        <TierBadge rec={rec} />
        <span className="text-[11px] text-ink-muted">
          {rec.activity === "Low"
            ? "Low-activity partner — tier demoted"
            : `${rec.activity}-activity partner`}
        </span>
        {h !== null ? (
          <span
            className="ml-auto text-[11px] text-ink-muted"
            title="Rank score H: your gain plus 30% of theirs (§7.3) — orders the cards"
          >
            Rank score <span className="num">H {fmt1(h)}</span>
          </span>
        ) : null}
      </header>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <AssetColumn title="You send" assets={rec.give} cuts={myCuts} />
        <AssetColumn title="You get" assets={rec.get} />
      </div>

      <div className="mt-3 grid gap-x-6 gap-y-2 lg:grid-cols-2">
        <Decomposition
          side={rec.sides.me}
          tables={rec.audit.lineup_tables.me}
          lead={<SideTag>You</SideTag>}
        />
        <Decomposition
          side={rec.sides.them}
          tables={rec.audit.lineup_tables.them}
          lead={<SideTag>{rec.counterparty}</SideTag>}
        />
      </div>

      <footer className="mt-3 space-y-1 border-t border-line pt-2 text-[11.5px] text-ink-muted">
        <p>
          Fairness: adjusted <span className="num">{fmt1(f.adj_give)}</span> vs{" "}
          <span className="num">{fmt1(f.adj_get)}</span> — gap{" "}
          <span className="num">{fmtPct(f.gap_pct, 1)}</span> of a{" "}
          <span className="num">{fmtPct(f.band_pct, 0)}</span> band
          {f.gap_pct > f.band_pct ? " (over the band — scheduled-cut exemption)" : ""} · raw{" "}
          <span className="num">{f.raw_ratio.toFixed(2)}×</span> against the{" "}
          <span className="num">{f.cap.toFixed(2)}×</span> anti-fleece cap
        </p>
        <p>
          Ask: open <span className="num">+{fmtPct(rec.anchor_ask_pct, 0)}</span> above
          this package on your side · your score at{" "}
          <OmegaSens sens={rec.omega_sensitivity} omegaMe={omegaMe} />
        </p>
        {anchors.map((a, i) => (
          <p key={i}>
            <AnchorLine a={a} />
          </p>
        ))}
        {rec.dip_targets.length ? (
          <p>
            Dip flags: {rec.dip_targets.map(describeDip).join(" · ")} — value down ≥ 6%
            from the 30-day high with role unchanged
          </p>
        ) : null}
      </footer>
    </article>
  );
}

function TierBadge({ rec }: { rec: TradeRec }) {
  const tone =
    rec.tier === "A"
      ? "border-sky-deep bg-chip text-sky-deep"
      : rec.tier === "B"
        ? "border-line text-ink"
        : "border-line text-ink-muted";
  return (
    <span
      className={`inline-flex items-baseline gap-1.5 rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.08em] ${tone}`}
    >
      <span className="num text-[11.5px] font-semibold">{rec.tier}</span>
      {tierLabel(rec)}
    </span>
  );
}

function SideTag({ children }: { children: ReactNode }) {
  return (
    <span className="mr-1 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-ink">
      {children}
    </span>
  );
}

function AssetColumn({
  title,
  assets,
  cuts,
}: {
  title: string;
  assets: TradeAsset[];
  cuts?: string[];
}) {
  const total = assets.reduce((s, a) => s + a.v, 0);
  return (
    <div className="overflow-hidden rounded-md border border-line">
      <div className="flex items-baseline justify-between gap-2 border-b border-line bg-field px-3 py-1.5">
        <span className="text-[10.5px] font-medium uppercase tracking-[0.08em] text-ink-muted">
          {title}
        </span>
        <span className="num text-[11px] text-ink-muted" title="Raw Σv — the anti-fleece basis">
          Σ {fmtValue(total)}
        </span>
      </div>
      <ul className="divide-y divide-field">
        {assets.map((a, i) => (
          <li key={i} className="flex items-baseline gap-2 px-3 py-1.5">
            {a.type === "pick" ? (
              <span className="rounded bg-chip px-1 text-[9.5px] uppercase tracking-[0.08em] text-ink-muted">
                pick
              </span>
            ) : null}
            <span className="min-w-0">
              <span className="text-[13px]">{a.name}</span>
              {cuts?.includes(a.name) ? (
                <span
                  className="ml-1.5 rounded bg-chip px-1 text-[9.5px] uppercase tracking-[0.08em] text-ink-muted"
                  title="Scheduled Aug-15 cut — doomed inventory"
                >
                  cut due
                </span>
              ) : null}
              {a.pricing ? (
                <span className="block text-[10.5px] text-ink-muted">
                  {a.pricing.band} — {a.pricing.band_reason}
                </span>
              ) : null}
            </span>
            <span className="num ml-auto text-right text-[13px]">
              {fmtValue(a.v)}
              {a.mv !== undefined && Math.round(a.mv) !== Math.round(a.v) ? (
                <span
                  className="block text-[10.5px] text-ink-muted"
                  title="Market-visible value (tranche anchor)"
                >
                  mkt {fmtValue(a.mv)}
                </span>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function OmegaSens({
  sens,
  omegaMe,
}: {
  sens: Record<string, number>;
  omegaMe: number;
}) {
  const entries = Object.entries(sens).sort((a, b) => Number(a[0]) - Number(b[0]));
  return (
    <>
      {entries.map(([k, v], i) => {
        const current = Math.abs(Number(k) - omegaMe) < 1e-9;
        return (
          <span key={k} className={current ? "text-ink" : undefined}>
            {i > 0 ? " · " : ""}ω {k}{" "}
            <span className={`num${v < 0 ? " text-star" : ""}`}>{fmtSigned(v, 1)}</span>
            {current ? " (now)" : ""}
          </span>
        );
      })}
    </>
  );
}

function AnchorLine({ a }: { a: PickAnchor }) {
  const belowFloor = a.side === "give" && a.tranche < a.sell_floor;
  const arb = a.concrete - a.tranche;
  return (
    <>
      Pick anchor: {a.pick} ({a.side === "give" ? "you send" : "you get"}) — market
      anchors <span className="num">{fmtValue(a.tranche)}</span>, concrete{" "}
      <span className="num">{fmtValue(a.concrete)}</span>
      {a.side === "give" ? (
        <>
          , sell floor <span className="num">{fmtValue(a.sell_floor)}</span>
        </>
      ) : (
        <>
          {" "}
          (anchor arb{" "}
          <span className={`num${arb < 0 ? " text-star" : ""}`}>{fmtSigned(arb)}</span>)
        </>
      )}
      {belowFloor ? (
        <span className="ml-1.5 rounded border border-line px-1 text-[9.5px] uppercase tracking-[0.08em]">
          below sell floor
        </span>
      ) : null}
    </>
  );
}
