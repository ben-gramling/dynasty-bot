import type { PlayerInfo, WaiverTarget } from "@/lib/queries";
import { fmtFaab, fmtSigned, fmtValue } from "@/lib/format";
import { Decomposition } from "@/components/decomposition";
import { Star } from "@/components/star";
import { ValueChip } from "@/components/value-chip";
import { InjuryTag, Tag } from "@/components/waivers/bits";

/**
 * A prominent recommended-claim card: verdict verb, bio line, the add/drop/bid
 * plan in user words, and the signature decomposition sentence (§12) with the
 * bid chip prepended. Full before/after lineup tables ride in the audit.
 */
export function ClaimCard({
  t,
  info,
  defaultOpen = false,
}: {
  t: WaiverTarget;
  info?: PlayerInfo;
  defaultOpen?: boolean;
}) {
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
        {t.free_option ? (
          <Tag emphasis title="Free-option rule: lands below the Aug-15 cut line, so the crunch charge cancels his value — never bid on him">
            free option
          </Tag>
        ) : null}
        {t.dip ? <Tag title="KTC value dipping — buy-low window">dip</Tag> : null}
        <span className="num ml-auto text-[14px]">KTC {fmtValue(t.v)}</span>
      </div>
      <p className="wv-plan">
        Add {t.player} · drop {t.drop ?? "no one — a slot is open"} · bid{" "}
        <span className="num">{fmtFaab(t.bid.bid)}</span>
        {t.ir_move ? ` · IR move: ${t.ir_move}` : ""}
        <span className="num">
          {" "}
          · raw {fmtSigned(t.netclaim_raw, 1)} · demand D {t.bid.D} · ceiling{" "}
          {fmtFaab(t.bid.ceiling)}
        </span>
        {t.bid.clamp ? ` · clamp: ${t.bid.clamp}` : ""}
      </p>
      <div className="mt-2">
        <Decomposition
          side={t.sides.me}
          tables={t.audit.lineup_tables}
          scoreLabel="net claim"
          lead={<ValueChip label="bid" text={fmtFaab(t.bid.bid)} />}
          defaultOpen={defaultOpen}
        />
      </div>
    </article>
  );
}
