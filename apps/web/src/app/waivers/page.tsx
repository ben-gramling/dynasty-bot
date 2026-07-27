import {
  getPlayerInfoMap,
  getWaiverBoard,
  type PlayerInfo,
  type WaiverBoard,
} from "@/lib/queries";
import { fmtDateTime, fmtFaab, fmtValue } from "@/lib/format";
import { Board } from "@/components/waivers/board";
import { Caret } from "@/components/waivers/bits";
import { ClaimCard } from "@/components/waivers/claim-card";
import { DropQueue } from "@/components/waivers/drop-queue";
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
  // The drop behind the claims: null when a roster slot is open (no drop needed).
  const claimDrop = board.targets.find((t) => !t.taxi_stash)?.drop ?? null;

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
            <span className="num">{recommended.length}</span> positive claims
          </span>
          {claimDrop ? (
            <span>Standing drop: {claimDrop}</span>
          ) : (
            <span>Open roster spot — claims need no drop</span>
          )}
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
          Claim score = v(add) − v(drop) against the standing drop; positive claims
          list here.{" "}
          {offseason
            ? "Offseason bids: $0 uncontested · $1 when a rival wants him · $3 cap when two do."
            : "In-season bids: the §6.4 ladder — lineup need against remaining budget, capped by the raw-value ceiling and 65% of FAAB."}
        </p>
        {topCards.length ? (
          <div className="mt-3 space-y-2">
            {topCards.map((t) => (
              <ClaimCard key={t.sid} t={t} info={info[t.sid]} />
            ))}
          </div>
        ) : (
          <p className="mt-3 text-ink-muted">
            No claims clear the bar today — the board below shows every scored target.
          </p>
        )}
        {restCount > 0 ? (
          <p className="mt-3 text-[12.5px] text-ink-muted">
            …and <span className="num">{restCount}</span> more positive claims on the
            board below{restAllZero ? (
              <>
                {" "}
                — every one uncontested at <span className="num">$0</span>
              </>
            ) : null}
            .
          </p>
        ) : null}
      </section>

      <section className="card">
        <h2 className="display text-[17px]">Full board</h2>
        <p className="mb-3 mt-1 text-[12.5px] text-ink-muted">
          Every scored target, ranked by claim score
          {claimDrop
            ? ` against the standing drop (${claimDrop})`
            : " — a roster slot is open, so no drop is charged"}
          . Expand a row for the plan.
        </p>
        {board.targets.length ? (
          <Board targets={board.targets} info={info} />
        ) : (
          <p className="text-ink-muted">No waiver targets — the pool is empty.</p>
        )}
      </section>

      <section className="card">
        <h2 className="display text-[17px]">Drop list</h2>
        <p className="mb-3 mt-1 text-[12.5px] text-ink-muted">
          Actives ascending by KTC value — informational housekeeping. The head of
          the list is the first player out whenever a claim needs a drop.
        </p>
        {board.drops.length ? (
          <DropQueue drops={board.drops} info={info} />
        ) : (
          <p className="text-ink-muted">No drop candidates.</p>
        )}
      </section>

      {board.taxi_fill.free_slots > 0 ? (
        <section className="card">
          <h2 className="display text-[17px]">Open taxi slots</h2>
          {board.taxi_fill.surplus_slots > 0 ? (
            <>
              <p className="mb-3 mt-1 text-[12.5px] text-ink-muted">
                <span className="num">{board.taxi_fill.surplus_slots}</span> surplus
                slot{board.taxi_fill.surplus_slots > 1 ? "s" : ""} open. A slot left
                empty at the week-4 lock is worth zero — stash one of these free
                options before then.
              </p>
              <ul className="space-y-1 text-[13px]">
                {board.taxi_fill.candidates.map((c) => (
                  <li key={c.player}>
                    <span className="font-medium">{c.player}</span>{" "}
                    <span className="text-ink-muted">{c.pos}</span>{" "}
                    <span className="num">{fmtValue(c.v)}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="mb-1 mt-1 text-[12.5px] text-ink-muted">
              <span className="num">{board.taxi_fill.free_slots}</span> open slot
              {board.taxi_fill.free_slots > 1 ? "s are" : " is"} earmarked to absorb
              incoming rookie-draft picks — leave it open; stashing here would force
              an extra cut on draft day.
            </p>
          )}
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
