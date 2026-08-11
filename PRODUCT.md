# Product — Ausvia

**Your path to Ausbildung.**

## What it is

A private, invitation-only AI-assisted platform that helps people find and
apply for Ausbildung (apprenticeship) opportunities in Germany. The core
promise: tell Ausvia what you're looking for, it searches real sources,
explains why (or why not) an opportunity fits, prepares your application,
and tracks it - while you keep final control over anything sent externally.

## Core workflow

**Discover → Match → Prepare → Apply → Track → Respond → Interview**

Implemented today: Discover, Match, Prepare, Apply (draft/package only, not
send), Track (status/timeline). Respond (Gmail reply tracking + AI-suggested
replies) and Interview (prep) are not built yet - see `ROADMAP.md`.

## Audience

Anyone looking for an Ausbildung in Germany. Particularly useful for
applicants who need help with German-language job postings, requirements,
and application conventions - not designed exclusively around one
nationality or background.

## Access model

Private, invitation-only. Access-code-gated registration (trial/standard/
premium/admin code types with expiry and max-uses), admin-managed. No public
registration, no payments in this version (payments are explicitly out of
scope - handled off-platform if/when needed). The access-code system is
decoupled from payment/plan logic so it can be extended later without a
rewrite (`InvitationCode.code_type` already models trial/standard/premium
tiers independently of any billing system).

## What exists today (see `PROJECT_AUDIT.md` for the full honest breakdown)

- Candidate profile (education, experience, skills, languages, preferences)
- Document library with content-validated uploads
- Job search against a real source (Bundesagentur Jobsuche API) + manual
  URL/text import as a universal fallback
- Duplicate detection across sources
- Deterministic, explainable match scoring (never an AI guess)
- AI-assisted (or template-based, when no AI key is configured) cover letter
  and email generation, grounded only in real profile/job data
- PDF application package assembly
- Application status tracking with a timeline and a mandatory human-approval
  gate before anything is considered "ready"
- Optional Gmail draft creation (architecture needs a redesign before real
  multi-user use - see `PROJECT_AUDIT.md`)
- Admin dashboard: users, invitation codes, job sources, AI usage

## What's explicitly not built yet

Gmail reply tracking/classification, AI-suggested replies, interview
preparation, a persistent AI assistant/chat, notifications, document AI
extraction, company analysis pages, onboarding wizard, saved searches/job
radar, analytics. Full list and reasoning in `PROJECT_AUDIT.md` and
`ROADMAP.md`.

## Non-negotiable product rules

- AI never invents candidate qualifications, experience, or company facts.
  If information is missing, say it's missing.
- No application, and no reply, is ever sent automatically. AI drafts; the
  user approves and sends.
- Every match score is explainable - strengths and gaps, never a bare number.
- External content (job postings, company pages, emails) is untrusted input
  and is never allowed to override system instructions.
