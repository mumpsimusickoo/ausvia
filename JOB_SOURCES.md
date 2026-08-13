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

**Correction (confirmed via current community documentation of this exact
endpoint, `bundesAPI/jobsuche-api`): this is not an official API.**
Bundesagentur für Arbeit has never published a developer API for this data
("...bietet die Bundesagentur für Arbeit dafür bis heute keine offizielle
API an" - no official API exists to this day). What `jobsearch.py` calls
is the internal endpoint the arbeitsagentur.de website's own frontend uses
- the `X-API-Key: jobboerse-jobsuche` value isn't a registered per-
developer credential to apply for, it's the same static key that frontend
uses, reverse-engineered and documented by the community. There is no more
official alternative to register for; this is the one access method that
exists, and the adapter already implements it exactly as documented.

**Known limitation, re-diagnosed:** confirmed HTTP 403 from this API,
live-tested from two structurally different networks (this project's
original development sandbox, and separately a residential/business ISP
connection in Morocco) with identical results down to the response body -
a genuine browser-header-spoofed request and a deliberately wrong API key
both produce the exact same blank 403, which rules out the key being
checked/rejected and rules out a simple "flag datacenter IPs" heuristic
(a real residential IP got the same wall). The main arbeitsagentur.de site
and even the actual jobsuche frontend page load completely normally from
the same networks, so this isn't a general connectivity block either. The
most consistent explanation is deliberate anti-automation hardening
specific to this internal, never-intended-for-third-parties endpoint, not
an IP-reputation issue a different host/network would sidestep. Per the
"never bypass anti-bot systems" rule, no further evasion was attempted -
manual import (see below) is the actual working path for this source,
same as any other source that can't be reached programmatically. The
adapter's field-name mapping remains a best-effort port of the previously-
working prototype's field names, defensively coded (`.get()` fallbacks,
full raw payload preserved in `JobListing.raw_snapshot` for reprocessing)
but still **unverified against a live response**, since none has ever
been obtained.

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
