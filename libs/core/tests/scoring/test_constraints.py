"""§4 the constraint vocabulary: compilation of the three sources under
strict precedence, the pinned §4 example compilations (§11.12(b)'s
shapes), conservative subject parsing, predicate semantics, and the
§11.12(f) posture-parity pin.

The five user examples ("ronak wants draft picks", "joey wants a running
back", "nobody wants stefon diggs", "josh b wants joe burrow", "colin is
willing to trade away treveon henderson") are pinned VERBATIM — the committed
fixtures really do roster Stefon Diggs and Joe Burrow on my team and TreVeyon
Henderson on cmgaither43's, and joeydavis299 really does roster RBs.

v8 (docs/hedge-db-v8-spec.md §4) extends the vocabulary — any-of atoms,
scoped pick classes, substring asset resolution, KEEPS/SHOPPING send-side
intel, multi-WANT→any-of folding, (team, side) precedence with a visible
shed list — tested from `test_object_grammar_scoped_picks` down."""

from __future__ import annotations

import pytest

from core.scoring import constraints as cn
from core.scoring import trades as tr

# the user's five §4 examples as market-intel docs (the skill's protocol:
# kind, team, subject, active)
INTEL = [
    {"kind": "WANT", "team": "ronakpatel32", "subject": "draft picks", "active": True},
    {"kind": "WANT", "team": "joeydavis299", "subject": "a running back", "active": True},
    {"kind": "DONT_WANT", "team": "*", "subject": "Stefon Diggs", "active": True},
    {"kind": "WANT", "team": "josbaski", "subject": "Joe Burrow", "active": True},
    {"kind": "OFFERED", "team": "cmgaither43", "subject": "TreVeyon Henderson", "active": True},
]


def test_section4_example_compilation_pinned(league):
    """§11.12(b)/§12(b): the spec's own example compilations, exactly."""
    compiled, ignored = cn.compile_intel(league, INTEL)
    assert ignored == []
    got = [(c.who, c.side, c.what, c.with_, c.mode) for c in compiled]
    assert got == [
        ("ronakpatel32", "receives", ("class", "pick"), None, "require"),
        ("joeydavis299", "receives", ("pos", "RB"), None, "require"),
        ("*", "receives", ("asset", "Stefon Diggs"), None, "exclude"),
        ("josbaski", "receives", ("asset", "Joe Burrow"), None, "require"),
        ("me", "receives", ("asset", "TreVeyon Henderson"), "cmgaither43", "prefer"),
    ]
    assert all(c.source == "intel" for c in compiled)


def test_subject_parsing_is_conservative(league):
    """§4: exact rostered-asset names, pick/player class keywords, and position
    keywords parse; everything else compiles to NO constraint — never guessed."""
    assert cn.parse_subject(league, "Joe Burrow") == ("asset", "Joe Burrow")
    assert cn.parse_subject(league, "  joe  burrow ") == ("asset", "Joe Burrow")
    assert cn.parse_subject(league, "draft picks") == ("class", "pick")
    assert cn.parse_subject(league, "picks") == ("class", "pick")
    assert cn.parse_subject(league, "veteran players") == ("class", "player")
    assert cn.parse_subject(league, "a running back") == ("pos", "RB")
    assert cn.parse_subject(league, "RB") == ("pos", "RB")
    assert cn.parse_subject(league, "a quarterback") == ("pos", "QB")
    assert cn.parse_subject(league, "tight ends") == ("pos", "TE")
    for junk in ("an elite young cornerstone", "Tom Brady", "", None, "win now help"):
        assert cn.parse_subject(league, junk) is None, junk
    # unparseable subjects on ACTIVE docs are reported back, never guessed
    docs = [{"kind": "WANT", "team": "vishan", "subject": "win now help", "active": True}]
    compiled, ignored = cn.compile_intel(league, docs)
    assert compiled == [] and len(ignored) == 1
    assert "never" in ignored[0]["reason"] or "no constraint" in ignored[0]["reason"]
    # inactive docs are revoked: silently skipped, not reported
    docs[0]["active"] = False
    compiled, ignored = cn.compile_intel(league, docs)
    assert compiled == [] and ignored == []
    # NOTE docs never compile and say so
    notes = [{"kind": "NOTE", "team": "millj", "subject": "says he is rebuilding"}]
    compiled, ignored = cn.compile_intel(league, notes)
    assert compiled == [] and "never compiled" in ignored[0]["reason"]


def test_precedence_later_source_wins_per_team(league):
    """§4 strict precedence: intel drops the posture default of exactly the
    team it names; a query constraint drops both for its team; wildcard
    constraints are additive and never override. On the fixture, ronakpatel32
    is the BUYER and millj the SELLER — the only posture defaults.

    v8 refines the precedence key to (team, side) — every constraint in this
    test sits on the receives side, so the pinned behavior is unchanged; the
    side split is pinned in test_precedence_keyed_on_team_and_side."""
    base, _ = cn.compile_constraints(league)
    assert [(c.who, c.what, c.source) for c in base] == [
        ("millj", ("class", "pick"), "posture"),
        ("ronakpatel32", ("class", "player"), "posture"),
    ]
    # intel names ronak: his posture default is gone, millj's survives, the
    # wildcard Diggs exclusion rides alongside
    with_intel, _ = cn.compile_constraints(league, intel=INTEL)
    srcs = {(c.who, c.source) for c in with_intel}
    assert ("ronakpatel32", "posture") not in srcs
    assert ("ronakpatel32", "intel") in srcs
    assert ("millj", "posture") in srcs
    assert ("*", "intel") in srcs
    # a query naming ronak drops his intel constraint too; millj still posture
    q = [{"who": "ronakpatel32", "side": "receives", "what": {"pos": "WR"}, "mode": "require"}]
    with_q, _ = cn.compile_constraints(league, intel=INTEL, query=q)
    ron = [c for c in with_q if c.who == "ronakpatel32"]
    assert [(c.what, c.mode, c.source) for c in ron] == [(("pos", "WR"), "require", "query")]
    assert ("millj", "posture") in {(c.who, c.source) for c in with_q}
    assert any(c.who == "*" and c.source == "intel" for c in with_q)
    # toggles: use_posture/use_intel off removes those sources entirely
    none_at_all, ig = cn.compile_constraints(
        league, intel=INTEL, use_posture=False, use_intel=False
    )
    assert none_at_all == [] and ig == []


def test_posture_defaults_reproduce_posture_allows_11_12f(league):
    """§11.12(f): with nothing overriding, the compiled posture defaults allow
    a give-package to a counterparty EXACTLY when v3.3's posture_allows lets
    that shape through — over every counterparty and a systematic sample of
    my real give-list packages (players-majority, picks-majority, and mixed
    shapes all occur in the sample)."""
    pcs = cn.posture_constraints(league)
    me_t = league.teams[league.me]
    pkgs = tr._packages(league, tr.give_list(league, me_t))[::37]
    shapes = {tr.offer_shape(p) for p in pkgs}
    assert shapes == {"players", "picks", "mixed"}  # all shapes exercised
    for opp in league.opponents:
        label = league.postures[opp]["label"]
        for p in pkgs:
            assert cn.package_allowed(pcs, opp, "give", p) == tr.posture_allows(
                label, tr.offer_shape(p)
            ), (opp, label, p.keys)
    # and the get side is never constrained by posture defaults (§4: they
    # compile on the receive side only)
    for opp in league.opponents:
        for p in tr._packages(league, tr.give_list(league, league.teams[opp]))[::197]:
            assert cn.package_allowed(pcs, opp, "get", p)


def test_predicate_semantics(league):
    """require {class} is MAJORITY, require {pos}/{asset} is containment,
    exclude is any-containment, `with` scopes to one counterparty, and
    prefer tags without excluding."""
    mine = tr.team_assets(league, league.teams[league.me])
    colin = tr.team_assets(league, league.teams["cmgaither43"])
    burrow_pick = tr.package_of(league, [mine["Joe Burrow"], mine["2027 R2 (own)"]])
    two_picks_burrow = tr.package_of(
        league, [mine["Joe Burrow"], mine["2027 R2 (own)"], mine["2028 R3 (own)"]]
    )
    diggs = tr.package_of(league, [mine["Stefon Diggs"]])
    compiled, _ = cn.compile_intel(league, INTEL)
    # require majority: a mixed 1-player/1-pick package is NOT picks-majority
    ron = [c for c in compiled if c.who == "ronakpatel32"]
    assert not cn.package_allowed(ron, "ronakpatel32", "give", burrow_pick)
    assert cn.package_allowed(ron, "ronakpatel32", "give", two_picks_burrow)
    # the same package is unconstrained toward a team the constraint not names
    assert cn.package_allowed(ron, "jaketoppen", "give", burrow_pick)
    # require containment: Burrow anywhere in the package satisfies josbaski
    jos = [c for c in compiled if c.who == "josbaski"]
    assert cn.package_allowed(jos, "josbaski", "give", burrow_pick)
    assert not cn.package_allowed(jos, "josbaski", "give", diggs)
    # exclude containment: Diggs poisons any package to ANY counterparty
    star = [c for c in compiled if c.who == "*"]
    for opp in ("jaketoppen", "ronakpatel32", "cmgaither43"):
        assert not cn.package_allowed(star, opp, "give", diggs)
        assert cn.package_allowed(star, opp, "give", burrow_pick)
    # prefer: tags the matching leg vs the named counterparty only, and only
    # on the preferred side; it never hard-filters
    hend = tr.package_of(league, [colin["TreVeyon Henderson"]])
    my_pick = tr.package_of(league, [mine["2027 R2 (own)"]])
    assert cn.leg_allowed(compiled, "cmgaither43", my_pick, hend)
    assert cn.leg_preferred(compiled, "cmgaither43", my_pick, hend) is True
    assert cn.leg_preferred(compiled, "cmgaither43", hend, my_pick) is False
    other = tr.package_of(league, [tr.team_assets(league, league.teams["jaketoppen"])["2028 R4 (own)"]])
    assert cn.leg_preferred(compiled, "jaketoppen", my_pick, other) is False


def test_query_constraint_validation(league):
    """§4 source 3: ad-hoc dicts are validated strictly — the user typed them,
    so malformed input raises instead of guessing."""
    ok = cn.query_constraint(
        league, {"who": "me", "side": "sends", "what": {"asset": "Joe Burrow"}, "mode": "exclude"}
    )
    assert (ok.who, ok.mode, ok.what) == ("me", "exclude", ("asset", "Joe Burrow"))
    ok2 = cn.query_constraint(
        league,
        {"who": "*", "side": "receives", "what": {"asset": "stefon diggs"}, "mode": "exclude"},
    )
    assert ok2.what == ("asset", "Stefon Diggs")  # canonicalized, case-insensitive
    for bad in [
        {"who": "nobody", "side": "receives", "what": {"pos": "RB"}, "mode": "require"},
        {"who": "millj", "side": "gets", "what": {"pos": "RB"}, "mode": "require"},
        {"who": "millj", "side": "receives", "what": {"pos": "K"}, "mode": "require"},
        {"who": "millj", "side": "receives", "what": {"class": "kicker"}, "mode": "require"},
        {"who": "millj", "side": "receives", "what": {"pos": "RB"}, "mode": "must"},
        {"who": "millj", "side": "receives", "what": {"pos": "RB", "class": "pick"}, "mode": "require"},
        {"who": "millj", "side": "receives", "what": {"asset": "Tom Brady"}, "mode": "require"},
        {"who": "millj", "side": "receives", "what": {"asset": "RB"}, "mode": "require", "with": "??"},
    ]:
        with pytest.raises(ValueError):
            cn.query_constraint(league, bad)


# --------------------------------------------------------------------- v8 §4


def _q(league, who, side, what, mode, **kw):
    d = {"who": who, "side": side, "what": what, "mode": mode}
    d.update(kw)
    return cn.query_constraint(league, d)


def test_object_grammar_scoped_picks(league):
    """v8 spec §4: OBJECT accepts `picks` scoped by a 4-digit year and/or a
    round token in ANY order; bare class words keep their pinned shapes."""
    assert cn.parse_subject(league, "2027 picks") == ("pick", (2027, None))
    assert cn.parse_subject(league, "R1 picks") == ("pick", (None, 1))
    assert cn.parse_subject(league, "2027 R1 picks") == ("pick", (2027, 1))
    assert cn.parse_subject(league, "r1 2027 picks") == ("pick", (2027, 1))
    assert cn.parse_subject(league, "2027 draft picks") == ("pick", (2027, None))
    assert cn.parse_subject(league, "some 2027 picks") == ("pick", (2027, None))
    # round tokens are open-ended grammar (R1/R2/... per the spec); a round no
    # league pick carries simply never matches — alphabet validation is the
    # hedge DB's job, not the grammar's
    assert cn.parse_subject(league, "R9 picks") == ("pick", (None, 9))
    # bare class words stay the pinned bare-class shapes (MAJORITY require)
    assert cn.parse_subject(league, "picks") == ("class", "pick")
    assert cn.parse_subject(league, "draft picks") == ("class", "pick")
    # not scoped-pick shapes: no picks word / duplicated scope tokens
    assert cn.parse_subject(league, "2027") is None
    assert cn.parse_subject(league, "2027 2028 picks") is None
    assert cn.parse_subject(league, "R1 R2 picks") is None


def test_scoped_pick_require_containment_vs_bare_majority(league):
    """v8 spec §4: a SCOPED pick require is CONTAINMENT (holds ≥1 matching
    pick), unlike the bare {class: pick} require which keeps its pinned
    MAJORITY (v3.3 posture-parity) semantics."""
    mine = tr.team_assets(league, league.teams[league.me])
    mixed = tr.package_of(league, [mine["Joe Burrow"], mine["2027 R2 (own)"]])
    bare = [_q(league, "millj", "receives", {"class": "pick"}, "require")]
    scoped = [_q(league, "millj", "receives", {"class": "pick", "year": 2027}, "require")]
    # the 1-player/1-pick mixed package is NOT picks-majority…
    assert not cn.package_allowed(bare, "millj", "give", mixed)
    # …but it CONTAINS a 2027 pick
    assert cn.package_allowed(scoped, "millj", "give", mixed)
    # scope really scopes: wrong year / wrong round fail, year+round combos work
    for what, ok in [
        ({"class": "pick", "year": 2028}, False),
        ({"class": "pick", "round": 2}, True),
        ({"class": "pick", "year": 2027, "round": 2}, True),
        ({"class": "pick", "year": 2027, "round": 4}, False),
    ]:
        c = [_q(league, "millj", "receives", what, "require")]
        assert cn.package_allowed(c, "millj", "give", mixed) is ok, what
    # current-year numbered picks carry year/round too
    current = tr.package_of(league, [mine["2026 1.01"]])
    c = [_q(league, "millj", "receives", {"class": "pick", "year": 2026, "round": 1}, "require")]
    assert cn.package_allowed(c, "millj", "give", current)


def test_scoped_pick_exclude_and_sends_side(league):
    """v8: scoped-pick exclude is containment on the named (team, side) —
    the spec's own example: 'Colin does not want to give up any 2027 picks'
    → exclude cmgaither43 sends 2027 picks bites HIS sent package only."""
    colin = tr.team_assets(league, league.teams["cmgaither43"])
    mine = tr.team_assets(league, league.teams[league.me])
    c = [_q(league, "cmgaither43", "sends", {"class": "pick", "year": 2027}, "exclude")]
    colin_2027 = tr.package_of(league, [colin["2027 R1 (own)"]])
    colin_2026 = tr.package_of(league, [colin["2026 1.04"]])
    my_2027 = tr.package_of(league, [mine["2027 R2 (own)"]])
    # colin's sent package (my "get") holding a 2027 pick is excluded
    assert not cn.package_allowed(c, "cmgaither43", "get", colin_2027)
    assert cn.package_allowed(c, "cmgaither43", "get", colin_2026)
    # MY give (what colin receives) is untouched by his sends-exclude
    assert cn.package_allowed(c, "cmgaither43", "give", my_2027)
    # and another counterparty's legs are unconstrained
    assert cn.package_allowed(c, "millj", "get", colin_2027)


def test_any_of_require_exclude_prefer(league):
    """v8 spec §4 any-of: require = matches ≥1 atom (containment per atom);
    exclude = matches ANY atom ⇒ excluded; prefer = matches ≥1 ⇒ ★."""
    mine = tr.team_assets(league, league.teams[league.me])
    what = {"any": [{"asset": "Mike Evans"}, {"pos": "TE"}, {"class": "pick", "year": 2027}]}
    evans = tr.package_of(league, [mine["Mike Evans"]])
    laporta = tr.package_of(league, [mine["Sam LaPorta"]])
    pick27 = tr.package_of(league, [mine["2027 R2 (own)"]])
    diggs = tr.package_of(league, [mine["Stefon Diggs"]])
    req = [_q(league, "millj", "receives", what, "require")]
    for pkg in (evans, laporta, pick27):
        assert cn.package_allowed(req, "millj", "give", pkg)
    assert not cn.package_allowed(req, "millj", "give", diggs)
    exc = [_q(league, "millj", "receives", what, "exclude")]
    assert cn.package_allowed(exc, "millj", "give", diggs)
    for pkg in (evans, laporta, pick27):
        assert not cn.package_allowed(exc, "millj", "give", pkg)
    pref = [_q(league, "millj", "receives", what, "prefer")]
    millj = tr.team_assets(league, league.teams["millj"])
    other = tr.package_of(league, [next(iter(millj.values()))])
    assert cn.leg_preferred(pref, "millj", laporta, other) is True
    assert cn.leg_preferred(pref, "millj", diggs, other) is False
    # prefer never hard-filters
    assert cn.package_allowed(pref, "millj", "give", diggs)


def test_pipe_grammar_subjects(league):
    """v8: pipe-separated alternatives compile to any-of; every alternative
    is independently parsed and one bad alternative poisons the subject
    (never guessed)."""
    assert cn.parse_subject(league, "Mike Evans|Travis Hunter") == (
        "any", (("asset", "Mike Evans"), ("asset", "Travis Hunter"))
    )
    assert cn.parse_subject(league, "Mike Evans|pos:RB|2027 R1 picks") == (
        "any", (("asset", "Mike Evans"), ("pos", "RB"), ("pick", (2027, 1)))
    )
    # bare class words inside a pipe list normalize to containment atoms
    assert cn.parse_subject(league, "picks|Mike Evans") == (
        "any", (("pick", (None, None)), ("asset", "Mike Evans"))
    )
    assert cn.parse_subject(league, "players|Mike Evans") == (
        "any", (("class", "player"), ("asset", "Mike Evans"))
    )
    # duplicates collapse; a single distinct atom is not wrapped
    assert cn.parse_subject(league, "Mike Evans|mike evans") == ("asset", "Mike Evans")
    # one unparseable / empty alternative poisons the whole subject
    assert cn.parse_subject(league, "Mike Evans|Tom Brady") is None
    assert cn.parse_subject(league, "Mike Evans||Travis Hunter") is None
    # the containment normalization really is containment: a mixed package
    # holds a player, so the players-alternative matches without majority
    mine = tr.team_assets(league, league.teams[league.me])
    mixed = tr.package_of(league, [mine["Joe Burrow"], mine["2027 R2 (own)"]])
    c = [_q(league, "millj", "receives", "players|Mike Evans", "require")]
    assert cn.package_allowed(c, "millj", "give", mixed)


def test_query_what_string_and_any_dict_validation(league):
    """v8: query `what` accepts the OBJECT grammar string; the {any: [...]}
    dict form is validated strictly — no nested any, no bare class atoms."""
    c = _q(league, "millj", "receives", "Mike Evans|Travis Hunter", "require")
    assert c.what == ("any", (("asset", "Mike Evans"), ("asset", "Travis Hunter")))
    c2 = _q(league, "millj", "receives", "2027 R1 picks", "require")
    assert c2.what == ("pick", (2027, 1))
    # single-atom any collapses
    c3 = _q(league, "millj", "receives", {"any": [{"pos": "RB"}, {"pos": "RB"}]}, "require")
    assert c3.what == ("pos", "RB")
    for bad in [
        {"any": [{"any": [{"pos": "RB"}]}]},          # nested any
        {"any": [{"class": "pick"}]},                  # bare class atom in any
        {"any": [{"class": "player"}]},                # bare class atom in any
        {"any": []},                                   # empty
        {"any": "Mike Evans"},                         # not a list of atoms
        {"any": [{"pos": "RB"}], "pos": "TE"},         # any not the only key
        {"class": "player", "year": 2027},             # scope on player class
        {"class": "pick", "year": 27},                 # not a 4-digit year
        {"class": "pick", "round": 0},                 # round < 1
        {"class": "pick", "year": 2027, "pos": "RB"},  # stray key
        {"year": 2027},                                # scope without class
    ]:
        with pytest.raises(ValueError):
            _q(league, "millj", "receives", bad, "require")
    with pytest.raises(ValueError):
        _q(league, "millj", "receives", "Mike Evans|Tom Brady", "require")


def test_substring_resolution(league):
    """v8 spec §4: asset resolution is exact case-insensitive name, else
    UNIQUE case-insensitive substring; ambiguity raises for queries (listing
    candidates) and is reported for intel — never guessed. The canonical name
    is stored in `what`."""
    assert cn.parse_subject(league, "Kenneth Walker") == ("asset", "Kenneth Walker III")
    c = _q(league, "millj", "receives", {"asset": "kenneth walker"}, "require")
    assert c.what == ("asset", "Kenneth Walker III")
    c2 = _q(league, "millj", "receives", "Kenneth Walker", "require")
    assert c2.what == ("asset", "Kenneth Walker III")
    # ambiguous substring: the fixture rosters five Smiths
    with pytest.raises(ValueError) as ei:
        _q(league, "millj", "receives", {"asset": "Smith"}, "require")
    for cand in ("Geno Smith", "DeVonta Smith"):
        assert cand in str(ei.value)
    assert cn.parse_subject(league, "Smith") is None
    # intel path: ignored with the candidate list in the reason, never guessed
    docs = [{"kind": "WANT", "team": "millj", "subject": "Smith", "active": True}]
    compiled, ignored = cn.compile_intel(league, docs)
    assert compiled == [] and len(ignored) == 1
    assert "Geno Smith" in ignored[0]["reason"]
    # unique-substring intel resolves to the canonical name
    docs = [{"kind": "WANT", "team": "millj", "subject": "Kenneth Walker", "active": True}]
    compiled, ignored = cn.compile_intel(league, docs)
    assert ignored == []
    assert compiled[0].what == ("asset", "Kenneth Walker III")


def test_keeps_and_shopping_compile(league):
    """v8 spec §4 send-side intel: KEEPS → hard EXCLUDE on (team, sends);
    SHOPPING → soft PREFER on (team, sends); both need a named team."""
    docs = [
        {"kind": "KEEPS", "team": "cmgaither43", "subject": "2027 picks", "active": True},
        {"kind": "SHOPPING", "team": "millj", "subject": "a running back", "active": True},
    ]
    compiled, ignored = cn.compile_intel(league, docs)
    assert ignored == []
    assert [(c.who, c.side, c.what, c.mode, c.source) for c in compiled] == [
        ("cmgaither43", "sends", ("pick", (2027, None)), "exclude", "intel"),
        ("millj", "sends", ("pos", "RB"), "prefer", "intel"),
    ]
    # KEEPS bites on colin's SENT package (my get side) only
    colin = tr.team_assets(league, league.teams["cmgaither43"])
    mine = tr.team_assets(league, league.teams[league.me])
    keeps = [compiled[0]]
    assert not cn.package_allowed(
        keeps, "cmgaither43", "get", tr.package_of(league, [colin["2027 R1 (own)"]])
    )
    assert cn.package_allowed(
        keeps, "cmgaither43", "get", tr.package_of(league, [colin["2028 R1 (own)"]])
    )
    assert cn.package_allowed(
        keeps, "cmgaither43", "give", tr.package_of(league, [mine["2027 R2 (own)"]])
    )
    # SHOPPING stars a leg where millj sends an RB, and never hard-filters
    millj = tr.team_assets(league, league.teams["millj"])
    rb = next(a for a in millj.values() if a.pos == "RB")
    not_rb = next(a for a in millj.values() if a.kind == "player" and a.pos not in (None, "RB"))
    my_pick = tr.package_of(league, [mine["2027 R2 (own)"]])
    shopping = [compiled[1]]
    assert cn.leg_preferred(shopping, "millj", my_pick, tr.package_of(league, [rb])) is True
    assert cn.leg_preferred(shopping, "millj", my_pick, tr.package_of(league, [not_rb])) is False
    assert cn.package_allowed(shopping, "millj", "get", tr.package_of(league, [not_rb]))
    # both kinds need a named team
    for kind in ("KEEPS", "SHOPPING"):
        compiled, ignored = cn.compile_intel(
            league, [{"kind": kind, "team": "*", "subject": "picks", "active": True}]
        )
        assert compiled == [] and "needs a named team" in ignored[0]["reason"]


def test_multi_want_folds_to_any_of(league):
    """v8 spec §4: multiple active WANT docs for the SAME team compile into
    ONE require whose what is the any-of of their subjects' atoms — either
    satisfies — instead of the old conjunctive stack."""
    docs = [
        {"kind": "WANT", "team": "cmgaither43", "subject": "a running back", "active": True},
        {"kind": "WANT", "team": "cmgaither43", "subject": "a tight end", "active": True},
        {"kind": "WANT", "team": "millj", "subject": "draft picks", "active": True},
    ]
    compiled, ignored = cn.compile_intel(league, docs)
    assert ignored == []
    assert [(c.who, c.side, c.what, c.mode) for c in compiled] == [
        ("cmgaither43", "receives", ("any", (("pos", "RB"), ("pos", "TE"))), "require"),
        # a lone WANT keeps its bare shape — MAJORITY for the class pin
        ("millj", "receives", ("class", "pick"), "require"),
    ]
    assert "'a running back'" in compiled[0].origin and "'a tight end'" in compiled[0].origin
    # either satisfies: RB-only OR TE-only pass, QB-only fails
    mine = tr.team_assets(league, league.teams[league.me])
    fold = [compiled[0]]
    rb = tr.package_of(league, [mine["Ashton Jeanty"]])
    te = tr.package_of(league, [mine["Sam LaPorta"]])
    qb = tr.package_of(league, [mine["Joe Burrow"]])
    assert cn.package_allowed(fold, "cmgaither43", "give", rb)
    assert cn.package_allowed(fold, "cmgaither43", "give", te)
    assert not cn.package_allowed(fold, "cmgaither43", "give", qb)
    # a bare pick-class WANT folds as the unscoped pick CONTAINMENT atom —
    # the only coherent OR reading ("either satisfies")
    docs2 = [
        {"kind": "WANT", "team": "cmgaither43", "subject": "a running back", "active": True},
        {"kind": "WANT", "team": "cmgaither43", "subject": "draft picks", "active": True},
    ]
    compiled2, _ = cn.compile_intel(league, docs2)
    assert len(compiled2) == 1
    assert compiled2[0].what == ("any", (("pos", "RB"), ("pick", (None, None))))
    mixed = tr.package_of(league, [mine["Joe Burrow"], mine["2027 R2 (own)"]])
    assert cn.package_allowed(compiled2, "cmgaither43", "give", mixed)  # contains a pick
    assert not cn.package_allowed(compiled2, "cmgaither43", "give", qb)
    # duplicate subject shapes collapse WITHOUT softening majority semantics
    docs3 = [
        {"kind": "WANT", "team": "cmgaither43", "subject": "draft picks", "active": True},
        {"kind": "WANT", "team": "cmgaither43", "subject": "picks", "active": True},
    ]
    compiled3, _ = cn.compile_intel(league, docs3)
    assert [c.what for c in compiled3] == [("class", "pick")]
    assert not cn.package_allowed(compiled3, "cmgaither43", "give", mixed)  # still majority
    # KEEPS folds the same way (cosmetic — exclude-any ≡ separate excludes)
    colin = tr.team_assets(league, league.teams["cmgaither43"])
    docs4 = [
        {"kind": "KEEPS", "team": "cmgaither43", "subject": "2027 picks", "active": True},
        {"kind": "KEEPS", "team": "cmgaither43", "subject": "Brock Bowers", "active": True},
    ]
    compiled4, _ = cn.compile_intel(league, docs4)
    assert [(c.side, c.what, c.mode) for c in compiled4] == [
        ("sends", ("any", (("pick", (2027, None)), ("asset", "Brock Bowers"))), "exclude")
    ]
    for name in ("2027 R1 (own)", "Brock Bowers"):
        assert not cn.package_allowed(
            compiled4, "cmgaither43", "get", tr.package_of(league, [colin[name]])
        ), name
    assert cn.package_allowed(
        compiled4, "cmgaither43", "get", tr.package_of(league, [colin["2028 R1 (own)"]])
    )


def test_precedence_keyed_on_team_and_side(league):
    """v8 spec §4: precedence is keyed on (team, side) — a query constraint
    about what a team RECEIVES sheds only that team's receives-side intel;
    sends-side intel survives, and vice versa. The spec's own example: a
    'colin receives pos:TE' query must NOT shed a colin KEEPS 2027-picks
    intel. Wildcards stay additive and never shed."""
    intel = [
        {"kind": "KEEPS", "team": "cmgaither43", "subject": "2027 picks", "active": True},
        {"kind": "WANT", "team": "cmgaither43", "subject": "a running back", "active": True},
    ]
    q = [{"who": "cmgaither43", "side": "receives", "what": {"pos": "TE"}, "mode": "require"}]
    res = cn.compile_constraints(league, intel=intel, query=q)
    kept, ignored = res
    assert ignored == []
    colin = [(c.side, c.mode, c.what, c.source) for c in kept if c.who == "cmgaither43"]
    assert ("sends", "exclude", ("pick", (2027, None)), "intel") in colin  # KEEPS survives
    assert ("receives", "require", ("pos", "TE"), "query") in colin
    # the receives-side WANT was shed — and visibly so
    assert not any(s == "receives" and src == "intel" for s, _, _, src in colin)
    assert [e["constraint"]["origin"] for e in res.shed] == [
        "intel WANT: cmgaither43 'a running back'"
    ]
    assert "cmgaither43" in res.shed[0]["why"] and "receives" in res.shed[0]["why"]
    # …and vice versa: a sends-side query sheds the KEEPS but not the WANT
    q2 = [{"who": "cmgaither43", "side": "sends", "what": {"asset": "Brock Bowers"}, "mode": "exclude"}]
    res2 = cn.compile_constraints(league, intel=intel, query=q2)
    colin2 = [(c.side, c.mode, c.source) for c in res2[0] if c.who == "cmgaither43"]
    assert ("receives", "require", "intel") in colin2  # WANT survives
    assert ("sends", "exclude", "query") in colin2
    assert not any(s == "sends" and src == "intel" for s, _, src in colin2)
    assert [e["constraint"]["origin"] for e in res2.shed] == [
        "intel KEEPS: cmgaither43 '2027 picks'"
    ]
    # posture defaults sit on the receives side: a sends-side query does NOT
    # shed the named team's posture default
    q3 = [{"who": "millj", "side": "sends", "what": {"pos": "RB"}, "mode": "exclude"}]
    res3 = cn.compile_constraints(league, query=q3)
    assert ("millj", "posture") in {(c.who, c.source) for c in res3[0]}
    assert res3.shed == []
    q4 = [{"who": "millj", "side": "receives", "what": {"pos": "RB"}, "mode": "require"}]
    res4 = cn.compile_constraints(league, query=q4)
    assert ("millj", "posture") not in {(c.who, c.source) for c in res4[0]}
    assert [e["constraint"]["origin"] for e in res4.shed] == ["posture SELLER"]
    # wildcard query constraints never shed anything
    q5 = [{"who": "*", "side": "receives", "what": {"pos": "TE"}, "mode": "prefer"}]
    res5 = cn.compile_constraints(league, intel=intel, query=q5)
    assert res5.shed == []
    assert {(c.who, c.side, c.source) for c in res5[0]} >= {
        ("cmgaither43", "sends", "intel"),
        ("cmgaither43", "receives", "intel"),
        ("*", "receives", "query"),
    }


def test_compile_result_shed_exposure(league):
    """v8: compile_constraints returns a (constraints, ignored) 2-tuple —
    the finder's unpack is untouched — that ALSO carries `.shed` with every
    precedence-dropped constraint dict and why."""
    res = cn.compile_constraints(league, intel=INTEL)
    a, b = res  # the historical 2-tuple unpack must keep working
    assert isinstance(res, tuple) and len(res) == 2
    assert res.constraints is a and res.ignored is b
    # the constraints element mirrors .shed for callers that only kept it
    assert a.shed is res.shed and list(a) == list(res.constraints)
    assert b == []
    # ronak's posture default was silently replaced by his intel — now visible
    assert [(e["constraint"]["who"], e["constraint"]["source"]) for e in res.shed] == [
        ("ronakpatel32", "posture")
    ]
    assert "intel" in res.shed[0]["why"]
    assert res.shed[0]["constraint"]["origin"] == "posture BUYER"
    # nothing shed when nothing overlaps
    assert cn.compile_constraints(league).shed == []


def test_to_dict_what_shapes(league):
    """v8: to_dict round-trips the new what shapes — scoped picks as
    {class: pick, year?, round?}, any-of as {any: [atom dicts]}."""
    c = _q(league, "millj", "receives", {"class": "pick", "year": 2027, "round": 1}, "require")
    assert c.to_dict()["what"] == {"class": "pick", "year": 2027, "round": 1}
    c2 = _q(league, "millj", "receives", {"class": "pick", "round": 3}, "exclude")
    assert c2.to_dict()["what"] == {"class": "pick", "round": 3}
    c3 = _q(
        league, "millj", "receives",
        {"any": [{"asset": "Mike Evans"}, {"pos": "TE"}, {"class": "pick", "year": 2027}]},
        "require",
    )
    assert c3.to_dict()["what"] == {
        "any": [{"asset": "Mike Evans"}, {"pos": "TE"}, {"class": "pick", "year": 2027}]
    }
    # the folded unscoped pick atom serializes as the bare {class: pick} dict
    docs = [
        {"kind": "WANT", "team": "cmgaither43", "subject": "a running back", "active": True},
        {"kind": "WANT", "team": "cmgaither43", "subject": "draft picks", "active": True},
    ]
    compiled, _ = cn.compile_intel(league, docs)
    assert compiled[0].to_dict()["what"] == {"any": [{"pos": "RB"}, {"class": "pick"}]}
