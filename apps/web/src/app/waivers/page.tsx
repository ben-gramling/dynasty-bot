import {
  getPlayerInfoMap,
  getWaiverBoard,
  type PlayerInfo,
  type QueuedClaim,
  type WaiverBoard,
} from "@/lib/queries";
import { fmtDateTime, fmtFaab, fmtValue } from "@/lib/format";
import { ValueChip } from "@/components/value-chip";
import { Board } from "@/components/waivers/board";
import { Caret } from "@/components/waivers/bits";
import { ClaimCard } from "@/components/waivers/claim-card";
import { DropQueue } from "@/components/waivers/drop-queue";
import { PromoteCard } from "@/components/waivers/promote-card";
import "./waivers.css";

/** How many recommended claims render as full cards before the board takes over. */
const TOP_CARDS = 5;

export default async function WaiversPage() {
  let board: WaiverBoard | null = null;
  let dbError = false;
  try {
    board = await getWaiverBoard();
  } catch {
    dbError = true;
  }

  if (dbError) {
    return (
      <section className="card">
        <h1 className="display text-[22px]">Waivers</h1>
        <p className="mt-2 text-ink-muted">
          Can&apos;t reach the database — check MONGODB_URI and retry.
        </p>
      </section>
    );
  }

  if (!board) {
    return (
      <section className="card">
        <h1 className="display text-[22px]">Waivers</h1>
        <p className="mt-2 text-ink-muted">No collector run yet — hit Refresh.</p>
      </section>
    );
  }

  let info: Record<string, PlayerInfo> = {};
  try {
    info = await getPlayerInfoMap([
      ...board.targets.map((t) => t.sid),
      ...board.drops.map((d) => d.sid),
    ]);
  } catch {
    // bios are enrichment only — the board renders without them
  }

  const offseason = board.mode === "offseason";
  const recommended = board.targets.filter((t) => t.recommended);
  const topCards = recommended.slice(0, TOP_CARDS);
  const restCount = recommended.length - topCards.length;
  const restAllZero = recommended.slice(TOP_CARDS).every((t) => t.bid.bid === 0);
  const freeCount = board.targets.filter((t) => t.free_option).length;
  const cutsDue = board.drops.filter((d) => d.scheduled_cut).length;
  const standingDrop = board.drops[0]?.player ?? null;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="display text-[22px]">Waivers</h1>
        <p className="wv-meta mt-1">
          <span>{offseason ? "Offseason mode" : "In-season mode"}</span>
          <span>
            FAAB left <span className="num">{fmtFaab(board.faab_remaining)}</span>
          </span>
          <span>
            <span className="num">{board.targets.length}</span> targets ·{" "}
            <span className="num">{freeCount}</span> free options
          </span>
          {standingDrop ? <span>Standing drop: {standingDrop}</span> : null}
          <span>
            Board computed <span className="num">{fmtDateTime(board.computed_at)}</span>
          </span>
        </p>
        {board.meta.alerts.length ? (
          <div className="card mt-3">
            <p className="font-semibold">Alerts</p>
            <ul className="mt-1 space-y-1 text-[12.5px]">
              {board.meta.alerts.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </header>

      <section className="card">
        <h2 className="display text-[17px]">Recommended claims</h2>
        <p className="mt-1 text-[12.5px] text-ink-muted">
          {offseason
            ? "Offseason bids: $0 uncontested · $1 when a rival wants him (D ≥ 1) · $3 cap when two do."
            : "In-season bids: sized by lineup gain against remaining budget, capped by the raw-value ceiling and 65% of FAAB."}
          {freeCount > 0 && cutsDue > 0 ? (
            <>
              {" "}
              Free option: with <span className="num">{cutsDue}</span> cuts due Aug 15,
              an add below the cut line scores ≈ 0 — the crunch charge cancels his
              value. Claim strictly-better doomed inventory at{" "}
              <span className="num">$0</span>; never pay for bodies you&apos;re about
              to cut.
            </>
          ) : null}
        </p>
        {topCards.length ? (
          <div className="mt-3 space-y-2">
            {topCards.map((t, i) => (
              <ClaimCard key={t.sid} t={t} info={info[t.sid]} defaultOpen={i === 0} />
            ))}
          </div>
        ) : (
          <p className="mt-3 text-ink-muted">
            No claims clear the bar today — the board below shows every scored target.
          </p>
        )}
        {restCount > 0 ? (
          <p className="mt-3 text-[12.5px] text-ink-muted">
            …and <span className="num">{restCount}</span> more recommended claims on the
            board below{restAllZero ? (
              <>
                {" "}
                — every one a free option at <span className="num">$0</span>
              </>
            ) : null}
            .
          </p>
        ) : null}
        {board.queued.length ? <Queued rows={board.queued} /> : null}
      </section>

      <section className="card">
        <h2 className="display text-[17px]">Full board</h2>
        <p className="mb-3 mt-1 text-[12.5px] text-ink-muted">
          Every scored target, ranked by crunch-aware net claim against the standing
          drop{standingDrop ? ` (${standingDrop})` : ""}. Expand a row for the full
          audit.
        </p>
        {board.targets.length ? (
          <Board targets={board.targets} info={info} />
        ) : (
          <p className="text-ink-muted">No waiver targets — the pool is empty.</p>
        )}
      </section>

      <section className="card">
        <h2 className="display text-[17px]">Drop queue</h2>
        <p className="mb-3 mt-1 text-[12.5px] text-ink-muted">
          Actives ranked by crunch-aware keep value (RV) — the head of the queue is
          the standing drop behind every claim. Aug 15 tags mark the draft-day cut
          plan.
        </p>
        {board.drops.length ? (
          <DropQueue drops={board.drops} info={info} />
        ) : (
          <p className="text-ink-muted">No drop candidates.</p>
        )}
      </section>

      {board.taxi_promotions.length ? (
        <section className="card">
          <h2 className="display text-[17px]">Taxi promotions</h2>
          <p className="mb-3 mt-1 text-[12.5px] text-ink-muted">
            Stashes worth activating now, with the drop each one forces.
          </p>
          <div className="space-y-2">
            {board.taxi_promotions.map((p) => (
              <PromoteCard key={p.player} p={p} />
            ))}
          </div>
        </section>
      ) : null}

      {board.rookie_inventory.length ? (
        <details className="card wv-details">
          <summary>
            <h2 className="display text-[17px]">Rookie-draft inventory</h2>
            <span className="text-[12.5px] text-ink-muted">
              <span className="num">{board.rookie_inventory.length}</span> players ·
              not claimable while the rookie draft is pending — these values price the
              picks
            </span>
            <Caret />
          </summary>
          <div className="wv-rookies mt-3">
            {board.rookie_inventory.map((r) => (
              <div key={r.player} className="wv-rookie">
                <span className="num w-6 text-right text-ink-muted">
                  {r.rookie_rank}
                </span>
                <span className="min-w-0 flex-1 truncate">{r.player}</span>
                <span className="text-ink-muted">{r.pos}</span>
                <span className="num w-14 text-right">{fmtValue(r.v)}</span>
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );
}

/** Post-draft queue (§6.1 erratum): swaps that flip positive once the crunch clears. */
function Queued({ rows }: { rows: QueuedClaim[] }) {
  return (
    <div className="mt-4 border-t border-line pt-3">
      <h3 className="display text-[13px] text-ink-muted">Queued for post-draft</h3>
      <ul className="mt-2 space-y-2">
        {rows.map((q) => (
          <li
            key={q.player}
            className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-[12.5px]"
          >
            <span className="font-medium">
              {q.action === "CLAIM" ? "Add" : q.action} {q.player}
            </span>
            {q.drop ? <span className="text-ink-muted">drop {q.drop}</span> : null}
            <ValueChip label="today" value={q.score_today} decimals={1} />
            <span className="text-ink-muted">→</span>
            <ValueChip label="post-draft" value={q.score_post_draft} decimals={1} />
            <span className="text-ink-muted">{q.note.replace(/^queued:\s*/, "")}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
