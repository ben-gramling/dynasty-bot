# Fixtures

Snapshots of the Sleeper API (2026 league) and derived boards captured 2026-07-26.
Together with `data/ktc_raw.json` and `data/ktc_sleeper_map.json` they are the
ground truth for the scoring tests, which assert EXACT expected numbers against
these files. Tests never hit live APIs. Regenerating any fixture changes those
expected numbers and must be a deliberate act, done together with updating the
affected tests.
