from core.db import get_db


def league():
    """The league collection (league doc + state/draft/trending singletons)."""
    return get_db()["league"]


def rosters():
    """The rosters collection (one doc per roster_id)."""
    return get_db()["rosters"]


def users():
    """The users collection (one doc per league member)."""
    return get_db()["users"]


def picks():
    """The picks collection (league-level traded picks)."""
    return get_db()["picks"]


def transactions():
    """The transactions collection (one doc per transaction_id)."""
    return get_db()["transactions"]


def players():
    """The players collection (Sleeper dump subset, one doc per player_id)."""
    return get_db()["players"]


def ktc_latest():
    """The ktc-latest collection (current KTC snapshot, one doc per asset)."""
    return get_db()["ktc-latest"]


def ktc_history():
    """The ktc-history collection (append-only daily per-asset values)."""
    return get_db()["ktc-history"]


def crosswalk():
    """The crosswalk collection (KTC playerID -> Sleeper player_id map)."""
    return get_db()["crosswalk"]


def waiver_board():
    """The waiver-board collection (scoring output)."""
    return get_db()["waiver-board"]


def trade_recs():
    """The trade-recs collection (scoring output)."""
    return get_db()["trade-recs"]


def league_table():
    """The league-table collection (scoring output)."""
    return get_db()["league-table"]


def runs():
    """The runs collection (collector run log + meta doc)."""
    return get_db()["runs"]
