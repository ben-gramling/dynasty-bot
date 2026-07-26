import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA = REPO_ROOT / "data"
FIXTURES = DATA / "fixtures"


def load_json(path: Path):
    return json.loads(path.read_text())


@pytest.fixture(scope="session")
def ktc_raw():
    return load_json(DATA / "ktc_raw.json")


@pytest.fixture(scope="session")
def ktc_sleeper_map():
    return load_json(DATA / "ktc_sleeper_map.json")


@pytest.fixture(scope="session")
def players_trimmed():
    return load_json(FIXTURES / "sleeper" / "players_trimmed.json")


@pytest.fixture(scope="session")
def ktc_sample_html():
    return (FIXTURES / "ktc_sample.html").read_text()
