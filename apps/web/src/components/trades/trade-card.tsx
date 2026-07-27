import type { TradeAsset, TradeRec } from "@/lib/queries";
import { fmtPct, fmtSigned, fmtValue } from "@/lib/format";
import { ValueChip } from "@/components/value-chip";
import { legLabel, ord, postureEvidenceNote } from "./derive";

/**
 * One ranked trade leg (scoring-system.md v3 §2–§5): You send / You get at
 * face KTC value, the headline ΔW(you) with the honest zero-sum "them" line,
 * the §3 gate strip (band gap, anti-fleece ratio, PASS), the §4 posture
 * shape line with visible holes, and the §5 execution notes (sequencing,
 * exclusive-with, anchor ask). The row-per-asset columns keep a 3-for-1 as
 * scannable as a 1-for-1.
 */
export function TradeCard({ rec, compact = false }: { rec: TradeRec; compact?: boolean }) {
  return (
    <article className="card" id={`leg-${rec.id}`}>
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {rec.rank !== undefined ? (
          <span
            className="num text-[13px] text-ink-muted"
            title="Rank: posture fit first, then ΔW(you)"
          >
            {rec.rank}
          </span>
        ) : null}
        <h3 className="display text-[17px]">
          <span className="text-ink-muted">With</span> {rec.counterparty}
        </h3>
        <LegBadge rec={rec} />
        <span className="num text-[11px] text-ink-muted">{rec.id}</span>
        <span className="ml-auto flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <ValueChip label="ΔW you" value={rec.dW.me} emphasis />
          <span
            className="text-[11.5px] text-ink-muted"
            title="Exact zero-sum by construction — their loss is your gain (§11.1)"
          >
            them <span className={`num${rec.dW.them < 0 ? " text-star" : ""}`}>
              {fmtSigned(rec.dW.them)}
            </span>
          </span>
        </span>
      </header>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <AssetColumn title="You send" assets={rec.give} />
        <AssetColumn title="You get" assets={rec.get} />
      </div>

      <GateStrip rec={rec} />

      <footer className="mt-2 space-y-1 text-[11.5px] text-ink-muted">
        <p>
          Shape: {rec.posture.shape} →{" "}
          <span className="font-medium text-ink">
            {rec.posture.label} {rec.counterparty}
          </span>{" "}
          ({postureEvidenceNote(rec)})
          {rec.posture.fit ? null : (
            <span> · does not fit posture — expect a harder sell</span>
          )}
          {rec.holes.length ? (
            <>
              {" "}
              · aims at their{" "}
              {rec.holes
                .map((h) => `${h.pos} (${ord(h.their_rank)})`)
                .join(", ")}
            </>
          ) : null}
        </p>
        <p>Sequencing: {rec.sequencing}</p>
        {!compact ? (
          <p>
            Ask: {rec.anchor_ask.note} — open at ≈{" "}
            <span className="num">{fmtValue(rec.anchor_ask.ask)}</span> on your side
          </p>
        ) : null}
        {rec.ceiling ? (
          <p title={rec.ceiling.note}>
            Band ceiling for this package: ≈{" "}
            <span className="num">{fmtValue(rec.ceiling.value)}</span> — negotiating
            room above the proposal
          </p>
        ) : null}
        {rec.exclusive_with.length ? (
          <p title="Shared assets — executing this leg takes the others off the board (§5)">
            Exclusive with{" "}
            <span className="num">{rec.exclusive_with.join(", ")}</span>
          </p>
        ) : null}
        {rec.taxi_stashed.me.length || rec.taxi_stashed.them.length ? (
          <p>
            Taxi routing:{" "}
            {rec.taxi_stashed.me.length
              ? `you stash ${rec.taxi_stashed.me.join(", ")}`
              : null}
            {rec.taxi_stashed.me.length && rec.taxi_stashed.them.length ? " · " : null}
            {rec.taxi_stashed.them.length
              ? `they stash ${rec.taxi_stashed.them.join(", ")}`
              : null}
          </p>
        ) : null}
        {rec.dip_notes.length ? (
          <p>Buy-low: {rec.dip_notes.join(", ")} — trading below the trailing-30-day high</p>
        ) : null}
        {rec.unvalued.length ? (
          <p className="text-ink">
            <WarnTag>unvalued</WarnTag> {rec.unvalued.join(", ")} — no KTC price;
            contributes 0 to ΔW, verify by hand (§11.7)
          </p>
        ) : null}
      </footer>
    </article>
  );
}

function LegBadge({ rec }: { rec: TradeRec }) {
  const tone =
    rec.leg_type === "buy"
      ? "border-sky-deep text-sky-deep"
      : rec.leg_type === "sell"
        ? "border-ink text-ink"
        : "border-line text-ink-muted";
  return (
    <span
      className={`rounded border bg-surface px-1.5 py-0.5 text-[10px] uppercase tracking-[0.08em] ${tone}`}
      title={
        rec.leg_type === "buy"
          ? "Adds a body — pairs with a sell-leg for roster neutrality (§5)"
          : rec.leg_type === "sell"
            ? "Sheds a body — needs no pairing (§5)"
            : "Bodies in = bodies out — order free (§5)"
      }
    >
      {legLabel(rec)}
    </span>
  );
}

function WarnTag({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded border border-line bg-chip px-1 text-[9.5px] uppercase tracking-[0.08em] text-ink-muted">
      {children}
    </span>
  );
}

function AssetColumn({ title, assets }: { title: string; assets: TradeAsset[] }) {
  const total = assets.reduce((s, a) => s + a.v, 0);
  return (
    <div className="overflow-hidden rounded-md border border-line">
      <div className="flex items-baseline justify-between gap-2 border-b border-line bg-field px-3 py-1.5">
        <span className="text-[10.5px] font-medium uppercase tracking-[0.08em] text-ink-muted">
          {title}
        </span>
        <span
          className="num text-[11px] text-ink-muted"
          title="Face Σv — the ΔW and anti-fleece basis (§2)"
        >
          Σ {fmtValue(total)}
        </span>
      </div>
      <ul className="divide-y divide-field">
        {assets.map((a) => (
          <li key={a.key} className="flex items-baseline gap-2 px-3 py-1.5">
            {a.type === "pick" ? (
              <span className="rounded bg-chip px-1 text-[9.5px] uppercase tracking-[0.08em] text-ink-muted">
                pick
              </span>
            ) : null}
            <span className="min-w-0">
              <span className="text-[13px]">{a.name}</span>
              {a.unvalued ? (
                <span
                  className="ml-1.5 rounded border border-line bg-chip px-1 text-[9.5px] uppercase tracking-[0.08em] text-ink-muted"
                  title="No KTC price on record — contributes 0 to ΔW (§11.7)"
                >
                  unvalued
                </span>
              ) : null}
            </span>
            <span className="num ml-auto text-right text-[13px]">
              {a.unvalued ? "—" : fmtValue(a.v)}
              {a.concrete !== undefined ? (
                <span
                  className="block text-[10.5px] text-ink-muted"
                  title={a.note ?? "Rookie-board slot value — information only, never scored"}
                >
                  concrete {fmtValue(a.concrete)}
                </span>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The §3 fairness gate, verbatim from the doc: band gap, raw ratio, verdict. */
function GateStrip({ rec }: { rec: TradeRec }) {
  const g = rec.gate;
  return (
    <p className="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-1 border-t border-line pt-2 text-[11.5px] text-ink-muted">
      <span
        title={`Adjusted values (consolidation-discounted): ${fmtValue(g.adj_give)} give vs ${fmtValue(g.adj_get)} get — gap ${fmtValue(g.gap)} of a ${fmtValue(g.band)} band`}
      >
        gap <span className="num">{fmtPct(g.gap_pct, 1)}</span> of{" "}
        <span className="num">{fmtPct(g.band_pct, 0)}</span> band
      </span>
      <span title="Raw Σv ratio against the anti-fleece cap — never exempted (§3.2)">
        raw <span className="num">{g.raw_ratio.toFixed(2)}×</span> of{" "}
        <span className="num">{g.cap.toFixed(2)}×</span> cap
      </span>
      <span title="Both post-trade rosters legal: minima, caps with taxi routing, IR, deadline (§3.3)">
        {g.legal ? "legal both sides" : "ILLEGAL"}
      </span>
      <span
        className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.08em] ${
          g.verdict === "PASS"
            ? "border-sky-deep text-sky-deep"
            : "border-star text-star"
        }`}
        title="Would they think it's fair? — the §3 gate over this league's observed KTC norms"
      >
        {g.verdict}
      </span>
    </p>
  );
}
