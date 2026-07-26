"""Regenerate data/fixtures/sleeper/players_trimmed.json from a full Sleeper players dump.

The trimmed dump keeps only skill-position players (QB/RB/WR/TE via position or
fantasy_positions) with a full_name, and only the fields the crosswalk join and
the collector's players collection need. Trimming never changes crosswalk results:
the join index is restricted to exactly this population.

Usage: uv run python scripts/trim_players_dump.py <path-to-players_nfl.json>
"""

import json
import sys
from pathlib import Path

from core.store import player_subset

OUT = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "sleeper" / "players_trimmed.json"


def main() -> None:
    dump = json.loads(Path(sys.argv[1]).read_text())
    trimmed = player_subset(dump)
    OUT.write_text(json.dumps(trimmed, separators=(",", ":"), sort_keys=True))
    print(f"wrote {OUT} ({len(trimmed)} players, {OUT.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
