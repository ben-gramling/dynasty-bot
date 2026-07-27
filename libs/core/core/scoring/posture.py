"""§4 posture: BUYER / SELLER / NEUTRAL from completed trades only.

Pure arithmetic over Sleeper transaction docs — no valuation, no lineup, no
probabilities. A team "bought" in a trade when its net flow was players-in /
picks-out, "sold" on the mirror. Over the trailing 12 months:

    BUYER  if bought >= sold + 1 and bought >= 2
    SELLER if sold  >= bought + 1 and sold  >= 2
    NEUTRAL otherwise; inactive (< 2 trades in window) is always NEUTRAL

Labels carry their evidence (the classifying trades, human-readable) and a
user override (posture-overrides collection) wins outright. Labels annotate and
order recommendations; they never gate and never touch ΔW.

The reference "now" is the newest transaction timestamp in the snapshot, so an
identical snapshot classifies identically (§11.9 determinism).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Mapping, Sequence

BUYER = "BUYER"
SELLER = "SELLER"
NEUTRAL = "NEUTRAL"
LABELS = (BUYER, SELLER, NEUTRAL)

_DAY_MS = 86_400_000


def _ts(t: Mapping) -> int:
    return int(t.get("status_updated") or t.get("created") or 0)


def _date(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()


def completed_trades(transactions: Sequence[Mapping]) -> list[Mapping]:
    """Completed trade-type docs, oldest first (deterministic order)."""
    trades = [
        t
        for t in transactions
        if t.get("type") == "trade" and t.get("status") == "complete"
    ]
    trades.sort(key=lambda t: (_ts(t), str(t.get("transaction_id"))))
    return trades


def window_trades(transactions: Sequence[Mapping], window_days: int) -> list[Mapping]:
    """Trades inside the trailing window, anchored at the newest trade timestamp."""
    trades = completed_trades(transactions)
    if not trades:
        return []
    ref = _ts(trades[-1])
    cutoff = ref - window_days * _DAY_MS
    return [t for t in trades if _ts(t) >= cutoff]


def trade_flows(t: Mapping, rid: int) -> tuple[int, int, int, int]:
    """(players_in, players_out, picks_in, picks_out) for roster `rid` in trade `t`."""
    adds = t.get("adds") or {}
    drops = t.get("drops") or {}
    picks = t.get("draft_picks") or []
    p_in = sum(1 for dest in adds.values() if int(dest) == rid)
    p_out = sum(1 for src in drops.values() if int(src) == rid)
    k_in = sum(1 for p in picks if int(p.get("owner_id") or -1) == rid)
    k_out = sum(1 for p in picks if int(p.get("previous_owner_id") or -1) == rid)
    return p_in, p_out, k_in, k_out


def trade_verdict(t: Mapping, rid: int) -> str | None:
    """"bought" (players in / picks out), "sold" (mirror), or None (neither shape)."""
    p_in, p_out, k_in, k_out = trade_flows(t, rid)
    dp, dk = p_in - p_out, k_in - k_out
    if dp > 0 and dk < 0:
        return "bought"
    if dp < 0 and dk > 0:
        return "sold"
    return None


def _evidence(t: Mapping, rid: int, verdict: str, name_of: Callable[[str], str]) -> dict:
    adds = t.get("adds") or {}
    drops = t.get("drops") or {}
    picks = t.get("draft_picks") or []
    got = [name_of(str(sid)) for sid, dest in sorted(adds.items()) if int(dest) == rid]
    got += [
        f"{p['season']} R{p['round']}"
        for p in picks
        if int(p.get("owner_id") or -1) == rid
    ]
    sent = [name_of(str(sid)) for sid, src in sorted(drops.items()) if int(src) == rid]
    sent += [
        f"{p['season']} R{p['round']}"
        for p in picks
        if int(p.get("previous_owner_id") or -1) == rid
    ]
    return {
        "transaction_id": str(t.get("transaction_id")),
        "date": _date(_ts(t)),
        "verdict": verdict,
        "got": got,
        "sent": sent,
        "summary": f"{verdict}: got {', '.join(got) or '—'} for {', '.join(sent) or '—'}",
    }


def classify_postures(
    transactions: Sequence[Mapping],
    rid_to_name: Mapping[int, str],
    name_of: Callable[[str], str] | None = None,
    *,
    window_days: int = 365,
    min_trades: int = 2,
    overrides: Mapping[str, str] | None = None,
) -> dict[str, dict]:
    """display_name -> posture dict (label, bought/sold tallies, evidence, source)."""
    name_of = name_of or (lambda sid: f"#{sid}")
    overrides = overrides or {}
    trades = window_trades(transactions, window_days)
    out: dict[str, dict] = {}
    for rid, team in sorted(rid_to_name.items()):
        mine = [t for t in trades if rid in (t.get("roster_ids") or [])]
        bought = sold = 0
        evidence: list[dict] = []
        for t in mine:
            verdict = trade_verdict(t, rid)
            if verdict == "bought":
                bought += 1
            elif verdict == "sold":
                sold += 1
            if verdict:
                evidence.append(_evidence(t, rid, verdict, name_of))
        if len(mine) < min_trades:
            label, note = NEUTRAL, f"inactive ({len(mine)} trades in window)"
        elif bought >= sold + 1 and bought >= 2:
            label, note = BUYER, None
        elif sold >= bought + 1 and sold >= 2:
            label, note = SELLER, None
        else:
            label, note = NEUTRAL, None
        entry = {
            "label": label,
            "bought": bought,
            "sold": sold,
            "trades": len(mine),
            "evidence": evidence,
            "source": "trades",
        }
        if note:
            entry["note"] = note
        ov = overrides.get(team)
        if ov in LABELS:
            entry["computed_label"] = label
            entry["label"] = ov
            entry["source"] = "override"
        out[team] = entry
    return out
