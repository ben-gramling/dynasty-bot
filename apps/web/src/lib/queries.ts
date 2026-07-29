/**
 * Typed reads over the collector's Mongo output (docs/scoring-system.md v5,
 * libs/core/core/store.py). One function per page need; every function selects
 * the "dynasty-bot" db by name and returns plain JSON-safe objects (Dates →
 * ISO strings, ObjectIds → hex strings) so results can cross into client
 * components untouched.
 */
import { getDb } from "@/lib/mongodb";

// ---- shared meta (compute_all meta block) ----

export interface ScoringMeta {
  mode: string;
  week: number;
  draft_status: string;
  current_year: number;
  /** Noise floor: guaranteed floors below this are inside KTC's error bars (§2). */
  w_min: number;
  replacement: Record<string, number>;
  unvalued_rostered: string[];
  alerts: string[];
  my_team: string;
}

// ---- waiver board (§6) ----

export interface BidBlock {
  mode: string;
  /** Rival demand — teams that visibly need him and can pay. */
  D: number;
  claim: number;
  ceiling: number;
  /** In-season only: 65%-of-FAAB clamp; null offseason. */
  clamp: number | null;
  bid: number;
}

export interface WaiverTarget {
  action: "CLAIM";
  player: string;
  sid: string;
  pos: string;
  v: number;
  /** Claim score = v(add) − v(drop) — the ranking score (§6). */
  claim: number;
  dL: number;
  /** Erratum 10: stashes on taxi — consumes no active spot, no drop needed. */
  taxi_stash: boolean;
  drop: string | null;
  recommended: boolean;
  dip: boolean;
  bid: BidBlock;
  rank: number;
}

/** Drop list row (§6): actives ascending by v — informational housekeeping. */
export interface DropRow {
  action: "DROP";
  player: string;
  sid: string;
  pos: string;
  v: number;
  unvalued: boolean;
}

export interface TaxiFill {
  free_slots: number;
  surplus_slots: number;
  candidates: { player: string; pos: string; v: number; note: string }[];
}

export interface RookieInventoryRow {
  player: string;
  pos: string;
  v: number;
  rookie_rank: number;
  note: string;
}

export interface WaiverBoard {
  computed_at: string;
  meta: ScoringMeta;
  mode: string;
  faab_remaining: number;
  targets: WaiverTarget[];
  drops: DropRow[];
  taxi_fill: TaxiFill;
  rookie_inventory: RookieInventoryRow[];
}

// ---- trade recs (§2–§5) ----

export interface TradeAsset {
  type: "player" | "pick";
  key: string;
  name: string;
  /** Face KTC value — what the market prices the asset at (§3). 0 when unvalued. */
  v: number;
  /** No KTC price on record — contributes 0 to ΔW; card flags it. */
  unvalued?: boolean;
  /** Current-year picks: rookie-board slot value (information only, never scored). */
  concrete?: number;
  note?: string;
}

/**
 * The §3 fairness gate — band, anti-fleece cap, legality. v3.4: `adj_give` /
 * `adj_get` are the EXACT totals KTC's own trade calculator displays for the
 * two sides (the reverse-engineered value adjustment, zero fitted parameters).
 */
export interface TradeGate {
  adj_give: number;
  adj_get: number;
  gap: number;
  gap_pct: number;
  band: number;
  band_pct: number;
  band_ok: boolean;
  raw_ratio: number;
  cap: number;
  ratio_ok: boolean;
  legal: boolean;
  verdict: string;
  /**
   * §4a v5 counterparty favorability, signed, from the SAME two adjusted
   * totals as this gate: the skew toward the counterparty in KTC's own
   * calculator variance units (|favor| ≤ 5 ⟺ their calculator literally says
   * FAIR at default variance; favor > 0 skews to them). Mirrored on the leg
   * card as `favor`. Optional: docs written before v5 omit it.
   */
  favor?: number;
}

/**
 * §2 v4 the two objective coordinates: `dS` is the change in STARTER value —
 * the max-Σv legal lineup at raw KTC over active + taxi (IR never counts) —
 * and `dF` the change in TOTAL FACE owned (players + picks at tranche).
 * Parameter-free; the verdict, floor, ceiling and breakeven all derive from
 * them (ceiling = max(dS, dF)).
 */
export interface Coords {
  dS: number;
  dF: number;
}

/**
 * Pre-v4 ledger split (v3.5 `{dS, dT}` — dT already δ-discounted). Kept ONLY
 * so board docs written before v4 still render; never present on v4 docs.
 */
export interface LedgerParts {
  dS?: number;
  dT?: number;
}

/** §4 posture context: observed-trades label + how this offer is shaped. */
export interface TradePosture {
  label: string; // BUYER | SELLER | NEUTRAL
  source: string; // "trades" | "override"
  evidence_count: number;
  shape: string; // what they receive: "players" | "picks" | "mixed"
  fit: boolean;
}

export interface TradeRec {
  action: "TRADE";
  id: string;
  /** Rank within the secondary sell list — pair legs carry none. */
  rank?: number;
  counterparty: string;
  leg_type: "buy" | "sell" | "neutral";
  give: TradeAsset[];
  get: TradeAsset[];
  /**
   * §2 v4 the two coordinates, PER SIDE against each side's own roster. `dF`
   * is exactly zero-sum across the parties of a leg (face conservation);
   * `dS` is not — deployment differs by roster, so a good leg can be
   * objectively good for BOTH sides. Absent on pre-v4 docs (render `dW`
   * instead).
   */
  coords?: { me: Coords; them: Coords };
  /** §2 v4 objective verdict per side: dS ≥ 0 AND dF ≥ 0, one strict. */
  verdict?: { me: boolean; them: boolean };
  /** §2 v4 guaranteed floor per side: min(dS, dF) — the worst case over
   * every rational preference. Ceiling derives as max(dS, dF) from coords. */
  floor?: { me: number; them: number };
  /**
   * §2 v4 breakeven δ* = dS / (dS − dF), per side — present ONLY on
   * preference trades (verdict false, exactly one coordinate positive);
   * null otherwise.
   */
  breakeven?: { me: number | null; them: number | null };
  /** "isolation" on leg cards: this leg alone. Pairs carry combined coords. */
  coords_basis?: string;
  /**
   * Pre-v4 wealth ledger (v3.4/v3.5 docs): per-side ΔW, its split, and its
   * basis. Never present on v4 docs — kept optional so old boards render.
   */
  dW?: { me: number; them: number };
  dW_parts?: {
    me: LedgerParts;
    them: LedgerParts;
  };
  dW_basis?: string;
  /** §5 v4 leg return on inventory deployed: isolation floor(me) ÷ Σv sent,
   * percent (pre-v4 docs: ΔW-based — same field, same rendering). */
  return_pct: number | null;
  /**
   * Leg MARKET return, percent: face ΔF(me) ÷ face Σv sent on this leg — the
   * raw face skim off this counterparty. v5 DEMOTED it from dial input to
   * annotation (the raw skim diverges from the counterparty's own calculator
   * by up to 14 pts — `favor` is the dial's input now). Optional: docs
   * written before v3.4.1 omit it.
   */
  market_return_pct?: number | null;
  /**
   * §4a v5 counterparty favorability for this leg, signed: the skew toward
   * the counterparty in KTC's own calculator variance units, derived from the
   * SAME adjusted totals as the gate (also mirrored at `gate.favor`).
   * |favor| ≤ 5 ⟺ their calculator literally says FAIR at default variance;
   * favor > 0 skews to them. Optional: docs written before v5 omit it.
   */
  favor?: number;
  gate: TradeGate;
  posture: TradePosture;
  /** Their league rank at each position I send — "aim at visible holes". */
  holes: { pos: string; their_rank: number }[];
  /** Δ(active roster) — sequencing only; taxi-routed arrivals excluded. */
  net_roster: { me: number; them: number };
  /**
   * §5 v3.2 count delta: players received − sent, counted wherever they land
   * (active or taxi-routed). Exact negation across sides.
   */
  net_players: { me: number; them: number };
  /** §5 v3.2 count delta: picks received − sent, regardless of year. */
  net_picks: { me: number; them: number };
  /**
   * True iff this leg alone nets 0 players AND 0 picks for me — executable
   * without pairing. Everything else is a building block (§5 v3.2).
   */
  standalone: boolean;
  sequencing: string;
  taxi_stashed: { me: string[]; them: string[] };
  anchor_ask: { pct: number; ask: number; note: string };
  /** §3 v3.1 band-edge ceiling — negotiating room above the proposal, info only. */
  ceiling?: { value: number; note: string };
  dip_notes: string[];
  unvalued: string[];
  notes?: string[];
  /** Shared-asset conflicts: executing this leg takes these off the board. */
  exclusive_with: string[];
}

/**
 * §5 v3.2 count-neutral hedged pair — the PRIMARY recommendation unit: a buy
 * side and a sell side (full embedded cards) sharing no assets, netting for my
 * side EXACTLY 0 players AND 0 picks (players count wherever they land; picks
 * regardless of year).
 */
export interface TradePair {
  id: string;
  buy: TradeRec;
  sell: TradeRec;
  /**
   * §5 v4 TOTAL return on inventory deployed, percent: guaranteed floor
   * min(dS, dF) combined ÷ Σv of every asset I send across both legs — the
   * ROBUST return (the δ dial's default view), the floor dial's robust filter
   * key, and the shipped sort key (ceiling desc as tie-break; the board
   * always ships in maximin order — the δ dial re-sorts client-side).
   */
  return_pct: number;
  /**
   * §4a/§5 v5: each leg's counterparty favorability (signed, KTC's own
   * calculator variance units, from the same adjusted totals as the gate) and
   * `min` — the least-happy counterparty, the favor-floor dial's filter key
   * and the storage bucket key. Optional: docs written before v5 omit it.
   */
  favor?: { buy: number; sell: number; min: number };
  /**
   * §5 v5 Σ face v of every asset I send across both legs — the return
   * denominator; with `coords` it lets the δ dial re-score return(δ) =
   * (dS + δ·(dF − dS)) ÷ sent client-side, O(stored) per dial move.
   * Optional: docs written before v5 omit it (robust view only).
   */
  sent?: number;
  /**
   * Pre-v5 (v3.4.1): each leg's market return, percent (raw face skim off
   * that leg's counterparty), and their max — the retired leg-cap dial's
   * filter key. REMOVED from v5 docs (the raw skim diverges from the
   * counterparty's calculator by up to 14 pts); kept optional so old boards
   * render.
   */
  leg_returns?: { buy: number; sell: number };
  max_leg_return_pct?: number;
  /**
   * §2 v4 combined coordinates, my side, BOTH legs applied together: dS via
   * one combined lineup solve (the legs interact), dF additive across legs.
   * Absent on pre-v4 docs (render `dW_combined` instead).
   */
  coords?: Coords;
  /** §2 v4: true on every stored pair (hard constraint §11.8b(d)). */
  verdict?: boolean;
  /** §2 v4 the guaranteed gain: min(dS, dF) combined. */
  floor?: number;
  /** §2 v4 the best case: max(dS, dF) combined. */
  ceiling?: number;
  /**
   * Pre-v4 combined wealth ledger (v3.4/v3.5 docs) — kept optional so old
   * boards render; never present on v4 docs.
   */
  dW_combined?: number;
  dW_combined_parts?: LedgerParts;
  dW_legs_isolated?: number;
  /** Combined Δ(active roster) — sequencing context only. */
  net_roster: number;
  /** Combined Δ(player count) for my side — exactly 0 by construction. */
  net_players: number;
  /** Combined Δ(pick count) for my side — exactly 0 by construction. */
  net_picks: number;
  fit_summary: string;
  sequencing: string;
  /** How many OTHER stored pairs share an asset with this one (§5 conflicts). */
  overlaps: number;
}

/** §5 v3.3 ≥-threshold counter: exact, or a verified floor when `saturated` ("≥ N"). */
export interface ThresholdCount {
  /** Percent, matches an entry of `presets`. */
  threshold: number;
  count: number;
  /** True when the counting budget truncated the walk — count is a floor. */
  saturated: boolean;
}

/**
 * §5 v5 per-BUCKET inventory: buckets stratify on PAIR FAVORABILITY
 * min(f_buy, f_sell) — the least-happy counterparty, in KTC's own calculator
 * variance units — over half-open (−∞,−10), [−10,−5), [−5,0), [0,+5), [+5,∞)
 * intervals (lo null on the open bottom — a leg can skew arbitrarily far
 * toward me; hi null on the open top). Per bucket the engine stores the
 * deduped UNION of the top-quota pairs by robust floor-return, by ΔS, and by
 * ΔF (so both δ-slider extremes have inventory); a favor-floor preset `f`
 * selects the buckets with lo ≥ f (the +2.5 preset sits inside [0,+5) and is
 * served from that bucket's stored inventory — bucket counts for it stay
 * floors). `count` is the bucket's legal pair count and `by_total` its counts
 * per ROBUST-return band (aligned with `presets`) — every count a verified
 * floor when `saturated` (outside whole-space walks: always). Docs written
 * before v5 carry max-leg market-return buckets in the same shape — render
 * defensively.
 */
export interface BandInfo {
  /** Bucket lower edge, favor units (inclusive); null = open bottom. */
  lo: number | null;
  /** Bucket upper edge, favor units (exclusive); null = open top. */
  hi: number | null;
  /** Pairs stored for this bucket (union ≤ 3× the per-bucket quota). */
  stored: number;
  /** Legal pairs in the bucket — a verified floor when saturated. */
  count: number;
  /** True when the count is a floor, not an exact tally ("≥ N"). */
  saturated: boolean;
  /** The bucket's counts per robust-return band (aligned with presets). */
  by_total?: number[];
}

/** §5 v3.3 storage-cap honesty: top `stored` by return kept of `total`. */
export interface TruncationInfo {
  stored: number;
  total: number;
  /** True when `total` itself is a saturated floor ("of ≥ N"). */
  total_saturated: boolean;
}

/** Unpaired buy — never a recommendation (§5 v3.2); one-line blocker only.
 * v4 docs carry `floor` (isolation guaranteed floor); pre-v4 docs carried
 * `dW`. The web renders neither — desk data only. */
export interface WatchEntry {
  counterparty: string;
  give: string[];
  get: string[];
  floor?: number;
  dW?: number;
  blocker: string;
}

export interface TradeRecsDoc {
  computed_at: string;
  meta: ScoringMeta;
  disabled: boolean;
  /**
   * Primary (§4a/§5 v5): the stratified stored pair space behind the
   * finder's THREE dials — δ selector (robust default; return(δ) re-scored
   * client-side from coords + sent), total-return floor on return(δ), and
   * counterparty-favorability floor on favor.min. Count-neutral pairs,
   * per-FAVOR-bucket union of tops (by robust return, ΔS, ΔF), the flat list
   * shipped in maximin order (robust return desc, ceiling tie-break). See
   * `bands` for per-bucket honesty.
   */
  pairs: TradePair[];
  /** Total-return floor presets, percent: [1, 2.5, 5, 10, 20]. */
  presets: number[];
  /**
   * v5 favor-floor presets, KTC variance units: [−10, −5, 0, +2.5, +5]
   * (+ "no floor" client-side). ±5 = their calculator's FAIR window.
   * Optional: docs written before v5 omit them.
   */
  favor_presets?: number[];
  /**
   * v5 δ-view presets: [0, 0.25, 0.5, 0.75, 1] (+ "robust" default
   * client-side). Views only — never score parameters (§9). Optional: docs
   * written before v5 omit them.
   */
  delta_presets?: number[];
  /** Pre-v5 (v3.4.1) leg-cap presets, percent — retired. Optional on old docs. */
  leg_cap_presets?: number[];
  /** Honest pair counts per floor preset (ascending; ≥-style compat, robust). */
  counts_by_threshold: ThresholdCount[];
  /** v5 per-favor-bucket inventory (ascending) — the favor dial's source. */
  bands: BandInfo[];
  /** Set when more pairs cleared the floor than were stored; null otherwise. */
  truncated: TruncationInfo | null;
  /**
   * Secondary: unpaired sell/neutral legs — building blocks with their count
   * deltas, never executable recommendations alone (§5 v3.2); never buys.
   * Data for the trade-negotiator desk — the web does not render them.
   */
  recommendations: TradeRec[];
  watch: WatchEntry[];
  notes: string[];
}

// ---- league table (§7) ----

export interface PositionGroup {
  sum: number;
  rank: number;
  players: { player: string; v: number }[];
}

export interface PickDetail {
  label: string;
  /** KTC tranche value — the number every league-mate sees. */
  v: number;
  band?: string;
  band_reason?: string;
  /** Current-year picks: rookie-board slot-implied value (annotation only). */
  concrete?: number;
}

export interface FutureBlock {
  picks: number;
  picks_detail: PickDetail[];
  taxi: number;
  taxi_detail: { player: string; v: number }[];
  F: number;
  F_rank: number;
}

/** One completed trade backing a posture label (§4 evidence). */
export interface EvidenceTrade {
  transaction_id: string;
  date: string;
  verdict: string; // "bought" | "sold"
  got: string[];
  sent: string[];
  summary: string;
}

/** The §7 market map block — the targeting console. */
export interface MarketBlock {
  posture: string; // BUYER | SELLER | NEUTRAL
  posture_source: string;
  bought: number;
  sold: number;
  trades_12mo: number;
  evidence: EvidenceTrade[];
  holes: { pos: string; rank: number }[];
  pick_inventory: {
    count: number;
    by_year: Record<string, number>;
    value: number;
  };
  faab: number;
}

export interface LeagueRow {
  team: string;
  roster_id: number;
  lineup: Record<string, PositionGroup>;
  L: number;
  L_rank: number;
  L_z: number;
  future: FutureBlock;
  market: MarketBlock;
}

export interface MyTeamDetail extends LeagueRow {
  picks_by_year: Record<string, PickDetail[]>;
  unvalued: string[];
}

export interface LeagueTableDoc {
  computed_at: string;
  meta: ScoringMeta;
  rows: LeagueRow[];
  L_mean: number;
  L_sigma: number;
  my_team: MyTeamDetail;
}

// ---- runs ----

export interface CollectorRun {
  id: string;
  started: string;
  finished: string | null;
  ok: boolean;
  error: string | null;
  counts: Record<string, number>;
}

// ---- helpers ----

/** BSON → plain JSON (Date → ISO string, ObjectId → hex via its toJSON). */
function toPlain<T>(doc: unknown): T {
  return JSON.parse(JSON.stringify(doc)) as T;
}

// ---- query functions (one per page need) ----

export async function getWaiverBoard(): Promise<WaiverBoard | null> {
  const db = await getDb();
  const doc = await db.collection("waiver-board").findOne({ _id: "latest" as never });
  return doc ? toPlain<WaiverBoard>(doc) : null;
}

export async function getTradeRecs(): Promise<TradeRecsDoc | null> {
  const db = await getDb();
  const doc = await db.collection("trade-recs").findOne({ _id: "latest" as never });
  return doc ? toPlain<TradeRecsDoc>(doc) : null;
}

export async function getLeagueTable(): Promise<LeagueTableDoc | null> {
  const db = await getDb();
  const doc = await db.collection("league-table").findOne({ _id: "latest" as never });
  return doc ? toPlain<LeagueTableDoc>(doc) : null;
}

function runFromDoc(doc: Record<string, unknown>): CollectorRun {
  const plain = toPlain<Record<string, unknown>>(doc);
  return {
    id: String(plain._id),
    started: String(plain.started),
    finished: plain.finished ? String(plain.finished) : null,
    ok: Boolean(plain.ok),
    error: plain.error ? String(plain.error) : null,
    counts: (plain.counts ?? {}) as Record<string, number>,
  };
}

/** Most recent collector run (excludes the "meta" doc). Null before first run. */
export async function getLastRun(): Promise<CollectorRun | null> {
  const db = await getDb();
  const doc = await db
    .collection("runs")
    .find({ _id: { $ne: "meta" as never }, started: { $exists: true } })
    .sort({ started: -1 })
    .limit(1)
    .next();
  return doc ? runFromDoc(doc) : null;
}

// ---- player bio enrichment (Sleeper players dump; _id = sleeper id) ----

export interface PlayerInfo {
  team: string | null;
  age: number | null;
  injury: string | null;
}

/**
 * Team/age/injury for a set of sleeper ids, keyed by id. Board/drop docs carry
 * only name+pos+value; the bio line (team · age) joins in from the `players`
 * collection. Missing ids are simply absent from the map.
 */
export async function getPlayerInfoMap(
  sids: string[]
): Promise<Record<string, PlayerInfo>> {
  if (!sids.length) return {};
  const db = await getDb();
  const docs = await db
    .collection("players")
    .find(
      { _id: { $in: sids } as never },
      { projection: { team: 1, age: 1, injury_status: 1 } }
    )
    .toArray();
  const map: Record<string, PlayerInfo> = {};
  for (const d of docs) {
    const p = toPlain<Record<string, unknown>>(d);
    map[String(p._id)] = {
      team: typeof p.team === "string" && p.team ? p.team : null,
      age: typeof p.age === "number" ? p.age : null,
      injury:
        typeof p.injury_status === "string" && p.injury_status
          ? p.injury_status
          : null,
    };
  }
  return map;
}
