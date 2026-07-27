import type { PlayerInfo, WaiverTarget } from "@/lib/queries";
import { fmtFaab, fmtValue } from "@/lib/format";
import { Star } from "@/components/star";
import { ValueChip } from "@/components/value-chip";
import { InjuryTag, Tag } from "@/components/waivers/bits";

/**
 * A prominent recommended-claim card: verdict verb, bio line, the
 * add/drop/bid plan in user words, and the claim sentence as value chips —
 * claim = v(add) − v(drop) straight off the doc (§6), never recomputed.
 */
export function ClaimCard({ t, info }: { t: WaiverTarget; info?: PlayerInfo }) {
  const bio = [t.pos, info?.team ?? "FA", info?.age != null ? `age ${info.age}` : null]
    .filter(Boolean)
    .join(" · ");
  return (
    <article className="rounded-md border border-line bg-surface px-4 py-3">
      <div className="wv-card-head">
        <span className="wv-verdict flex items-baseline gap-1.5">
          {t.recommended ? <Star size={11} title="Recommended" /> : null}
          Claim
        </span>
        <span className="wv-player">{t.player}</span>
        <span className="text-[12.5px] text-ink-muted">{bio}</span>
        <InjuryTag status={info?.injury ?? null} />
        {t.taxi_stash ? (
          <Tag emphasis title="Erratum 10: stashes on taxi — consumes no active spot, no drop needed">
            taxi stash
          </Tag>
        ) : null}
        {t.dip ? <Tag title="KTC value dipping — buy-low window">dip</Tag> : null}
        <span className="num ml-auto text-[14px]">KTC {fmtValue(t.v)}</span>
      </div>
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
      <p className="mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-1">
        <ValueChip label="claim" value={t.claim} emphasis />
        <span className="text-[11px] text-ink-muted">
          = v(add) − v(drop)
        </span>
        <ValueChip label="bid" text={fmtFaab(t.bid.bid)} />
      </p>
    </article>
  );
}
