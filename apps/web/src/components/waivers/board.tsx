import type { PlayerInfo, WaiverTarget } from "@/lib/queries";
import { fmtFaab, fmtValue } from "@/lib/format";
import { Star } from "@/components/star";
import { Caret, InjuryTag, SignedCell, Tag } from "@/components/waivers/bits";

/**
 * The full waiver board: every scored target in claim-score rank order,
 * position filter on top. The filter is radios + CSS `:has` — client-side,
 * zero JS, and it only hides rows: star markers and ledger colors never
 * repaint. Each row expands (details/summary) to the plan line (§6).
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
          <span className="wv-r" title="Claim score = v(add) − v(drop) — the ranking score">
            Claim
          </span>
          <span className="wv-r" title="Lineup delta if claimed — bid sizing only, never the score">
            ΔL
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
        <SignedCell v={t.claim} decimals={0} />
        <SignedCell v={t.dL} />
        <span className="num wv-r text-ink-muted">{t.bid.D}</span>
        <span className="wv-r whitespace-nowrap">
          <span className="num">{fmtFaab(t.bid.bid)}</span>
          {t.taxi_stash ? (
            <>
              {" "}
              <Tag title="Stashes on taxi — consumes no active spot, no drop needed">
                taxi
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
          Add {t.player} ·{" "}
          {t.taxi_stash
            ? "stash on taxi — no drop needed"
            : `drop ${t.drop ?? "no one — a slot is open"}`}{" "}
          · bid <span className="num">{fmtFaab(t.bid.bid)}</span>
          <span className="num">
            {" "}
            · demand D {t.bid.D} · ceiling {fmtFaab(t.bid.ceiling)}
          </span>
          {t.bid.clamp !== null ? (
            <span className="num"> · clamp {fmtFaab(t.bid.clamp)}</span>
          ) : null}
        </p>
      </div>
    </details>
  );
}
