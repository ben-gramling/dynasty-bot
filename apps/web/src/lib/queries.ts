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
  rank: number;
  counterparty: string;
  leg_type: "buy" | "sell" | "neutral";
  give: TradeAsset[];
  get: TradeAsset[];
  /** ΔW both ways — exact zero-sum by construction (§11.1). */
  dW: { me: number; them: number };
  gate: TradeGate;
  posture: TradePosture;
  /** Their league rank at each position I send — "aim at visible holes". */
  holes: { pos: string; their_rank: number }[];
  net_roster: { me: number; them: number };
  sequencing: string;
  taxi_stashed: { me: string[]; them: string[] };
  anchor_ask: { pct: number; ask: number; note: string };
  dip_notes: string[];
  unvalued: string[];
  notes?: string[];
  /** Shared-asset conflicts: executing this leg takes these off the board. */
  exclusive_with: string[];
}

/** §5 roster-neutral bundle: a buy-leg with its hedge sell-leg (ids into recommendations). */
export interface TradePair {
  legs: string[];
  dW: number;
  net_roster: number;
  note: string;
}

export interface TradeRecsDoc {
  computed_at: string;
  meta: ScoringMeta;
  disabled: boolean;
  recommendations: TradeRec[];
  pairs: TradePair[];
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
