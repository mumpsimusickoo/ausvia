# Job Sources — AUSVIA

## Adapter architecture

`app/jobs/adapters/base.py` defines `JobSourceAdapter` (abstract:
`search()`, `get_job()`, `normalize()`, `check_availability()`) and a
common `NormalizedJob` dataclass every source maps into. The rest of the
app (search, matching, application generation) only ever deals with
`NormalizedJob`/`Job` - never a source's raw shape.

Sources are registered in `app/jobs/adapters/manager.py` and can be
enabled/disabled independently by an admin at `/admin/job-sources` with no
code changes. Ingestion (`app/jobs/ingest.py`) isolates failures per source
- one source erroring never blocks the others or crashes a search.

## Current sources

### Bundesagentur für Arbeit (Jobsuche API) — `ArbeitsagenturAdapter`

Official, free, public API (no account required) behind
arbeitsagentur.de/jobsuche - the same one the site's own frontend uses.
Wraps the pre-existing `jobsearch.py` client. **Known limitation:** this
project's development sandbox gets HTTP 403 from that API - confirmed it's
not a general connectivity issue (other sites reachable fine) and adding
browser-like headers didn't help, so it's almost certainly bot-protection
on datacenter/cloud egress IPs, not a broken key. Per the "never bypass
anti-bot systems" rule, no further evasion was attempted. The adapter's
field-name mapping is therefore a best-effort port of the previously-
working prototype's field names, defensively coded (`.get()` fallbacks,
full raw payload preserved in `JobListing.raw_snapshot` for reprocessing)
but **unverified against a live response**. If results come back
empty/wrong on a normal (non-sandboxed) network, check the raw response
shape first.

### Manual import — universal fallback, not a "source" in the adapter sense

`app/jobs/manual_import.py`: a permitted plain GET request + BeautifulSoup
readable-text extraction, with graceful fallback to manual text paste on
any failure (blocked, unreachable, non-HTML, oversized). Verified working
end-to-end against real pages. This exists specifically so the product
never depends on any single external source being available - explicitly
required by the spec.

Two convenience layers on top, both still one-URL-at-a-time-reviewed, still
never bypassing a block:

- **Bulk paste** (`app/models/manual_import.py`'s `ManualImportBatch`,
  `app/jobs/routes.py`'s `/jobs/import/fetch`): up to 10 URLs pasted at
  once, each fetched independently (one blocked URL doesn't stop the
  others), then stepped through the same single-item review form one at a
  time - never a bulk multi-save.
- **Browser bookmarklet** (`_bookmarklet_href()` in `app/jobs/routes.py`,
  `/jobs/import/bookmarklet`): reads `document.title`/`location.href`/
  `document.body.innerText` directly out of the DOM of whatever page the
  user is already looking at - no request of AUSVIA's own, so nothing for
  a site to block in the first place. Hands the captured data to AUSVIA
  only via a same-origin-safe URL fragment (never sent to any server),
  landing on the same CSRF-protected review form as every other import
  path; nothing saves until the user reviews and submits it.

## Before adding a new source

Per the product directive: verify an official API exists and read its
current documentation before integrating anything. Check auth requirements,
rate limits, licensing/commercial-use restrictions, and whether automated
collection is actually permitted. Use the official API where one exists.
Never bypass CAPTCHAs, authentication, anti-bot protection, or paywalls -
if there's no legitimate way to get a source's data, it doesn't get
integrated; users fall back to manual import for that source.

## Duplicate detection

`app/jobs/dedupe.py` — v1 heuristic: normalized company name (legal-suffix-
stripped, e.g. "Siemens GmbH" → "siemens"), normalized title (strips
"(m/w/d)"-style noise), location, and start date must all match exactly for
two listings to be grouped under one canonical `Job`. Deliberately not
fuzzy/embedding-based yet (see `DECISIONS.md`) - sufficient for one real
source today, upgradeable without touching callers when a second source
makes near-duplicate-but-not-identical postings a real problem.

## Normalized job schema

See `app/jobs/adapters/base.py`'s `NormalizedJob` dataclass and
`app/models/job.py`'s `Job` model for the full field list (title, company,
location, federal_state, postal_code, start_date, application_deadline,
salary, requirements, language_requirements, skills, education_requirements,
contact info, application_url, source metadata).
