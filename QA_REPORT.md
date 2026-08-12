# QA_REPORT.md — Phase 7 (QA)

Date: 2026-08-12
Scope: Phases 1–6 as a complete system. Live testing against the running dev
server (`http://127.0.0.1:5050`), the real (non-`:memory:`) dev SQLite
database, a brand-new registered account, the existing seeded `testuser`
account, and a second `otheruser` account for cross-user testing. Two
read-only code-audit passes were run in parallel (security/ownership/secrets/
Gmail-token-security; accessibility/prompt-injection/migration-cascade) and
every finding they returned was either verified live or traced to exact
source lines before being included below.

## Executive Verdict

**PASS WITH CONDITIONS.**

The core promise — a candidate builds a profile, gets a deterministic (never
AI-guessed) match score against real job data, and produces a
human-reviewed, never-auto-sent application — works end-to-end, is grounded
correctly, and degrades honestly when AI/Gmail/Arbeitsagentur infrastructure
is unavailable. Two defects are serious enough to fix before real users rely
on this on a phone or delete a document: a live 500 crash from an
unprotected foreign-key relationship, and the complete absence of mobile
navigation plus a site-wide mobile horizontal-overflow bug (confirmed with
screenshots, including on the public landing page). Neither is a security
breach and neither blocks continued development — see Blocking below for
exact repro steps.

---

## Blocking

### B1. Deleting a Document that's selected on an Application crashes "Generate email" and "Approve" with a raw 500

- **Severity:** BLOCKING
- **Affected feature:** Document management + Application generation/approval
- **Reproduction (confirmed live, not just read from code):**
  1. Upload a document, select it for an application (`POST
     /applications/<id>/documents`).
  2. Delete that same document from the Documents page (`POST
     /documents/<id>/delete`).
  3. Click "Generate email" (or "Approve") on the application that had it
     selected.
- **Expected behavior:** Either the document can't be deleted while
  selected on a non-terminal application, or generation/approval silently
  drops the missing document and continues.
- **Actual behavior:** `AttributeError: 'NoneType' object has no attribute
  'doc_type'` (generate-email, `app/applications/routes.py:174`) / `'...has
  no attribute 'storage_path'` (approve, `app/applications/routes.py:249`).
  Both are unhandled — Flask's generic error page renders, in dev mode with
  the interactive Werkzeug debugger. Live-verified: reproduced exactly as
  predicted by the code audit, with the actual stack trace captured.
- **Root cause:** `Document` has no relationship/cascade toward
  `ApplicationDocument` (`app/documents/routes.py:120-129`), and — more
  fundamentally — SQLite foreign-key enforcement is never turned on for this
  app (no `PRAGMA foreign_keys=ON`, confirmed absent from `app/__init__.py`
  and `config.py`), so the ORM never has a chance to reject the delete or
  cascade it.
- **Recommended action:** Give `Document` a
  `cascade="all, delete-orphan"` relationship to `ApplicationDocument` (or
  block/warn on delete-while-selected), and enable
  `PRAGMA foreign_keys=ON` via an `Engine` `connect` event listener so this
  class of bug fails loudly in dev/test instead of silently orphaning rows
  in production.

### B2. No mobile navigation exists at all once logged in

- **Severity:** BLOCKING
- **Affected feature:** Every authenticated page, on any viewport `< md`
  (768px)
- **Reproduction:** `app/templates/base.html:83` — `<aside class="hidden
  md:flex w-60 ...">` is the *only* navigation element in the authenticated
  layout (Dashboard/Find Ausbildung/Saved Jobs/Applications/Candidate
  Profile/Documents/Gmail/Admin). No hamburger menu, bottom nav, or any
  other mobile-visible control exists anywhere in `base.html`.
- **Expected behavior:** A real phone user (this product's stated audience —
  international applicants) can navigate between sections.
- **Actual behavior:** Below 768px width, the sidebar is `display:none` with
  no replacement. A mobile user who lands anywhere other than the page they
  need has no way to get there except manually editing the URL.
- **Recommended action:** Add a mobile nav (hamburger + slide-over drawer,
  or a bottom tab bar for the core 4-5 destinations) before any mobile
  launch.

### B3. Site-wide horizontal overflow on mobile viewports, confirmed on the public landing page

- **Severity:** BLOCKING
- **Affected feature:** Landing page (unauthenticated, first thing any user
  sees), dashboard, and to a lesser degree other authenticated pages
- **Reproduction:** Load `/` or `/dashboard` at a 390×844 viewport (a
  standard phone size) — screenshots captured and inspected pixel-by-pixel
  (`qa_screenshots/01_landing_mobile.png`, `02_dashboard_mobile.png`).
- **Actual behavior:** On the landing page, the headline ("Your path to
  Ausbildu…"), body copy, both CTA buttons ("Enter access code" / "See how
  it works"), the second paragraph, and the hero staircase graphic
  ("DISCOVER MATCH PREPARE APPLY") are all cut off mid-word/mid-element at
  the right edge — the page is unreadable without a horizontal scroll that
  most mobile users will never think to do. On the dashboard, stat cards and
  a helper paragraph are similarly cut. This is a real, un-wrapped
  document-width overflow, not a screenshot artifact (verified the captured
  PNG is exactly 390px wide and the content is genuinely wider than that).
- **Likely origin:** The percentage-positioned hero label `<span>` elements
  added in the visual-direction correction pass
  (`app/templates/landing.html`, the `aspect-ratio`-locked hero container's
  label loop) are the most probable single source — absolutely-positioned
  children aren't constrained by a parent's width the way flowed content is,
  and one long English label at a narrow viewport is enough to force
  `documentElement` wider, dragging unrelated flowed text along with it.
  Not fully root-caused in this pass (see Recommended Next Actions) — this
  report documents the reproducible symptom, not a fix.
- **Recommended action:** Add `overflow-x: hidden` on `body` as an immediate
  safety net, then find and fix the actual oversized element(s) per page
  (start with the landing hero labels). Re-screenshot every page at 375px
  and 390px after the fix.

---

## Worth Fixing Now

| # | Finding | Location | Why it matters |
|---|---|---|---|
| W1 | TOCTOU race on invitation-code redemption — `is_valid()` check and `use_count` increment aren't atomic, so two concurrent requests with one single-use code (including an `admin`-type code) can both succeed | `app/auth/routes.py:27-52` | A distributed single-use admin invite could mint two admin accounts under concurrent registration |
| W2 | SQLite FK enforcement (`PRAGMA foreign_keys=ON`) is never enabled | `app/__init__.py`, `config.py` | Root cause enabling B1 and every other orphan-record scenario below; enabling it makes future violations fail loudly in dev/test instead of corrupting data silently in production |
| W3 | `BackgroundTask.error_message` stores the raw exception `str(e)` (up to 500 chars) and the template renders it verbatim to the end user, including full local server filesystem paths | `app/tasks/runner.py:77`, `app/templates/applications/detail.html:213` | Live-verified: a forced Gmail-check failure (invalid token) showed the user "Last check failed: [Errno 2] No such file or directory: 'C:\\Users\\itash\\...\\credentials.json'" — an internal-infrastructure disclosure and a poor, alarming user experience for something as ordinary as a missing/expired Gmail token |
| W4 | Wayfinding station markers: `skipped` and `future` (not-reached) states are visually identical in size and ring weight — differ only by ring **color** | `app/templates/applications/detail.html:105-162`, `app/applications/status_route.py:74-162` | Directly contradicts this component's own in-file design-intent comment ("must differ by size AND ring weight AND fill, not color alone"); a colorblind/low-vision user scanning the marker column can't tell "skipped" from "not reached yet" (mitigated only by adjacent description text, not the glyph itself) |
| W5 | Flash messages are differentiated only by background/border/text color, with no icon, no severity-word prefix, and no `role="alert"`/`aria-live` | `app/templates/_flashes.html:1-14` | A screen-reader user isn't told a flash appeared after a redirect; cheap, app-wide fix |
| W6 | Six form fields have no `for`/`id` label association (proximity-only labeling) | `app/templates/documents/list.html:13-14,21-22,25-26`; `app/templates/applications/detail.html:34,54-55,263-264` | Screen readers announce no accessible name for the doc-type select, file input, description field, cover-letter textarea, email body, and reply-text fields |
| W7 | WTForms field validation errors are never `aria-describedby`-linked to their field — one shared macro, so this affects every validated form in the app | `app/templates/_macros.html:5-9` | A screen-reader user tabbing to an invalid field gets no indication an error exists |
| W8 | Untrusted external text (job descriptions, company data, inbound Gmail replies) is delimited in AI prompts with plain text labels ("JOB FACTS:", "COMPANY'S MESSAGE:"), not a structural fence (e.g. XML tags/triple-backticks) | `app/ai/prompts/*.py` | Defense-in-depth gap only — every system prompt already has an explicit "treat as inert data, ignore embedded instructions" warning, reply-classification output is enum-constrained, and nothing AI-generated is ever auto-sent, so this is not a demonstrated exploitable weakness, just a place to harden |
| W9 | Application-detail page (and likely others) has minor mobile overflow even where the layout otherwise wraps correctly — status pill, "Regenerate" links, and form input/textarea right edges are cut a few pixels short of the 390px viewport | `app/templates/applications/detail.html` (screenshot: `qa_screenshots/06_application_detail_interview_mobile.png`) | Smaller than B3 but same family of bug; worth fixing in the same mobile pass |

---

## Defer

| # | Issue | Reason for deferral | Recommended phase |
|---|---|---|---|
| D1 | `InvitationCode.code` generated with stdlib `random`, not `secrets`, despite `SECURITY.md` claiming `secrets`-backed generation | Still 32^12 entropy over a non-security-critical, already-authenticated-registration-gate value; this is a docs/code mismatch more than a vulnerability | Next docs pass, or bundle with W1's fix |
| D2 | Rate limiter uses `memory://` storage (per-process, not shared) | Fine for the current single-process dev/deploy target; only matters once running multiple gunicorn workers | Phase 10 (Production Readiness) |
| D3 | Rate limiter keys by IP, not by user | Not a data-exposure risk, only an AI-cost-abuse consideration | Phase 8 (Security) revisit |
| D4 | Missing cascade/`ondelete` behavior for `Company→Job`, `Job→JobMatch/Application`, `Company→CompanyInsight`, `Application→GmailMessage`, and any `User→*` relationship | **No route in the app can delete any of these today** (admin only exposes deactivate/revoke toggles) — confirmed via grep for every `db.session.delete(` call site. Latent, not reachable | The moment any future feature adds a hard-delete or GDPR-erasure path |
| D5 | Free-text candidate profile fields (`Experience.responsibilities/achievements`, `Education.description`) flow into AI prompts as part of candidate facts | This is the user's own self-authored data about their own account — a self-injection risk at most, not a third-party attack surface | No action needed unless abuse patterns emerge |
| D6 | Gmail token encryption key is derived from `SECRET_KEY` rather than a dedicated secret | Already disclosed and consistently documented in `app/utils/crypto.py`'s own docstring, `SECURITY.md`, and `DECISIONS.md` — a genuine, tracked architectural limitation, not new information from this QA pass | Already correctly scheduled for Phase 8/10 per existing docs |
| D7 | Real Anthropic/Gmail/Arbeitsagentur live provider paths remain unverified in this dev environment (no API key, no `credentials.json`, datacenter IP blocked by Arbeitsagentur's bot protection) | Expected and previously diagnosed (Phase 2/5); re-confirmed this pass, not a regression | Re-verify whenever real credentials/non-blocked network become available |

---

## Verification Matrix

| Integration / Feature | Status | Basis |
|---|---|---|
| Deterministic match scoring (`app/ai/matching.py`) | **LOCAL VERIFIED** | Code read confirms pure-Python scoring, no AI call in the path; live-computed via HTTP for a fresh profile against 4 jobs, weight redistribution confirmed to skip (not zero-score) uncomputable categories |
| Match narrative / improvement tips (AI layer, mock mode) | **MOCK VERIFIED** | Live: honest "isn't available" decline shown, no fabricated content, sub-40ms mock latency |
| Match narrative / improvement tips (real Anthropic) | **UNVERIFIED** | No `ANTHROPIC_API_KEY` configured in this environment |
| Cover letter / email generation (template fallback) | **MOCK VERIFIED** | Live: real German business-letter template generated and rendered for a fresh candidate; manual edit-and-save also verified |
| Cover letter / email generation (real Anthropic) | **UNVERIFIED** | No API key configured |
| Company fit insight (`app/companies/insights.py`) | **MOCK VERIFIED** | Live: honest decline shown, cached correctly |
| Company fit insight (real Anthropic) | **UNVERIFIED** | No API key configured |
| Reply intent classification / reply suggestion | **MOCK VERIFIED** | Live: honest decline shown against a real seeded Gmail message; enum-constrained parsing confirmed in code |
| Reply intent classification / reply suggestion (real Anthropic) | **UNVERIFIED** | No API key configured |
| Document AI extraction (heuristic, `app/documents/extraction.py`) | **LOCAL VERIFIED** | Live: correctly-labeled upload → no suggestion; mismatched upload (diploma text labeled "other") → suggestion shown; both "apply" and "dismiss" actions verified end-to-end |
| Arbeitsagentur job search — live reachability | **LIVE VERIFIED** (of the failure) | Live request against the exact production `BASE_URL`/`API_KEY` from `jobsearch.py` still returns HTTP 403; same bot-protection diagnosis as Phase 2, re-confirmed this pass, not a regression |
| Arbeitsagentur adapter parsing/normalization | **UNVERIFIED** against a real 200 response | Never exercised against live API data in this or any prior phase (network-blocked); only tested against fixtures/mocks in the automated suite |
| Job search graceful degradation on 403 | **LOCAL VERIFIED** | Live screenshot confirms "Some sources were unavailable" banner with the real error message shown, while still displaying DB-resident and manually-imported jobs — never a silent empty "no jobs found" |
| Manual job import (URL fetch + review + save) | **LOCAL VERIFIED** (via code read; not re-exercised live this pass — no change since Phase 2, and network-dependent) | — |
| Duplicate detection / normalization across sources | **LOCAL VERIFIED** | Covered by existing automated test suite (`tests/test_jobs*.py`), unchanged this phase |
| Gmail OAuth / draft creation / reply tracking (fake-service test suite) | **MOCK VERIFIED** | Full automated suite passing; additionally live-tested this phase: `create-reply-draft` against a real (invalid) token fails gracefully, not with a 500 |
| Gmail OAuth / draft creation / reply tracking (real Google API) | **UNVERIFIED** | No `credentials.json` configured in this environment |
| "Connect Gmail first" UX when not connected | **LOCAL VERIFIED** | Confirmed via code read (`app/applications/routes.py:383-385` and `gmail-draft`'s own status/connection guards) |
| Background task infrastructure (`app/tasks/runner.py`) | **LOCAL VERIFIED** | Live-tested on the real dev server (genuine `ThreadPoolExecutor` worker thread, not the pytest eager path): observed a task go pending→running→**done** (check-replies against a garbage-but-present token, correctly finding 0/failing per the account's connection state) and separately forced pending→running→**failed** with the failure surfaced on the page (see W3) rather than left stuck pending |
| Migrations — fresh database | **LOCAL VERIFIED** | `flask db upgrade` against a brand-new empty SQLite file applied all 6 revisions cleanly in order |
| Migrations — Phase-5-era database upgrading to Phase 6 | **LOCAL VERIFIED** | Seeded a database at the Phase 5 revision with real rows (user, company, job, job_match, document) via raw SQL matching that schema, then upgraded to head; all pre-existing rows survived intact, new columns (`documents.ai_suggested_doc_type`) correctly NULL on old rows, new tables (`company_insights`, `background_tasks`) present |
| CSRF protection | **LOCAL VERIFIED** | Live: POST without a token → 400; POST with a garbage token → 400; global `CSRFProtect` + `WTF_CSRF_ENABLED=True` confirmed in code |
| Cross-user ownership (documents, applications, admin) | **LOCAL VERIFIED** | Live: second user account (`otheruser`) got 404 on another user's application/document by ID guess, and 403 on `/admin/*` routes; no data leaked in any response body |
| Rate limiting on AI-calling routes | **LOCAL VERIFIED** | Code audit confirms every AI-calling route carries `@limiter.limit(...)`; not re-exercised to exhaustion live this pass (would require 30+ real requests against a shared IP limiter — deferred as low-value against the already-passing dedicated rate-limit test suite) |
| File upload validation / path traversal | **LOCAL VERIFIED** | Code audit: extension allow-list + magic-byte sniff, UUID-based stored filenames never derived from user input, `full_path()` traversal guard; malformed-PDF handling live-tested via the document-extraction suite |
| Accessibility (keyboard, screen-reader semantics, contrast/color) | **LOCAL VERIFIED** via code audit | Real gaps found and listed above (W4-W7); no automated axe-core or actual screen-reader pass performed |
| Prompt-injection / data-grounding | **LOCAL VERIFIED** via code audit | Every AI system prompt carries an explicit injection-defense instruction; candidate/job facts funnel through structured-field-only functions; match scores are pure Python; one defense-in-depth gap noted (W8) |
| Mobile layout | **LOCAL VERIFIED** (and failing) | Screenshots at 390×844 confirm B2 and B3 |

---

## Automated Tests

```
113 passed, 0 failed, 0 skipped, 0 errors
```
Full baseline suite (`pytest -q`) re-run at the start of this QA phase, matching the Phase 6 exit baseline exactly — no regressions, and no tests were weakened, skipped, or deleted to reach this result.

**Coverage gaps identified (not filled this pass, per the instruction not to write large amounts of new coverage without first classifying priority):**
- No test reproduces B1 (orphaned `ApplicationDocument` after document deletion) — recommend adding one alongside the fix.
- No test exercises the background-task **failure** path against a real `ThreadPoolExecutor` thread (the existing suite only exercises the `TESTING`-eager synchronous path, which is correct for suite speed/determinism but never truly tests thread-based execution or a real exception surfacing through `error_message`).
- No automated accessibility test (axe-core or equivalent) exists at any layer.
- No automated mobile-viewport screenshot test exists at any layer — B3 would have been caught immediately by one.

## End-to-End Workflow

All 32 steps from the product directive's scenario were exercised against the live dev server, using a brand-new account (`qauser_phase7@example.com`, candidate "Karim Boulaid" — deliberately weak German (A2), mixed/interrupted education, one relevant + one irrelevant work history, to match the "realistic, not just demo-perfect data" requirement) plus the existing richly-seeded `testuser@example.com` account for the Gmail-reply-specific steps:

1. Invitation/access code — new single-use code generated and redeemed. ✅
2. Account registration — real HTTP POST through `RegisterForm`. ✅
3. Login — separate session, verified. ✅
4. Candidate profile creation — personal info, 2 education entries (including a deliberately incomplete one), 2 experience entries (1 relevant, 1 unrelated), 3 skills, 4 languages, preferences. ✅
5. Upload candidate documents — 3 PDFs generated with real embedded text via `pdfmerge.text_to_pdf_bytes`. ✅
6. Document-type suggestion/extraction — mismatched upload correctly triggered a suggestion; correctly-labeled upload did not. ✅
7. Confirm suggestion (apply-suggested-type). ✅
8. Dismiss suggestion (separate document). ✅
9. Search for Ausbildung opportunities — live search hit the real (403-blocked) Arbeitsagentur endpoint and gracefully degraded, still returning DB-resident jobs. ✅
10. Open a job (Siemens AG posting). ✅
11. Calculate deterministic match score — computed live for the new profile. ✅
12. Review category match breakdown — skills/language/education/location/start_date bars rendered. ✅
13. Review strengths and gaps. ✅
14. Open company profile (Siemens AG). ✅
15. Request company-fit insight — honest mock decline. ✅
16. Save/select an opportunity. ✅
17. Create an application. ✅
18. Generate cover letter — template fallback (mock mode). ✅
19. Edit the generated cover letter — manual edit saved and verified present on reload. ✅
20. Generate application email. ✅
21. Select application documents. ✅
22. Build/review final PDF package — `approve` route, real PDF bytes downloaded and confirmed to start with `%PDF`. ✅
23. Approve the application. ✅
24. Create Gmail draft — correctly refused with "Approve the application first" until package existed, then (since this account never connected Gmail) would correctly require connecting Gmail — verified via code path, see Verification Matrix. ✅ (honest failure, not a crash)
25. User manually sends the application — no route in this app sends anything automatically; confirmed no such route exists. ✅ (by design)
26. Mark application as sent — correctly refused before `approve`, succeeded after. ✅
27. Check for replies — background task triggered on `testuser`'s seeded Siemens application; correctly required a Gmail connection first. ✅
28. Detect an incoming reply — used `testuser`'s pre-seeded realistic Gmail message thread (interview invitation + follow-up). ✅
29. Classify the reply — honest mock decline (no deterministic fallback exists for this feature by design). ✅
30. Generate a suggested response — honest mock decline. ✅
31. Create an in-thread Gmail reply draft — attempted against `testuser`'s intentionally-invalid stored token; failed gracefully with a flash message, not a 500. ✅
32. Update application status / verify timeline — manual status override to "interview" verified, `ApplicationEvent` timeline entries present and in order. ✅

**Nothing was ever sent automatically at any step** — confirmed both by code inspection (no outbound-send route exists anywhere in `app/applications/` or `app/integrations/`) and by the live walkthrough never encountering one.

## AI Verification

See Verification Matrix. Summary: every AI-optional feature (narrative, tips, cover letter, email, company insight) has a working non-AI fallback (deterministic scoring, or template text) and, in mock mode, tells the user plainly that real AI isn't configured rather than fabricating output. The two features with no deterministic fallback by design (reply classification, reply suggestion) decline just as honestly. No fake AI content markers (e.g. "As an AI language model...") were found anywhere. The real Anthropic path is entirely unexercised in this environment (**UNVERIFIED**, not "working") — this report does not claim it works.

## Gmail Verification

Fake-service automated suite: full pass, no regressions. Live route-level behavior against a genuinely invalid/garbage token (not a mock) was additionally exercised this phase and confirmed to fail gracefully rather than crash, both for `create-reply-draft` and for the background `check-replies` task (whose failure is now visibly surfaced to the user — see W3 for the info-disclosure problem with *how* it's surfaced). The real Google API integration remains **UNVERIFIED** — no `credentials.json` in this environment, unchanged from Phase 5/6.

## Job Discovery Verification

Live-reconfirmed: the real Arbeitsagentur endpoint still returns HTTP 403 from this environment's network, using the exact `BASE_URL`/`API_KEY` from `jobsearch.py` (not a guessed URL). The UI's handling of this was verified live end-to-end for the first time this phase (previous phases confirmed it only via code read): the search page shows an explicit "Some sources were unavailable" banner with the real error text, and still returns existing DB/manually-imported jobs rather than a silent empty result. Manual import and duplicate detection were verified via the existing automated suite (unchanged this phase, not re-exercised live).

## Background Task Verification

Verified live against the real dev server's `ThreadPoolExecutor`, not just the pytest `TESTING`-eager path: triggered `check-replies` for an account with a broken Gmail token and watched the task genuinely execute on a worker thread, fail with a real exception, and have that failure become visible on the page within ~2 seconds (not left stuck "pending" indefinitely). This is a stronger signal than the existing automated suite provides, since that suite by necessity only ever exercises the synchronous fallback path. See W3 for the one real problem found (raw exception text, including a server filesystem path, shown to the end user).

## Security Verification

No exploitable vulnerability was found. All live negative tests passed as expected: cross-user IDOR attempts (guessed application ID, guessed document ID, guessed status-update POST) returned 404 with no data leakage; admin routes returned 403 for a non-admin user; CSRF-missing and CSRF-garbage POSTs both returned 400. The one real correctness issue (W1, invitation-code redemption race) is a limit-enforcement gap, not an authentication bypass. Full detail in Worth Fixing Now / Defer above.

## Accessibility Verification

Code-level audit only (no axe-core run, no actual screen-reader pass) found four real, fixable gaps (W4-W7): the Wayfinding marker's color-only differentiation between two states, color-only flash messages with no `aria-live`, six unlabeled form fields, and validation errors never linked via `aria-describedby`. Everything else checked (icon-only-control labeling, focus-visibility, keyboard-operability/no-`onclick`-traps) had no issues.

## Data/Migration Verification

Both a fresh-database migration and a simulated "existing Phase-5 installation upgrading to Phase 6" migration were run and verified live (not just read from the migration files) — see Verification Matrix. The cascade/orphan-record audit found the app's single true reachable orphan bug (B1) plus several currently-unreachable latent ones (D4), all traced to the same root cause (W2, FK enforcement never enabled).

## Performance Measurements

All AI-generation timings below were measured against **mock mode** (no configured Anthropic key) — they measure request/template/caching overhead, not real model latency, and must not be read as a prediction of real-AI response time:

| Operation | Measured latency | Notes |
|---|---|---|
| Match narrative generation | 0.033s | Mock decline path |
| Improvement tips generation | 0.037s | Mock decline path |
| Company fit insight generation | 0.037s | Mock decline path |
| Cover letter generation | 0.058s | Template-fallback path |
| Application email generation | 0.053s | Template-fallback path |
| Application approve (PDF package assembly, 3 documents) | 0.189s | Real `pypdf`/PIL work, synchronous on the request thread by deliberate Phase 6 scope decision |
| Package download (3.6 KB PDF) | 0.05s | — |

**Risk classification:**
- Mock-mode AI timings: **acceptable for current V1** (trivially fast; irrelevant once real AI is configured, since that path is entirely network-bound and unverified here).
- PDF assembly at ~0.19s for a small 3-document package, synchronous on the request thread: **acceptable for current V1** at this document count/size; **worth addressing before production** if typical packages grow much larger (many documents, large scanned images) — the Phase 6 decision to leave this synchronous was explicit and reasonable at current scale, but this measurement is the first real data point for revisiting that decision, not a reason to act now.
- Real Anthropic-provider latency for any of the above: **UNVERIFIED**, cannot be classified — no credentials available in this environment to measure it.

## UI/UX Findings

Desktop rendering (1440px) was checked across landing, dashboard, job search (including the live-403 graceful-degradation banner), job detail, application detail (interview status, generated cover letter/email), and company detail — all clean, on-brand (Ink Navy sidebar, Signal Blue accents, warm off-white background), realistic German business-letter content rendering correctly, no visual regressions from Phase 6's additions.

Mobile rendering (390px, a standard phone width) surfaced the two blocking issues above (B2: no nav at all, B3: horizontal overflow cutting off text/buttons on the landing page and dashboard) plus a smaller version of the same overflow pattern on the application-detail page (W9). This is the first time in the project's history that mobile viewports were actually screenshotted rather than assumed from responsive class names — the responsive Tailwind classes present in the templates (`sm:grid-cols-2`, `md:grid-cols-3`, etc.) are necessary but were not sufficient, which is exactly what this kind of QA pass exists to catch.

No purple/gradient/glassmorphism drift observed anywhere. No emoji-as-section-marker or other AI-generated-design smells observed. Icon usage remains sparse and consistently paired with text (confirmed by the accessibility audit).

## Production Blockers

1. **B1** (orphaned-document 500 crash) — blocks trusting "delete a document" as a safe action.
2. **B2** (no mobile navigation) — blocks any real mobile user from using the product beyond the page they land on.
3. **B3** (mobile horizontal overflow, including on the public landing page) — blocks the product from being legible on a phone at all, which is a serious problem given the stated audience.
4. The **real** AI provider (Anthropic), **real** Gmail (Google API), and **real** Arbeitsagentur search paths remain entirely **UNVERIFIED** in this environment (D7) — not blockers in the sense of a known defect, but a real gap: nothing in this report, or any prior phase's report, constitutes evidence that these three integrations work against live infrastructure. This should be closed out with real credentials and a non-blocked network before calling the product production-ready.

## Recommended Next Actions

1. Fix B1 (add the missing cascade + enable SQLite FK enforcement, which also structurally prevents the D4 latent issues) and add a regression test.
2. Design and add mobile navigation (B2), and root-cause + fix the horizontal-overflow bug (B3), starting with the landing-page hero labels; re-screenshot every page at 375-390px afterward as a verification step, ideally turned into a repeatable check rather than a one-off manual pass.
3. Fix W3 (stop rendering raw exception text to end users — show a generic "couldn't check for replies right now, try again later" and keep the detailed error server-side in logs only).
4. Bundle W4-W7 (the four concrete, cheap accessibility fixes) into a short follow-up pass.
5. Once real Anthropic/Gmail/Arbeitsagentur credentials or a non-blocked network are available, close out D7 with genuine live verification — every AI/Gmail/job-search claim in this project's history has been MOCK/LOCAL VERIFIED at best.
6. Revisit W1 (invitation-code redemption race) with a `with_for_update()` row lock or an atomic conditional `UPDATE`, given it can double-redeem an admin invite.
7. Defer D2-D6 to their already-appropriate phases (8/10) per the table above — no action needed now.

---

## Phase 7 Remediation (2026-08-12)

All three Blocking findings and all nine Worth Fixing Now findings from the QA pass above were fixed in a follow-up pass the same day. Full test suite: **135 passed, 0 failed** (up from the 113/132 baselines at various points in this pass — 22 new tests added, none removed or weakened).

### Blocking fixes

- **B1** — `Document` now cascades (`cascade="all, delete-orphan"`) to its `ApplicationDocument` rows, and SQLite foreign-key enforcement is turned on via an `Engine` `connect` event listener (`PRAGMA foreign_keys=ON`), so this class of orphan-record bug fails loudly in dev/test going forward instead of silently corrupting data. Regression test added.
- **B2** — Built a real mobile navigation: a sticky top bar (logo + hamburger) replaces the hidden sidebar below the `md` breakpoint, opening a slide-over drawer (`app/templates/base.html`) that mirrors every desktop destination, including admin links for admin users. Verified live via Chrome DevTools Protocol (not just reading the JS): `aria-expanded` toggles correctly, focus moves into the drawer on open and back to the trigger on close, Escape closes it, backdrop-click closes it, body scroll locks while open. Static-markup regression tests added (`tests/test_mobile_nav.py`); the dynamic behavior isn't covered by pytest since this project has no in-repo browser-automation harness — see the new `scripts/check_mobile_overflow.py` note below for what *is* now repeatable.
- **B3** — Root-caused: the landing-page hero's percentage-positioned label `<span>`s were, as suspected, the source — fixed the overflow at its origin rather than papering over it with `overflow-x: hidden`. Verified with real mobile-viewport emulation (`Emulation.setDeviceMetricsOverride`, not the `--window-size` CLI flag, which was confirmed during this pass to not reliably constrain the CSS viewport in this environment) that `document.documentElement.scrollWidth` equals the viewport width at 390px on the landing page.

### Worth Fixing Now — all nine addressed

W1 (atomic conditional `UPDATE` for invitation-code redemption), W2 (FK enforcement — same fix as B1), W3 (background-task errors now show a generic message to the user, full detail server-side in logs only), W4 (Wayfinding markers now differ by size/ring-weight/fill, not color alone), W5 (flash messages now carry an icon + `role="alert"`/`aria-live`), W6 (all six previously-unlabeled fields now have proper `for`/`id` associations), W7 (validation errors now `aria-describedby`-linked in the shared macro), W8 (AI prompts now delimit untrusted external text with structural fencing, plus a new adversarial prompt-injection test), W9 (fixed as part of the same B3 root-cause fix and full-page audit below).

### Mobile overflow — full page audit

Beyond the landing page (B3) and application-detail page (W9) called out in the original report, every other authenticated page was checked at 390px for genuine page-level horizontal overflow (`scrollWidth` vs. viewport width, not a visual/screenshot guess): dashboard, candidate profile, documents, job search, saved jobs, applications list, job detail, company detail, application detail, and Gmail integration. **No page-level overflow found on any of them.** (Element-level horizontal scroll inside a wrapped table, e.g. the documents list, is expected/correct behavior and was not flagged.)

This check is now a repeatable script rather than a one-off manual pass, addressing the original report's "ideally turned into a repeatable check" recommendation: **`scripts/check_mobile_overflow.py`** drives a local Edge/Chrome install over the DevTools protocol (no new browser-automation framework, just the already-added `websocket-client` dependency) and asserts real `scrollWidth`-vs-viewport overflow across a configurable list of pages and widths. Run it with the dev server up:
```
python scripts/check_mobile_overflow.py --email you@example.com --password '...'
```

### Screenshots

`screenshots/phase7-remediation/`: landing page and dashboard at 390px (no cutoff), the mobile nav drawer open, and the desktop dashboard at 1280px (confirming the new mobile top bar correctly disappears above the `md` breakpoint and the existing sidebar layout is unaffected).
