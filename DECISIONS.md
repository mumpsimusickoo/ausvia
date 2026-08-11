# Decision Log — Ausvia

Each entry: decision, reason, alternatives considered, consequences. Newest
first. Don't reopen a settled decision without new evidence — see entry
format below for what was actually weighed.

---

## 2026-08-11 — Rebrand to "Ausvia"

**Decision:** Rename the product from the working title "Ausbildung Career
Agent" to **Ausvia**, with tagline "Your path to Ausbildung." Apply the new
brand across user-facing surfaces (page titles, nav, landing page, logo)
without renaming the repository, Python package structure, or database.

**Reason:** Explicit product/brand directive.

**Alternatives considered:** Renaming the repo folder and Python import
paths (`app.*`) to match — rejected as high-risk, zero functional benefit
churn touching every file's imports, and the directive itself says "do not
delete, restart, replace, or rebuild."

**Consequences:** All template titles, nav branding, and landing copy now
say Ausvia. `app.py`, the `app/` package, `requirements.txt`, and the git
history still reference the original working name in places (e.g. the repo
folder name `ausbildung-finder/`) - this is cosmetic-only and intentional.

---

## 2026-08-11 — Brand palette reuses the existing Tailwind slate/blue scale

**Decision:** Adopt the new brand's exact neutral colors (`#F7F8FA`,
`#E2E8F0`, `#0F172A`, `#64748B`, `#94A3B8`) and semantic colors (`#16A34A`,
`#D97706`, `#DC2626`) as-is, without introducing new custom Tailwind tokens
for them, because they are pixel-identical or near-identical to Tailwind's
built-in `slate` and `green-600`/`amber-600`/`red-600` - which the app's
templates already used throughout Phases 1-4. Only the primary "brand" blue
scale was refined to the exact spec hex (`#2563EB`/`#3B82F6`, which are
themselves exactly Tailwind's `blue-600`/`blue-500`).

**Reason:** Avoid introducing redundant design tokens for values already
~99% in use; matches the directive's own "do not overengineer" principle.

**Alternatives considered:** Defining a fully custom neutral/semantic scale
from scratch and re-theming every template to reference it explicitly -
rejected as unnecessary churn with no visible difference.

**Consequences:** The rebrand touched `base.html`'s Tailwind config, the new
logo, and copy - not a page-by-page re-theme, since the existing utility
classes already matched the new spec almost exactly.

---

## 2026-08-11 — Gmail OAuth flagged as needing redesign, not fixed in Phase 4.5

**Decision:** Document the single-user OAuth flow (`gmail_client.py`'s
`run_local_server()` + shared `token.json`) as a known architectural gap in
`PROJECT_AUDIT.md` rather than redesigning it during the brand/audit phase.

**Reason:** Phase 4.5 was scoped to audit + brand/design system per the
directive's own phase breakdown; a proper per-user OAuth web flow (auth URL
→ callback route → encrypted per-user token storage) is a substantial
feature change that belongs in Phase 5/6 alongside the rest of the Gmail
reply-tracking work, not bundled into a rebrand.

**Alternatives considered:** Fixing it immediately since it's flagged as a
security concern - considered, but doing it properly requires new DB models
(`GmailConnection` with per-user encrypted tokens) and new routes, which is
feature work, not brand/audit work; bundling it would blur the phase
boundary the directive itself asks to respect.

**Consequences:** Gmail draft creation remains usable only in a single-
developer local setup until this is addressed. Flagged prominently in the
audit so it isn't silently forgotten.

---

## 2026-08-10 — Evolve the existing Flask app rather than rewrite in Next.js/Postgres

**Decision:** Build out the platform on the existing Python/Flask codebase
(SQLAlchemy + SQLite, upgradeable to Postgres via `DATABASE_URL`) instead of
the master spec's literal default recommendation of a Next.js/TypeScript/
Postgres stack.

**Reason:** The existing repo already had working, real integrations
(Bundesagentur Jobsuche API client, Gmail OAuth draft creation, PDF merge);
the dev machine had no Docker/Postgres available; a full rewrite would
discard working code for no functional gain. User deferred the choice to
this judgment call.

**Alternatives considered:** Next.js + TypeScript + Postgres (the spec's
literal default) - rejected per the reasoning above.

**Consequences:** Server-rendered Jinja2 + Tailwind CDN frontend rather than
a SPA. This is the foundational decision everything since Phase 1 builds on.

---

## 2026-08-10/11 — AI features are deterministic-first, AI-optional

**Decision:** Every AI-assisted feature (match scoring, cover letter/email
generation) computes its core output deterministically in plain Python
first; a configured AI provider only adds narrative polish or personalized
prose on top of already-computed, real facts. The app is fully functional
with zero AI credentials configured (`AI_PROVIDER=mock` default).

**Reason:** Spec's explicit anti-hallucination and "never present an AI
guess as a guaranteed fact" requirements; also means the app never depends
on a paid API key to be useful, and match scores are always explainable and
reproducible.

**Alternatives considered:** Asking an LLM directly for a match score or
letting cover letter generation be AI-only with a "coming soon" mock state -
rejected as both less trustworthy and less honest about what's real.

**Consequences:** `app/ai/matching.py` and `app/ai/cover_letter.py`
(template path) are real, tested, working code paths - not stubs. The real
`AnthropicProvider` path exists and is architecturally sound but has never
been exercised against a live API key in this environment (see
`PROJECT_AUDIT.md`).

---

## 2026-08-10 — Job source architecture: adapter pattern, manual import as universal fallback

**Decision:** All job sources implement a common `JobSourceAdapter`
interface (`search`/`get_job`/`normalize`/`check_availability`); manual URL/
text import is a permanent, source-independent fallback, not a stopgap.

**Reason:** Spec requirement that the product never depend on any single
external source being available; the Bundesagentur API turned out to be
blocked from this dev sandbox's network, which validated the design (search
degrades gracefully, manual import still works fully).

**Consequences:** Adding a second real source later (e.g. an official
company-careers feed, if one exists) is a new adapter class, not a rewrite.

---

## 2026-08-10 — Duplicate detection: simple normalized-match heuristic, not fuzzy/embedding-based

**Decision:** `app/jobs/dedupe.py` groups postings under one canonical `Job`
via exact matching on normalized company name (legal-suffix-stripped),
title (noise-stripped), location, and start date - not fuzzy string
matching or embeddings.

**Reason:** Simple, fully deterministic, explainable, and sufficient for the
one real source currently integrated. Avoids the complexity and cost of an
embedding-based approach before there's a second/third source to actually
need it for.

**Consequences:** Postings that are the same job but described with
different location strings or missing a start date won't currently be
merged. Documented as a v1 heuristic in the module docstring, upgradeable
without touching callers.

---

## 2026-08-10 — Human approval is mandatory before any application "package" is built

**Decision:** The `Application.status` can only become `ready` via an
explicit user "Approve application" action; nothing is ever auto-sent.
Gmail integration only ever creates drafts, never sends.

**Reason:** Explicit, repeated spec requirement (sections 47/58/28 across
both the original and Ausvia directives).

**Consequences:** Every AI-assisted generation step (cover letter, email)
is followed by a review/edit step before the approval gate; this shaped the
whole `app/applications` route design.
