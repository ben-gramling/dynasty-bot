/**
 * Typed reads over the collector's Mongo output (docs/scoring-system.md v3,
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
  /** Noise floor: trades below this ΔW are inside KTC's own error bars (§2). */
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
  /** Face KTC value — the ΔW basis. 0 when unvalued (display "—", §11.7). */
  v: number;
  /** No KTC price on record — contributes 0 to ΔW; card flags it. */
  unvalued?: boolean;
  /** Current-year picks: rookie-board slot value (information only, never scored). */
  concrete?: number;
  note?: string;
}

/** The §3 fairness gate — band, anti-fleece cap, legality. */
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
  /** ΔW both ways — exact zero-sum by construction (§11.1). */
  dW: { me: number; them: number };
  /** §5 v3.3 leg return on inventory deployed: ΔW(me) ÷ Σv sent, percent. */
  return_pct: number | null;
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
   * §5 v3.3 return on inventory deployed, percent: combined ΔW(me) ÷ Σv of
   * every asset I send across both legs — the dial's ranking metric.
   */
  return_pct: number;
  dW_combined: number;
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

/** §5 v3.3 dial counter: exact, or a verified floor when `saturated` ("≥ N"). */
export interface ThresholdCount {
  /** Percent, matches an entry of `presets`. */
  threshold: number;
  count: number;
  /** True when the counting budget truncated the walk — count is a floor. */
  saturated: boolean;
}

/** §5 v3.3 storage-cap honesty: top `stored` by return kept of `total`. */
export interface TruncationInfo {
  stored: number;
  total: number;
  /** True when `total` itself is a saturated floor ("of ≥ N"). */
  total_saturated: boolean;
}

/** Unpaired buy — never a recommendation (§5 v3.2); one-line blocker only. */
export interface WatchEntry {
  counterparty: string;
  give: string[];
  get: string[];
  dW: number;
  blocker: string;
}

export interface TradeRecsDoc {
  computed_at: string;
  meta: ScoringMeta;
  disabled: boolean;
  /**
   * Primary (§5 v3.3): the stored pair space behind the target-return dial —
   * count-neutral pairs ranked by return_pct descending, capped at the
   * engine's max_stored_pairs (see `truncated`).
   */
  pairs: TradePair[];
  /** Dial presets, percent: [1, 2.5, 5, 10, 20]. */
  presets: number[];
  /** Honest pair counts per preset (ascending thresholds). */
  counts_by_threshold: ThresholdCount[];
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
