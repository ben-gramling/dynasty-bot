import type { DropRow, PlayerInfo } from "@/lib/queries";
import { fmtValue } from "@/lib/format";
import { Decomposition } from "@/components/decomposition";
import { Caret, InjuryTag, Tag, fmt1 } from "@/components/waivers/bits";

/**
 * The drop queue (§6.2): actives ranked ascending by crunch-aware keep value
 * RV. The head of the queue is the standing drop behind every claim on the
 * board; scheduled cuts carry the Aug-15 tag (the draft-day drop plan); rows
 * above the drop floor demand explicit confirmation. Every row expands to its
 * §12 decomposition (score = −RV).
 */
export function DropQueue({
  drops,
  info,
}: {
  drops: DropRow[];
  info: Record<string, PlayerInfo>;
}) {
  return (
    <div className="wv-scroll">
      <div className="wv-grid wv-grid--drops wv-head" aria-hidden>
        <span className="wv-r">#</span>
        <span>Player</span>
        <span>Pos</span>
        <span>Team</span>
        <span className="wv-r">Age</span>
        <span className="wv-r">KTC</span>
        <span className="wv-r" title="Crunch-aware keep value — what dropping him really costs">
          RV
        </span>
        <span className="wv-r" title="Gross keep value, before the crunch discount">
          RV⁰
        </span>
        <span>Notes</span>
        <span />
      </div>
      {drops.map((d, i) => (
        <QueueRow key={d.sid} d={d} n={i + 1} info={info[d.sid]} />
      ))}
    </div>
  );
}

function QueueRow({ d, n, info }: { d: DropRow; n: number; info?: PlayerInfo }) {
  return (
    <details className="wv-row" data-pos={d.pos}>
      <summary className="wv-grid wv-grid--drops">
        <span className="num wv-r text-ink-muted">{n}</span>
        <span className="truncate">
          {d.player} <InjuryTag status={info?.injury ?? null} />
        </span>
        <span className="text-ink-muted">{d.pos}</span>
        <span className="text-ink-muted">{info?.team ?? "FA"}</span>
        <span className="num wv-r text-ink-muted">{info?.age ?? "—"}</span>
        <span className="num wv-r">{fmtValue(d.v)}</span>
        <span className="num wv-r">{fmt1(d.rv)}</span>
        <span className="num wv-r text-ink-muted">{fmt1(d.rv0)}</span>
        <span className="whitespace-nowrap">
          {d.scheduled_cut ? (
            <Tag emphasis title="Head of the cut plan — due at the Aug 15 roster lock">
              Aug 15 cut
            </Tag>
          ) : null}{" "}
          {d.unvalued ? <Tag title="No KTC value on record">unvalued</Tag> : null}{" "}
          {d.require_confirm ? (
            <Tag title="Gross keep value sits above the drop floor — confirm before dropping">
              confirm first
            </Tag>
          ) : null}
        </span>
        <Caret />
      </summary>
      <div className="wv-row-detail">
        <p className="wv-plan">
          Drop {d.player} · costs <span className="num">{fmt1(d.rv)}</span> crunch-aware
          {" "}(<span className="num">{fmt1(d.rv0)}</span> gross)
          {d.scheduled_cut ? " · already part of the Aug 15 cut plan" : ""}
          {d.require_confirm ? " · above the drop floor — confirm before dropping" : ""}
        </p>
        <div className="mt-1.5">
          <Decomposition
            side={d.sides.me}
            tables={d.audit.lineup_tables}
            defaultOpen
          />
        </div>
      </div>
    </details>
  );
}
