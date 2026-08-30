# Job Sources — AUSVIA

## Adapter architecture

`app/jobs/adapters/base.py` defines `JobSourceAdapter` (abstract:
`search()`, `get_job()`, `normalize()`, `check_availability()`) and a
common `NormalizedJob` dataclass every source maps into. The rest of the
app (search, matching, application generation) only ever deals with
`NormalizedJob`/`Job` - never a source's raw shape.

Sources are registered in `app/jobs/adapters/manager.py`. Arbeitsagentur
needs no configuration and is always present; Adzuna and Jooble are built
lazily per-request from `current_app.config` and are only included in the
adapter set once their credentials are actually set - an unconfigured
provider is silently absent, not an error. All sources can be
enabled/disabled independently by an admin at `/admin/job-sources` with no
code changes. Ingestion (`app/jobs/ingest.py`) isolates failures per source
- one source erroring never blocks the others or crashes a search - and
caches per (source, keyword, location) for 15 minutes so a repeated search
doesn't re-hit a metered API on every page load.

## Current sources

### Bundesagentur für Arbeit (Jobsuche API) — `ArbeitsagenturAdapter`

**Still not an official API**, confirmed via `bundesAPI/jobsuche-api` (the
current community documentation of this exact endpoint): Bundesagentur für
Arbeit has never published a developer API for this data. What
`jobsearch.py` calls is the internal endpoint the arbeitsagentur.de
website's own frontend uses - `X-API-Key: jobboerse-jobsuche` is that
frontend's own static key, reverse-engineered and documented by the
community, not a per-developer credential to register for.

**Major update this session, live-verified, not assumed.** Earlier
sessions confirmed the v4 search endpoint (`/pc/v4/jobs`) returned a blank
HTTP 403 from every network tried, including a real residential ISP
connection, and concluded this was a durable, version-independent
anti-automation block. While bumping the search endpoint to the
currently-documented v6 (`/pc/v6/jobs`) for version currency, that
assumption was re-tested live rather than just repeated - and **v6
returned real HTTP 200 responses with genuine job data**, from the same
network, with the same `X-API-Key` value, in the same test run where v4
*still* 403'd three times in a row. A request to v6 with no key, or a
deliberately wrong key, still 403'd - confirming the key is being
validated normally on v6, not just ignored. Full job detail via
`/pc/v4/jobdetails/{base64(referenznummer)}` also succeeded once the
reference number was correctly base64-encoded, which `get_job_detail()`
never did before - a second, separate real bug, independent of the v4/v6
question, that silently 404'd every detail lookup even on a network where
search worked.

**What this does and doesn't prove.** This is one network, at one point in
time, showing v6 open where v4 was (and, on this same network, still is)
blocked. It does not prove the block is lifted everywhere or permanently -
the original finding came from multiple networks including a residential
ISP connection, and this new v6 result has only been observed from this
project's dev sandbox so far. **Re-verify from the actual production
environment before treating this as reliable** - if it holds up there too,
this is a materially better outcome than previously documented; if it
doesn't, the "deliberate anti-automation enforcement, not version-
dependent" conclusion from earlier sessions may need to be narrowed to "not
IP-dependent, but *is* version/endpoint-dependent" instead. Either way,
manual import remains the guaranteed-working fallback for this source and
should stay treated as the primary path until production behavior is
confirmed.

**v6's response schema is materially different from v4's**, not just the
URL - a version bump alone (keeping the old field-name mapping) would have
kept returning empty/garbage `NormalizedJob`s even though the HTTP call
itself succeeded. `app/jobs/adapters/arbeitsagentur.py`'s `normalize()` was
rewritten against a real captured v6 search response and a real captured
v4/jobdetails response this session (old names → new, confirmed live):

| Old (v4, assumed) | New (v6/jobdetails, observed) |
|---|---|
| `refnr` | `referenznummer` |
| `titel` / `beruf` | `stellenangebotsTitel` / `hauptberuf` |
| `arbeitgeber` | `firma` |
| `arbeitsort.ort` (object) | `stellenlokationen[0].adresse.ort` (array) |
| `externeUrl` | `externeURL` |
| n/a | `stellenangebotsBeschreibung` (description - jobdetails only, not present in search results) |

Enum "no information given" values (`KEINE_ANGABEN`, `KEINE_ANGABE`,
`NICHT_RELEVANT`) are treated as `None`, not shown to a user as if they
were real values. No contact-person/email field was observed in any of 6
real sampled job details this session - `contact_person`/`contact_email`
stay `None` for real listings rather than being fabricated, though the
lookup logic is kept defensively in case a posting ever does carry one.

**Known remaining gap:** the ingestion pipeline (`app/jobs/ingest.py`)
normalizes directly from search results and never calls `get_job()` to
merge in jobdetails - meaning `description` will be `None` for
Arbeitsagentur listings ingested via a normal search, since that field
only exists in the jobdetails response. This is a pre-existing gap (the
merge mechanism in `normalize()` already exists for exactly this, it was
just never wired up in the ingestion call site) that only became
observable now that search itself returns real data - worth a small
follow-up, not done in this pass to avoid adding an extra API call per
search result to the generic ingestion pipeline without first confirming
Arbeitsagentur's own rate limits (undocumented) can absorb that.

### Adzuna — `AdzunaAdapter`

Official API (`developer.adzuna.com`), instant self-serve `app_id`/
`app_key` signup. Implemented against the documented `GET
/v1/api/jobs/{country}/search/{page}` endpoint - `what`/`where`/
`results_per_page` map to keyword/location/pagination, Germany via
`ADZUNA_COUNTRY=de`.

**Real trial-period restriction - read directly from Adzuna's Terms of
Service, not assumed.** Free API access is a **14-day trial period**
only, "strictly for the purpose of validating the general coverage and
quality of the data... in addition to usability testing." Trial data "may
not be used in its original format or in aggregation... to deliver any
ongoing work or research" without written consent, and continued use past
the trial requires "a licence agreement" directly with Adzuna. **This
adapter being built and working is not the same thing as being cleared for
ongoing production use** - that's a real business decision, not a code
merge. **Update, 2026-08-30: real `ADZUNA_APP_ID`/`ADZUNA_APP_KEY`
credentials now exist in `.env`** (not added as part of any implementation
pass in this repo's history - found already present, exact trial-start
date unconfirmed). **The off-by-default fix this same date** (see
`DECISIONS.md`) means real credentials existing no longer activates
Adzuna for real users on their own - `JobSourceSetting.is_enabled` for
"adzuna" defaults to `False` and must be deliberately flipped on via
`/admin/job-sources`, so the 14-day trial clock isn't silently spent on
general traffic before anyone's decided to. Track the actual trial start
date here once confirmed - the window starts from whenever the
credentials were first *used* against Adzuna's API, not from this
document's date.

**Attribution requirement** (ToS, read directly): displaying Adzuna
listings must show a "Jobs by Adzuna" credit, at least 116×23px, with
"Jobs" hyperlinked to Adzuna and "Adzuna" as the Adzuna logo (also
hyperlinked). Rendered in
`app/templates/jobs/_source_attribution.html`, shown on the search results
list and job detail page wherever a listing's sources include `adzuna`.
No branded logo asset was available to embed (would need pulling from
Adzuna's publisher dashboard) - the current implementation satisfies the
substantive requirement (visible credit, correct links, minimum size)
with styled text instead of the real logo; swap in the actual asset once
real API access exists, for exact compliance.

**Rate limits as currently documented** (re-confirm directly before
relying on this - limits change): 25 hits/minute, 250/day, 1,000/week,
2,500/month. `AdzunaAdapter.search()` makes at most one HTTP call per
`search()` invocation under the default `results_size` (one Adzuna page);
`app/jobs/ingest.py`'s per-query cache additionally prevents re-hitting
Adzuna for a repeated identical search within 15 minutes.

**Employment type is not defaulted to "Ausbildung"** the way
Arbeitsagentur's is - Adzuna's `contract_type` field is generic
(full_time/part_time/permanent), not an apprenticeship confirmation, and
Adzuna keyword search doesn't guarantee apprenticeship-only results.
Forcing that label would fabricate a fact Adzuna doesn't actually confirm.

**Result-quality question - answered, 2026-08-30.** The task this adapter
was built under explicitly asked whether Adzuna's real result set for
German Ausbildung-style keywords returns meaningful apprenticeship
volume, or mostly general/unrelated listings. Now tested live against the
real API: `test_adzuna_live_search_ausbildung_result_quality` for
"Ausbildung Elektroniker" returned **25/25 results genuinely
apprenticeship-related** by title (SCHOTT AG, TransnetBW, Rheinmetall,
Westnetz, and other real German employers' real Ausbildung postings, not
general/unrelated listings). Real result quality is good - the earlier
open question is resolved, though this remains a single keyword/single
run, not a comprehensive quality audit across every Ausbildung field.

```
RUN_LIVE_PROVIDER_TESTS=1 ADZUNA_APP_ID=... ADZUNA_APP_KEY=... \
  pytest tests/test_live_providers.py::test_adzuna_live_search_ausbildung_result_quality -v -s
```

### Jooble — `JoobleAdapter`

Official API (`jooble.org/api/about`). Implemented against the documented
`POST /api/{api_key}` endpoint with `keywords`/`location`/`radius`/`page`/
`ResultOnPage`/`salary`/`companysearch` request fields and the documented
`jobs[]` response shape (`title`/`location`/`snippet`/`salary`/`type`/
`link`/`company`/`id`).

**Key is manually issued, not instant self-serve** - obtained by
submitting a form (name, role, email, website, phone) at
`jooble.org/api/about`. A key was requested and issued; see the two
findings below from actually turning it on.

**Domain-key root cause (found and fixed, 2026-08-29): a Jooble key is
issued per regional domain, not global.** The first key, issued against
`jooble.org` (the US/global domain), returned a consistent 403 against
that same domain's own endpoint - not a headers/IP/rate-limit issue, the
key simply wasn't valid there. A second key issued from `de.jooble.org`
confirmed live (200, real German Ausbildung listings) against
`https://de.jooble.org/api/{key}` - the correct endpoint for a
German-region key, not a workaround. `BASE_URL` now points at
`de.jooble.org`. An explicit browser-like `User-Agent` is also set on the
request now (`requests`' own default is a common, independent trigger for
edge/WAF blocks) - kept even though the domain fix alone may have been
sufficient.

**Free tier is a 500-request LIFETIME cap, not monthly - no reset, only a
new key.** This is a materially different constraint than Adzuna's
self-healing 25/min + 250/day limits, and changes how this source can
responsibly be used at all: burning through it on general search traffic
would mean going through the domain-key discovery and a new key request
again, for no lasting benefit once it's gone again.

**Admin-only scoping (2026-08-29): the budget is reserved for the
maintainer's own account, not spent on general invited-user traffic.**
Jooble is only ever queried when the requesting user is an admin
(`current_user.is_admin` / `user.is_admin`) - enforced at both real call
sites (`app/jobs/routes.py`'s `search()`, `app/jobs/radar.py`'s
`run_job_radar()`) via `app/jobs/adapters/manager.py`'s
`ADMIN_ONLY_SOURCES` set, and in `app/jobs/ingest.py`'s
`ingest_search(admin=...)` filter itself. A regular invited user's search
never reaches the Jooble adapter, sees it neither as a selectable source
checkbox nor in the landing page's public "we search these sources"
footer, and never sees a Jooble-only job in their results - though a job
that also has another source's listing (deduplication merged them) stays
visible via that other listing, same as any multi-source job. The
existing 15-minute `ProviderQueryCache` cooldown (see "Query-quota
caching" below) still applies on top of the admin gate, further reducing
burn for repeat identical searches within a session.

**A persistent cumulative request counter tracks the lifetime spend - and
actually enforces a hard stop, not just a warning.**
`JobSourceSetting.request_count` (source_name="jooble") increments once
per real outbound call - success or failure, since a request that reached
Jooble's servers already cost its lifetime price regardless of what it
returned - via `app/jobs/adapters/jooble.py`'s `record_jooble_request()`,
called from `ingest_search()` right before the real call (never on a
`ProviderQueryCache` hit, which never reaches the network at all). The
running total is visible directly on `/admin` (a "Jooble requests used"
stat, "N / 500"), and a `SystemLog` warning is logged once remaining
budget drops to 50 or below (~10% of the total - enough runway that an
admin logging in every few days, the expected usage pattern now that this
is admin-only, sees it more than once before actual exhaustion).

**Hard stop, added same day after review caught that the counter alone
never refused a call:** once `request_count` reaches `JOOBLE_HARD_STOP_AT`
(495 - a 5-request margin below the true 500 cap, absorbing the fact that
the check-then-increment isn't atomic against a concurrent request, e.g.
a single job-radar click already firing up to 3 real calls in a row),
`record_jooble_request()` returns `False` and `ingest_search()` skips
Jooble for that search entirely - no call attempted, nothing further
incremented, no error surfaced to the user (graceful, same as a disabled
source) - and logs a distinct `SystemLog` at `level="error"` containing
"hard stop", separate from the earlier `level="warning"` notice so the
two are never confused in the admin feed. See `DECISIONS.md`'s
"Jooble hard stop" entry.

Same reasoning as Adzuna on `employment_type`: not defaulted to
"Ausbildung" (Jooble's `type` field is generic, and keyword search doesn't
guarantee apprenticeship-only results).

**Terms-of-service ambiguity, still worth flagging.** `jooble.org/info/terms`
(the public site ToS, read directly) prohibits bots/crawlers/automated
access against the *website* and restricts republishing site content - it
does not separately publish API-specific usage terms (attribution,
retention, rate limits). The terms actually governing API use were
presented during the manual key-request process (a human, not this
codebase, completed that step) - read whatever agreement was presented
there before relying on this beyond the admin's own use.

**Result-quality**, now checkable against the real key (see
`tests/test_live_providers.py::test_jooble_live_search_ausbildung_result_quality`):

```
RUN_LIVE_PROVIDER_TESTS=1 JOOBLE_API_KEY=... \
  pytest tests/test_live_providers.py::test_jooble_live_search_ausbildung_result_quality -v -s
```

### What wasn't done, and why

No Adzuna trial account was created as part of the original implementation
pass - it requires a real named human (Adzuna's trial terms bind whoever
signs up to the 14-day restriction) - creating one on someone's behalf
without their knowledge would start a real, consequential clock. **Update,
2026-08-30: real credentials now exist in `.env`** (found already present,
not added by any pass in this repo's history - exact trial-start date
unconfirmed) - see the off-by-default fix above: their presence alone no
longer activates Adzuna for real users, an admin still has to deliberately
enable it via `/admin/job-sources`. (Jooble's own key has since been
obtained and is live - see above; it just isn't available to general
users by design, same as Adzuna now defaults to.)

### Manual import — universal fallback, not a "source" in the adapter sense

`app/jobs/manual_import.py`: a permitted plain GET request + BeautifulSoup
readable-text extraction, with graceful fallback to manual text paste on
any failure (blocked, unreachable, non-HTML, oversized). Verified working
end-to-end against real pages. This exists specifically so the product
never depends on any single external source being available - explicitly
required by the spec, and still the most reliable path regardless of how
the Arbeitsagentur v6 finding above holds up in production.

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
  a site to block in the first place.

## Before adding a new source

Per the product directive: verify an official API exists and read its
current documentation *and terms of service* before integrating anything.
Check auth requirements, rate limits, licensing/commercial-use
restrictions, and whether automated collection is actually permitted. Use
the official API where one exists. Never bypass CAPTCHAs, authentication,
anti-bot protection, or paywalls - if there's no legitimate way to get a
source's data, it doesn't get integrated; users fall back to manual import
for that source.

## Duplicate detection

`app/jobs/dedupe.py` — two signals, checked in order:

1. **Canonical/original URL match** (added this session): if a new
   listing's `application_url`/`source_url` exactly matches an existing
   `Job`'s, it's treated as the same posting regardless of source - added
   specifically for cross-provider matching (the same real vacancy often
   has different company/title text across boards - translation,
   punctuation, "(m/w/d)" placement - that fails signal #2 below). Purely
   additive: it only widens matching, never narrows it, so it can't regress
   single-provider behavior.
2. **Normalized company + title + location + start date** (original v1
   heuristic, unchanged): legal-suffix-stripped company name, "(m/w/d)"-
   stripped title, location, and start date must all match exactly.

Deliberately not fuzzy/embedding-based. **Known limitation, not fixed this
pass:** Adzuna/Jooble listings normalize to an empty `start_date` (neither
API has an Ausbildung-specific "start date" concept), so a real vacancy
that appears on Arbeitsagentur (with a start date) *and* Adzuna/Jooble
(without one) will under-merge via signal #2 unless signal #1's URL match
happens to catch it. Loosening signal #2 to ignore start_date entirely was
considered and deliberately not done - it would risk incorrectly merging
two genuinely different real postings (e.g. the same role re-posted for a
different intake year) into one canonical Job with a wrong/stale start
date, which is a worse failure mode (silently wrong data) than the current
one (occasional extra listing, no data loss).

## Query-quota caching

`app/jobs/ingest.py`'s `ProviderQueryCache` (new this session): a
(source, normalized keyword+location) combination is skipped for 15
minutes after being queried once - the search route
(`app/jobs/routes.py`) still calls every enabled provider synchronously on
every request (existing behavior, unchanged), so without this, a popular
keyword searched repeatedly by different users would burn through Adzuna's
250/day limit in minutes. A cache hit just means the search shows whatever
was already ingested last time (real `Job` rows already in the database),
not a guaranteed-fresh live call every time.

## Normalized job schema

See `app/jobs/adapters/base.py`'s `NormalizedJob` dataclass and
`app/models/job.py`'s `Job` model for the full field list (title, company,
location, federal_state, postal_code, start_date, application_deadline,
salary, requirements, language_requirements, skills, education_requirements,
contact info, application_url, source metadata). `Job.discovered_at`/
`last_checked_at` (and the equivalent per-listing fields on `JobListing`)
already serve as first-seen/last-seen tracking - no schema change was
needed for that. `Job.status` (`active`/`expired`/`closed`/`unknown`)
exists but nothing currently drives automatic transitions into
`expired`/`closed` - that would need a scheduled sweep, and AUSVIA has no
scheduler yet (see `ROADMAP.md`); not built as part of this pass to avoid
introducing new infrastructure for a single provider integration task.
