import type { DropRow, PlayerInfo } from "@/lib/queries";
import { fmtValue } from "@/lib/format";
import { InjuryTag, Tag } from "@/components/waivers/bits";

/**
 * The drop list (§6): actives ascending by KTC value — informational
 * housekeeping. The head of the list is the standing drop behind every
 * claim on the board.
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
        <span>Notes</span>
      </div>
      {drops.map((d, i) => (
        <div key={d.sid} className="wv-row wv-grid wv-grid--drops wv-static" data-pos={d.pos}>
          <span className="num wv-r text-ink-muted">{i + 1}</span>
          <span className="truncate">
            {d.player} <InjuryTag status={info?.[d.sid]?.injury ?? null} />
          </span>
          <span className="text-ink-muted">{d.pos}</span>
          <span className="text-ink-muted">{info?.[d.sid]?.team ?? "FA"}</span>
          <span className="num wv-r text-ink-muted">{info?.[d.sid]?.age ?? "—"}</span>
          <span className="num wv-r">{d.unvalued ? "—" : fmtValue(d.v)}</span>
          <span className="whitespace-nowrap">
            {i === 0 ? (
              <Tag emphasis title="Lowest-v active — the drop behind every claim on the board">
                standing drop
              </Tag>
            ) : null}{" "}
            {d.unvalued ? (
              <Tag title="No KTC value on record — a body, not value; never treat 0 as truth">
                unvalued
              </Tag>
            ) : null}
          </span>
        </div>
      ))}
    </div>
  );
}
