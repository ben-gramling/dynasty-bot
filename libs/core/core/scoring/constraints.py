"""§4 v8 targeting & market constraints — ONE machine-executable vocabulary.

Every targeting fact is a CONSTRAINT the spread finder (§4a) and the v8 hedge
DB apply:

    constraint = { who: <username> | "me" | "*",
                   side: "receives" | "sends",
                   what: OBJECT (below),
                   with: <username> | null,   # optional: only vs this counterparty
                   mode: "require" | "exclude" | "prefer" }

OBJECT — the what-grammar. Dict forms (ad-hoc queries) and the normalized
internal tuples they compile to:

    {"class": "pick"|"player"}                       ("class", c)
    {"pos": "QB"|"RB"|"WR"|"TE"}                     ("pos", P)
    {"asset": <name-or-key>}                         ("asset", canonical)
    {"class": "pick", "year": int?, "round": int?}   ("pick", (year|None, round|None))
        # SCOPED pick class (v8) — a query atom must carry year and/or round
        # (both absent is the bare class above); intel folding may produce the
        # fully-unscoped ("pick", (None, None)) containment atom.
    {"any": [atom, ...]}                             ("any", (atom, ...))
        # any-of (v8): atoms are pos / asset / scoped-pick dicts — no nested
        # any, no bare class atoms in query dicts. Intel folding may place an
        # internal ("class", "player") atom in an any; like EVERY any-atom it
        # is evaluated by containment.

Text form (the CLI OBJECT grammar — also the intel-subject grammar): an asset
name, a pick/player class keyword, a position keyword or a `pos:RB` token, a
scoped pick class — `picks` scoped by a 4-digit year and/or a round token
`R1`/`R2`/... in ANY order ("2027 picks", "R1 picks", "2027 R1 picks") — or
pipe-separated alternatives of the above ("Mike Evans|pos:RB|2027 R1 picks")
compiling to any-of. A bare class word inside a pipe list normalizes to its
containment atom ("picks" → unscoped pick atom; "players" → player-class
containment atom).

Asset-name resolution (v8, everywhere an OBJECT/subject names an asset): exact
case-insensitive name match first, else UNIQUE case-insensitive substring
against the same rostered-asset universe as before ("Kenneth Walker" resolves
to Kenneth Walker III); query dicts additionally match asset KEYS exactly.
Ambiguity is a ValueError listing the candidates for query constraints and an
ignored-with-reason report (candidates included) for intel subjects — never a
guess. The resolved canonical name is stored in `what`.

Semantics are PER LEG: `who receives what` constrains the package flowing TO
`who` on any leg they are party to; `who = "*"` means every counterparty; `me`
is my own side. `require` — every leg involving `who` must match (hard).
`exclude` — no leg may match (hard). `prefer` — matching legs are tagged ★
(soft; never reorders slider math).

Matching is conservative and asymmetric by design:

- require {class: c} means the package is MAJORITY class c (offer_shape) —
  exactly v3.3's posture_allows behavior, which the posture defaults must
  reproduce when nothing overrides them (§11.12(f)).
- require on a SCOPED pick atom is CONTAINMENT — the package holds ≥1 pick
  matching the year/round scope. THE DISTINCTION (v8): bare {class: "pick"}
  require keeps the pinned MAJORITY semantics (v3.3 posture parity); adding a
  year and/or round scope switches require to containment, because a scoped
  pick is a targeting fact about specific picks, not about the package shape.
- require {pos}/{asset} means the package CONTAINS such an asset.
- require {any: [...]} means the package matches ≥1 atom, containment for
  every atom kind.
- exclude means the package contains NO such asset (any-containment — the
  stronger, safer reading for every `what` shape; for any-of: matching ANY
  atom excludes).
- prefer means the package contains such an asset (majority for bare {class};
  ≥1 atom containment for any-of).

Three sources, strict precedence (§4 — later source wins PER (team, side)
since v8; wildcard constraints are additive and never override or get
overridden):

1. Posture defaults (auto-compiled): BUYER → require receives {class: player};
   SELLER → require receives {class: pick}; NEUTRAL → no constraint.
2. Market intel (the `market-intel` Mongo collection; docs carry kind
   WANT/DONT_WANT/OFFERED/REJECTED/NOTE/KEEPS/SHOPPING, team, subject text,
   active flag): WANT → require on their receive side; DONT_WANT → exclude on
   their receive side; OFFERED(asset) → prefer on MY receive side vs that
   team; REJECTED → exclude of that exact shape; KEEPS → hard EXCLUDE on the
   team's SEND side (v8: "not willing to trade away X"); SHOPPING → soft
   PREFER on the team's send side (v8: "looking to move X"); NOTE → never
   compiled. Subjects parse with the full OBJECT grammar above; anything
   unparseable compiles to NO constraint and is reported back as such, never
   guessed. Multiple active WANT docs for the SAME team compile into ONE
   require whose what is the any-of of their subjects' atoms (either
   satisfies) — never a conjunctive stack (v8); multiple KEEPS fold the same
   way (cosmetic: an exclude-any is identical to separate excludes).
3. Ad-hoc query constraints (per §4a call) — override intel/posture for the
   exact (team, side) pairs they name (v8: a query about what a team RECEIVES
   no longer sheds that team's send-side intel, and vice versa); malformed
   query constraints raise (the caller typed them).

`compile_constraints` returns a CompileResult — a (constraints, ignored)
2-tuple exactly as before (existing callers unpack it unchanged) that ALSO
carries `.shed`: every posture/intel constraint dropped by precedence, as
[{"constraint": <dict>, "why": <str>}], so the board can display silent
replacements (v8).

Pure functions over LeagueState + plain dicts; no I/O, no Mongo — the caller
fetches `market-intel` docs and hands them in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from core.scoring import model as md
from core.scoring import posture as ps
from core.scoring.trades import Package, offer_shape, team_assets

REQUIRE, EXCLUDE, PREFER = "require", "exclude", "prefer"
MODES = (REQUIRE, EXCLUDE, PREFER)
SIDES = ("receives", "sends")
POSITIONS = ("QB", "RB", "WR", "TE")
INTEL_KINDS = ("WANT", "DONT_WANT", "OFFERED", "REJECTED", "NOTE", "KEEPS", "SHOPPING")

# intel kinds that need a named team (a "*" KEEPS/SHOPPING/WANT is meaningless)
_NAMED_TEAM_KINDS = ("WANT", "OFFERED", "REJECTED", "KEEPS", "SHOPPING")

# v8 §4: intel kinds folded per team into ONE constraint — kind → (mode, side).
# WANT folding is the required OR semantics ("either satisfies"); KEEPS folding
# is cosmetic (exclude-any ≡ separate excludes) but keeps the echo compact.
_FOLDED_KINDS = {"WANT": (REQUIRE, "receives"), "KEEPS": (EXCLUDE, "sends")}


@dataclass(frozen=True, slots=True)
class Constraint:
    """One compiled §4 constraint. `what` is a normalized tuple — ("class", c),
    ("pos", P), ("asset", name-or-key), ("pick", (year|None, round|None)) for
    scoped pick classes, or ("any", (atom, ...)) — see the module docstring.
    For parsed intel the asset value is the canonical rostered name; ad-hoc
    queries may carry a raw name or key (matched against both)."""

    who: str  # username | "me" | "*"
    side: str  # "receives" | "sends"
    what: tuple[str, Any]
    with_: str | None
    mode: str
    source: str  # "posture" | "intel" | "query"
    origin: str  # human-readable provenance

    def to_dict(self) -> dict:
        return {
            "who": self.who,
            "side": self.side,
            "what": _what_dict(self.what),
            "with": self.with_,
            "mode": self.mode,
            "source": self.source,
            "origin": self.origin,
        }


def _what_dict(what: tuple[str, Any]) -> dict:
    """Serialize a normalized what-tuple back to the OBJECT dict form."""
    kind, val = what
    if kind == "any":
        return {"any": [_what_dict(a) for a in val]}
    if kind == "pick":
        year, rnd = val
        d: dict = {"class": "pick"}
        if year is not None:
            d["year"] = year
        if rnd is not None:
            d["round"] = rnd
        return d
    return {kind: val}


# ------------------------------------------------------------- what-matching


def _contains(pkg: Package, what: tuple[str, Any]) -> bool:
    """Any-containment: does the package hold an asset matching `what`?
    Asset refs match key exactly or name case-insensitively; scoped pick atoms
    match the pick's year/round (absent scope = any); any-of matches when ANY
    atom is contained."""
    kind, val = what
    if kind == "any":
        return any(_contains(pkg, atom) for atom in val)
    if kind == "class":
        return any(a.kind == val for a in pkg.assets)
    if kind == "pos":
        return any(a.kind == "player" and a.pos == val for a in pkg.assets)
    if kind == "pick":
        year, rnd = val
        return any(
            a.kind == "pick"
            and (year is None or a.pick.year == year)
            and (rnd is None or a.pick.round == rnd)
            for a in pkg.assets
        )
    low = val.lower()
    return any(a.key == val or a.name.lower() == low for a in pkg.assets)


def _satisfies_require(pkg: Package, what: tuple[str, Any]) -> bool:
    """require-matching: bare {class} is MAJORITY (offer_shape — §11.12(f)
    posture parity); {pos}/{asset}, SCOPED pick atoms (v8 — the deliberate
    majority-vs-containment distinction, see module docstring) and any-of
    (≥1 atom) are containment."""
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

_POS_TOKEN = re.compile(r"pos:([a-z]+)")
_YEAR_TOKEN = re.compile(r"\d{4}")
_ROUND_TOKEN = re.compile(r"r([1-9]\d*)")


def _asset_names(league: md.LeagueState) -> dict[str, str]:
    """lowercased rostered asset name -> canonical name (players, taxi, picks
    of every team). Conservative universe: only assets that can actually move."""
    out: dict[str, str] = {}
    for t in league.teams.values():
        for name in team_assets(league, t):
            out[name.lower()] = name
    return out


def _resolve_asset(league: md.LeagueState, text: str, *, keys: bool = False) -> str:
    """v8 asset-name resolution: exact case-insensitive name, else (query dicts
    only) exact asset key, else UNIQUE case-insensitive substring. Ambiguity or
    no match raise ValueError — candidates listed, never guessed."""
    names = _asset_names(league)
    low = " ".join(text.strip().lower().split())
    canonical = names.get(low)
    if canonical is not None:
        return canonical
    if keys and any(
        a.key == text for t in league.teams.values() for a in team_assets(league, t).values()
    ):
        return text
    hits = sorted({canon for k, canon in names.items() if low and low in k})
    if len(hits) == 1:
        return hits[0]
    if hits:
        raise ValueError(
            f"asset {text!r} is ambiguous — candidates: {', '.join(hits)} — "
            "name more of it; never guessed (§4)"
        )
    raise ValueError(f"asset {text!r} matches no rostered asset name or key")


def _scoped_pick(s: str) -> tuple[str, tuple[int | None, int | None]] | None:
    """v8 scoped pick class grammar on a lowercased string: `picks` scoped by
    a 4-digit year and/or a round token `R<n>` in any order. Returns the
    ("pick", (year, round)) atom, or None when `s` is not that shape."""
    year: int | None = None
    rnd: int | None = None
    rest: list[str] = []
    for tok in s.split():
        if _YEAR_TOKEN.fullmatch(tok):
            if year is not None:
                return None
            year = int(tok)
        elif m := _ROUND_TOKEN.fullmatch(tok):
            if rnd is not None:
                return None
            rnd = int(m.group(1))
        else:
            rest.append(tok)
    if year is None and rnd is None:
        return None  # bare class words are handled (majority) upstream
    if _CLASS_WORDS.get(" ".join(rest)) != "pick":
        return None
    return ("pick", (year, rnd))


def _parse_atom(
    league: md.LeagueState, text: str, *, bare_class: bool
) -> tuple[str, Any]:
    """One OBJECT alternative → a normalized atom. Raises ValueError (with
    candidates on ambiguity) — callers decide whether that surfaces as an
    error (query) or an ignored-with-reason report (intel). `bare_class=False`
    (inside an any-of) normalizes class words to containment atoms."""
    s = " ".join(str(text).strip().split())
    if not s:
        raise ValueError("empty OBJECT")
    low = s.lower()
    names = _asset_names(league)
    canonical = names.get(low)
    if canonical is not None:
        return ("asset", canonical)
    for art in _ARTICLES:
        if low.startswith(art):
            low = low[len(art):]
            break
    if low in _CLASS_WORDS:
        cls = _CLASS_WORDS[low]
        if bare_class:
            return ("class", cls)
        # inside an any-of every atom is containment: "picks" → the unscoped
        # pick atom; "players" → an internal player-class containment atom
        return ("pick", (None, None)) if cls == "pick" else ("class", "player")
    if low in _POS_WORDS:
        return ("pos", _POS_WORDS[low])
    if m := _POS_TOKEN.fullmatch(low):
        p = m.group(1).upper()
        if p not in POSITIONS:
            raise ValueError(f"pos:{m.group(1)} must be one of {POSITIONS}")
        return ("pos", p)
    scoped = _scoped_pick(low)
    if scoped is not None:
        return scoped
    # v8: substring resolution LAST — it never shadows a class/pos keyword or
    # the scoped-pick grammar
    resolved = _resolve_asset(league, s)  # raises with candidates / no-match
    return ("asset", resolved)


def _parse_object(
    league: md.LeagueState, text: str, *, bare_class: bool = True
) -> tuple[str, Any]:
    """The full v8 OBJECT grammar: pipe-separated alternatives → any-of (each
    alternative independently parsed; a single distinct atom collapses); no
    pipe → one atom. Raises ValueError, never guesses."""
    if not isinstance(text, str):
        raise ValueError("subject must be text")
    if "|" in text:
        parts = [p.strip() for p in text.split("|")]
        if any(not p for p in parts):
            raise ValueError(f"empty alternative in {text!r}")
        atoms: list[tuple[str, Any]] = []
        for p in parts:
            a = _parse_atom(league, p, bare_class=False)
            if a not in atoms:
                atoms.append(a)
        return atoms[0] if len(atoms) == 1 else ("any", tuple(atoms))
    return _parse_atom(league, text, bare_class=bare_class)


def parse_subject(league: md.LeagueState, text: str) -> tuple[str, Any] | None:
    """Conservative §4 subject parser over the full v8 OBJECT grammar: asset
    names (exact, else unique substring), pick/player class keywords, position
    keywords / `pos:RB`, scoped pick classes ("2027 R1 picks"), pipe-separated
    any-of. Anything else → None (reported, never guessed)."""
    if not isinstance(text, str):
        return None
    try:
        return _parse_object(league, text)
    except ValueError:
        return None


def _atoms_of(what: tuple[str, Any]) -> list[tuple[str, Any]]:
    """Flatten a parsed what into its any-of atoms (v8 WANT/KEEPS folding).
    A bare pick class folds as the unscoped pick containment atom; a bare
    player class folds as the internal player-class containment atom."""
    if what[0] == "any":
        return list(what[1])
    if what == ("class", "pick"):
        return [("pick", (None, None))]
    return [what]


def _fold_group(
    kind: str, team: str, group: list[tuple[tuple[str, Any], str]]
) -> tuple[tuple[str, Any], str]:
    """v8 §4: fold one team's WANT (or KEEPS) docs into ONE what + origin.
    A single doc — or several with the identical subject shape — keeps its
    what verbatim (bare class stays MAJORITY); distinct shapes become the
    any-of of their atoms (either satisfies)."""
    if len(group) == 1:
        what, subject = group[0]
        return what, f"intel {kind}: {team} {subject!r}"
    whats: list[tuple[str, Any]] = []
    for w, _ in group:
        if w not in whats:
            whats.append(w)
    origin = f"intel {kind}: {team} " + " | ".join(f"{s!r}" for _, s in group)
    if len(whats) == 1:
        return whats[0], origin
    atoms: list[tuple[str, Any]] = []
    for w in whats:
        for a in _atoms_of(w):
            if a not in atoms:
                atoms.append(a)
    return ("any", tuple(atoms)), origin


def compile_intel(
    league: md.LeagueState, docs: Sequence[Mapping]
) -> tuple[list[Constraint], list[dict]]:
    """§4 source 2 — market-intel docs (kind, team, subject, active) compiled
    to constraints. Returns (constraints, ignored) where `ignored` reports
    every ACTIVE doc that compiled to nothing and why — unparseable or
    ambiguous subjects are never guessed at (§4; ambiguity reasons list the
    candidates); inactive docs are revoked and silently skipped. v8: multiple
    WANT docs for one team fold into ONE any-of require (either satisfies),
    KEEPS docs fold identically (cosmetic)."""
    out: list[Constraint] = []
    ignored: list[dict] = []

    def skip(doc: Mapping, reason: str) -> None:
        ignored.append({"doc": dict(doc), "reason": reason})

    parsed: list[tuple[str, str, tuple[str, Any], str]] = []  # kind, team, what, subject
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
        if kind in _NAMED_TEAM_KINDS and team == "*":
            skip(doc, f"{kind} needs a named team")
            continue
        try:
            what = _parse_object(league, subject)
        except ValueError as exc:
            skip(doc, f"subject {subject!r}: {exc} — no constraint compiled (§4)")
            continue
        parsed.append((kind, team, what, subject))

    folded: set[tuple[str, str]] = set()
    for kind, team, what, subject in parsed:
        if kind in _FOLDED_KINDS:
            if (kind, team) in folded:
                continue  # already folded into the first occurrence
            folded.add((kind, team))
            group = [(w, s) for k2, t2, w, s in parsed if (k2, t2) == (kind, team)]
            what, origin = _fold_group(kind, team, group)
            mode, side = _FOLDED_KINDS[kind]
            out.append(Constraint(team, side, what, None, mode, "intel", origin))
            continue
        origin = f"intel {kind}: {team} {subject!r}"
        if kind == "DONT_WANT":
            out.append(Constraint(team, "receives", what, None, EXCLUDE, "intel", origin))
        elif kind == "REJECTED":
            # exclude of that exact shape: they turned this down on their
            # receive side — never offer it again
            out.append(Constraint(team, "receives", what, None, EXCLUDE, "intel", origin))
        elif kind == "SHOPPING":
            # v8: soft prefer on the team's SEND side — they want to move it
            out.append(Constraint(team, "sends", what, None, PREFER, "intel", origin))
        else:  # OFFERED — prefer on MY receive side vs that team
            out.append(Constraint("me", "receives", what, team, PREFER, "intel", origin))
    return out, ignored


def _validate_what_dict(
    league: md.LeagueState, m: Mapping, *, in_any: bool = False
) -> tuple[str, Any]:
    """Validate one query OBJECT dict → normalized what-tuple. Malformed input
    raises ValueError. Inside an any-of (`in_any`): no nested any, no bare
    class atoms — pos/asset/scoped-pick only (v8)."""
    if not isinstance(m, Mapping) or not m:
        raise ValueError(
            "constraint what must be one of {class}/{pos}/{asset}/{any} "
            "(a pick class may carry year/round)"
        )
    keys = set(m)
    if "any" in keys:
        if in_any:
            raise ValueError("any-of atoms cannot nest another any")
        if keys != {"any"}:
            raise ValueError("what.any must be the only key")
        items = m["any"]
        if isinstance(items, (str, bytes)) or not isinstance(items, Sequence) or not items:
            raise ValueError("what.any must be a non-empty list of atoms")
        atoms: list[tuple[str, Any]] = []
        for it in items:
            a = _validate_what_dict(league, it, in_any=True)
            if a not in atoms:
                atoms.append(a)
        return atoms[0] if len(atoms) == 1 else ("any", tuple(atoms))
    if "class" in keys:
        val = m["class"]
        if val not in ("pick", "player"):
            raise ValueError(f"what.class={val!r} must be 'pick' or 'player'")
        extra = keys - {"class", "year", "round"}
        if extra:
            raise ValueError(f"unexpected what keys {sorted(extra)}")
        year = m.get("year")
        rnd = m.get("round")
        if val == "player" and (year is not None or rnd is not None):
            raise ValueError("year/round scoping applies to the pick class only")
        if year is not None and (
            isinstance(year, bool) or not isinstance(year, int) or not 1000 <= year <= 9999
        ):
            raise ValueError(f"what.year={year!r} must be a 4-digit year")
        if rnd is not None and (
            isinstance(rnd, bool) or not isinstance(rnd, int) or rnd < 1
        ):
            raise ValueError(f"what.round={rnd!r} must be a positive round number")
        if year is None and rnd is None:
            if in_any:
                raise ValueError(
                    "bare class atoms are not allowed inside any — use pos/asset/"
                    "scoped-pick atoms (a pick class needs year and/or round)"
                )
            return ("class", val)
        return ("pick", (year, rnd))
    if len(keys) != 1:
        raise ValueError(
            "constraint what must be exactly one of {class}/{pos}/{asset}/{any} "
            "(a pick class may carry year/round)"
        )
    ((kind, val),) = m.items()
    if kind == "pos":
        if val not in POSITIONS:
            raise ValueError(f"what.pos={val!r} must be one of {POSITIONS}")
        return ("pos", val)
    if kind == "asset":
        if not isinstance(val, str) or not val.strip():
            raise ValueError("what.asset must be a non-empty name or key")
        return ("asset", _resolve_asset(league, val, keys=True))
    raise ValueError(f"unknown what kind {kind!r}")


def query_constraint(league: md.LeagueState, d: Mapping) -> Constraint:
    """§4 source 3 — validate one ad-hoc constraint dict. Malformed input
    raises ValueError: the user typed it, so it is corrected, never guessed.
    `what` may be an OBJECT dict or (v8) an OBJECT grammar string —
    "Mike Evans|pos:RB|2027 R1 picks"."""
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
    if isinstance(what_d, str):
        what = _parse_object(league, what_d)
    else:
        what = _validate_what_dict(league, what_d)
    return Constraint(
        who=who, side=side, what=what, with_=with_, mode=mode,
        source="query", origin="ad-hoc query constraint",
    )


class _ConstraintList(list):
    """The compiled constraint list, carrying the same `.shed` as the
    CompileResult it rides in — so a caller that unpacked the historical
    2-tuple can still reach the shed list off its first element."""

    shed: list[dict]


class CompileResult(tuple):
    """`compile_constraints` result: unpacks as the historical (constraints,
    ignored) 2-tuple — the finder's `compiled, ignored = ...` works untouched —
    while ALSO exposing `.shed` (v8): every posture/intel constraint dropped by
    (team, side) precedence, as [{"constraint": <dict>, "why": <str>}]. The
    constraints element mirrors `.shed` too (see _ConstraintList)."""

    shed: list[dict]

    def __new__(cls, constraints: list[Constraint], ignored: list[dict], shed: list[dict]):
        cl = _ConstraintList(constraints)
        cl.shed = shed
        self = tuple.__new__(cls, (cl, ignored))
        self.shed = shed
        return self

    @property
    def constraints(self) -> list[Constraint]:
        return self[0]

    @property
    def ignored(self) -> list[dict]:
        return self[1]


def compile_constraints(
    league: md.LeagueState,
    intel: Sequence[Mapping] = (),
    query: Sequence[Mapping] = (),
    *,
    use_posture: bool = True,
    use_intel: bool = True,
) -> CompileResult:
    """The §4 compiler: all three sources under STRICT precedence — later
    source wins PER (team, side) (v8; wildcard `*` constraints are additive,
    never overriding and never overridden). A (team, side) named by any query
    constraint sheds that team's intel AND posture constraints ON THAT SIDE
    ONLY — a query about what a team receives leaves its send-side intel
    (KEEPS/SHOPPING) standing, and vice versa; a (team, side) named by any
    intel constraint sheds the matching posture default (§11.12(f): posture
    defaults act exactly like v3.3 posture_allows when no later source names
    the team's receive side). Returns a CompileResult — the (constraints,
    ignored_intel) 2-tuple of old, carrying the dropped constraints in `.shed`
    so silent replacements stay visible on the board."""
    posture_cs = posture_constraints(league) if use_posture else []
    intel_cs, ignored = compile_intel(league, intel) if use_intel else ([], [])
    query_cs = [query_constraint(league, d) for d in query]
    q_named = {(c.who, c.side) for c in query_cs if c.who != "*"}
    i_named = {(c.who, c.side) for c in intel_cs if c.who != "*"}
    shed: list[dict] = []
    kept: list[Constraint] = []
    for c in posture_cs:
        key = (c.who, c.side)
        if key in q_named:
            shed.append({
                "constraint": c.to_dict(),
                "why": f"query constraint on ({c.who}, {c.side}) overrides the posture default",
            })
        elif key in i_named:
            shed.append({
                "constraint": c.to_dict(),
                "why": f"intel on ({c.who}, {c.side}) overrides the posture default",
            })
        else:
            kept.append(c)
    for c in intel_cs:
        if c.who != "*" and (c.who, c.side) in q_named:
            shed.append({
                "constraint": c.to_dict(),
                "why": f"query constraint on ({c.who}, {c.side}) overrides this intel",
            })
        else:
            kept.append(c)
    kept += query_cs
    return CompileResult(kept, ignored, shed)
