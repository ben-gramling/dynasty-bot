"""§4 v5 targeting & market constraints — ONE machine-executable vocabulary.

Every targeting fact is a CONSTRAINT the spread finder (§4a) applies:

    constraint = { who: <username> | "me" | "*",
                   side: "receives" | "sends",
                   what: {class: "pick"|"player"} | {pos: "QB"|"RB"|"WR"|"TE"}
                         | {asset: <name|key>},
                   with: <username> | null,   # optional: only vs this counterparty
                   mode: "require" | "exclude" | "prefer" }

Semantics are PER LEG: `who receives what` constrains the package flowing TO
`who` on any leg they are party to; `who = "*"` means every counterparty; `me`
is my own side. `require` — every leg involving `who` must match (hard).
`exclude` — no leg may match (hard). `prefer` — matching legs are tagged ★
(soft; never reorders slider math).

Matching is conservative and asymmetric by design:

- require {class: c} means the package is MAJORITY class c (offer_shape) —
  exactly v3.3's posture_allows behavior, which the posture defaults must
  reproduce when nothing overrides them (§11.12(f)).
- require {pos}/{asset} means the package CONTAINS such an asset.
- exclude means the package contains NO such asset (any-containment — the
  stronger, safer reading for all three `what` shapes).
- prefer means the package contains such an asset (majority for {class}).

Three sources, strict precedence (§4 — later source wins PER TEAM, keyed on
`who`; wildcard constraints are additive and never override or get overridden):

1. Posture defaults (auto-compiled): BUYER → require receives {class: player};
   SELLER → require receives {class: pick}; NEUTRAL → no constraint.
2. Market intel (the `market-intel` Mongo collection; docs carry kind
   WANT/DONT_WANT/OFFERED/REJECTED/NOTE, team, subject text, active flag):
   WANT → require on their receive side; DONT_WANT → exclude on their receive
   side; OFFERED(asset) → prefer on MY receive side vs that team; REJECTED →
   exclude of that exact shape; NOTE → never compiled. Subject text is parsed
   CONSERVATIVELY — exact rostered-asset name, pick-class keywords, or
   position keywords; anything unparseable compiles to NO constraint and is
   reported back as such, never guessed.
3. Ad-hoc query constraints (per §4a call) — override both for the teams they
   name; malformed query constraints raise (the caller typed them).

Pure functions over LeagueState + plain dicts; no I/O, no Mongo — the caller
fetches `market-intel` docs and hands them in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from core.scoring import model as md
from core.scoring import posture as ps
from core.scoring.trades import Package, offer_shape, team_assets

REQUIRE, EXCLUDE, PREFER = "require", "exclude", "prefer"
MODES = (REQUIRE, EXCLUDE, PREFER)
SIDES = ("receives", "sends")
POSITIONS = ("QB", "RB", "WR", "TE")
INTEL_KINDS = ("WANT", "DONT_WANT", "OFFERED", "REJECTED", "NOTE")


@dataclass(frozen=True, slots=True)
class Constraint:
    """One compiled §4 constraint. `what` is a normalized ("class"|"pos"|"asset",
    value) pair; for parsed intel the asset value is the canonical rostered
    name; ad-hoc queries may carry a raw name or key (matched against both)."""

    who: str  # username | "me" | "*"
    side: str  # "receives" | "sends"
    what: tuple[str, str]
    with_: str | None
    mode: str
    source: str  # "posture" | "intel" | "query"
    origin: str  # human-readable provenance

    def to_dict(self) -> dict:
        return {
            "who": self.who,
            "side": self.side,
            "what": {self.what[0]: self.what[1]},
            "with": self.with_,
            "mode": self.mode,
            "source": self.source,
            "origin": self.origin,
        }


# ------------------------------------------------------------- what-matching


def _contains(pkg: Package, what: tuple[str, str]) -> bool:
    """Any-containment: does the package hold an asset matching `what`?
    Asset refs match key exactly or name case-insensitively."""
    kind, val = what
    if kind == "class":
        return any(a.kind == val for a in pkg.assets)
    if kind == "pos":
        return any(a.kind == "player" and a.pos == val for a in pkg.assets)
    low = val.lower()
    return any(a.key == val or a.name.lower() == low for a in pkg.assets)


def _satisfies_require(pkg: Package, what: tuple[str, str]) -> bool:
    """require-matching: {class} is MAJORITY (offer_shape — §11.12(f) posture
    parity); {pos}/{asset} is containment."""
    if what[0] == "class":
        return offer_shape(pkg) == ("players" if what[1] == "player" else "picks")
    return _contains(pkg, what)


def _applies_to(c: Constraint, opp_name: str, package_side: str) -> bool:
    """Does `c` constrain the package on `package_side` ("give" = the package
    the counterparty receives / I send; "get" = the mirror) of a leg vs
    `opp_name`?"""
    if c.with_ is not None and c.with_ != opp_name:
        return False
    if c.who == "me":
        their_side = "sends" if c.side == "receives" else "receives"
    elif c.who == "*" or c.who == opp_name:
        their_side = c.side
    else:
        return False  # names a different team: this leg is unconstrained by it
    return package_side == ("give" if their_side == "receives" else "get")


def package_allowed(
    constraints: Sequence[Constraint], opp_name: str, package_side: str, pkg: Package
) -> bool:
    """Hard require/exclude verdict for ONE package of a leg vs `opp_name` —
    the §4a push-down predicate: constraints filter candidate packages BEFORE
    any gate work, and every §4 constraint is single-package, so a leg is
    allowed iff both its packages are."""
    for c in constraints:
        if not _applies_to(c, opp_name, package_side):
            continue
        if c.mode == REQUIRE and not _satisfies_require(pkg, c.what):
            return False
        if c.mode == EXCLUDE and _contains(pkg, c.what):
            return False
    return True


def leg_allowed(
    constraints: Sequence[Constraint], opp_name: str, give: Package, get: Package
) -> bool:
    """Hard verdict for a whole leg (I send `give` to opp_name, receive `get`)."""
    return package_allowed(constraints, opp_name, "give", give) and package_allowed(
        constraints, opp_name, "get", get
    )


def leg_preferred(
    constraints: Sequence[Constraint], opp_name: str, give: Package, get: Package
) -> bool:
    """Soft ★ tag: any prefer-constraint matches either package of the leg."""
    for c in constraints:
        if c.mode != PREFER:
            continue
        for side, pkg in (("give", give), ("get", get)):
            if _applies_to(c, opp_name, side) and _satisfies_require(pkg, c.what):
                return True
    return False


# ----------------------------------------------------------------- compilers


def posture_constraints(league: md.LeagueState) -> list[Constraint]:
    """§4 source 1 — auto-compiled posture defaults, one per non-NEUTRAL
    counterparty. Reproduces v3.3 posture_allows exactly when nothing
    overrides (§11.12(f)): BUYER receives players-majority, SELLER receives
    picks-majority, NEUTRAL unconstrained. Overrides are already folded into
    league.postures upstream."""
    out: list[Constraint] = []
    for name in league.opponents:
        label = league.postures.get(name, {}).get("label", ps.NEUTRAL)
        if label == ps.BUYER:
            what: tuple[str, str] = ("class", "player")
        elif label == ps.SELLER:
            what = ("class", "pick")
        else:
            continue
        out.append(
            Constraint(
                who=name, side="receives", what=what, with_=None, mode=REQUIRE,
                source="posture", origin=f"posture {label}",
            )
        )
    return out


_ARTICLES = ("a ", "an ", "the ", "some ")

_CLASS_WORDS = {
    "pick": "pick", "picks": "pick", "draft pick": "pick", "draft picks": "pick",
    "draft capital": "pick", "future picks": "pick",
    "player": "player", "players": "player",
    "veteran": "player", "veterans": "player", "veteran players": "player",
}

_POS_WORDS = {
    "qb": "QB", "quarterback": "QB", "quarterbacks": "QB",
    "rb": "RB", "running back": "RB", "running backs": "RB",
    "wr": "WR", "wide receiver": "WR", "wide receivers": "WR",
    "receiver": "WR", "receivers": "WR",
    "te": "TE", "tight end": "TE", "tight ends": "TE",
}


def _asset_names(league: md.LeagueState) -> dict[str, str]:
    """lowercased rostered asset name -> canonical name (players, taxi, picks
    of every team). Conservative universe: only assets that can actually move."""
    out: dict[str, str] = {}
    for t in league.teams.values():
        for name in team_assets(league, t):
            out[name.lower()] = name
    return out


def parse_subject(league: md.LeagueState, text: str) -> tuple[str, str] | None:
    """Conservative §4 subject parser: exact rostered-asset name (case-
    insensitive) → ("asset", canonical); pick/player class keywords →
    ("class", …); position keywords → ("pos", …) — leading articles stripped.
    Anything else → None (reported, never guessed)."""
    if not isinstance(text, str):
        return None
    s = " ".join(text.strip().lower().split())
    if not s:
        return None
    canonical = _asset_names(league).get(s)
    if canonical is not None:
        return ("asset", canonical)
    for art in _ARTICLES:
        if s.startswith(art):
            s = s[len(art):]
            break
    if s in _CLASS_WORDS:
        return ("class", _CLASS_WORDS[s])
    if s in _POS_WORDS:
        return ("pos", _POS_WORDS[s])
    return None


def compile_intel(
    league: md.LeagueState, docs: Sequence[Mapping]
) -> tuple[list[Constraint], list[dict]]:
    """§4 source 2 — market-intel docs (kind, team, subject, active) compiled
    to constraints. Returns (constraints, ignored) where `ignored` reports
    every ACTIVE doc that compiled to nothing and why — unparseable subjects
    are never guessed at (§4); inactive docs are revoked and silently skipped."""
    out: list[Constraint] = []
    ignored: list[dict] = []

    def skip(doc: Mapping, reason: str) -> None:
        ignored.append({"doc": dict(doc), "reason": reason})

    for doc in docs:
        if not doc.get("active", True):
            continue
        kind = doc.get("kind")
        team = doc.get("team")
        subject = doc.get("subject")
        if kind not in INTEL_KINDS:
            skip(doc, f"unknown kind {kind!r}")
            continue
        if kind == "NOTE":
            skip(doc, "NOTE — context for the desk, never compiled (§4)")
            continue
        if team in (None, "", "*"):
            team = "*"
        elif team not in league.teams or team == league.me:
            skip(doc, f"unknown team {team!r}")
            continue
        if kind in ("WANT", "OFFERED", "REJECTED") and team == "*":
            skip(doc, f"{kind} needs a named team")
            continue
        what = parse_subject(league, subject)
        if what is None:
            skip(
                doc,
                f"subject {subject!r} not parseable as a rostered asset, "
                "pick/player class, or position — no constraint compiled (§4)",
            )
            continue
        origin = f"intel {kind}: {team} {subject!r}"
        if kind == "WANT":
            out.append(Constraint(team, "receives", what, None, REQUIRE, "intel", origin))
        elif kind == "DONT_WANT":
            out.append(Constraint(team, "receives", what, None, EXCLUDE, "intel", origin))
        elif kind == "REJECTED":
            # exclude of that exact shape: they turned this down on their
            # receive side — never offer it again
            out.append(Constraint(team, "receives", what, None, EXCLUDE, "intel", origin))
        else:  # OFFERED — prefer on MY receive side vs that team
            out.append(Constraint("me", "receives", what, team, PREFER, "intel", origin))
    return out, ignored


def query_constraint(league: md.LeagueState, d: Mapping) -> Constraint:
    """§4 source 3 — validate one ad-hoc constraint dict. Malformed input
    raises ValueError: the user typed it, so it is corrected, never guessed."""
    who = d.get("who")
    if who not in ("me", "*") and who not in league.teams:
        raise ValueError(f"constraint who={who!r} is not 'me', '*', or a league username")
    if who == league.me:
        who = "me"
    side = d.get("side")
    if side not in SIDES:
        raise ValueError(f"constraint side={side!r} must be 'receives' or 'sends'")
    mode = d.get("mode")
    if mode not in MODES:
        raise ValueError(f"constraint mode={mode!r} must be require/exclude/prefer")
    with_ = d.get("with", d.get("with_"))
    if with_ is not None and with_ not in league.teams:
        raise ValueError(f"constraint with={with_!r} is not a league username")
    what_d = d.get("what")
    if not isinstance(what_d, Mapping) or len(what_d) != 1:
        raise ValueError("constraint what must be exactly one of {class}/{pos}/{asset}")
    ((kind, val),) = what_d.items()
    if kind == "class":
        if val not in ("pick", "player"):
            raise ValueError(f"what.class={val!r} must be 'pick' or 'player'")
    elif kind == "pos":
        if val not in POSITIONS:
            raise ValueError(f"what.pos={val!r} must be one of {POSITIONS}")
    elif kind == "asset":
        if not isinstance(val, str) or not val.strip():
            raise ValueError("what.asset must be a non-empty name or key")
        names = _asset_names(league)
        canonical = names.get(val.strip().lower())
        if canonical is not None:
            val = canonical
        elif not any(
            a.key == val for t in league.teams.values() for a in team_assets(league, t).values()
        ):
            raise ValueError(f"what.asset={val!r} matches no rostered asset name or key")
    else:
        raise ValueError(f"unknown what kind {kind!r}")
    return Constraint(
        who=who, side=side, what=(kind, val), with_=with_, mode=mode,
        source="query", origin="ad-hoc query constraint",
    )


def compile_constraints(
    league: md.LeagueState,
    intel: Sequence[Mapping] = (),
    query: Sequence[Mapping] = (),
    *,
    use_posture: bool = True,
    use_intel: bool = True,
) -> tuple[list[Constraint], list[dict]]:
    """The §4 compiler: all three sources under STRICT precedence — later
    source wins PER TEAM (keyed on `who`; wildcard `*` constraints are
    additive, never overriding and never overridden). A team named by any
    query constraint sheds its intel AND posture constraints; a team named by
    any intel constraint sheds its posture default (§11.12(f): posture
    defaults act exactly like v3.3 posture_allows when no later source names
    the team). Returns (constraints, ignored_intel)."""
    posture_cs = posture_constraints(league) if use_posture else []
    intel_cs, ignored = compile_intel(league, intel) if use_intel else ([], [])
    query_cs = [query_constraint(league, d) for d in query]
    q_named = {c.who for c in query_cs if c.who != "*"}
    i_named = {c.who for c in intel_cs if c.who != "*"}
    kept = [c for c in posture_cs if c.who not in q_named and c.who not in i_named]
    kept += [c for c in intel_cs if c.who == "*" or c.who not in q_named]
    kept += query_cs
    return kept, ignored
