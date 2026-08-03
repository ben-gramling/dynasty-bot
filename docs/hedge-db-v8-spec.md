# v8 — The Hedge Database (spec, post-review)

Revised after a 3-lens adversarial review (22 findings, 4 blockers) and live
measurement of the complete pool. The measurement that reshaped the design:

- Complete |favor| ≤ 5 pool on the live snapshot: **13,490,657 legs**,
  4.43 GB as Python objects, 121.7 s to build.
- Total crossing space **8.54e12**; the ≥1%-floor region alone is
  **~2.5e12 crossings** with a measured **53.5% qualifying rate** in its top
  reaches → the "all pairs ≥ 1%" universe is **10⁹–10¹² pairs (terabytes)**.
- Measured walk rate 92,811 visits/s ⇒ full enumeration ≈ **months**, not
  minutes. Literal pair materialization is dead — no dial rescues it.

## 0. Architecture: complete LEGS, exact SEARCHES, cached VIEWS

Every possible hedge is a pair of fair-band gate-clean legs. The legs are
enumerable and small (13.5M); the pairs are not (10⁹–10¹²). So:

- **Tier 1 — the legs store (the database).** The COMPLETE fair-band leg
  inventory, persisted columnar once per snapshot. Nothing sampled away —
  variants_per_signature and every scan cap are OFF (drain mode). This is the
  "massive database": the atoms of every possible hedge, with every field
  filters need.
- **Tier 2 — exact searches over it.** Any filter set is answered by the
  §4a v6 seeded sound walk (integer k5 key, XTOL, pair_ds_bound skip,
  pair_eval exact joint coords) over the warm legs store, with user filters
  pushed down to leg masks BEFORE crossing. The result list is **provably the
  exact top-K under the active filters** (sound-break guarantee). Every
  search result is **cached by (DB fingerprint, canonical filter
  fingerprint)** — repeating or revisiting a filter state is instant and
  byte-identical. Count tallies above the walked bar are exact; deeper
  tallies are verified floors (v5.1 honesty language survives unchanged).
- **The board is a view.** Rendered from cached search payloads + the
  PERSISTED snapshot (below) — regeneration never re-searches unless the
  filter state is genuinely new.

store_floor stops being a DB edge: any floor is servable per query; cost
scales with the region and a per-search visit budget guards it (saturation
disclosed, never expected for filtered queries).

## 1. The universe and its disclosed edges

A servable hedge pair = two legs, each: gate-clean (§3 band + ratio ≤ 1.35 +
legal), |favor| ≤ 5 (build band β — KTC's own FAIR window), packages ≤ 3
assets, top-2 cornerstones never shipped, taxi/unvalued not in give-lists,
Σv inside the fleece bracket; pair: count-neutral (0 players AND 0 picks),
distinct counterparties, my-asset-disjoint, verdict-good (ΔS ≥ 0 AND ΔF ≥ 0,
one strict) at the query's floor. (0,0)-signature legs never pair (§5
scope decision, unchanged; they are simply out of the hedge board's scope —
`find`/`pairs` still exist for standalone questions). The DB cannot answer
favor floors below −β: same raise-with-rebuild-hint guard as the finder.
Preference trades stay `find`/`score` territory.

## 2. Storage (`.cache/hedgedb/<content-fp16>-<params-fp16>/`)

- `snapshot.json.gz` — **the full Snapshot payload the DB was priced from.**
  Board and offer mode build their LeagueState from THIS, never from live
  Mongo — cards, KTC links, rdp_ids, market_map and stored coords can never
  disagree (the "page cannot disagree" contract), and card_packages can never
  KeyError on a roster that changed after the build. Side benefit: board
  regens skip the ~1.1 s Atlas round-trip (Mongo is touched only for the
  staleness banner and intel).
- `meta.json` — fingerprints, params, band, build stats, per-search
  completion certificates for the baked default board.
- `legs/` — one raw `.npy` PER COLUMN (np.load mmap_mode works on .npy, NOT
  on .npz — verified) + `manifest.json`: sig(np,nk) i8×2, opp i8, favor f64
  (1dp-quantized values verbatim), dface f64, sent f64, a f64, iso_floor f64,
  mask u64 (give-list ≈ 35 assets, fits), ragged give/get asset-index arrays
  + offsets, ragged out4/in4 value columns + offsets. ~2 GB on disk, columns
  load lazily.
- `assets.json` — index → {key, kind, pos, name, v, pick fields}, in-package
  asset ORDER preserved everywhere (float summation order is pinned).
- `searches/<query-fp>.json` — cached search payloads: pair (buy,sell) leg
  indices, exact coords from pair_eval at search time, counts + completion
  flags, applied/shed constraints. The default board's 11 searches are baked
  at build time as the first cache entries.

**Fingerprint**: content-normalized (strip `_id`/`fetched_at`, sort
transactions by transaction_id) + ktc_calculator INCLUDED. Rationale: the DB
persists priced VALUES, so every pricing input must key it (not a finder-cache
bug fix — the finder cache stores only descriptors and was never stale). A
collect that changed nothing reuses the DB; cold start's collect is
conditional (skip if last collect < 6 h and rosters unchanged — else collect,
then rebuild only if the content fingerprint moved).

## 3. Build (`score_trade.py hedgedb build`)

1. `build_pair_pool(league, enforce_posture=False, favor_band=5.0)` — 4.5 GB
   (grows with the KTC table), ~2 min today. Posture never baked in.
2. Serialize legs columnar + snapshot + assets (+~2 GB transient coexistence).
3. Bake the default board: one seeded sound walk per counterparty
   (`with_team` partition, no constraints, min_return 1 %, stored top-K = 50
   per team, shown top-5). Seed bar fixed at the walk floor − 5e-5 sliver,
   1e-12 slack — ONE qualifying predicate shared verbatim by every sink and
   recount. Parallel by (signature, contiguous buy-chunk) — signature (1,−1)
   is 86 % of the space, so chunking WITHIN it is what parallelizes; chunk
   outputs concatenate in buy-order before the final display-precision sort
   (deterministic under any worker scheduling). Fork memory: parent 4.5 GB +
   ~1.8 GB COW dirtying for the dominant chunk's child — fits 47 GB with 4–6
   workers.
4. Atomic dir rename. Guard budget per search with per-search saturation
   flags recorded in the certificate (expected complete; disclosed if not).

Cold build target: **~5–15 min end-to-end** (pool 2 + serialize 2 + bake
3–10 parallel). "Long is fine" per the product contract; same-day reopen with
unchanged content = **0 s** (fingerprint hit).

## 4. Query layer (`hedgedb board`)

Filter compile → leg masks (numpy) → serve:

1. **Cache hit** (same DB + same canonical filter state) → instant,
   byte-identical.
2. **Provable post-filter**: a narrowing filter change is served from a
   cached search's stored top-50/team ONLY when provably exact, decided by
   the survivor test (≥ K stored entries survive the new filter). Honest hit
   rates by dial: raising min-return is ALWAYS exact from storage (return is
   the sort key — survivors are a prefix, to any depth); team drops/focus
   always (per-team lists independent); asset/position requires and excludes
   usually (survivorship uncorrelated with ranking — the test decides);
   favor TIGHTENING usually FAILS the test by geometry (my return is the
   negation of their favor, so the stored top-50 hugs the old floor —
   tightening decapitates the list) and falls through to a fresh walk, as do
   δ-view changes and shape filters. The fallback is automatic and sound —
   the board is never wrong, only slower on those moves. (Per-favor-slice
   baking could mitigate; deliberately rejected as precision machinery —
   keep the storage dumb, the fallback honest.)
3. **Fresh walk** otherwise: filters pushed to leg level, seeded sound walk,
   pair_eval on survivors, Packages materialized only for legality/cards of
   candidates. Latency scales with the filtered region: single-team or
   asset-pinned queries seconds; a full unfiltered board re-walk is the baked
   case and never recurs. Honest budget: **≤ ~60 s worst case for a novel
   full-board filter state** (Python walk; vectorized crossing is a staged
   optimization, not a correctness dependency). End-to-end CLI wall time
   including ~0.6 s startup from the stored snapshot.

Vocabulary (§4 semantics unchanged, precedence posture < intel < query,
unparseable intel reported never guessed) plus:

- **any-of**: `--require "millj receives Mike Evans|Travis Hunter|Javonte
  Williams"` (≥1 contained). Intel subjects accept `A|B|C`.
- **Send-side intel** (the query grammar already has `sends`; intel gains it):
  new kinds **KEEPS** ("not willing to trade away X") → hard EXCLUDE on
  team-sends, and **SHOPPING** ("willing/looking to move X") → soft PREFER on
  team-sends. Both persist to `market-intel` and auto-compile like WANT/
  DONT_WANT. SKILL.md classification protocol gains both.
- **Scoped pick classes**: OBJECT accepts `picks` scoped by a year and/or a
  round token in any order — `2027 picks`, `R1 picks`, `2027 R1 picks` —
  usable on either side and in any-of sets ("Colin does not want to give up
  any 2027 picks" → exclude `cmgaither43 sends 2027 picks`). Evaluation is
  containment over the assets sidecar's pick year/round fields. This also
  makes "ronak doesn't want any 2026 picks"-style intel machine-parseable
  (receives side, same mechanism).
- **Precedence refined to (team, side)**: a query constraint about what a
  team RECEIVES no longer sheds that team's SEND-side intel (and vice
  versa) — "what if Colin receives a TE" cannot silently discard "Colin
  keeps his 2027 picks". The shed list stays visible on the board.
- **Asset-name resolution matches `resolve()`**: unique case-insensitive
  substring ("Kenneth Walker" → Kenneth Walker III), ambiguity → error
  listing candidates, never guessed.
- **Multiple WANT intel for one team compile as any-of** (OR), not a
  conjunctive stack — "Colin wants a RB" then "Colin wants a TE" means
  either satisfies him; explicit conjunctions only via ad-hoc `--require`
  repeats in one invocation.
- **Alphabet validation**: a require naming an asset no DB leg can carry
  (protected cornerstone, taxi, another team's player) ERRORS with the
  reason — never renders a silently-empty card wearing exact-proof language.
- **Per-team favor window**: `--favor-for cmgaither43=-3:5`, in the engine's
  counterparty-positive units (min −3 ⇒ at most 3 points against Colin on his
  own calculator), applied to every stored leg whose counterparty is that
  team wherever the pair appears. SKILL.md carries the utterance→sign map.
- Sliders `--delta/--min-return/--top`, `--focus TEAM` (that card first).

**Session state**: the skill re-passes the COMPLETE current filter set on
every invocation (board and offer identically — offer takes the full filter
flag set); persistent wants live in Mongo intel as today. The board renders a
"constraints in effect" block with provenance (posture/intel/query) and
anything shed by precedence — silent replacement is visible.

**Freshness, two-axis**: the page shows the snapshot age the DB was priced
from (red > 6 h) AND a red "Mongo has a newer collect — rebuild before you
quote" banner when live data moved past the DB. Never auto-rebuilds.

**One canonical out path** shared by board and offer (offer regenerates THE
board file) so the published artifact URL stays stable all session.

## 5. Offer mode (`hedgedb offer --opponent X --give "..." --get "..."`)

1. `tr.propose` exactly as given: REAL gate PASS/FAIL with reasons, our
   verdict/interval, their coords, favor tag. Independent of the DB and its
   caps (cornerstones, >3 assets, gate-FAIL all scoreable — §10 pins).
2. **Count-neutral offers don't cross**: disclosed "already count-neutral —
   nothing to offset" on the card (today's CLI semantics, now pinned).
3. Else hedge pipeline: vectorized prefilter (complement signature, other
   counterparties, asset-disjoint — mask when representable, explicit key-set
   check when the offer uses assets outside the give-list alphabet, active
   filter masks) → rank by stored k5/dF bound → **cap candidates (top ~10k)**
   → materialize Packages, legality (live, memoized), pair_eval exact combined
   coords → verdict-good hedges ranked maximin. The ≤2-assets-out heuristic
   from `score --hedge` is DROPPED (a (+1,+1) offer like Jukinski's needs
   3-asset gives by arithmetic). Latency budget ≤ ~30 s.
   **The favor window binds the HEDGE legs only (v8.0.1)**: favor is a
   politeness filter on legs WE propose — an offer the counterparty already
   made is never filtered by its own favor, however lopsided toward us; it
   is disclosed on every hedge (favor.offer / favor.min) instead. Pre-fix,
   a generous offer's favor poisoned the pair minimum and silently emptied
   the hedge list.
4. Gate-FAIL offers: hedges still computed, labeled ("if you took it anyway"),
   with `--alternatives` counters alongside. [OPEN DIAL 3]
5. Board regenerated: counterparty focused first, offer card pinned with the
   gate verdict loud.

## 6. Change map

- NEW `libs/core/core/scoring/hedgedb.py` — build/serialize/load/search/
  cache/offer. The columnar walk lives here against the pinned primitives
  (canonical_sig, k5, XTOL, pair_ds_bound, pair_eval); `finder.py`/
  `trades.py` default paths untouched — every existing test stands as-is.
- `constraints.py` — any-of, favor_for, substring resolution, `A|B|C`
  subjects, multi-WANT→any-of compile.
- `dashboard.py` — payload-from-search-cache builder (render_html gets only:
  constraints-in-effect block, two-axis freshness, focus/pin). Board renders
  from the STORED snapshot's league.
- `score_trade.py` — `hedgedb build|board|offer|status`.
- `params.py` — hedgedb_band=5.0, stored top-K, search visit budget.
- Packaging: numpy via optional extra **`core[hedgedb]`** (NOT a base dep —
  the Lambda layer installs core's full closure and must not grow numpy);
  hedgedb raises "install core[hedgedb]" on ImportError. Collector untouched.
- SKILL.md rewrite; docs/scoring-system.md §12.
- Tests: `test_hedgedb.py` on committed fixtures at REDUCED params
  (max_package=2 / high floor) — brute-force parity of the columnar walk vs
  find_spreads on identical scopes, roundtrip byte-identity, cache-hit
  identity, post-filter-monotonicity pins, offer-pipeline parity, alphabet
  validation, any-of/favor_for compile pins. Full-scale build exercised
  manually, never in the suite.

## 7. Decided

- Legs complete / searches exact / views cached — the only shape the
  measured numbers permit.
- Board default: min_return 1 %, favor −5..+5, top-5 shown, 50 stored/team.
- Rebuild only when the content fingerprint moves; snapshot persisted inside
  the DB; renders never touch live Mongo for pricing.
- numpy optional-extra, local only. Lambda/collector untouched.
- v5.1 honesty survives verbatim: exact where a walk completed, "≥ N"
  where budget-truncated; certificates recorded per search.

## 8. Dials (DECIDED with the user, 2026-08-03)

1. **Novel-filter latency**: Option A — Python walks first (~≤60 s worst
   case, once per novel state, cached forever); vectorized crossing is a
   later drop-in optimization behind the same cache if real sessions hit the
   slow path often. Known consequence (user-acknowledged): league-wide favor
   tightening with no team/asset named is the shape that pays the minute.
2. **Build band**: β = 5. Favor floors below −5 need a rebuild at a wider
   band; the guard raises with that hint.
3. **Gate-FAIL offers**: hedges computed and shown, labeled "if you took it
   anyway", with --alternatives counters alongside.
4. **Stored search depth**: 50 per team.
