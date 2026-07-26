"""Mongo persistence for the collector. Every writer takes an optional db
handle (defaults to core.db.get_db(), which honors set_db test injection).

Document keys:
  league        _id = league_id (kind "league"), "state:nfl", "trending",
                "draft:<draft_id>" (kind-tagged singletons)
  rosters       _id = roster_id (int)
  users         _id = user_id
  picks         _id = "<season>-<round>-<original roster_id>"
  transactions  _id = transaction_id, + week
  players       _id = player_id (Sleeper dump subset, skill positions only)
  ktc-latest    _id = str(playerID), raw KTC asset
  ktc-history   _id = "<playerID>:<date>", {playerID, date, value_1qb, value_sf, rank_1qb}
  crosswalk     _id = str(ktc playerID), + "meta" doc
  waiver-board  _id = "latest" singleton (compute_all waiver_board + meta)
  trade-recs    _id = "latest" singleton (compute_all trade_recs + meta)
  league-table  _id = "latest" singleton (compute_all league_table + my_team + meta)
  runs          run log entries + "meta" doc (players_last_fetched)
"""

from datetime import datetime, timedelta, timezone

from pymongo import ReplaceOne

from core.db import get_db

# Fields kept in the players collection: everything the crosswalk join
# (full_name/position/fantasy_positions/team/status) and the scoring/web
# layers (age, depth chart, injury, search_rank, ...) read.
PLAYER_FIELDS = (
    "player_id",
    "first_name",
    "last_name",
    "full_name",
    "search_full_name",
    "position",
    "fantasy_positions",
    "team",
    "age",
    "years_exp",
    "status",
    "injury_status",
    "injury_body_part",
    "injury_notes",
    "depth_chart_position",
    "depth_chart_order",
    "number",
    "search_rank",
    "news_updated",
    "birth_date",
)

SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def trim_player(rec: dict) -> dict:
    return {f: rec[f] for f in PLAYER_FIELDS if f in rec}


def player_subset(dump: dict[str, dict]) -> dict[str, dict]:
    """Skill-position players with a full_name, trimmed to PLAYER_FIELDS."""
    out = {}
    for pid, rec in dump.items():
        positions = set([rec["position"]] if rec.get("position") else [])
        positions |= set(rec.get("fantasy_positions") or [])
        if rec.get("full_name") and positions & SKILL_POSITIONS:
            out[pid] = trim_player(rec)
    return out


def pick_id(pick: dict) -> str:
    """Traded-pick identity: (season, round, original-owner roster_id) is unique."""
    return f"{pick['season']}-{pick['round']}-{pick['roster_id']}"


def ktc_history_rows(assets: list[dict], date: str) -> list[dict]:
    return [
        {
            "_id": f"{a['playerID']}:{date}",
            "playerID": a["playerID"],
            "date": date,
            "value_1qb": a["oneQBValues"]["value"],
            "value_sf": a["superflexValues"]["value"],
            "rank_1qb": a["oneQBValues"]["rank"],
        }
        for a in assets
    ]


def _replace_all(coll, docs: list[dict]) -> int:
    """Full-collection refresh with no reader-visible empty window: upsert the new
    generation in place, then prune ids that vanished. Not transactional — a crash
    mid-write leaves a mixed generation (fully rebuilt next run), never an empty one."""
    if docs:
        coll.bulk_write([ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in docs])
    coll.delete_many({"_id": {"$nin": [d["_id"] for d in docs]}})
    return len(docs)


# ---- sleeper refresh ----


def upsert_league(league: dict, db=None) -> None:
    coll = (db or get_db())["league"]
    doc = {**league, "_id": league["league_id"], "kind": "league", "fetched_at": _now()}
    coll.replace_one({"_id": doc["_id"]}, doc, upsert=True)


def upsert_state(state: dict, db=None) -> None:
    coll = (db or get_db())["league"]
    coll.replace_one(
        {"_id": "state:nfl"},
        {**state, "_id": "state:nfl", "kind": "state", "fetched_at": _now()},
        upsert=True,
    )


def upsert_draft(draft: dict, picks: list[dict], traded_picks: list[dict], db=None) -> None:
    coll = (db or get_db())["league"]
    doc = {
        **draft,
        "_id": f"draft:{draft['draft_id']}",
        "kind": "draft",
        "picks": picks,
        "traded_picks": traded_picks,
        "fetched_at": _now(),
    }
    coll.replace_one({"_id": doc["_id"]}, doc, upsert=True)


def upsert_trending(add: list[dict], drop: list[dict], db=None) -> None:
    coll = (db or get_db())["league"]
    coll.replace_one(
        {"_id": "trending"},
        {"_id": "trending", "kind": "trending", "add": add, "drop": drop, "fetched_at": _now()},
        upsert=True,
    )


def replace_rosters(rosters: list[dict], db=None) -> int:
    docs = [{**r, "_id": r["roster_id"], "fetched_at": _now()} for r in rosters]
    return _replace_all((db or get_db())["rosters"], docs)


def replace_users(users: list[dict], db=None) -> int:
    docs = [{**u, "_id": u["user_id"], "fetched_at": _now()} for u in users]
    return _replace_all((db or get_db())["users"], docs)


def replace_picks(traded_picks: list[dict], db=None) -> int:
    docs = [{**p, "_id": pick_id(p), "fetched_at": _now()} for p in traded_picks]
    return _replace_all((db or get_db())["picks"], docs)


def upsert_transactions(week: int, txs: list[dict], db=None) -> int:
    if not txs:
        return 0
    coll = (db or get_db())["transactions"]
    coll.bulk_write(
        [
            ReplaceOne(
                {"_id": t["transaction_id"]},
                {**t, "_id": t["transaction_id"], "week": week},
                upsert=True,
            )
            for t in txs
        ]
    )
    return len(txs)


def refresh_players(dump: dict[str, dict], db=None) -> int:
    docs = [{**rec, "_id": pid} for pid, rec in player_subset(dump).items()]
    return _replace_all((db or get_db())["players"], docs)


def load_players(db=None) -> dict[str, dict]:
    """Stored dump subset keyed by player_id (crosswalk input on dump-skip days)."""
    return {doc["_id"]: doc for doc in (db or get_db())["players"].find()}


# ---- ktc ----


def replace_ktc_latest(assets: list[dict], db=None) -> int:
    now = _now()
    docs = [{**a, "_id": str(a["playerID"]), "fetched_at": now} for a in assets]
    return _replace_all((db or get_db())["ktc-latest"], docs)


def append_ktc_history(assets: list[dict], date: str | None = None, db=None) -> int:
    """Append-only daily rows; idempotent per (playerID, date)."""
    date = date or _now().date().isoformat()
    rows = ktc_history_rows(assets, date)
    if not rows:
        return 0
    coll = (db or get_db())["ktc-history"]
    coll.bulk_write([ReplaceOne({"_id": r["_id"]}, r, upsert=True) for r in rows])
    return len(rows)


def ktc_value_history_max(days: int = 30, db=None) -> dict[str, float]:
    """§7.6 DIP input: ktc playerID (str) -> max value_1qb over the trailing days."""
    since = (_now() - timedelta(days=days)).date().isoformat()
    out: dict[str, float] = {}
    for row in (db or get_db())["ktc-history"].find({"date": {"$gte": since}}):
        pid = str(row["playerID"])
        if row["value_1qb"] > out.get(pid, -1):
            out[pid] = row["value_1qb"]
    return out


# ---- crosswalk ----


def replace_crosswalk(entries: dict[str, dict], meta: dict | None = None, db=None) -> int:
    docs = [{**e, "_id": ktc_id} for ktc_id, e in entries.items()]
    docs.append({"_id": "meta", **(meta or {}), "built_at": _now()})
    return _replace_all((db or get_db())["crosswalk"], docs) - 1


# ---- scoring outputs ----


def scoring_docs(outputs: dict, computed_at: datetime | None = None) -> dict[str, dict]:
    """compute_all output -> one "latest" singleton doc per tab collection.
    The my-team detail rides on league-table (it renders on the League tab)."""
    base = {"_id": "latest", "computed_at": computed_at or _now(), "meta": outputs["meta"]}
    return {
        "waiver-board": {**base, **outputs["waiver_board"]},
        "trade-recs": {**base, **outputs["trade_recs"]},
        "league-table": {**base, **outputs["league_table"], "my_team": outputs["my_team_detail"]},
    }


def save_scoring(outputs: dict, computed_at: datetime | None = None, db=None) -> None:
    db = db if db is not None else get_db()
    for name, doc in scoring_docs(outputs, computed_at).items():
        db[name].replace_one({"_id": "latest"}, doc, upsert=True)


# ---- runs ----


def log_run(run: dict, db=None) -> None:
    (db or get_db())["runs"].insert_one(run)


def get_players_last_fetched(db=None) -> datetime | None:
    meta = (db or get_db())["runs"].find_one({"_id": "meta"}) or {}
    ts = meta.get("players_last_fetched")
    return ts.replace(tzinfo=timezone.utc) if ts and ts.tzinfo is None else ts


def set_players_last_fetched(when: datetime | None = None, db=None) -> None:
    (db or get_db())["runs"].update_one(
        {"_id": "meta"},
        {"$set": {"players_last_fetched": when or _now()}},
        upsert=True,
    )
