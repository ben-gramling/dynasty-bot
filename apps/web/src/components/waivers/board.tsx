import type { PlayerInfo, WaiverTarget } from "@/lib/queries";
import { fmtFaab, fmtValue } from "@/lib/format";
import { Decomposition } from "@/components/decomposition";
import { Star } from "@/components/star";
import { ValueChip } from "@/components/value-chip";
import { Caret, InjuryTag, SignedCell, Tag } from "@/components/waivers/bits";

/**
 * The full waiver board: every scored target in NetClaim rank order, position
 * filter on top. The filter is radios + CSS `:has` — client-side, zero JS, and
 * it only hides rows: star markers and ledger colors never repaint.
 * Each row expands (details/summary) to the plan line + §12 decomposition.
 */

const POSITIONS = ["QB", "RB", "WR", "TE"] as const;

export function Board({
  targets,
  info,
}: {
  targets: WaiverTarget[];
  info: Record<string, PlayerInfo>;
}) {
  const counts = new Map<string, number>();
  for (const t of targets) counts.set(t.pos, (counts.get(t.pos) ?? 0) + 1);

  return (
    <div className="wv-board">
      <fieldset className="wv-filter">
        <legend className="sr-only">Filter the board by position</legend>
        <label>
          <input type="radio" name="wv-pos" value="ALL" defaultChecked />
          <span>
            All <span className="num">{targets.length}</span>
          </span>
        </label>
        {POSITIONS.filter((p) => counts.get(p)).map((p) => (
          <label key={p}>
            <input type="radio" name="wv-pos" value={p} />
            <span>
              {p} <span className="num">{counts.get(p)}</span>
            </span>
          </label>
        ))}
      </fieldset>

      <div className="wv-scroll mt-3">
        <div className="wv-grid wv-head" aria-hidden>
          <span className="wv-r">#</span>
          <span>Player</span>
          <span>Pos</span>
          <span>Team</span>
          <span className="wv-r">Age</span>
          <span className="wv-r">KTC</span>
          <span className="wv-r" title="Lineup delta if claimed">
            ΔL
          </span>
          <span className="wv-r" title="Crunch-aware NetClaim — the ranking score">
            Net
          </span>
          <span className="wv-r" title="NetClaim without the crunch charge">
            Raw
          </span>
          <span className="wv-r" title="Rival demand — teams that want him and can pay">
            D
          </span>
          <span className="wv-r">Bid</span>
          <span />
        </div>
        {targets.map((t) => (
          <BoardRow key={t.sid} t={t} info={info[t.sid]} />
        ))}
      </div>
    </div>
  );
}

function BoardRow({ t, info }: { t: WaiverTarget; info?: PlayerInfo }) {
  return (
    <details className="wv-row" data-pos={t.pos}>
      <summary className="wv-grid">
        <span className="num wv-r text-ink-muted">{t.rank}</span>
        <span className="truncate">
          {t.recommended ? (
            <Star size={9} className="mr-1 inline-block" title="Recommended claim" />
          ) : null}
          {t.player} <InjuryTag status={info?.injury ?? null} />
        </span>
        <span className="text-ink-muted">{t.pos}</span>
        <span className="text-ink-muted">{info?.team ?? "FA"}</span>
        <span className="num wv-r text-ink-muted">{info?.age ?? "—"}</span>
        <span className="num wv-r">{fmtValue(t.v)}</span>
        <SignedCell v={t.dL} />
        <SignedCell v={t.netclaim} />
        <SignedCell v={t.netclaim_raw} />
        <span className="num wv-r text-ink-muted">{t.bid.D}</span>
        <span className="wv-r whitespace-nowrap">
          <span className="num">{fmtFaab(t.bid.bid)}</span>
          {t.free_option ? (
            <>
              {" "}
              <Tag title="Free-option rule: lands below the Aug-15 cut line — never bid on him">
                free
              </Tag>
            </>
          ) : null}
          {t.dip ? (
            <>
              {" "}
              <Tag title="KTC value dipping — buy-low window">dip</Tag>
            </>
          ) : null}
        </span>
        <Caret />
      </summary>
      <div className="wv-row-detail">
        <p className="wv-plan">
          Add {t.player} · drop {t.drop ?? "no one — a slot is open"} · bid{" "}
          <span className="num">{fmtFaab(t.bid.bid)}</span>
          {t.free_option ? " — free option, never pay" : ""}
          {t.ir_move ? ` · IR move: ${t.ir_move}` : ""}
          <span className="num">
            {" "}
            · ceiling {fmtFaab(t.bid.ceiling)}
          </span>
          {t.bid.clamp ? ` · clamp: ${t.bid.clamp}` : ""}
        </p>
        <div className="mt-1.5">
          <Decomposition
            side={t.sides.me}
            tables={t.sides.me.dL_terms.length ? t.audit.lineup_tables : undefined}
            scoreLabel="net claim"
            lead={<ValueChip label="bid" text={fmtFaab(t.bid.bid)} />}
            defaultOpen
          />
        </div>
      </div>
    </details>
  );
}
