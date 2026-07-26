import os

_client = None
_test_db = None


def get_client():
    """Get the shared MongoClient singleton."""
    global _client
    if _client is None:
        from pymongo import MongoClient

        # serverSelectionTimeoutMS matches PyMongo's default (30s) so an
        # Atlas primary election — which typically completes in 10-15s —
        # doesn't kill short-lived tasks like the collector Lambda, which
        # has no auto-restart.
        _client = MongoClient(
            host=os.environ["MONGODB_URI"],
            serverSelectionTimeoutMS=30000,
            connectTimeoutMS=5000,
            socketTimeoutMS=30000,
            maxIdleTimeMS=60000,
        )
    return _client


def get_db(db_name=None):
    """Get a database by name. Returns the test db if one was injected."""
    if _test_db is not None:
        return _test_db
    if db_name is None:
        db_name = os.environ.get("MONGODB_DB", "dynasty-bot")
    return get_client()[db_name]


def set_db(db):
    """For testing: inject a mock database."""
    global _test_db
    _test_db = db
