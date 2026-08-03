"""§12 v8: the hedge database — complete legs, exact searches, cached views.

The measured truth that shapes this module: the complete |favor| <= 5 pool is
~13.5M legs, and its >= 1%-floor crossing region is ~2.5e12 pairs at a ~53%
qualifying rate — the pair universe is not materializable at any dial setting.
Every possible hedge, however, is a pair of LEGS, and the legs are small. So:

- `build` enumerates the COMPLETE fair-band pool once (drain mode — no
  variant sampling at all), serializes it columnar (one .npy per column, a
  global package-descriptor list, an asset sidecar) TOGETHER WITH the full
  Snapshot it was priced from, and bakes the default per-counterparty board
  searches as the first cache entries.
- `HedgeDB.search` answers any §4a query with the seeded sound walk over the
  warm columns — the same integer-k5 key, XTOL boundary semantics,
  `pair_ds_bound` pricing skip and exact `pair_eval` the finder pins — with
  user filters applied to legs BEFORE crossing. The result list is provably
  the exact top-K under the active filters; counts are exact when the walk
  completed and verified floors otherwise (§11.12(e) verbatim).
- Every search result is cached under a fingerprint of the COMPILED
  constraints + sliders, so revisiting a filter state is instant and
  byte-identical, and intel changes (which compile differently) miss the
  cache exactly when they should.
- `HedgeDB.offer` scores an arbitrary proposal via `tr.propose` (real gate,
  outside-the-pool assets welcome) and crosses it against the stored legs of
  every other counterparty for its exact hedge set.

Boards render from the STORED snapshot's league — never from live Mongo — so
cards, KTC links and coordinates can never disagree with each other, whatever
has been collected since the build.

numpy is required only here, as the `core[hedgedb]` extra: the module imports
without it and raises a clear error on first use (the collector Lambda never
touches this path).

Determinism notes (§11.9 discipline):
- Package descriptors store asset keys IN PACKAGE ORDER; packages are
  rebuilt via `tr.package_of` from the stored snapshot's league, so float
  summation order — and therefore every gate/coordinate figure — is
  bit-identical to the build.
- All float columns are float64 stored verbatim (`np.save`); the two
  genuinely fractional pick prices survive exactly.
- Walk order is `sorted((u, i))` exactly as the finder does it; the columnar
  arrays only supply the (identical IEEE) inputs.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import constraints as cn
from . import model as md
from . import trades as tr
from .finder import DEFAULT_CACHE_DIR, params_fingerprint, _view_return
from .params import Params
from .snapshot import Snapshot

_SEED_WIDTH = 150  # §4a v6 warm-bar seed width — same as the finder's
_EMPTY4 = ((), (), (), ())
_SCHEMA_VERSION = 1

# scalar leg columns, one .npy each (float64/ints stored verbatim)
_COLUMNS = (
    "np", "nk", "opp", "mask", "favor", "dface", "sent", "a", "iso_floor",
    "give_pid", "get_pid",
    "out_off", "out_vals", "in_off", "in_vals",
)


def _np():
    try:
        import numpy
    except ImportError as e:  # pragma: no cover - environment-dependent
        raise ImportError(
            "the hedge database needs numpy — install the core[hedgedb] extra "
            "(uv sync installs it locally; the collector Lambda never needs it)"
        ) from e
    return numpy


# ------------------------------------------------------------ fingerprints


def _normalize(o: Any) -> Any:
    """Strip Mongo bookkeeping (`_id`, `fetched_at`) that changes on every
    collect without changing content, so an unchanged world reuses the DB."""
    if isinstance(o, Mapping):
        return {
            k: _normalize(v)
            for k, v in sorted(o.items())
            if k not in ("_id", "fetched_at")
        }
    if isinstance(o, (list, tuple)):
        return [_normalize(x) for x in o]
    return o


def content_fingerprint(snapshot: Snapshot) -> str:
    """Content hash of every PRICING input. Unlike the finder cache's
    fingerprint this one INCLUDES `ktc_calculator` — the DB persists priced
    VALUES (favor, ΔF, sent, pick prices), so every input that prices them
    must key it. `value_history_max` is deliberately excluded: it feeds only
    the display-level dip notes, which render from the stored snapshot anyway.
    Doc lists are sorted by content so Mongo natural order cannot flip the
    hash."""
    payload = {
        "league": snapshot.league,
        "rosters": snapshot.rosters,
        "users": snapshot.users,
        "traded_picks": snapshot.traded_picks,
        "draft": snapshot.draft,
        "state": snapshot.state,
        "ktc_assets": snapshot.ktc_assets,
        "crosswalk": snapshot.crosswalk,
        "my_roster_id": snapshot.my_roster_id,
        "player_names": snapshot.player_names,
        "transactions": snapshot.transactions,
        "posture_overrides": snapshot.posture_overrides,
        "ktc_calculator": snapshot.ktc_calculator,
    }
    payload = _normalize(payload)
    for key in ("rosters", "users", "traded_picks", "ktc_assets", "transactions"):
        payload[key] = sorted(
            payload[key], key=lambda d: json.dumps(d, sort_keys=True, default=str)
        )
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def db_dir(
    snapshot: Snapshot, params: Params, cache_dir: Path | str | None = None
) -> Path:
    root = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    cf = content_fingerprint(snapshot)[:16]
    pf = params_fingerprint(params)[:16]
    return root / "hedgedb" / f"{cf}-{pf}"


# ------------------------------------------------------- snapshot round-trip


_SNAPSHOT_FIELDS = (
    "league", "rosters", "users", "traded_picks", "draft", "state",
    "ktc_assets", "crosswalk", "my_roster_id", "player_names",
    "value_history_max", "transactions", "posture_overrides", "ktc_calculator",
)


def _snapshot_payload(snapshot: Snapshot) -> dict:
    return {k: getattr(snapshot, k) for k in _SNAPSHOT_FIELDS}


def _write_snapshot(path: Path, snapshot: Snapshot) -> Snapshot:
    """Serialize the snapshot and return the RELOADED copy — the build prices
    everything from the reloaded payload, so what a later `board`/`offer`
    rebuilds is byte-identical to what the arrays were computed from."""
    blob = json.dumps(_snapshot_payload(snapshot), default=str).encode()
    with gzip.open(path, "wb") as fh:
        fh.write(blob)
    return load_snapshot(path)


def load_snapshot(path: Path) -> Snapshot:
    with gzip.open(path, "rb") as fh:
        payload = json.loads(fh.read())
    return Snapshot(**payload)


# ------------------------------------------------------------------- build


def _leg_arrays(pool: tr.PairPool, numpy) -> tuple[dict, list[list[str]], list[dict]]:
    """Flatten the object pool into columns + the global package-descriptor
    list (asset keys IN PACKAGE ORDER — the reconstruction contract) + the
    asset sidecar (per-asset filter attributes)."""
    np_ = numpy
    n = len(pool.legs)
    pid_of: dict[tuple[str, ...], int] = {}
    descriptors: list[list[str]] = []
    asset_ix: dict[str, int] = {}
    assets: list[dict] = []

    def _pid(pkg: tr.Package) -> int:
        ident = tuple(a.key for a in pkg.assets)
        pid = pid_of.get(ident)
        if pid is None:
            pid = pid_of[ident] = len(descriptors)
            descriptors.append(list(ident))
            for a in pkg.assets:
                if a.key not in asset_ix:
                    asset_ix[a.key] = len(assets)
                    p = a.pick
                    assets.append(
                        {
                            "key": a.key,
                            "kind": a.kind,
                            "name": a.name,
                            "pos": a.pos,
                            "v": a.v,
                            "year": p.year if p is not None else None,
                            "round": p.round if p is not None else None,
                        }
                    )
        return pid

    cols = {
        "np": np_.empty(n, np_.int16),
        "nk": np_.empty(n, np_.int16),
        "opp": np_.empty(n, np_.int16),
        "mask": np_.empty(n, np_.uint64),
        "favor": np_.empty(n, np_.float64),
        "dface": np_.empty(n, np_.float64),
        "sent": np_.empty(n, np_.float64),
        "a": np_.empty(n, np_.float64),
        "iso_floor": np_.empty(n, np_.float64),
        "give_pid": np_.empty(n, np_.int32),
        "get_pid": np_.empty(n, np_.int32),
    }
    out_off = np_.zeros(4 * n + 1, np_.int64)
    in_off = np_.zeros(4 * n + 1, np_.int64)
    out_vals: list[float] = []
    in_vals: list[float] = []

    for i, leg in enumerate(pool.legs):
        if leg[tr.L_MASK] >> 64:
            raise ValueError(
                "give-list alphabet exceeds 64 bits — widen the mask column"
            )
        cols["np"][i] = leg[tr.L_NP]
        cols["nk"][i] = leg[tr.L_NK]
        cols["opp"][i] = leg[tr.L_OPP]
        cols["mask"][i] = leg[tr.L_MASK]
        cols["favor"][i] = leg[tr.L_FAVOR]
        cols["dface"][i] = leg[tr.L_DFACE]
        cols["sent"][i] = leg[tr.L_SENT]
        cols["a"][i] = leg[tr.L_A]
        cols["iso_floor"][i] = leg[tr.L_FLOOR]
        cols["give_pid"][i] = _pid(leg[tr.L_GIVE])
        cols["get_pid"][i] = _pid(leg[tr.L_GET])
        for j in range(4):
            seg = leg[tr.L_OUT4][j]
            out_vals.extend(seg)
            out_off[4 * i + j + 1] = out_off[4 * i + j] + len(seg)
            seg = leg[tr.L_IN4][j]
            in_vals.extend(seg)
            in_off[4 * i + j + 1] = in_off[4 * i + j] + len(seg)

    cols["out_off"] = out_off
    cols["out_vals"] = np_.asarray(out_vals, np_.float64)
    cols["in_off"] = in_off
    cols["in_vals"] = np_.asarray(in_vals, np_.float64)
    return cols, descriptors, assets


def build(
    snapshot: Snapshot,
    params: Params | None = None,
    *,
    cache_dir: Path | str | None = None,
    bake: bool = True,
    bake_intel: Sequence[Mapping] | None = None,
    bake_workers: int = 0,
    progress=None,
) -> "HedgeDB":
    """Cold start: enumerate the complete band pool, persist it, bake the
    default board. Idempotent — an existing complete DB for this content
    fingerprint is reopened, not rebuilt."""
    numpy = _np()
    params = params or Params()
    target = db_dir(snapshot, params, cache_dir)
    say = progress or (lambda msg: None)
    if (target / "meta.json").exists():
        say(f"hedge DB already built for this snapshot: {target}")
        db = HedgeDB.open(target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(
            tempfile.mkdtemp(dir=str(target.parent), prefix=target.name + ".tmp")
        )
        try:
            say("persisting the snapshot …")
            stored = _write_snapshot(tmp / "snapshot.json.gz", snapshot)
            league = md.build_league(stored, params)
            say(
                f"building the complete |favor| <= {params.hedgedb_band:g} pool "
                "(~2 min, ~4.5 GB) …"
            )
            pool = tr.build_pair_pool(
                league, enforce_posture=False, favor_band=params.hedgedb_band
            )
            say(f"pool: {len(pool.legs):,} legs — serializing columnar …")
            cols, descriptors, assets = _leg_arrays(pool, numpy)
            n_legs = len(pool.legs)
            opp_names = list(pool.opp_names)
            del pool  # drop the ~4.5 GB object graph before the bake
            legs_dir = tmp / "legs"
            legs_dir.mkdir()
            for name, arr in cols.items():
                numpy.save(legs_dir / f"{name}.npy", arr)
            del cols
            (tmp / "packages.json").write_text(
                json.dumps(descriptors, separators=(",", ":"))
            )
            (tmp / "assets.json").write_text(
                json.dumps(assets, separators=(",", ":"))
            )
            (tmp / "searches").mkdir()
            meta = {
                "schema": _SCHEMA_VERSION,
                "content_fingerprint": content_fingerprint(stored),
                "params_fingerprint": params_fingerprint(params),
                "params": asdict(params),  # informational; identity is the hash
                "band": params.hedgedb_band,
                "store_top": params.hedgedb_store_top,
                "legs": n_legs,
                "opp_names": opp_names,
                "packages": len(descriptors),
                "assets": len(assets),
                "last_collect": None,  # CLI stamps it after build
            }
            (tmp / "meta.json").write_text(json.dumps(meta, indent=2))
            os.replace(tmp, target)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        say(f"hedge DB written: {target}")
        db = HedgeDB.open(target, params=params)
    if bake:
        say("baking the default board (one exact search per counterparty) …")
        db.bake_default_board(intel=bake_intel, workers=bake_workers, progress=say)
    return db


# -------------------------------------------------------------------- handle


class HedgeDB:
    """An opened hedge database: mmap'd leg columns + the stored snapshot's
    league + the search cache. One instance per process; ktc_fast's memo
    tables bind to one snapshot at a time, which this satisfies."""

    def __init__(self, path: Path, params: Params | None = None):
        numpy = _np()
        self.path = Path(path)
        self.meta = json.loads((self.path / "meta.json").read_text())
        if self.meta.get("schema") != _SCHEMA_VERSION:
            raise ValueError(
                f"hedge DB at {path} has schema {self.meta.get('schema')!r}; "
                f"this code reads {_SCHEMA_VERSION} — rebuild"
            )
        self._params_obj = params or Params()
        if params_fingerprint(self._params_obj) != self.meta["params_fingerprint"]:
            raise ValueError(
                f"hedge DB at {path} was built under different Params than the "
                "ones passed to open() — pass the build's Params (the dir name "
                "carries its fingerprint) or rebuild"
            )
        self._cols: dict[str, Any] = {}
        for name in _COLUMNS:
            self._cols[name] = numpy.load(
                self.path / "legs" / f"{name}.npy", mmap_mode="r"
            )
        self.descriptors: list[list[str]] = json.loads(
            (self.path / "packages.json").read_text()
        )
        self.assets: list[dict] = json.loads((self.path / "assets.json").read_text())
        self.opp_names: list[str] = self.meta["opp_names"]
        self._league: md.LeagueState | None = None
        self._by_key: dict[str, tr.Asset] | None = None
        self._pkg_cache: dict[int, tr.Package] = {}
        self._index = None
        self._buckets: dict[tuple[int, int], Any] | None = None
        self._iso_ds_cache: dict[int, float] = {}
        self._hot: dict[str, Any] | None = None
        # §12 persistent legality: tri-state per leg (-1 unknown, 0 illegal,
        # 1 legal), discovered lazily by walks and FLUSHED across sessions —
        # full §3.3 legality costs a package rebuild + a roster simulation per
        # leg, and re-deriving it per process measured minutes on novel
        # full-scale searches. Values are deterministic per snapshot, so a
        # max-merge (known beats unknown, known values agree) is exact.
        lp = self.path / "legality.npy"
        if lp.exists():
            self._legal_col = numpy.load(lp).copy()
        else:
            self._legal_col = numpy.full(int(self.meta["legs"]), -1, numpy.int8)
        self._legal_dirty = False

    def _flush_legality(self) -> None:
        if not self._legal_dirty:
            return
        numpy = _np()
        lp = self.path / "legality.npy"
        merged = self._legal_col
        if lp.exists():
            merged = numpy.maximum(merged, numpy.load(lp))
        fd, tmp = tempfile.mkstemp(dir=str(self.path), suffix=".npy.tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                numpy.save(fh, merged)
            os.replace(tmp, lp)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        self._legal_col = merged
        self._legal_dirty = False

    def _hot_cols(self) -> dict[str, Any]:
        """In-RAM copies of the walk's hot scalar columns (~650 MB at full
        scale) — mmap scalar reads are ~10× slower than array indexing and the
        walk reads them per visit."""
        if self._hot is None:
            numpy = _np()
            self._hot = {
                name: numpy.ascontiguousarray(self._cols[name])
                for name in ("opp", "mask", "dface", "sent", "a", "favor")
            }
        return self._hot

    # ------------------------------------------------------------- plumbing

    @classmethod
    def open(cls, path: Path | str, params: Params | None = None) -> "HedgeDB":
        return cls(Path(path), params=params)

    @classmethod
    def open_for(
        cls,
        snapshot: Snapshot,
        params: Params | None = None,
        cache_dir: Path | str | None = None,
    ) -> "HedgeDB":
        """Open the DB matching this snapshot's CONTENT, or raise with the
        rebuild hint — a fingerprint mismatch must never render silently."""
        params = params or Params()
        target = db_dir(snapshot, params, cache_dir)
        if not (target / "meta.json").exists():
            raise FileNotFoundError(
                f"no hedge DB for this snapshot content at {target} — run "
                "`score_trade.py hedgedb build` (the data changed since the "
                "last build, or none was ever built)"
            )
        return cls(target, params=params)

    @property
    def league(self) -> md.LeagueState:
        if self._league is None:
            stored = load_snapshot(self.path / "snapshot.json.gz")
            self._league = md.build_league(stored, self._params_obj)
            self._index = tr.team_index(self._league.teams[self._league.me])
        return self._league

    @property
    def index(self):
        if self._index is None:
            _ = self.league
        return self._index

    def package(self, pid: int) -> tr.Package:
        """Rebuild package `pid` from its descriptor against the stored
        snapshot's league — same asset order, same float summation order,
        bit-identical figures (§11.12(d))."""
        pkg = self._pkg_cache.get(pid)
        if pkg is None:
            if self._by_key is None:
                league = self.league
                by_key: dict[str, tr.Asset] = {}
                for t in league.teams.values():
                    for a in tr.team_assets(league, t).values():
                        by_key[a.key] = a
                self._by_key = by_key
            pkg = tr.package_of(
                self.league, [self._by_key[k] for k in self.descriptors[pid]]
            )
            self._pkg_cache[pid] = pkg
        return pkg

    def _cols4(self, i: int, which: str) -> tuple:
        off = self._cols[f"{which}_off"]
        vals = self._cols[f"{which}_vals"]
        base = 4 * i
        return tuple(
            tuple(float(x) for x in vals[off[base + j] : off[base + j + 1]])
            for j in range(4)
        )

    def _leg_legal(self, i: int) -> bool:
        v = self._legal_col[i]
        if v < 0:
            league = self.league
            give = self.package(int(self._cols["give_pid"][i]))
            get = self.package(int(self._cols["get_pid"][i]))
            opp = self.opp_names[int(self._cols["opp"][i])]
            ok = tr.legality(
                league, league.teams[league.me], league.teams[opp], give, get
            )["legal"]
            self._legal_col[i] = 1 if ok else 0
            self._legal_dirty = True
            return ok
        return bool(v)

    def _pair_eval(self, bi: int, si: int) -> tuple[float, float, float, float, float]:
        """Mirror of `PairPool.pair_eval` over the columns: ONE combined
        starter re-solve, additive ΔF, floor/ceiling/return."""
        bo, so = self._cols4(bi, "out"), self._cols4(si, "out")
        bin_, sin_ = self._cols4(bi, "in"), self._cols4(si, "in")
        d_s = self.index.delta(
            (bo[0] + so[0], bo[1] + so[1], bo[2] + so[2], bo[3] + so[3]),
            (bin_[0] + sin_[0], bin_[1] + sin_[1], bin_[2] + sin_[2], bin_[3] + sin_[3]),
        )
        dface = self._cols["dface"]
        sent = self._cols["sent"]
        d_f = float(dface[bi]) + float(dface[si])
        floor = d_s if d_s < d_f else d_f
        ceiling = d_f if d_s < d_f else d_s
        return floor / (float(sent[bi]) + float(sent[si])), floor, ceiling, d_s, d_f

    def buckets(self) -> dict[tuple[int, int], Any]:
        """(np, nk) signature -> ascending leg-index array."""
        if self._buckets is None:
            numpy = _np()
            np_arr = numpy.asarray(self._cols["np"])
            nk_arr = numpy.asarray(self._cols["nk"])
            sigs = {}
            order = numpy.lexsort((nk_arr, np_arr))
            cuts = numpy.flatnonzero(
                (numpy.diff(np_arr[order]) != 0) | (numpy.diff(nk_arr[order]) != 0)
            )
            for chunk in numpy.split(order, cuts + 1):
                if len(chunk):
                    sig = (int(np_arr[chunk[0]]), int(nk_arr[chunk[0]]))
                    sigs[sig] = numpy.sort(chunk)
            self._buckets = sigs
        return self._buckets

    # ------------------------------------------------------------ the query

    _QUERY_DEFAULTS: dict[str, Any] = {
        "constraints": (),
        "use_intel": True,
        "use_posture": True,
        "delta": "robust",
        "min_return": 1.0,
        "favor_min": -5.0,
        "favor_max": 5.0,
        "favor_for": None,  # {team: {"min": f|None, "max": f|None}}
        "with_team": None,
        "shape": None,
        "top": None,  # None -> params.hedgedb_store_top
    }

    def _normalize_query(self, query: Mapping | None) -> dict:
        q = dict(self._QUERY_DEFAULTS)
        for k, v in (query or {}).items():
            if k == "intel":
                continue
            if k not in self._QUERY_DEFAULTS:
                raise ValueError(f"unknown hedgedb query key {k!r}")
            q[k] = v
        delta = q["delta"]
        if delta != "robust" and not (
            isinstance(delta, (int, float)) and 0.0 <= delta <= 1.0
        ):
            raise ValueError(f"delta must be 'robust' or a number in [0, 1], got {delta!r}")
        if q["shape"] not in (None, "starter>team", "team>starter"):
            raise ValueError("shape must be 'starter>team', 'team>starter', or None")
        band = float(self.meta["band"])
        for k in ("favor_min", "favor_max"):
            v = q[k]
            if v is not None and abs(v) > band:
                raise ValueError(
                    f"{k}={v} lies outside the DB's build band ±{band:g} — the "
                    f"stored pool cannot represent that leg; rebuild with "
                    f"hedgedb_band >= {abs(v):g} to serve it"
                )
        ff = q["favor_for"]
        if ff is not None:
            for team, win in ff.items():
                if team not in self.opp_names:
                    raise ValueError(f"favor_for names unknown counterparty {team!r}")
                for k in ("min", "max"):
                    v = win.get(k)
                    if v is not None and abs(v) > band:
                        raise ValueError(
                            f"favor_for[{team}].{k}={v} lies outside the DB's "
                            f"build band ±{band:g} — rebuild to serve it"
                        )
        wt = q["with_team"]
        if wt is not None and wt not in self.opp_names:
            raise ValueError(f"with_team={wt!r} is not a counterparty username")
        top = q["top"]
        if top is None:
            q["top"] = int(self.meta.get("store_top", 50))
        elif not (isinstance(top, int) and top > 0):
            raise ValueError(f"top must be a positive int, got {top!r}")
        return q

    def _compile(self, q: dict, intel: Sequence[Mapping] | None):
        res = cn.compile_constraints(
            self.league,
            intel=intel or (),
            query=q["constraints"],
            use_posture=q["use_posture"],
            use_intel=q["use_intel"],
        )
        # tolerate both the historical 2-tuple and a (compiled, ignored, shed)
        if len(res) == 2:
            compiled, ignored = res
            shed: list = list(getattr(compiled, "shed", []) or [])
        else:
            compiled, ignored, shed = res
        return compiled, ignored, shed

    def query_fingerprint(self, q: dict, compiled) -> str:
        payload = {
            "schema": _SCHEMA_VERSION,
            "content": self.meta["content_fingerprint"],
            "params": self.meta["params_fingerprint"],
            "sliders": {
                k: q[k]
                for k in (
                    "delta", "min_return", "favor_min", "favor_max",
                    "favor_for", "with_team", "shape", "top",
                )
            },
            "compiled": [c.to_dict() for c in compiled],
        }
        blob = json.dumps(payload, sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()[:24]

    def _eligible_mask(self, q: dict, compiled):
        """Leg-level eligibility: the exact §5.0.1 favor push-down (pair
        min/max decompose onto legs), per-team favor windows, and the §4
        constraint vocabulary evaluated through `cn.package_allowed` itself —
        per DISTINCT package, never re-implemented — mapped onto legs via
        their package ids."""
        numpy = _np()
        favor = numpy.asarray(self._cols["favor"])
        opp = numpy.asarray(self._cols["opp"])
        elig = numpy.ones(len(favor), bool)
        if q["favor_min"] is not None:
            elig &= favor >= q["favor_min"]
        if q["favor_max"] is not None:
            elig &= favor <= q["favor_max"]
        for team, win in (q["favor_for"] or {}).items():
            oi = self.opp_names.index(team)
            m = opp == oi
            lo, hi = win.get("min"), win.get("max")
            if lo is not None:
                elig &= ~m | (favor >= lo)
            if hi is not None:
                elig &= ~m | (favor <= hi)
        if compiled:
            give_pid = numpy.asarray(self._cols["give_pid"])
            get_pid = numpy.asarray(self._cols["get_pid"])
            n_opp = len(self.opp_names)
            give_pids = numpy.unique(give_pid)
            get_pids = numpy.unique(get_pid)
            give_ok = numpy.ones((n_opp, len(self.descriptors)), bool)
            get_ok = numpy.ones((n_opp, len(self.descriptors)), bool)
            for oi, name in enumerate(self.opp_names):
                for pid in give_pids:
                    give_ok[oi, pid] = cn.package_allowed(
                        compiled, name, "give", self.package(int(pid))
                    )
                for pid in get_pids:
                    get_ok[oi, pid] = cn.package_allowed(
                        compiled, name, "get", self.package(int(pid))
                    )
            elig &= give_ok[opp, give_pid] & get_ok[opp, get_pid]
        return elig

    def search(
        self,
        query: Mapping | None = None,
        intel: Sequence[Mapping] | None = None,
        use_cache: bool = True,
    ) -> dict:
        """§12 exact search. Returns the finder's result shape (spreads with
        full leg cards, counts, exact, applied_constraints, ignored_intel)
        plus `db` provenance and `shed_constraints`."""
        q = self._normalize_query(query)
        compiled, ignored, shed = self._compile(q, intel)
        qfp = self.query_fingerprint(q, compiled)
        cache_file = self.path / "searches" / f"{qfp}.json"
        if use_cache and cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text())
                return self._payload(cached, q, compiled, ignored, shed, cached=True)
            except (json.JSONDecodeError, OSError, KeyError):
                pass  # unreadable cache entry: re-search
        raw = self._search_uncached(q, compiled)
        raw["qfp"] = qfp
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(cache_file.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(raw, fh, separators=(",", ":"))
            os.replace(tmp, cache_file)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        return self._payload(raw, q, compiled, ignored, shed, cached=False)

    # ----------------------------------------------------------- the walk

    def _search_uncached(self, q: dict, compiled) -> dict:
        """The §4a v6 seeded sound walk over the columns — a faithful mirror
        of `finder.find_spreads`'s crossing (same key, same XTOL, same
        `pair_ds_bound` skip, same heap and tie-breaks), with legs eligible
        under the compiled constraints + favor windows."""
        numpy = _np()
        params = self.league.params
        delta = q["delta"]
        min_ret = float(q["min_return"]) / 100.0
        favor_min, favor_max = q["favor_min"], q["favor_max"]
        shape = q["shape"]
        top = q["top"]
        budget = params.hedgedb_search_budget
        elig = self._eligible_mask(q, compiled)

        hot = self._hot_cols()
        opp_arr = hot["opp"]
        mask_arr = hot["mask"]
        dface_arr = hot["dface"]
        sent_arr = hot["sent"]
        a_arr = hot["a"]
        favor_arr = hot["favor"]

        with_oi = (
            self.opp_names.index(q["with_team"]) if q["with_team"] is not None else None
        )

        buckets = self.buckets()
        n_buy = n_sell = 0
        for sig, idx in buckets.items():
            n_el = int(elig[idx].sum())
            if tr.canonical_sig(sig):
                n_buy += n_el
            if tr.canonical_sig((-sig[0], -sig[1])):
                n_sell += n_el

        def _favor_pair(bi: int, si: int) -> tuple[float, float, float]:
            fb, fs = float(favor_arr[bi]), float(favor_arr[si])
            return fb, fs, fb if fb < fs else fs

        def _qualifying(bi: int, si: int):
            if int(opp_arr[si]) == int(opp_arr[bi]) or (
                int(mask_arr[si]) & int(mask_arr[bi])
            ):
                return None
            if with_oi is not None and with_oi not in (int(opp_arr[bi]), int(opp_arr[si])):
                return None
            if self._leg_legal(bi) is False or self._leg_legal(si) is False:
                return None
            ret_, floor_, ceil_, ds_, df_ = self._pair_eval(bi, si)
            fb_, fs_, fmin_ = _favor_pair(bi, si)
            if favor_min is not None and fmin_ < favor_min:
                return None
            if favor_max is not None and (fb_ if fb_ > fs_ else fs_) > favor_max:
                return None
            if shape == "starter>team" and not ds_ > df_:
                return None
            if shape == "team>starter" and not df_ > ds_:
                return None
            if not tr.verdict_of(ds_, df_):
                return None
            return ret_ if ret_ >= min_ret - 1e-12 else None

        # §4a v6 warm bar (see finder.py) — EXACT: the bar is a return some
        # qualifying pair actually achieves, so the walk still reaches every
        # member of the true top-K; counts.matched becomes a floor when the
        # bar rises above min_return, and `bar_raised` discloses it.
        def _cand(idx_arr):
            """Eligible candidates of a bucket, ascending index — the same
            multiset and order the finder's `if eligible(i)` comprehension
            walks."""
            return idx_arr[elig[idx_arr]]

        seed_bar = min_ret
        sound_break = delta == "robust"
        if sound_break and top:
            seeds: list[float] = []
            for sig in sorted(buckets):
                if not tr.canonical_sig(sig):
                    continue
                comp = buckets.get((-sig[0], -sig[1]))
                if comp is None or not len(comp):
                    continue
                cb, cs = _cand(buckets[sig]), _cand(comp)
                if not len(cb) or not len(cs):
                    continue
                # sorted(key=rank) with stable ties == stable argsort over the
                # ascending-index candidate array
                rb = -(dface_arr[cb] / sent_arr[cb])
                rs = -(dface_arr[cs] / sent_arr[cs])
                bs_seed = cb[numpy.argsort(rb, kind="stable")[:_SEED_WIDTH]].tolist()
                ss_seed = cs[numpy.argsort(rs, kind="stable")[:_SEED_WIDTH]].tolist()
                for bi in bs_seed:
                    for si in ss_seed:
                        r_ = _qualifying(bi, si)
                        if r_ is not None:
                            seeds.append(r_)
            if len(seeds) >= top:
                seeds.sort(reverse=True)
                seed_bar = max(min_ret, seeds[top - 1])

        def _sorted_side(cand):
            """(u_list, i_list, opp_list, mask_list, a_list, sent_list,
            favor_list) in walk order. `lexsort((i, u))` is exactly
            `sorted((u, i))`: ascending u, ties by ascending index; u itself
            is the same 5·bar·Σsent − (3·ΔF + 2·A) arithmetic elementwise."""
            if sound_break:
                u = 5.0 * seed_bar * sent_arr[cand] - (
                    3.0 * dface_arr[cand] + 2.0 * a_arr[cand]
                )
                order = numpy.lexsort((cand, u))
            else:
                # numeric-δ order needs a per-leg starter solve (not
                # vectorizable); sort in Python exactly like the finder
                pairs = sorted((order_key(int(i)), int(i)) for i in cand)
                i_list = [i for _, i in pairs]
                u_list = [u_ for u_, _ in pairs]
                ci = numpy.asarray(i_list, dtype=numpy.int64)
                return (
                    u_list, i_list,
                    opp_arr[ci].tolist(), mask_arr[ci].tolist(),
                    a_arr[ci].tolist(), sent_arr[ci].tolist(),
                    favor_arr[ci].tolist(),
                )
            ci = cand[order]
            return (
                u[order].tolist(), ci.tolist(),
                opp_arr[ci].tolist(), mask_arr[ci].tolist(),
                a_arr[ci].tolist(), sent_arr[ci].tolist(),
                favor_arr[ci].tolist(),
            )

        if not sound_break:
            def order_key(i: int) -> float:
                w = self._iso_ds_cache.get(i)
                if w is None:
                    w = self._iso_ds_cache[i] = self.index.delta(
                        self._cols4(i, "out"), self._cols4(i, "in")
                    )
                return -(w + delta * (float(dface_arr[i]) - w))

        from heapq import heappush, heappushpop

        heap: list[tuple] = []
        visits = valid = matched = 0
        complete = True
        for sig in sorted(buckets):
            if not complete:
                break
            if not tr.canonical_sig(sig):
                continue
            comp = buckets.get((-sig[0], -sig[1]))
            if comp is None or not len(comp):
                continue
            cb, cs = _cand(buckets[sig]), _cand(comp)
            if not len(cb) or not len(cs):
                continue
            bs_u, bs_i, bs_opp, bs_mask, bs_a, bs_sent, _ = _sorted_side(cb)
            ss = _sorted_side(cs)
            if with_oi is None:
                ss_out = ss
            else:
                keep = [k for k, o in enumerate(ss[2]) if o == with_oi]
                ss_out = tuple([col[k] for k in keep] for col in ss)
            for nb in range(len(bs_i)):
                if not complete:
                    break
                ub, bi = bs_u[nb], bs_i[nb]
                b_opp, b_mask = bs_opp[nb], bs_mask[nb]
                my_ss = ss if (with_oi is None or b_opp == with_oi) else ss_out
                my_u, my_i, my_opp, my_mask, my_a, my_sent, my_favor = my_ss
                if not my_i:
                    continue
                if sound_break and ub + my_u[0] > tr.XTOL:
                    break
                b_a = bs_a[nb]
                b_sent = bs_sent[nb]
                vb = None
                for ns in range(len(my_i)):
                    us = my_u[ns]
                    if sound_break and ub + us > tr.XTOL:
                        break
                    visits += 1
                    if visits > budget:
                        visits -= 1
                        complete = False
                        break
                    if my_opp[ns] == b_opp or (my_mask[ns] & b_mask):
                        continue
                    if vb is None:
                        vb = self._leg_legal(bi)
                    if vb is False:
                        break
                    si = my_i[ns]
                    if self._leg_legal(si) is False:
                        continue
                    valid += 1
                    if sound_break and tr.pair_ds_bound(b_a, my_a[ns]) < seed_bar * (
                        b_sent + my_sent[ns]
                    ) - tr.XTOL:
                        continue
                    ret, floor, ceil, d_s, d_f = self._pair_eval(bi, si)
                    fb, fs, fmin = _favor_pair(bi, si)
                    if favor_min is not None and fmin < favor_min:
                        continue
                    if favor_max is not None and (fb if fb > fs else fs) > favor_max:
                        continue
                    if shape == "starter>team" and not d_s > d_f:
                        continue
                    if shape == "team>starter" and not d_f > d_s:
                        continue
                    if delta == "robust" and not tr.verdict_of(d_s, d_f):
                        continue
                    sent = b_sent + my_sent[ns]
                    rv = _view_return(d_s, d_f, sent, delta)
                    if rv < min_ret - 1e-12:
                        continue
                    matched += 1
                    e = (rv, ceil, -bi, -si, d_s, d_f, ret, sent)
                    if len(heap) < top:
                        heappush(heap, e)
                    elif e > heap[0]:
                        heappushpop(heap, e)

        self._flush_legality()
        kept = sorted(
            heap,
            key=lambda e: (-round(100.0 * e[0], 2), -round(e[1], 1), -e[2], -e[3]),
        )
        return {
            "pairs": [
                {
                    "buy": -e[2], "sell": -e[3],
                    "dS": e[4], "dF": e[5], "ret": e[6], "rv": e[0],
                    "ceiling": e[1], "sent": e[7],
                }
                for e in kept
            ],
            "counts": {
                "legs": {"buy": n_buy, "sell": n_sell},
                "crossings": visits,
                "valid": valid,
                "matched": matched,
                "returned": len(kept),
            },
            "exact": complete,
            "bar_raised": seed_bar > min_ret,
        }

    # ------------------------------------------------------------ payloads

    def _payload(self, raw: dict, q, compiled, ignored, shed, cached: bool) -> dict:
        """Finder-shaped result from a raw (possibly cached) search: leg cards
        via `tr.build_card` against the stored snapshot's league, gate verdict
        PASS (pool legs passed at build), favor/sequencing/preferred exactly
        as the finder emits them."""
        league = self.league
        spreads = []
        card_cache: dict[int, dict] = {}

        def leg_card(i: int, leg_id: str) -> dict:
            base = card_cache.get(i)
            if base is None:
                give = self.package(int(self._cols["give_pid"][i]))
                get = self.package(int(self._cols["get_pid"][i]))
                base = tr.build_card(
                    league, self.opp_names[int(self._cols["opp"][i])], give, get
                )
                base["gate"]["verdict"] = "PASS"
                card_cache[i] = base
            card = dict(base)
            card["id"] = leg_id
            return card

        for n, p in enumerate(raw["pairs"], 1):
            bi, si = int(p["buy"]), int(p["sell"])
            b = leg_card(bi, f"F{n}-buy")
            s = leg_card(si, f"F{n}-sell")
            fb, fs = float(self._cols["favor"][bi]), float(self._cols["favor"][si])
            fmin = fb if fb < fs else fs
            d_s, d_f = p["dS"], p["dF"]
            floor = d_s if d_s < d_f else d_f
            at_cap = b["sequencing"].startswith("at the roster cap")
            preferred = cn.leg_preferred(
                compiled, b["counterparty"],
                self.package(int(self._cols["give_pid"][bi])),
                self.package(int(self._cols["get_pid"][bi])),
            ) or cn.leg_preferred(
                compiled, s["counterparty"],
                self.package(int(self._cols["give_pid"][si])),
                self.package(int(self._cols["get_pid"][si])),
            )
            spreads.append(
                {
                    "id": f"F{n}",
                    "buy": b,
                    "sell": s,
                    "coords": {"dS": round(d_s, 1), "dF": round(d_f, 1)},
                    "verdict": tr.verdict_of(d_s, d_f),
                    "floor": round(floor, 1),
                    "ceiling": round(p["ceiling"], 1),
                    "sent": round(p["sent"], 1),
                    "return_robust": round(100.0 * p["ret"], 2),
                    "return_view": round(100.0 * p["rv"], 2),
                    "favor": {
                        "buy": round(fb, 2),
                        "sell": round(fs, 2),
                        "min": round(fmin, 2),
                    },
                    "preferred": preferred,
                    "sequencing": (
                        "at the roster cap: agreement-first — verbal yes on the buy, "
                        "execute the sell, then the buy (Sleeper processes trades instantly)"
                        if at_cap
                        else "roster space available: the buy may execute first — "
                        "agreement-first still applies"
                    ),
                    "net_players": 0,
                    "net_picks": 0,
                    "net_roster": b["net_roster"]["me"] + s["net_roster"]["me"],
                }
            )
        return {
            "spreads": spreads,
            "counts": raw["counts"],
            "exact": raw["exact"],
            "bar_raised": raw.get("bar_raised", False),
            "applied_constraints": [c.to_dict() for c in compiled],
            "ignored_intel": ignored,
            "shed_constraints": shed,
            "db": {
                "path": str(self.path),
                "content_fingerprint": self.meta["content_fingerprint"],
                "band": self.meta["band"],
                "legs": self.meta["legs"],
                "cached": cached,
                "qfp": raw.get("qfp"),
            },
        }

    # --------------------------------------------------------------- bake

    def bake_default_board(
        self, intel=None, workers: int = 0, progress=None
    ) -> None:
        """The default board's 11 searches, run through the ordinary cached
        `search` path so a later `board` with the same filters is a pure cache
        read. Parallel via fork when `workers > 1` — each search writes its
        own cache file atomically, and every search is deterministic, so
        worker scheduling cannot affect content."""
        say = progress or (lambda msg: None)
        teams = sorted(self.opp_names)
        if workers and workers > 1:
            import multiprocessing as mp

            _ = self.league  # materialize BEFORE forking (copy-on-write share)
            global _BAKE_STATE
            _BAKE_STATE = (self, intel)
            with mp.get_context("fork").Pool(min(workers, len(teams))) as pool:
                for name in pool.imap_unordered(_bake_one, teams):
                    say(f"  baked {name}")
            # workers flushed their legality discoveries read-merge-write;
            # pick the merged column up for this process
            numpy = _np()
            lp = self.path / "legality.npy"
            if lp.exists():
                self._legal_col = numpy.maximum(self._legal_col, numpy.load(lp))
        else:
            for name in teams:
                self.search({"with_team": name}, intel=intel)
                say(f"  baked {name}")

    # --------------------------------------------------------------- offer

    def offer(
        self,
        opp_name: str,
        give_names: Sequence[str],
        get_names: Sequence[str],
        query: Mapping | None = None,
        intel: Sequence[Mapping] | None = None,
    ) -> dict:
        """Score an arbitrary proposal (real gate — PASS or FAIL with reasons)
        and cross it against the stored legs of every OTHER counterparty for
        its exact hedge set. The ≤2-assets-out heuristic of the old
        `score --hedge` is gone: the store holds every 1..3-asset package, and
        e.g. a (+1 player, +1 pick) offer NEEDS 3-asset gives by arithmetic."""
        league = self.league
        card = tr.propose_by_names(league, opp_name, give_names, get_names)
        give, get = tr.card_packages(league, card)
        np_off = get.n_players - give.n_players
        nk_off = get.n_picks - give.n_picks
        result: dict = {"offer": card, "hedges": [], "counts": None, "exact": True}
        if np_off == 0 and nk_off == 0:
            result["note"] = (
                "already count-neutral (0 players / 0 picks net) — nothing to "
                "offset; the proposal stands alone"
            )
            return result

        q = self._normalize_query(query)
        compiled, ignored, shed = self._compile(q, intel)
        elig = self._eligible_mask(q, compiled)
        numpy = _np()
        min_ret = float(q["min_return"]) / 100.0
        favor_min, favor_max = q["favor_min"], q["favor_max"]
        top = q["top"]

        comp_sig = (-np_off, -nk_off)
        bucket = self.buckets().get(comp_sig)
        if bucket is None or not len(bucket):
            result["note"] = (
                f"no stored leg has the complementary count signature "
                f"{comp_sig} — no hedge exists inside the DB's edges"
            )
            return result

        opp_arr = self._cols["opp"]
        mask_arr = self._cols["mask"]
        dface_arr = self._cols["dface"]
        sent_arr = self._cols["sent"]
        a_arr = self._cols["a"]
        favor_arr = self._cols["favor"]

        # my-asset disjointness vs the offer runs on KEY SETS, not the stored
        # bitmask: the offer may ship assets outside the give-list alphabet
        # (cornerstones, taxi), which have no bit — and provably never appear
        # in any stored leg, so the key-set test is exact where the mask
        # cannot represent the offer
        offer_my_keys = {a["key"] for a in card["give"]}
        try:
            offer_oi = self.opp_names.index(opp_name)
        except ValueError:
            offer_oi = -1

        out4_off, in4_off = give.cols, get.cols
        dface_off = get.v_me_sum - give.v_me_sum
        sent_off = give.v_sum
        a_off = self.index.delta(_EMPTY4, get.cols)
        favor_off = card["gate"]["favor"]
        offer_canon = tr.canonical_sig((np_off, nk_off))

        cand = [int(i) for i in bucket if elig[i] and int(opp_arr[i]) != offer_oi]
        bar = min_ret
        sound = q["delta"] == "robust"

        def _u_leg(i: int) -> float:
            return 5.0 * bar * float(sent_arr[i]) - (
                3.0 * float(dface_arr[i]) + 2.0 * float(a_arr[i])
            )

        u_off = 5.0 * bar * sent_off - (3.0 * dface_off + 2.0 * a_off)
        ordered = sorted((_u_leg(i), i) for i in cand)

        from heapq import heappush, heappushpop

        heap: list[tuple] = []
        visits = valid = matched = 0
        complete = True
        budget = league.params.hedgedb_search_budget
        give_keys_cache: dict[int, set] = {}
        for us, si in ordered:
            # sound only for the robust objective (§11.13): u bounds the pair
            # floor from above at bar = min_return, so past this point no pair
            # can qualify at all — a numeric δ view keeps the flat walk
            if sound and u_off + us > tr.XTOL:
                break
            visits += 1
            if visits > budget:
                complete = False
                break
            gk = give_keys_cache.get(si)
            if gk is None:
                gk = set(self.descriptors[int(self._cols["give_pid"][si])])
                give_keys_cache[si] = gk
            if gk & offer_my_keys:
                continue
            if self._leg_legal(si) is False:
                continue
            valid += 1
            so, sin_ = self._cols4(si, "out"), self._cols4(si, "in")
            d_s = self.index.delta(
                (
                    out4_off[0] + so[0], out4_off[1] + so[1],
                    out4_off[2] + so[2], out4_off[3] + so[3],
                ),
                (
                    in4_off[0] + sin_[0], in4_off[1] + sin_[1],
                    in4_off[2] + sin_[2], in4_off[3] + sin_[3],
                ),
            )
            d_f = dface_off + float(dface_arr[si])
            floor = d_s if d_s < d_f else d_f
            ceil = d_f if d_s < d_f else d_s
            sent = sent_off + float(sent_arr[si])
            ret = floor / sent if sent else 0.0
            fl = float(favor_arr[si])
            fmin = favor_off if favor_off < fl else fl
            fmax = favor_off if favor_off > fl else fl
            if favor_min is not None and fmin < favor_min:
                continue
            if favor_max is not None and fmax > favor_max:
                continue
            if not tr.verdict_of(d_s, d_f):
                continue
            rv = _view_return(d_s, d_f, sent, q["delta"])
            if rv < min_ret - 1e-12:
                continue
            matched += 1
            e = (rv, ceil, -si, d_s, d_f, ret, sent, fl)
            if len(heap) < top:
                heappush(heap, e)
            elif e > heap[0]:
                heappushpop(heap, e)

        self._flush_legality()
        kept = sorted(heap, key=lambda e: (-round(100.0 * e[0], 2), -round(e[1], 1), -e[2]))
        hedges = []
        for n, e in enumerate(kept, 1):
            rv, ceil, nsi, d_s, d_f, ret, sent, fl = e
            si = -nsi
            give_h = self.package(int(self._cols["give_pid"][si]))
            get_h = self.package(int(self._cols["get_pid"][si]))
            hcard = tr.build_card(
                league, self.opp_names[int(self._cols["opp"][si])], give_h, get_h
            )
            hcard["gate"]["verdict"] = "PASS"
            hcard["id"] = f"H{n}"
            floor = d_s if d_s < d_f else d_f
            hedges.append(
                {
                    "id": f"H{n}",
                    "hedge": hcard,
                    "offer_side": "buy" if offer_canon else "sell",
                    "coords": {"dS": round(d_s, 1), "dF": round(d_f, 1)},
                    "verdict": tr.verdict_of(d_s, d_f),
                    "floor": round(floor, 1),
                    "ceiling": round(ceil, 1),
                    "sent": round(sent, 1),
                    "return_robust": round(100.0 * ret, 2),
                    "return_view": round(100.0 * rv, 2),
                    "favor": {
                        "offer": round(favor_off, 2),
                        "hedge": round(fl, 2),
                        "min": round(min(favor_off, fl), 2),
                    },
                }
            )
        result["hedges"] = hedges
        result["counts"] = {
            "candidates": len(cand),
            "crossings": visits,
            "valid": valid,
            "matched": matched,
            "returned": len(hedges),
        }
        result["exact"] = complete
        result["applied_constraints"] = [c.to_dict() for c in compiled]
        result["ignored_intel"] = ignored
        result["shed_constraints"] = shed
        return result


_BAKE_STATE: tuple | None = None


def _bake_one(team: str) -> str:
    db, intel = _BAKE_STATE
    db.search({"with_team": team}, intel=intel)
    return team
