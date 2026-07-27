"""dynasty-bot collector: Sleeper sync + KTC scrape + crosswalk -> Mongo.

Runs as a zip Lambda (`app.lambda_handler`, daily EventBridge cron + on-demand
web Refresh) and locally via `just collect`. DRY_RUN=1 skips all Mongo I/O and
prints counts.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

from core import ktc, store
from core.crosswalk import build_crosswalk
from core.scoring import Snapshot, compute_all
from core.sleeper import LEAGUE_ID_2025, LEAGUE_ID_2026, MY_ROSTER_ID, SleeperClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("collector")

PLAYERS_MAX_AGE = timedelta(hours=20)  # Sleeper asks for at most one dump per day


def collect(dry_run: bool = False) -> dict:
    started = datetime.now(timezone.utc)
    counts: dict[str, int] = {}
    try:
        with SleeperClient() as client:
            state = client.state()
            league = client.league()
            rosters = client.rosters()
            users = client.users()
            traded_picks = client.traded_picks()
            drafts = [
                (client.draft(d["draft_id"]),
                 client.draft_picks(d["draft_id"]),
                 client.draft_traded_picks(d["draft_id"]))
                for d in client.drafts()
            ]
            week = state.get("leg") or 1  # offseason activity all lands in round 1
            transactions = client.transactions(LEAGUE_ID_2026, week)
            trending_add = client.trending("add")
            trending_drop = client.trending("drop")

            # §4 posture input: completed trades from BOTH league seasons.
            # The trailing-12-month window itself lives in scoring/posture.py.
            trade_history: list[dict] = []
            for league_id, season in ((LEAGUE_ID_2025, "2025"), (LEAGUE_ID_2026, "2026")):
                seen: set[str] = set()
                for rnd in range(1, 19):
                    for t in client.transactions(league_id, rnd) or []:
                        if (
                            t.get("type") == "trade"
                            and t.get("status") == "complete"
                            and t["transaction_id"] not in seen
                        ):
                            seen.add(t["transaction_id"])
                            trade_history.append(
                                {**t, "league_id": league_id, "season": season}
                            )
            trade_history.sort(
                key=lambda t: (t.get("status_updated") or t.get("created") or 0,
                               t["transaction_id"])
            )

            last_fetched = None if dry_run else store.get_players_last_fetched()
            players_stale = (
                last_fetched is None or started - last_fetched > PLAYERS_MAX_AGE
            )
            players_dump = client.players_nfl() if players_stale else None

        ktc_assets = ktc.scrape()

        sleeper_players = (
            store.player_subset(players_dump) if players_dump else store.load_players()
        )
        crosswalk, unresolved = build_crosswalk(ktc_assets, sleeper_players)
        if unresolved:
            logger.warning("crosswalk unresolved KTC playerIDs: %s", unresolved)

        counts = {
            "rosters": len(rosters),
            "users": len(users),
            "picks": len(traded_picks),
            "drafts": len(drafts),
            "transactions": len(transactions),
            "trade_history": len(trade_history),
            "trending_add": len(trending_add),
            "trending_drop": len(trending_drop),
            "players": len(sleeper_players) if players_dump else 0,
            "ktc_assets": len(ktc_assets),
            "crosswalk": len(crosswalk),
            "crosswalk_unresolved": len(unresolved),
        }

        # scoring recompute BEFORE any writes: raw and tab docs land together,
        # so a scoring failure never leaves fresh raw next to stale tab docs
        draft_doc = next(
            (d for d, _, _ in drafts if d.get("season") == league.get("season")),
            drafts[0][0] if drafts else {},
        )
        mapped = {e["sleeper_id"] for e in crosswalk.values()}
        rostered = {pid for r in rosters for pid in (r.get("players") or [])}
        # names for posture evidence too: players in the trade history may be
        # long gone from rosters and KTC
        traded_sids = {
            str(sid)
            for t in trade_history
            for sid in {**(t.get("adds") or {}), **(t.get("drops") or {})}
        }
        player_names = {
            sid: {"name": rec.get("full_name") or f"#{sid}", "pos": rec.get("position") or "UNK"}
            for sid in (rostered | traded_sids) - mapped
            if (rec := sleeper_players.get(sid))
        }
        snapshot = Snapshot(
            league=league,
            rosters=rosters,
            users=users,
            traded_picks=traded_picks,
            draft=draft_doc,
            state=state,
            ktc_assets=ktc_assets,
            crosswalk=crosswalk,
            my_roster_id=MY_ROSTER_ID,
            player_names=player_names,
            # read before today's append: the dip note is invariant to whether a
            # player's own same-day value is in its trailing max
            value_history_max={} if dry_run else store.ktc_value_history_max(),
            transactions=trade_history,
            posture_overrides={} if dry_run else store.posture_overrides(),
        )
        computed_at = datetime.now(timezone.utc)
        outputs = compute_all(snapshot)
        for alert in outputs["meta"]["alerts"]:
            logger.warning("scoring alert: %s", alert)
        counts["waiver_targets"] = len(outputs["waiver_board"]["targets"])
        counts["trade_recs"] = len(outputs["trade_recs"]["recommendations"])
        counts["trade_pairs"] = len(outputs["trade_recs"]["pairs"])
        counts["league_rows"] = len(outputs["league_table"]["rows"])
        # §5 v3.3 dial visibility: pair counts per return preset (saturated
        # counters are verified floors, marked with a trailing +)
        for e in outputs["trade_recs"]["counts_by_threshold"]:
            key = f"pairs_ge_{e['threshold']:g}pct".replace(".", "_")
            counts[key] = e["count"]
        logger.info(
            "trade pairs by threshold: %s%s",
            {f"{e['threshold']:g}%": f"{e['count']}{'+' if e['saturated'] else ''}"
             for e in outputs["trade_recs"]["counts_by_threshold"]},
            " (truncated: %s)" % outputs["trade_recs"]["truncated"]
            if outputs["trade_recs"]["truncated"] else "",
        )

        if not dry_run:
            store.upsert_league(league)
            store.upsert_state(state)
            for draft, picks, draft_traded in drafts:
                store.upsert_draft(draft, picks, draft_traded)
            store.upsert_trending(trending_add, trending_drop)
            store.replace_rosters(rosters)
            store.replace_users(users)
            store.replace_picks(traded_picks)
            store.upsert_transactions(week, transactions)
            store.upsert_trades(trade_history)
            if players_dump:
                store.refresh_players(players_dump)
                store.set_players_last_fetched(started)
            store.replace_ktc_latest(ktc_assets)
            store.append_ktc_history(ktc_assets)
            store.replace_crosswalk(crosswalk, meta={"unresolved": unresolved})
            store.save_scoring(outputs, computed_at)

        run = {
            "started": started,
            "finished": datetime.now(timezone.utc),
            "ok": True,
            "counts": counts,
            "error": None,
        }
    except Exception as exc:
        run = {
            "started": started,
            "finished": datetime.now(timezone.utc),
            "ok": False,
            "counts": counts,
            "error": f"{type(exc).__name__}: {exc}",
        }
        if not dry_run:
            store.log_run(run)
        raise
    if not dry_run:
        store.log_run(run)
    logger.info("collect ok=%s dry_run=%s counts=%s", run["ok"], dry_run, json.dumps(counts))
    if dry_run:
        print(json.dumps(counts, indent=2))
    return run


def lambda_handler(event, context):
    run = collect(dry_run=os.environ.get("DRY_RUN") == "1")
    return {"ok": run["ok"], "counts": run["counts"]}


if __name__ == "__main__":
    lambda_handler(None, None)
