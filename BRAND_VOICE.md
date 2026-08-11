# Brand Voice & Iconography — AUSVIA

New in this pass (2026-08-11) — not covered by the logo spec (that's the
mark only) or by `DESIGN_SYSTEM.md` (that's visual tokens). This is the
first time voice/tone and iconography have been defined explicitly, rather
than existing only as an emergent pattern across templates and prompts.

## Voice & tone

1. **Say what's true, plainly.** No hype, no "AI magic" language, no
   exclamation-mark enthusiasm. This isn't a style preference — it's the
   same honesty principle that governs the product's AI behavior
   (`AI.md`'s deterministic-first rule, the mock provider's plain refusals
   instead of fake output) applied to UI copy. If a feature isn't
   available, say so directly ("AI narrative isn't available because no
   provider is configured" — the app's actual existing copy — not "Oops!
   Something went wrong ✨").
2. **Respect that this is a stressful, high-stakes process for the user.**
   Applicants are often navigating a foreign system, in a language they're
   still learning, for something that matters to their life plans. Calm
   and direct beats cheerful or casual. Never joke about rejection,
   deadlines, or gaps in a candidate's profile.
3. **Every control says exactly what it does.** "Approve application," not
   "Let's go!" — buttons, links, and confirmations name the actual action,
   not a mood. This is already the app's practice (see any template); this
   just makes it an explicit rule so it survives new contributors and new
   pages.
4. **Errors explain what happened and what to do next — never apologize
   for existing.** "This document is corrupted or unreadable — please
   re-upload it" (the app's actual copy, from the Phase 4 PDF-merge fix),
   not "Sorry, something went wrong."
5. **AI-generated content is never presented as more certain than it is.**
   Confidence is always qualified in the same terms the product already
   uses elsewhere — high/medium/low, never a fabricated percentage — and
   AI output is labeled as AI output (source/provider shown), never
   blended invisibly with deterministic facts. This applies to every
   future AI-assisted feature (interview prep, company research), not just
   the ones that exist today.

This is descriptive of what the product's actual copy already does
(cover letter/email generation refusals, the corrupt-PDF error, the match-
score "not an AI guess" framing on the job detail page) as much as it is
prescriptive — the goal is to make the existing instinct explicit so it's
consistent as new features and new contributors add copy.

## Iconography & imagery

**Decision: icons only, no illustration.** No mascots, no hero
illustrations, no decorative graphics — consistent with "premium European
career-tech," not "friendly SaaS with an illustrated empty-state
character." Any future empty-state or onboarding graphic should be
typographic/geometric (in the spirit of the logo mark itself), never a
drawn character or scene.

**Icon style, going forward: a single-weight line/stroke icon set** —
geometric, restrained, matching the logo's own construction language
(constant stroke width, no fine detail, holds at small sizes). No filled/
solid icon style, no duotone, no photographic icons.

**Known gap, not fixed in this pass:** the app currently has **no real
icon set at all** — status indicators use raw Unicode glyphs (✓, ❌, ⚠) in
`jobs/detail.html`'s strengths/gaps list. `❌` in particular renders as a
colorful emoji on most platforms (red X in a rounded square), which
directly contradicts "no generic AI sparkle" / restrained-premium — it's
the most visually inconsistent element in the current UI. Replacing these
with a real inline SVG line-icon set (checkmark, X, question-mark, arrow —
small enough vocabulary to hand-author 3-4 icons consistent with the
symbol's own stroke language, no need for a full third-party icon library)
is flagged here as a concrete, scoped fix for a future UX pass — not
executed now since it's template-level UI work, not brand-definition work,
and this checkpoint's brief was to define the stance, not implement it.
