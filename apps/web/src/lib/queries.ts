/**
 * Typed reads over the collector's Mongo output (docs/scoring-system.md §12,
 * libs/core/core/store.py). One function per page need; every function selects
 * the "dynasty-bot" db by name and returns plain JSON-safe objects (Dates →
 * ISO strings, ObjectIds → hex strings) so results can cross into client
 * components untouched.
 */
import { getDb } from "@/lib/mongodb";

// ---- shared decomposition shapes (§12 explainability contract) ----

export interface DLTerm {
  kind: "starter" | "backup";
  slot: string;
  out: string;
  in: string;
  delta: number;
}

export interface CrunchInfo {
  cuts_before: number;
  cuts_after: number;
  rescued: string[];
}

/** One side of a move. lineup_weighted + wealth_weighted + crunch_term = score (±0.1). */
export interface SideDecomp {
  omega: number;
  dL: number;
  dNC: number;
  dA: number;
  dC: number;
  score: number;
  lineup_weighted: number;
  wealth_weighted: number;
  crunch_term: number;
  dL_terms: DLTerm[];
  crunch?: CrunchInfo;
}

export interface LineupSlotRow {
  slot: string;
  player: string;
  v: number;
}

export interface BeforeAfter {
  before: LineupSlotRow[];
  after: LineupSlotRow[];
}

export interface ScoringMeta {
  mode: string;
  week: number;
  draft_status: string;
  current_year: number;
  omega_me: number;
  replacement: Record<string, number>;
  unvalued_rostered: string[];
  alerts: string[];
  my_team: string;
}

// ---- waiver board ----

export interface BidBlock {
  mode: string;
  D: number;
  netclaim: number;
  netclaim_raw: number;
  ceiling: number;
  clamp: string | null;
  bid: number;
}

export interface WaiverTarget {
  action: "CLAIM";
  player: string;
  sid: string;
  pos: string;
  v: number;
  dL: number;
  netclaim: number;
  netclaim_raw: number;
  drop: string | null;
  ir_move: string | null;
  recommended: boolean;
  free_option: boolean;
  dip: boolean;
  bid: BidBlock;
  sides: { me: SideDecomp };
  audit: { lineup_tables: BeforeAfter };
  rank: number;
}

export interface DropRow {
  action: "DROP";
  player: string;
  sid: string;
  pos: string;
  v: number;
  rv: number;
  rv0: number;
  scheduled_cut: boolean;
  unvalued: boolean;
  require_confirm: boolean;
  sides: { me: SideDecomp };
  audit: { lineup_tables: BeforeAfter };
}

export interface QueuedClaim {
  action: string;
  player: string;
  drop: string | null;
  score_today: number;
  score_post_draft: number;
  note: string;
}

export interface TaxiPromotion {
  action: "PROMOTE";
  player: string;
  attached_drop: string | null;
  score: number;
  lock_penalty: number;
  omega_dl: number;
  sides: { me: SideDecomp };
  audit: { lineup_tables: BeforeAfter };
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
  queued: QueuedClaim[];
  taxi_promotions: TaxiPromotion[];
  taxi_fill?: {
    free_slots: number;
    surplus_slots: number;
    candidates: { player: string; pos: string; v: number; note: string }[];
  };
  rookie_inventory: RookieInventoryRow[];
}

// ---- trade recs ----

export interface TradeAsset {
  type: "player" | "pick";
  name: string;
  v: number;
  mv?: number;
  pricing?: { rule: string; band: string; band_reason: string };
}

export interface Fairness {
  adj_give: number;
  adj_get: number;
  gap_pct: number;
  band_pct: number;
  adj: string;
  raw_ratio: number;
  cap: number;
}

export interface TradeRec {
  action: "TRADE";
  counterparty: string;
  give: TradeAsset[];
  get: TradeAsset[];
  sides: { me: SideDecomp; them: SideDecomp };
  fairness: Fairness;
  tier: string;
  posture_fit: boolean;
  activity: string;
  anchor_ask_pct: number;
  omega_sensitivity: Record<string, number>;
  dip_targets: unknown[];
  pick_anchor: unknown[];
  audit: { lineup_tables: { me: BeforeAfter; them: BeforeAfter } };
}

export interface TradeZoneRow {
  target: string;
  v: number;
  owner: string;
  their_floor: number;
  my_ceiling: number;
  zone: number;
}

export interface TradeRecsDoc {
  computed_at: string;
  meta: ScoringMeta;
  disabled: boolean;
  recommendations: TradeRec[];
  per_opponent: Record<string, TradeRec[]>;
  trade_zone: TradeZoneRow[];
}

// ---- league table ----

export interface PositionGroup {
  sum: number;
  rank: number;
  players: { player: string; v: number }[];
}

export interface PickDetail {
  label: string;
  p: number;
  mv: number;
  rule?: string;
  band?: string;
  band_reason?: string;
  sell_floor?: number;
}

export interface FutureBlock {
  picks: number;
  picks_detail: PickDetail[];
  taxi: number;
  taxi_detail: { player: string; v: number }[];
  F: number;
  F_rank: number;
}

export interface MarketBlock {
  cuts: number;
  C: number;
  cut_list: string[];
  faab: number;
}

export interface LeagueRow {
  team: string;
  roster_id: number;
  lineup: Record<string, PositionGroup>;
  L: number;
  L_rank: number;
  L_z: number;
  omega: number;
  omega_suggest: number;
  future: FutureBlock;
  market: MarketBlock;
}

export interface MyTeamDetail extends LeagueRow {
  picks_by_year: Record<string, PickDetail[]>;
  crunch_due: string;
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
