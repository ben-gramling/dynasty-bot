import type { TradeAsset, TradeRec } from "@/lib/queries";
import { fmtPct, fmtSigned, fmtValue } from "@/lib/format";
import { ValueChip } from "@/components/value-chip";
import { legLabel, ord, postureEvidenceNote } from "./derive";

/**
 * One ranked trade leg (scoring-system.md v4 §2–§5): You send / You get at
 * face KTC value, the headline GUARANTEED FLOOR (min of the two objective
 * coordinates) with the interval up to the ceiling, both sides' own
 * coordinates ("starters +X · face +Y" — dF negates across sides, dS does
 * not), the §3 gate strip (KTC-calculator gap, anti-fleece ratio, PASS), the
 * §4 posture shape line with visible holes, and the §5 execution notes
 * (sequencing, exclusive-with, anchor ask). Pre-v4 docs (no `coords`) fall
 * back to the stored ledger line. The row-per-asset columns keep a 3-for-1 as
 * scannable as a 1-for-1.
 */
export function TradeCard({ rec, compact = false }: { rec: TradeRec; compact?: boolean }) {
  const c = rec.coords;
  return (
    <article className="card" id={`leg-${rec.id}`}>
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {rec.rank !== undefined ? (
          <span
            className="num text-[13px] text-ink-muted"
            title="Rank: guaranteed floor descending (§2 v4 maximin)"
          >
            {rec.rank}
          </span>
        ) : null}
        <h3 className="display text-[17px]">
          <span className="text-ink-muted">With</span> {rec.counterparty}
        </h3>
        <LegBadge rec={rec} />
        <span
          className="num text-[11px] text-ink-muted"
          title="Your count deltas (§5 v3.2): players count wherever they land — active or taxi; picks count as picks regardless of year"
        >
          {fmtSigned(rec.net_players.me)} players / {fmtSigned(rec.net_picks.me)}{" "}
          picks
        </span>
        <span className="num text-[11px] text-ink-muted">{rec.id}</span>
        <span className="ml-auto flex flex-wrap items-baseline gap-x-2 gap-y-1">
          {c && rec.floor ? (
            <>
              <ValueChip label="guaranteed you" value={rec.floor.me} emphasis />
              <span
                className="text-[11.5px] text-ink-muted"
                title="The §2 v4 interval: your gain lies between the guaranteed floor min(ΔS, ΔF) and the ceiling max(ΔS, ΔF), whatever your stored-value preference — this leg alone"
              >
                up to{" "}
                <span className="num">
                  {fmtSigned(Math.max(c.me.dS, c.me.dF))}
                </span>
              </span>
            </>
          ) : rec.dW ? (
            <ValueChip label="ΔW you" value={rec.dW.me} emphasis />
          ) : null}
        </span>
      </header>

      <CoordsLines rec={rec} />

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
            contributes 0 to both coordinates, verify by hand (§11.7)
          </p>
        ) : null}
      </footer>
    </article>
  );
}

/**
 * §2 v4: both sides' coordinates — "starters +X · face +Y" — with each side's
 * verdict context. ΔF negates exactly across the sides (face conservation);
 * ΔS is each side's own deployment, which is why a good trade can be good for
 * both. Preference sides show their breakeven δ*. Omitted for board docs
 * written before v4 (they carry the retired ledger split instead).
 */
function CoordsLines({ rec }: { rec: TradeRec }) {
  const c = rec.coords;
  if (!c) return null;
  return (
    <div className="mt-1.5 space-y-0.5 text-[11.5px] text-ink-muted">
      <p title="Your two objective coordinates (§2 v4): ΔS = starter value (max-Σv lineup at raw KTC over active + taxi), ΔF = total face owned (players + picks at tranche). No blend, no parameter — the gain is the interval between them.">
        you: starters <span className="num">{fmtSigned(c.me.dS)}</span> · face{" "}
        <span className="num">{fmtSigned(c.me.dF)}</span>
        <SideVerdict rec={rec} side="me" />
        {rec.coords_basis === "isolation" ? (
          <span> — this leg alone; the pair combines both legs</span>
        ) : null}
      </p>
      <p title="Their own coordinates against their own roster — dF is the exact negation of yours (face conserves), dS is not (deployment differs), so both sides can genuinely gain (§11.1)">
        them: starters <span className="num">{fmtSigned(c.them.dS)}</span> · face{" "}
        <span className="num">{fmtSigned(c.them.dF)}</span>
        <SideVerdict rec={rec} side="them" />
      </p>
    </div>
  );
}

/** Verdict tail for one side: objectively good, preference (with δ*), or bad. */
function SideVerdict({ rec, side }: { rec: TradeRec; side: "me" | "them" }) {
  const good = rec.verdict?.[side];
  const b = rec.breakeven?.[side];
  if (good) return <span> — objectively good</span>;
  if (b !== null && b !== undefined) {
    return (
      <span
        title="Not good for every rational preference — good exactly beyond this stored-value breakeven δ* = ΔS/(ΔS − ΔF) (§2 v4)"
      >
        {" "}
        — preference trade, δ* <span className="num">{b.toFixed(2)}</span>
      </span>
    );
  }
  if (good === false) return <span> — bad at every preference</span>;
  return null;
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
          ? "Adds player(s) — executes only inside a pair netting 0 players / 0 picks (§5 v3.2)"
          : rec.leg_type === "sell"
            ? "Sheds player(s) — a building block; pair before executing (§5 v3.2)"
            : "Players in = players out — check the pick delta; only 0 players / 0 picks executes alone (§5 v3.2)"
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
          title="Face Σv — what the market prices, the anti-fleece and return-denominator basis (§3)"
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
                  title="No KTC price on record — contributes 0 to both coordinates (§11.7)"
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
        title={`What their KTC trade calculator shows: ${fmtValue(g.adj_give)} your side vs ${fmtValue(g.adj_get)} theirs — gap ${fmtValue(g.gap)} of a ${fmtValue(g.band)} band (§3.1 exact port)`}
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
