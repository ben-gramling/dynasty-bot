# dynasty-bot web design plan

The design contract for `apps/web`. Foundation implements the tokens/shell; tab agents (Waivers, League — the Trades tab was removed in v7.1) follow this document exactly — every color, face, and chart decision derives from here. Subject: a one-manager front office for **Chicago Dynasty**. The user is the manager of team *what would it take* (roster 4); he returns daily to answer three questions: what do I claim, what do I offer, where do I stand. The page is a decision instrument — a scouting terminal, dense and numeric — not a marketing page.

## 1. Mode and tokens

**One mode: light.** A cool, sky-tinted paper — the Chicago flag's white field, not cream. Everything warm/terracotta is out; everything near-black/neon is out.

| Token | Hex | Role |
|---|---|---|
| `field` | `#F2F7FA` | Page ground — flag-white cooled toward the lake |
| `surface` | `#FFFFFF` | Cards, tables, inputs |
| `ink` | `#14212E` | Primary text, positive numbers, axes-text |
| `sky` | `#A8D8F0` | Chicago-flag sky band — structural accent: masthead band, active-tab underline, chip fills (at low alpha), row highlights |
| `sky-deep` | `#1877B8` | Interactive: links, buttons, focus rings, series-1 chart hue |
| `star` | `#C8102E` | Chicago-flag red — six-pointed stars and **negative numbers only** |

Derived (not new hues): `ink-muted` = ink blended 62% into field (`#5B6E7E`), `line` = `#D8E4EC` for card borders, `chip` = `#E5F1F8` chip fill. Rule of discipline: **red never decorates.** It appears exactly twice in the system — as the six-pointed star glyph (identity/emphasis marker) and as the color of a negative number (ledger semantics). Positive numbers are ink, not green; the page reads like a ledger, not a traffic light.

## 2. Type roles (all via `next/font`, self-hosted at build)

| Role | Face | Use |
|---|---|---|
| Display | **Big Shoulders** | Wordmark, tab labels, section headings, verdict verbs (CLAIM / TRADE / DROP). Named for Sandburg's Chicago — "City of the Big Shoulders" — a condensed American grotesque built for Chicago's civic design system. Used with restraint: headings only, never body. |
| Body / UI | **Public Sans** | All prose, labels, buttons, empty states. Plain civic sans; disappears behind the content. |
| Data | **IBM Plex Mono** | Every numeral on the page: chips, tables, bids, KTC values. `font-variant-numeric: tabular-nums` everywhere digits align. KTC value is the currency of the page and always wears this face. |

Scale: display 28/22/17 (600–700, slight tracking-tight on the wordmark), body 14/13, data 13/12. Sentence case everywhere ("Add", "Bid $0", "You send / You get", "Strength"). Uppercase reserved for Big Shoulders headings and chip keys.

## 3. Layout concept

One fixed masthead — a flag-band construction (thin sky band, then the white masthead row) — over a dense, single-column instrument panel capped at 1200px; every page is cards on the field, tables first, charts second.

```
┌──────────────────────────────────────────────────────────────────┐
│ ███████████████████████ sky band (6px) ██████████████████████████│
│  ✶✶✶✶ CHICAGO DYNASTY   Waivers  League            ● 2h ago  ⟳    │  ← masthead (surface)
│        front office      ────────                  Refresh       │  ← active tab: sky underline
├──────────────────────────────────────────────────────────────────┤
│  field #F2F7FA                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ SECTION HEADING (Big Shoulders)                 meta  ···  │  │
│  │ ┌────────────────────────────────────────────────────────┐ │  │
│  │ │ row · verdict · [lineup +1] [wealth +1,075] [crunch −1,069] → [score +7] ▸ │  │
│  │ │   └─ expands: ΔL terms · crunch line · before/after    │ │  │
│  │ └────────────────────────────────────────────────────────┘ │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

Masthead: wordmark left (four red six-pointed stars over "CHICAGO DYNASTY", "front office" as a small sub-line), the three tabs beside it, run-status pill + Refresh right. Mobile: wordmark row, tabs scroll horizontally beneath, pill collapses to dot + age. The six-pointed star recurs exactly where emphasis is earned: the wordmark, the "recommended" marker on waiver cards, the my-team marker in league charts. Never as bullet decoration.

## 4. Signature element: the decomposition sentence

Every recommendation (claim, drop, promote, trade side) renders its §12 breakdown as one readable line of inline value chips that expands to the full audit. This is the page's one memorable device; everything around it stays quiet.

Markup (server-renderable, works without JS via `details/summary`):

```html
<details class="decomp">
  <summary>                                     <!-- the sentence -->
    <span class="chip"><span class="chip-k">lineup</span><span class="chip-v">−129</span></span> ·
    <span class="chip"><span class="chip-k">wealth</span><span class="chip-v">+776</span></span> ·
    <span class="chip"><span class="chip-k">crunch</span><span class="chip-v">+1,399</span></span>
    <span class="decomp-eq">=</span>
    <span class="chip chip-score"><span class="chip-k">score</span><span class="chip-v">+2,045</span></span>
    <svg class="decomp-caret"/>                 <!-- rotates 90° on open, CSS only -->
  </summary>
  <div class="decomp-audit">
    1. ΔL terms table — kind · slot · out · in · Δ (from sides.*.dL_terms)
    2. Crunch line — "Cuts 3 → 1 · rescued Joe Flacco, Stefon Diggs"
    3. Before/after lineup tables (audit.lineup_tables), side by side, stacked on mobile
    4. Sum line — "−128.7 + 775.6 + 1,398.5 = 2,045.4" (components must sum; the data guarantees ±0.1)
  </div>
</details>
```

Chip anatomy: `chip-k` is Public Sans 10.5px uppercase in ink-muted; `chip-v` is IBM Plex Mono tabular, ink when ≥ 0 (with explicit `+`), star-red when negative (true minus `−`, U+2212). Chip fill `#E5F1F8` (sky at low alpha), radius 4px. The score chip gets a `sky-deep` 1px border — it is the sentence's verb. The chips come straight from `sides.me.lineup_weighted / wealth_weighted / crunch_term / score` — never recomputed in the UI, never hand-written. Bid cards prepend a bid chip ("Bid $0"); drop rows use the same schema. Caret rotation is the only transition and is removed under `prefers-reduced-motion`.

## 5. Chart palette (league tab especially)

Charts are hand-rolled semantic HTML/SVG: magnitude = bars from a zero baseline, one axis only, thin marks with 4px rounded data-ends and 2px surface gaps, hover tooltips, and a table view always present. Text wears ink tokens, never series colors. Legend whenever ≥ 2 series.

**Default league chart is single-series**: all 12 team bars in `sky-deep`, my team marked by a red six-pointed star beside the label plus a deeper step — never 12 hues. When genuinely multi-series (e.g. lineup vs futures per team), use the fixed categorical order below; a team/series keeps its hue no matter what filters remove.

Categorical order (fixed): `#1877B8` (sky-deep, series 1) → `#D97706` → `#12876F` → `#6F5BC4` → `#B0417F`.
Polarity (signed deltas): positive `#1877B8`, negative `#C8102E`, neutral midpoint `#5B6E7E`. Sequential (single-hue magnitude): sky-deep light→dark.

Validator run (`validate_palette.js`, light mode):

```
Palette (light, surface #fcfcfb, categorical): 5 slots
  [PASS] Lightness band         all 5 inside L 0.43–0.77
  [PASS] Chroma floor           all 5 >= 0.1
  [PASS] CVD separation         worst adjacent #12876F↔#D97706 ΔE 10.3 (protan) · tritan 8.7
  [PASS] Normal-vision floor    worst adjacent #B0417F↔#6F5BC4 ΔE 15.9 (normal)
  [PASS] Contrast vs surface    all 5 >= 3:1

  → ALL CHECKS PASS
```

## 6. Copy rules

User-side vocabulary, sentence case: "Add", "Bid $0", "You send / You get", "Strength", "Cuts due". Verdict verbs (CLAIM, TRADE) may be Big Shoulders caps — they are headings. Empty states instruct: "No collector run yet — hit Refresh." Errors say what happened and what to do: "Can't reach the database — check MONGODB_URI and retry." No apology, no filler.

## 7. Quality floor

Responsive to mobile (tabs scroll, audit tables stack, wide tables scroll inside their card with `overflow-x: auto`); visible `:focus-visible` ring (2px sky-deep, 2px offset); `prefers-reduced-motion` kills the caret transition and any hover motion; `details/summary` keeps the signature element functional without JS; tabular numerals on every digit column.

## 8. Self-critique vs the banned looks

- **Cream + terracotta + serif template** — no serif anywhere; the paper is cool (`#F2F7FA`, blue-tinted), not cream; the accent system is civic blue/red from a real flag, not terracotta.
- **Near-black + acid-green terminal** — light mode, executed once and well; the "terminal" density comes from mono numerals and tight tables, not from a dark theme.
- **Broadsheet hairline newspaper** — structure comes from filled sky bands, card surfaces, and 4px-radius chips, not hairline column rules; Big Shoulders is highway-signage, not a blackletter masthead; no justified columns.
- **Generic dashboard default** (the real risk): what makes this page unmistakable is the flag-band masthead with six-pointed stars, the ledger convention (red = negative only, no green), and the decomposition sentence as the atom of every list. If a screenshot could pass for a template admin panel, one of those three is being under-executed — fix that rather than adding decoration.
