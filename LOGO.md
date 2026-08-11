# Logo — AUSVIA Aperture (rev 1.0, approved)

Implemented 2026-08-11 from the approved logo specification PDF
("Brand identity with logo.pdf", rev 1.0). This document records what was
built, the exact geometry/ratios (transcribed, not re-derived), and every
place this pass had to make a judgment call the spec didn't fully pin down.

## What it is

**Aperture**: a route climbing to a point, cut out of a solid tile
(counterform construction — the path is an opening, never a drawn line).
Read a second time, it's an "A" — the first letter of both Ausbildung and
Ausvia — with the crossbar removed so the path stays open at the base.
One shape, one fill, no gradient, no fine detail: it survives 16px, pure
black, pure white, and every reversal.

## Construction (spec section 02, transcribed exactly)

- Artboard 96×96. Tile 92×92, inset 2, corner radius 22 (24%).
- Counter span 56 wide, apex y=19, feet y=75.
- Path width 12.5, constant, perpendicular.
- Leg angle 63.4° from horizontal (1:2 rise).
- Apex mitered, on the vertical axis.
- `fill-rule="evenodd"` — the counter is never its own shape, always a cut.

Verified by hand: the leg slope (rise:run = 2:1 → atan(2) = 63.43°) and
perpendicular leg width (≈12.52) both check out exactly against the given
path data, confirming the spec's numbers and the SVG path agree.

```
M24 2 H72 A22 22 0 0 1 94 24 V72 A22 22 0 0 1 72 94
H24 A22 22 0 0 1 2 72 V24 A22 22 0 0 1 24 2 Z
M20 75 L48 19 L76 75 L62 75 L48 47 L34 75 Z
```

(The PDF's copy of this path had two OCR/extraction artifacts — a missing
`//` in the `xmlns` URL and a mis-encoded `viewBox` attribute name — both
obviously corrupted in extraction, not intentional; corrected here since
every numeric value in the path itself matches the construction spec
exactly.)

## Wordmark (spec section 03)

Sora SemiBold (600), lowercase always, −4% (−40/1000 em) tracking.

**Implemented as a true outlined vector**, not live text in a webfont:
downloaded the real Sora variable font (Google Fonts, SIL OFL — license
bundled at `app/static/brand/Sora-OFL.txt`), instantiated the 600 weight,
and extracted the exact "ausvia" glyph outlines with `fontTools`
(`svgPathPen` + `transformPen`, applying the spec's −4% tracking between
each glyph). This is the licensed typeface's real letterforms baked to a
static path — not a hand-drawn approximation in a substitute face, which
the spec explicitly prohibits ("do not re-set it in a substitute
typeface"). Resulting bounding box: 2966.5 × 776.0 units (a wide, compact
lowercase word, consistent with the spec's description of Sora's
single-storey `a` and tight `v`/`i` gaps).

Because the wordmark is now a static outline, **the live app does not need
to load Sora as a webfont at all** — see the typography decision in
`DESIGN_SYSTEM.md`.

## Symbol-to-wordmark lockup (spec section 04)

Primary horizontal: symbol height = 1.05× wordmark size, gap = 0.34× symbol
height, symbol vertically centred on the wordmark's optical block (bbox
centre), not its baseline. Computed exactly (not rounded) for the wordmark
at native scale:

| | value |
|---|---|
| Wordmark | 2966.5 × 776.0 |
| Symbol | 814.8 × 814.8 (scale 8.4875) |
| Gap | 277.0 |
| Canvas | 4058.3 × 814.8 |

Stacked: symbol 1.7× wordmark size, gap 0.27× symbol height, both
horizontally centred. Canvas 2966.5 × 2451.4.

These exact numbers are what's baked into both `app/templates/_logo.html`
(the live Jinja macros) and the static lockup SVGs in
`app/static/brand/` — same source geometry, two output forms.

## Color (spec section 08)

| Name | Hex | Usage |
|---|---|---|
| Ink Navy | `#0B1220` | Text/wordmark color and backgrounds on **light** surfaces; the page/surface background on **dark** contexts |
| Signal Blue | `#2563EB` | **The symbol's default fill on light backgrounds** (5.17:1 on white, AA-safe) |
| Bright Blue | `#3B82F6` | The symbol's fill on **dark/ink** backgrounds only (5.4:1 on Ink Navy vs. Signal Blue's 2.9:1) |
| Black / White | — | Monochrome pair (symbol and wordmark both the same single color) |

### Signal Blue vs. Ink Navy: resolved

**Signal Blue is the symbol's default fill on light backgrounds. Ink Navy
is not a default mark color at all — it's the text/wordmark and
surface color.** This was re-examined and confirmed (previously left as
an open reading, flagged as reversible) against explicit spec language,
not just asset file names:

- The earlier "Brand identity with logo.pdf" (v1.0, the document this
  rev 1.0 spec refines) states the color roles explicitly: **"Signal
  Blue: Primary actions, the mark on light"** and **"Bright Blue: Dark
  mode only — the mark on ink."** Ink Navy's row reads "Surfaces, type,
  the mark" — listing "the mark" too, but alongside "surfaces" and
  "type," which is why it reads as the *type/background* color that
  happens to also cover monochrome/print treatments of the mark, not the
  primary colored fill. Signal Blue and Bright Blue are the two rows that
  name a *background context* ("on light" / "on ink") for the mark
  specifically — that pairing is the actual rule: light → Signal Blue,
  dark → Bright Blue.
- Rev 1.0's own section 08 confirms the same pairing operationally: "On
  `#0B1220` [Signal Blue] drops to 2.9:1, which is **why the dark version
  steps up to Bright Blue** at 5.4:1." "Steps up to Bright Blue" only
  makes sense as a description of swapping *away from* a Signal-Blue
  baseline for dark contexts — i.e., Signal Blue is the assumed light-
  context default that the dark version deviates from.
- The rendered reference art across all three logo PDFs in this project
  (the original 8-concept exploration, the v1.0 identity, and this rev
  1.0 spec) consistently shows the primary lockup's symbol in blue, not
  ink, in every "primary/light" example shown.

Section 09's file table (`ausvia-symbol-ink.svg` = "default, light
backgrounds") is the one piece of text that reads the other way taken in
isolation — but weighed against the explicit color-role sentence above
plus the contrast-figure phrasing plus the consistent reference art
across three documents, the file table's "default" more plausibly means
"the default *neutral/monochrome-adjacent variant* for editorial/print
use," not "the default colored fill for the primary product lockup."
**This is the final determination — not re-litigated further unless a
future spec revision says otherwise.**

**What changed as a result:** the symbol now renders Signal Blue by
default on light backgrounds (was Ink Navy); the wordmark text stays Ink
Navy (unchanged — text color was never the ambiguous part). Updated in
`app/templates/_logo.html`'s macro defaults, and regenerated
`ausvia-lockup-primary-light.svg`, `ausvia-lockup-stacked.svg`, and
`ausvia-lockup-tagline.svg` in `app/static/brand/`. The dark/ink lockup
(Bright Blue symbol + white wordmark) was already correct and is
unchanged. `ausvia-symbol-ink.svg` remains available as a real asset (an
ink-colored symbol variant genuinely has print/monochrome-adjacent uses)
but is no longer the implied default anywhere in the live app.

### Signal Blue as primary-action color: confirmed, one inconsistency fixed

Separately from the symbol-color question: Signal Blue (`bg-brand-600`,
exactly `#2563EB`) already drives every primary CTA button across the
app (confirmed by grep across all templates - "Approve application,"
"Start application," "Search," every primary form-submit button). Links
use `text-brand-700` (`#1D4ED8`) — one shade darker than Signal Blue
within the same scale, a deliberate, defensible offset for text-on-white
legibility, not a deviation from the brand color.

**One real inconsistency found and fixed:** form focus rings
(`app/templates/_macros.html`) used `focus:ring-brand-500`, which
resolves to `#3B82F6` — **Bright Blue**, the spec's dark-background-only
color — applied to focus states on white input fields. Changed to
`brand-600` (Signal Blue) in both `render_field()` and
`render_checkbox()`, the two places this is defined. This was a real,
if minor, violation of the "Bright Blue is dark-only" rule; it's fixed
project-wide from a single centralized location.

## Wordmark casing: two different rules for two different things

- **The logotype (graphic)** is lowercase "ausvia," always, per this spec
  — implemented that way in every SVG asset and in `_logo.html`.
- **Text mentions of the brand** (page `<title>`, headings, prose, docs)
  stay **AUSVIA**, all caps — the standing correction from the Phase 5.5
  checkpoint, which this spec doesn't override (it only specifies the
  logotype's own case, not how the name should read in running text).

This reverses part of the Phase 5.5 checkpoint's `_logo.html` change,
which had made the wordmark *graphic* uppercase too — that was correct
under the brand direction known at the time, and is superseded now that
an approved logo spec exists.

## Clear space & minimum size (spec section 06)

Clear space = ½ symbol height on all sides. Minimum sizes: full lockup
88px wide; symbol alone 16px screen / 6mm print. Verified live — the
generated favicon PNGs hold up cleanly at both 32px and 16px (see
`app/static/brand/favicon-32.png` / `favicon-16.png`).

## App icon & favicon (spec section 07)

The tile **is** the icon — no added container, since it's already a
self-contained rounded shape. For iOS/Android specifically, the spec
calls for a different treatment: a plain (unrounded) square canvas in
solid Ink Navy with the mark's chevron drawn as a **positive white shape**
(not a cutout) at 66% of the canvas, since app-icon sources must be
opaque and platforms apply their own corner mask —
`app/static/brand/ausvia-appicon-source.svg` (1024×1024) implements this
exactly. The web favicon (`favicon.svg` + PNG fallbacks) uses the normal
counterform tile in Signal Blue, per the file table.

## Asset index (`app/static/brand/`)

| File | Content |
|---|---|
| `ausvia-symbol-{ink,blue,bright,black,white,currentcolor}.svg` | Symbol alone, six fills |
| `favicon.svg`, `favicon-32.png`, `favicon-16.png` | Web favicon (Signal Blue), verified at both sizes |
| `ausvia-wordmark-{ink,white,currentcolor}.svg` | Wordmark alone, outlined |
| `ausvia-lockup-primary-{light,dark}.svg` | Primary horizontal lockup (ink-on-light / bright+white-on-dark) |
| `ausvia-lockup-mono-{black,white}.svg` | Monochrome lockups |
| `ausvia-lockup-stacked{,-dark}.svg` | Stacked lockup |
| `ausvia-lockup-tagline.svg` | Stacked lockup + tagline (reference/print asset — see typography decision for why this one file uses live Sora text) |
| `ausvia-appicon-source.svg` | 1024×1024 iOS/Android source, per section 07 |
| `Sora-OFL.txt` | Bundled license for the outlined wordmark's source font |

## Live implementation

`app/templates/_logo.html` exports `symbol()`, `wordmark()`, and
`lockup()` Jinja macros using this exact geometry (not an approximation —
the same numbers as the static assets above). Used in `base.html`'s
authenticated sidebar (bright-on-ink) and `landing.html`'s header
(ink-on-light). Verified by fetching the real rendered pages from the
running dev server and screenshotting them — not just reading the
template source — see `DECISIONS.md` for the verification note.

## Not covered by the approved spec (this pass's own proportional choice)

The "with tagline" lockup's tagline size/spacing isn't in the spec's
numeric construction sections (only symbol/wordmark ratios are specified).
Chose tagline size ≈26% of wordmark height, measured to fit exactly within
the stacked lockup's canvas width using the real font metrics (not
guessed) — reasonable and consistent with the rest of the system, but
open to adjustment since it wasn't a specified ratio.
