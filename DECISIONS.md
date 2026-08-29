# Decision Log — AUSVIA

Each entry: decision, reason, alternatives considered, consequences. Newest
first. Don't reopen a settled decision without new evidence — see entry
format below for what was actually weighed.

---

## 2026-08-29 — i18n pass 3 resolve: dashboard_insight and process_qa join the "follows UI language" bucket, plus a LazyString sweep and a quota-blocked reply-suggestion verification

**Resolved, not left open: `dashboard_insight.py` and `process_qa.py`
both belong in the "follows UI language" bucket**, same as match
explanation/company insight/profile coaching/interview prep/CV profile
statement. Confirmed by tracing the actual call chain, not assumption:
`generate_dashboard_insight()` is called from `app/main/routes.py` and
its `summary_text` is rendered directly on the Dashboard via
`intelligence_surface()` - the identical component company insight and
profile coaching already use, in the identical "Erkenntnis erzeugen /
Regenerate" pattern. `generate_process_qa_answer()` is called from
`app/profile/routes.py` and its `answer_text` is rendered in the
Candidate Profile screen's "Common questions" section, next to a
"Show answer" button. Both are unambiguously candidate-facing, on two of
the highest-traffic screens in the app - there was never a real "maybe
internal-only" case to make for either.

**Current (pre-fix) output language checked by inspection and live
testing, not assumed:** neither prompt (`app/ai/prompts/dashboard_insight.py`/
`process_qa.py`) had any language instruction at all - the same missing-
instruction pattern found and fixed in company insight/profile coaching/
interview prep during the original pass 3 sweep. For process_qa
specifically, `question_text` was already locale-aware (`PROCESS_QA_
QUESTIONS`, an `_l()`-wrapped dict from i18n pass 2) - a German UI
already showed a German question, but the answer's language was left to
the model's own inference from that question, not explicitly instructed.
Live-tested before this fix: generating an answer under English UI, then
switching to German UI and reopening the same question, showed the
question text in German with its own cached answer still in English -
the same missing-locale-in-cache-key bug already found and fixed in the
other five features, now confirmed here too rather than assumed to be
absent. (The rate-limited free-tier Gemini quota that later blocked
further live testing this session - see below - prevented capturing a
second, from-scratch generation under German UI as additional evidence,
but the cache-staleness bug alone is conclusive: the pre-fix code had no
mechanism to notice a locale change at all.)

**Wired the same way as the original five:** both prompt builders now
take an explicit `locale` argument and append `app/ai/language.py`'s
`language_instruction()`; both orchestration functions call `get_locale()`
internally (no route changes); both models gained a `generated_locale`
column (migration `b00ad196d445`) checked alongside their existing
staleness signals (`profile_updated_at_snapshot` for both,
`application_count_snapshot` additionally for `DashboardInsight`).

**Grounding-validator check, per the same standard applied to CV profile
statement: neither has a hardcoded-language validation assumption,
because neither has a second validation pass at all.** Both are single-
pass generation (`provider.complete()` called once, response stored
directly) - the same shape as match explanation, company insight, and
profile coaching, not the two-pass generate-then-validate shape unique to
cover letter and CV profile statement. Nothing to fix here beyond the
language instruction itself.

**A closed pass-2 gap, not a new pass-3 mistake, found while in these two
files:** both `NOT_CONFIGURED_TEXT` mock-decline messages were still
plain hardcoded English strings, never wrapped in `_l()` at all - the
same gap already found and closed in four sibling features during the
original pass 3 pass. Fixed the same way: `_l()` at definition, `str()`
at the assignment site (the `LazyString`-can't-bind-to-SQLite bug from
i18n pass 2, recurring in the exact same shape).

**Full `LazyString`→non-string-sink sweep, as requested - result: no
further instances found.** Every `_l(` call site in the codebase was
enumerated and traced to its destination. The dangerous pattern (a
module-level `_l()` constant or dict value assigned *directly*, with no
intervening `str()`/`%`-formatting, to a SQLAlchemy column) existed in
exactly eight places total: the original `NOT_CONFIGURED_NOTE` (i18n pass
2), the four `NOT_CONFIGURED_TEXT`/`NOT_CONFIGURED_REPLY` constants closed
in the original pass 3 sweep, `NARRATIVE_NOT_CONFIGURED_TEXT`/`TIPS_
NOT_CONFIGURED_TEXT` (added and already `str()`-wrapped correctly in that
same pass), and the two closed in this entry - all eight now fixed.
Every other `_l(` call site in the codebase is one of two safe shapes,
confirmed by tracing each to where its value is actually consumed: (1) a
WTForms field label or `SelectField` choice label (`app/*/forms.py`) -
rendered via `field.label`/the `<option>` text in a template, never
itself the value that gets validated and stored (the submitted form
*value* is always the plain code string); or (2) a display-label dict
(`APPLICATION_STATUS_LABELS`, `DOCUMENT_TYPE_LABELS`, `REPLY_INTENT_
LABELS`, `CHECKLIST_LABEL_TRANSLATIONS`, `_COMPLETENESS_PHRASING`,
`STATION_LABELS`, `PROCESS_QA_QUESTIONS`) whose values only ever flow
into a Jinja template (`{{ label_dict[key] }}`, safely stringified by
Jinja's own rendering) or into an *immediate* `gettext()`/`_()` call's
`%`-placeholder substitution (which resolves the `LazyString` to a plain
`str` via Python's own `%`-formatting before the result - already a
plain string - reaches `flash()`) - never a bare assignment to a model
attribute. No sweep finding required a code change beyond the two already
fixed above.

**Reply suggestion: attempted live re-verification, blocked by a real,
external constraint, not skipped.** Built a synthetic-but-realistic
Gmail reply (a real `GmailMessage` row on a real `Application`, exactly
the shape `app/ai/reply_ai.classify_reply()`/`generate_reply_suggestion()`
expect - no code changes needed to exercise it, confirming a mocked
reply genuinely can stand in for a real Gmail-sourced one for this
purpose) and called `generate_reply_suggestion()` against it with the
*real* configured provider (not `FakeProvider`). It failed with
`google.genai.errors.ClientError: 429 RESOURCE_EXHAUSTED` -
`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, the same daily quota
this session's UI testing had already hit earlier (visible in the browser
as "AI provider is rate-limited right now."), not something introduced
by this pass. Test data cleaned up; no orphaned rows left behind. Given
the quota is account-wide and daily (not a short burst), no further real-
provider verification was possible in this session. What stands instead,
already true before this entry: `tests/test_ai_prompt_injection.py::
test_reply_suggestion_prompt_fences_adversarial_company_message` asserts
the exact fixed `REPLY_SYSTEM` German-mandating constant is what's sent,
byte-for-byte, with no locale branching anywhere in `build_reply_prompt()`
- verified by the type system and a direct equality assertion, not
inferred from the file's shape - and `tests/test_reply_ai.py`'s existing
mock/fake-provider tests confirm the orchestration path stores whatever
the provider returns without alteration. Reply suggestions remain
unconditionally German by construction; a real-model confirmation that
the *model itself* honors that system prompt is the one piece of
evidence this session could not obtain, the same open item every other
already-live-verified feature in this app implicitly carries (a prompt
can only be proven "sent correctly"; whether the model complies is never
fully provable without spending a real call, and this session's quota
ran out before reply suggestion got one).

**Full pytest suite: 588 passed / 3 skipped (586 + 2).** Two new tests
added (`test_dashboard_insight_regenerates_when_ui_locale_changes`,
`test_process_qa.py::test_regenerates_when_ui_locale_changes`), same
locale-cache-invalidation shape as the original pass 3's narrative/
CV-profile-statement tests, using `FakeProvider` (no quota spent).

---

## 2026-08-29 — i18n pass 3: the AI content language split, a CV-statement bucket reassignment, and two real bugs (a shared mock message, a LazyString/SQLite crash)

**The split (restated, not rediscovered - this was the given spec):**
cover letter, application email, and reply suggestions stay German
unconditionally - real German-employer-facing text, where an English
document simply fails, not a translation-quality question. Match
explanation/improvement tips, company insight, profile coaching,
interview prep, and CV profile statement follow the session's UI locale -
content written for the candidate, not an employer. Job posting data, the
CV PDF export, and `app/ai/matching.py`'s deterministic scoring functions
are untouched by this pass, confirmed by inspection, not just left alone
by assumption - the second one specifically because pass 2 already fixed
a real mixed-language bug there (English gap sentences mid-German
sentence, from mistaking it for AI-content scope) and touching it again
here would be exactly the scope confusion that bug came from.

**Locale reaches every prompt builder through `app/i18n.py`'s
`get_locale()`, called once inside each orchestration function
(`generate_narrative()`/`generate_company_insight()`/etc.), never as a
parameter threaded through route handlers.** All five call sites into
these features (`app/jobs/routes.py`, `app/companies/routes.py`,
`app/profile/routes.py`, `app/applications/routes.py` x2) needed zero
changes - the same "session/g state, not an ad-hoc parameter" pattern
i18n pass 1/2 already established for every other locale-aware helper.
A shared `app/ai/language.py` helper (`language_instruction(locale)`)
builds one line appended to each "follows" feature's system prompt,
naming the target language explicitly rather than leaving the model to
infer it from a prompt that now mixes hardcoded-English instructions
with locale-aware (German-or-English, per i18n pass 2) fact strings -
unreliable inference was the actual mechanism behind the bug pass 2 found
in the matching engine, and this pass's whole job is to not repeat that
pattern anywhere else.

**CV profile statement moves buckets: it used to hardcode German
unconditionally, and now follows the UI language - a real behavior
change, not just a wrapping exercise.** Given by the spec, and correct on
inspection: unlike the cover letter/email/reply, this text is never
submitted anywhere by AUSVIA itself (`app/ai/cv_profile_statement.py`'s
own docstring: "purely informational... the user copies this text into
their own separately maintained CV") - it's advisory content shown to the
candidate, same as profile coaching, not a document going to a German
employer. Both its generation prompt and its validation prompt
(`app/ai/prompts/cv_profile_statement.py`) needed the change - the
validation prompt used to hardcode "check for German grammar/spelling
errors" unconditionally, which would have silently misfired (checking
English text against German grammar rules) the instant this stopped
always producing German. Now takes the target language name as a
template parameter, generated from the same `locale` passed to
generation, so the two passes can never disagree about which language the
text is supposed to be in.

**Cache staleness now has a locale dimension, not just a profile-edit
dimension - real schema change, six new columns, one new migration
(`d0a13f3299ee`).** `JobMatch.narrative_locale`/`improvement_tips_locale`
(tracked separately - they're generated and cached independently) and
`CompanyInsight`/`ProfileCoaching`/`InterviewPrep`/`CvProfileStatement`'s
new `generated_locale` column are checked alongside the existing
`profile_updated_at_snapshot` staleness check in every orchestration
function: a cached English narrative is not served to a session that has
since switched to German, and vice versa. This was a genuine design
decision, not mechanically required by "thread locale into the prompt"
alone - the alternative (only checking locale at generation time, never
at cache-read time) would satisfy "the feature is *capable* of producing
either language" while still silently serving stale-language content on
every subsequent view after a language switch, which contradicts the
spec's own framing of "follows the UI language" as a live property of the
session, not a one-time choice frozen at first generation. The existing,
already-accepted staleness pattern (a manual "Regenerate" control, no
automatic re-generation) still governs *content* staleness on unrelated
changes (a job's own facts changing doesn't auto-invalidate its
narrative, unchanged from before this pass) - only the locale axis is new
here, and only affects whether the *cached* text is trusted, not whether
regeneration happens automatically.

**A real, previously-invisible bug found by this pass's own verification
step, not by inspection:** `app/jobs/matching.py`'s
`generate_narrative()`/`generate_improvement_tips()` were the only two AI
orchestration functions in the whole codebase that never special-cased
mock mode - every sibling feature (`CompanyInsight`/`ProfileCoaching`/
`InterviewPrep`/`CvProfileStatement`/`reply_ai.py`) declines honestly with
its own locale-aware message when no AI provider is configured; these two
silently fell through to `MockAIProvider`'s own generic, hardcoded-English
`NOT_CONFIGURED_MESSAGE` regardless of locale. Verifying "generate once in
English, once in German" for match explanation under mock mode would have
returned identical English text both times - caught directly by that
required verification step, not found by reading the code first. Fixed by
giving both functions their own honest, locale-aware decline text
(`NARRATIVE_NOT_CONFIGURED_TEXT`/`TIPS_NOT_CONFIGURED_TEXT`), matching
every sibling feature's pattern - `MockAIProvider.NOT_CONFIGURED_MESSAGE`
itself is untouched, since (checked directly) these two were its only
callers; every other feature already intercepts before reaching it.

**A deferred i18n pass 2 gap closed here, not a pass-3 mechanism bug:**
`app/ai/cv_profile_statement.py`, `interview_prep.py`, `profile_coaching.py`,
`app/companies/insights.py`, and `app/ai/reply_ai.py`'s `NOT_CONFIGURED_REPLY`
each had their own hardcoded-English "AI feature isn't available"
fallback message, none of them wrapped in `_()`/`_l()` during i18n pass 2
- a real miss, not a deliberate exclusion (nothing in pass 2's report
flagged these as out of scope). Fixed alongside this pass's own changes
to the same functions, using the same `_l()` + `str()`-at-assignment
pattern pass 2 established for `app/ai/reply_ai.py`'s
`NOT_CONFIGURED_NOTE` (a bare `LazyString` can't bind to a SQLite column -
see pass 2's entry). `NOT_CONFIGURED_REPLY` specifically was left
deliberately untranslated in pass 2 - `ai_suggested_reply` also holds
real AI-drafted replies, which stay German unconditionally, and "what
language does the *fallback* in this shared field follow" was explicitly
deferred to this pass rather than guessed at in pass 2. Resolved now:
follows the UI language, since the fallback is a status message about the
tool's own capability, shown to the candidate, not text sent to an
employer - consistent with `NOT_CONFIGURED_NOTE`'s existing treatment of
the same distinction.

**A second real bug, found by the full pytest suite, not by manual
testing:** giving `NOT_CONFIGURED_TEXT` (`app/ai/cv_profile_statement.py`)
the same `_l()` treatment and assigning it directly to a model column
raised `sqlite3.ProgrammingError: Error binding parameter 3: type
'LazyString' is not supported` - the identical bug pass 2 found and fixed
in `app/ai/reply_ai.py`'s `NOT_CONFIGURED_NOTE`, recurring here because
each of these five sibling constants needed the same fix independently
applied, not inherited from a shared base. Fixed the same way: an
explicit `str(...)` at the assignment site, still inside the active
request (correct locale already resolved at that point).

**Grounding validation: no language-dependent string matching found in
any of the five "follows" features, and the one place that pattern
exists elsewhere is unaffected by this pass.** Four of the five
(narrative/improvement tips, company insight, profile coaching, interview
prep) have exactly one validation layer - the system prompt's own
anti-hallucination instructions - not the "two-layer" shape stated in
this pass's own brief; only CV profile statement (like cover letter) has
a genuine second, separate AI validation pass, and it's model-based, not
string-matching against the generated text, so it carries no language-
dependency risk beyond the "which language's grammar are we checking"
issue already fixed above. The one real load-bearing *string-matching*
grounding check in the codebase -
`app/ai/job_requirements_extraction.py`'s `_validate_and_ground()`, which
checks extracted skills/languages/contact details are literal substrings
of the source posting text - belongs to a feature this pass explicitly
doesn't touch (job posting data, never a language-generation question),
and both sides of its comparison are always the source posting's own
German text regardless of UI locale, so it has no exposure to the
language-dependency risk this pass was asked to watch for.

**Nine features exist in `app/ai/prompts/`, not eight - the extra four
are deliberately untouched, flagged rather than silently absorbed into
either bucket:** `followup_email.py` shares cover letter/email's
unconditional-German shape exactly (a real follow-up email a candidate
could send) and needed no code change, just confirmation. `dashboard_
insight.py` (cross-application synthesis) and `process_qa.py` (answers to
a fixed set of process questions) are structurally the same shape as the
five "follows" features - written for the candidate, not an employer -
but weren't named in this pass's brief, so they're left exactly as pass 2
found them (English-only) rather than assumed into scope. `job_
explainer.py` calibrates its own output language to the candidate's
*stated German proficiency level* (A1/A2 candidates get English with
glossed German terms; B1+ get plain German) - a deliberately different,
orthogonal signal from the UI locale toggle, already correct on its own
terms and not something this pass's "follows the UI language" framing
should be applied to without a separate decision. All four are real,
working features; none were miscategorized, they simply weren't part of
what was asked this time.

**Verification: all eight named features confirmed via live generation
against the real configured provider (Gemini), not mocked** - each of the
five "follows" features generated once with the session in English, once
in German, for the same underlying profile/job/company data, with the
"Regenerate" control forcing a fresh call past the new locale-aware cache
each time; each of the three "always German" features confirmed via live
regeneration under an English-locale session (cover letter regenerated
fresh, English UI, German output, unchanged from before - the two
locale-following fields on the same page, the cover letter's own
validation status message and the freshly-generated CV profile statement,
correctly rendered in English in the same request, proving the two
mechanisms coexist correctly on one screen). One incidental register
observation, not a bug: the AI's own formality choice for German output
varies between the informal "du" the rest of the app's copy uses and the
formal "Sie" a real cover letter correctly uses - company insight and
profile coaching both landed on "Sie" in testing, which is grammatically
correct but inconsistent with the app's own established tone elsewhere.
Nothing in the prompt currently specifies a register for the "follows"
features (only the always-German prompts specify "Sie-Form", correctly,
since those go to an employer) - a real, scoped follow-up (add an
explicit "du" instruction to the five "follows" system prompts) if it's
judged worth the model-behavior risk of changing working prompt text for
a tone preference, not fixed in this pass. Full pytest suite: 586 passed
/ 3 skipped (583 + 3 - two new tests confirming the locale-cache
invalidation in `app/jobs/matching.py`'s narrative generation plus its
own honest mock-decline path, one confirming the same for CV profile
statement's two-pass generate-then-validate flow).

---

## 2026-08-28 — i18n pass 2: mass string extraction, a matching-engine gap fixed beyond its original scope, and a stale-catalog gotcha for every future translation change

**Scope: every in-scope template and Python module now wraps its
user-facing strings in `_()`/`_l()`/`ngettext()`**, group by group (shared
components, auth, dashboard/digest, jobs, applications, profile/documents,
company, landing, errors, integrations, admin), each followed by its own
`pybabel extract`/`update`/translate/`compile` cycle rather than one
extraction at the end - see the pass's own report for the per-template
count. Still out of scope, unchanged from pass 1: `app/ai/prompts/*`
(prompt builders) and any text an AI provider itself generates (cover
letter body, application email body, reply suggestions, match narratives,
company insight, interview prep, CV profile statement) - that's pass 3's
per-feature language split, not this pass's. Job posting data
(titles/descriptions/requirements/company names) stays untranslated for
the same reason as pass 1: translating a posting would misrepresent the
source. Internal audit content (`log_event()` messages, and raw internal
codes like `InvitationCode.code_type`, `User.role`/`User.plan`,
`JobSourceSetting.last_run_message`) is deliberately left untranslated -
it's operator/log content, not product copy, and translating it would
make server-side logs harder to grep, not easier to read.

**One deterministic-content case turned out to be in scope after all,
despite an earlier in-pass note that deferred it:** `app/ai/matching.py`'s
five scorer functions (`_score_skills`/`_score_language`/`_score_education`/
`_score_location`/`_score_start_date`) build the strengths/gaps sentences
behind every match card's summary line and the Job Detail breakdown -
plain Python string formatting, never an LLM call (the module's own
header comment: "never guessed by an LLM"). A first pass through this
file left them alone with a comment promising a "separate follow-up in
DECISIONS.md," on the theory that anything living under `app/ai/` was
pass-3 territory. Live verification in German surfaced why that line was
wrong: every job card on the Find Ausbildung results page rendered a
sentence like *"Startdatum erfüllt · Neckarsulm is outside stated
preferences and candidate is not open to relocation."* - German
category name, English gap sentence, mid-sentence, on the single
highest-traffic screen in the app. That's not an AI-content-language
question (pass 3's actual remit); it's the same class of miss as every
other deterministic-string gap this pass exists to close, just filed
under the wrong directory. Fixed by wrapping all five scorers' strength/
gap/label/note strings in `_()` with proper `%(name)s` placeholders (raw
job-posting substrings inside them - skill names, location names - stay
untranslated, same rule as everywhere else job data appears). The
no-longer-accurate "deferred, see DECISIONS.md" comment in
`app/jobs/matching.py`'s `summarize_match_line()` was corrected in the
same commit rather than left stale.

**A real, previously-unseen Flask-Babel gotcha: the compiled `.mo`
catalog loads once per process and never reloads on its own** - distinct
from pass 1's documented `g`-scoped per-request locale cache
(`ctx.babel_locale`), which is a different mechanism, already covered
above, and unaffected by this. Editing `translations/de/LC_MESSAGES/
messages.po` and re-running `pybabel compile` rewrites the `.mo` file on
disk, but a Flask process that already parsed a translation into memory
keeps using that in-memory copy for the rest of its life - confirmed by
reproducing the exact symptom this pass hit: after several
extract/translate/compile cycles against a dev server that had been
running since the session started, some `_()` calls translated correctly
(whatever was in the catalog the first time that locale's `.mo` got
loaded) while others - added in later cycles - kept rendering their raw
English `msgid`, all on the same page, in the same request. Not a `g`
cache issue (that resets every request); this one only clears on process
restart. Jinja **templates** don't have this problem (Flask's debug-mode
autoreloader checks template mtimes per render), which is exactly why
this went unnoticed through most of the pass - only catalog (`.po`/`.mo`)
edits are affected. Practical consequence, worth restating in
`DEPLOYMENT.md`'s existing Translations section: a Railway deploy that
ships a `.po`/`.mo` change needs an actual process restart to take
effect, same as the deploy already needs one for compiled CSS - a `git
push` alone that doesn't restart the running dyno would silently ship
stale translations, indistinguishable from the extraction/compile step
having been skipped entirely.

**A real SQLAlchemy/sqlite3 binding bug, not a translation-content bug:**
`app/ai/reply_ai.py`'s `NOT_CONFIGURED_NOTE` is a module-level
`lazy_gettext()` constant (correct - it's evaluated once at import time,
long before any request exists, so it must be lazy, same reasoning as
`APPLICATION_STATUS_LABELS` and friends). Assigning it directly to
`GmailMessage.classification_notes` and committing raised `sqlite3.
ProgrammingError: Error binding parameter 3: type 'LazyString' is not
supported` - found by the full pytest suite, not by manual verification,
since it only manifests on an actual DB write, not on template rendering
(Jinja/`str.format` coerce a `LazyString` to text transparently; the
sqlite3 DBAPI does not). Every other `_l()`-wrapped module constant in
this codebase is either rendered directly in a template or used as a
dict-lookup value for display - this was the only case of one being
written to a database column, which is why the bug didn't surface until
this specific call site. Fixed with an explicit `str(NOT_CONFIGURED_NOTE)`
at the assignment site, still inside the active request (correct locale
resolved at that point) - not by making the constant eager, which would
have frozen it to whichever locale happened to be active when the module
was first imported.

**Admin group: five real operator screens translated
(`admin/overview.html`, `codes.html`, `users.html`, `job_sources.html`,
`ai_usage.html`, plus their routes/forms) - `admin/components.html` and
`diagnostics/arbeitsagentur_cors_test.html` deliberately excluded, not
silently skipped.** The five are screens an admin actually operates from
day to day, same standard as every other screen this pass covers.
`admin/components.html` is the component-layer's own living reference
page (its own header comment: "Nothing on this page is wired to real
data or a real route"), deliberately mixing English descriptive
prose with German fixture strings as demo content - translating the
English half would not make it more correct, since the page's job is to
document the component layer for whoever builds the next screen, not to
be used by an end operator. `diagnostics/arbeitsagentur-cors-test` is an
unauthenticated, unlinked, explicitly temporary route (its own comment:
"Remove this route + its template ... once the finding is confirmed
either way") - not a surface worth translating before it's deleted.

---

## 2026-08-28 — i18n pass 1: English supersedes the bundle's bilingual rule, locale storage architecture, and a real Flask-Babel path bug

**English is the default UI language, with a real switcher for full locale
switching. This explicitly and deliberately supersedes the AUSVIA 2.0
bundle's own stated rule** (`AUSVIA_2_0_SCREEN_INVENTORY.md` section 0.1:
*"Beschriftungen bleiben in der Sprache der Anwendung, Fließtext ist
deutsch"* - English labels, permanently-German prose, mixed on every
screen forever). That rule was never implemented and is not the target
here - recorded explicitly so a future cold session that reads the
Foundations brief on its own doesn't "correct" the app back toward the
bundle's mixed-language model, believing this pass's actual output to be
a regression from the spec. **AI-generated content language is a
separate, per-feature axis from the UI language toggle, deferred to pass
3, not decided or built this pass:** cover letter / application email /
reply suggestions stay German always (they go to real German employers -
an English Anschreiben fails outright); match explanation / company
insight / profile coaching / interview prep / CV profile statement follow
whichever UI language the viewer has chosen (content for the user, not
for an employer); job posting data (titles/descriptions/requirements)
is never translated, since translating a posting would misrepresent what
the source actually said. Nothing in this pass touches an AI prompt.

**Why three passes, not one:** a half-extracted set of templates is
recoverable (some copy is still English, nothing is broken) - a
half-configured Babel setup is not (the app either resolves and renders
translations correctly end-to-end, or it silently doesn't). Pass 1 is
infrastructure + the switcher, proven end-to-end on a small number of
strings; pass 2 is mass string extraction across every other template;
pass 3 is wiring the AI-content language split above into the real prompt
builders. This entry covers only pass 1.

**Locale storage: `User.locale` for a logged-in visitor, a cookie for a
logged-out one - not a choice between them, a convergence.** The landing
page has no user, so a cookie is required regardless; the question worth
answering was whether the account column earns its keep given that cost.
It does, cheaply: `User.locale` (`String(5)`, `NOT NULL`, `default="en"`)
has existed, completely unused, since `c4d57a2bd219` - the very first
migration - so wiring it up needed no new migration, nothing to flag for
Railway. Cross-device continuity (a preference set on one browser
reappearing after logging into the same account on another) is a real,
free benefit once the column exists; a cookie alone can't do that. The
two sources converge at the auth boundary
(`sync_explicit_locale_to_user()`, called from both `login()` and
`register()`, `app/auth/routes.py`): if the browser carries an explicit
locale cookie at the moment of login or registration, it's written into
the account, overriding whatever the account already held (its own prior
choice, or - for every pre-i18n account - the untouched schema default).
Without this, "the choice survives login" (a required verification
state) would fail the instant `current_user.is_authenticated` starts
outranking the cookie in `get_locale()`'s priority order - an existing
account's stale "en" default would silently override a real anonymous
choice the moment a session exists. `get_locale()` itself
(`app/i18n.py`) therefore trusts `current_user.locale` unconditionally
once authenticated - not because a fresh login re-derives anything, but
because sync already ran first, and the column is never in an
indeterminate state (always a real, valid code) to begin with.

**Accept-Language is consulted only when there's no cookie at all**, not
recomputed on every anonymous request regardless of a prior explicit
choice - the tier boundary that matters is "has this visitor ever made an
explicit choice," not "is a session cookie technically still fresh." A
visitor who explicitly chose English is never silently flipped back to
German by their own browser's header on a later visit.

**A real bug found and fixed before anything shipped:**
`BABEL_TRANSLATION_DIRECTORIES` was first set to the bare string
`"translations"`. Flask-Babel resolves a relative translation-directory
path against `app.root_path` - which for this app is `app/` (the package
`Flask(__name__)` was constructed with, since `create_app()` lives in
`app/__init__.py`), not the repository root where `translations/` and
`babel.cfg` actually live alongside `tailwind.config.js`. The bug was
silent, not a crash: Flask-Babel found no catalog at the resolved (wrong,
nonexistent) path and fell back to `NullTranslations`, so every `_()`
call kept returning its English `msgid` verbatim regardless of which
locale `get_locale()` correctly resolved to - the switcher looked like it
worked (cookie set, `aria-current` moved, `User.locale` updated) while
the actual translated text never appeared. Caught by this pass's own
required Playwright verification (a live en→de switch on the dashboard
that should have changed the nav text and didn't), not by the unit tests
alone - the unit tests exercised `get_locale()` directly and it was
already correct in isolation, which is exactly why this class of bug
needs a real rendered check, not just function-level coverage. Fixed by
making the path absolute (`os.path.join(BASE_DIR, "translations")`,
`config.py`), the same `BASE_DIR`-relative pattern `UPLOAD_DIR`/
`GENERATED_DIR` already use for exactly this reason.

**A second, subtler issue found while chasing the first one - test-only,
not a real app bug:** even after the path fix, a `client`-fixture-based
pytest reproduction of the same switch-then-check flow still failed.
Cause: `tests/conftest.py`'s `app` fixture wraps the entire test function
body in one `with application.app_context(): yield application` block -
correct and necessary for every other extension this suite touches (`db`,
`current_user`, etc.), but it means every `client.post()`/`client.get()`
call within one test shares a single Flask `g` object, because Flask
reuses an already-active app context for a request rather than pushing a
fresh one when a `RequestContext` is pushed inside an existing
`AppContext`. Flask-Babel caches the resolved locale on exactly that `g`
object (`ctx.babel_locale`, `flask_babel/__init__.py`) and never
re-derives it once cached - correct behavior for one real request in
production (a fresh WSGI call always gets a fresh context there), wrong
for several simulated "requests" sharing one test-scoped context. Fixed
by calling `flask_babel.refresh()` - its own documented mechanism for
exactly this class of problem (its docstring names the identical
symptom: "the `flash()` function would probably return English text and
a now German page" without it) - right after every place this pass
changes which locale should be active (`main.set_locale`, and both sync
call sites in `auth/routes.py`). This is not purely a test workaround:
without it, a locale-dependent flash message or other content rendered
later in the very same request that performed the switch could still
show the pre-switch locale, in production too, not just under this
suite's fixture pattern - `refresh()` closes a real (if currently
unexercised, since `set_locale()` itself renders nothing) correctness
gap, not only a testability one.

**Two proof-of-concept surfaces, deliberately small, not the start of
mass extraction:** the sidebar/drawer nav labels (`base.html`'s
`nav_items`, 7 strings, visible on every authenticated screen) are the
only template strings wrapped in `_()` this pass.
`format_local_date()`/`format_local_currency()` (`app/i18n.py`, thin
None-safe wrappers around `flask_babel`'s own locale-aware formatters)
are wired into exactly two real template call sites (Job Detail's
deadline line, Application Detail's "applied since" line) plus
`main/routes.py`'s `_relative_date()` absolute-date branch - each was
previously a hardcoded `%d.%m.%Y`, meaning an English-UI user was
already seeing German-style dates before this pass; fixed as a side
effect at these three sites specifically, not chased down at every other
`strftime` call site in the app (a real, large remaining set - that's
pass 2's job). `format_local_currency()` has **no live call site at
all** - deliberately, not an oversight: `Job.salary` is the one
money-shaped field anywhere in this schema, and it's a pre-formatted
free-text string from each source adapter (Arbeitsagentur's
`verguetungsangabe` text, Adzuna's own min-max string), never a numeric
amount - there is nothing real to format. Demonstrated instead at
`/admin/components` with a literal example value, the same
don't-fabricate-a-call-site-a-field-doesn't-back reasoning as Job
Detail's dropped "duration" tile and Find Ausbildung's dropped filters.

**The switcher's `next` field, not a Referer header or session state, is
what preserves the current page through a switch** - a hidden input read
from `request.full_path` (Flask already injects `request` into every
template; `nav_links()` already reads `request.endpoint` directly the
same way) at render time, validated server-side by `safe_next_path()`
(same-origin-relative only, rejects a scheme-relative or absolute
target) before being used as the redirect location - not trusted
verbatim the way `auth.login`'s pre-existing `next` param already isn't
validated, since this route (unlike login) has no `login_required` gate
narrowing who can submit it.

**Verification:** full pytest suite 583 passed / 3 skipped (555 + 28,
including a translation-catalog staleness guard - recompiles the
committed `.po` into a scratch dir and byte-diffs it against the
committed `.mo`, same class of gap as `check-css-stale.js` - and an
extraction-completeness guard that fails if a fresh `pybabel extract`
would produce a `msgid` missing from the committed catalog).
`npm run build:css` / `check:css` clean (the switcher's new classes are
compiled in). Playwright, both themes, 1920px and 375px, zero horizontal
overflow: a fresh browser with a German OS locale correctly defaulted to
German on the switcher (real Accept-Language detection - this
environment's Chromium genuinely reports `de-DE`, not staged); en→de→en
on the dashboard changed the sidebar nav live both directions; the
choice survived a page reload; the choice survived login for an account
whose own stored locale was still the untouched "en" default (confirmed
against the real dev database, not just the test suite); switching while
on `/jobs/?keywords=Elektroniker&min_score=50` preserved both query
params exactly; the desktop and mobile switcher instances correctly swap
visibility at the `md` breakpoint with no third, orphaned copy answering
a click. One aria-label collision caught by the existing test suite, not
found by inspection: `role="group" aria-label="Language"` on the
switcher collided with `test_landing_screen.py`'s own
`body.index("Language")` position check (part of the value-blocks
weighting-order regression test, an unrelated pre-existing test) - fixed
by renaming the group label to `"Choose language"` rather than touching
the older, correct test.

**Consequences:** `app/i18n.py` (new), `babel.cfg` (new, repo root),
`translations/de/LC_MESSAGES/{messages.po,messages.mo}` (new),
`messages.pot` (new, committed as the extraction template `pybabel
update` needs, not just a build byproduct). `config.py` gained
`LANGUAGES`/`BABEL_DEFAULT_LOCALE`/`BABEL_TRANSLATION_DIRECTORIES` (fixed
product decisions, not env-configurable, unlike `AI_PROVIDER`/
`STORAGE_PROVIDER`). `app/extensions.py` gained the `babel` singleton;
`app/__init__.py` wires it and two new Jinja globals
(`format_local_date`/`format_local_currency`, `get_locale`).
`app/main/routes.py` gained `POST /set-locale`; `app/auth/routes.py`'s
`login()`/`register()` each gained one sync + one `refresh_locale()`
call. `_components.html` gained `language_switcher()`; `base.html` and
`landing.html` each gained two/one call sites respectively in the spaces
already reserved for it. `requirements.txt` gained `Flask-Babel==4.0.0`
(pulls in `Babel`/`pytz` as real runtime dependencies, not dev-only - the
locale selector runs on every request). 28 new tests
(`tests/test_i18n.py`). `DEPLOYMENT.md` gained a "Translations (i18n)"
section documenting the three `pybabel` commands and when to run them,
mirroring the Tailwind CSS pre-deploy discipline. `ROADMAP.md`'s i18n
entry rewritten to mark pass 1 done and describe passes 2/3, replacing
wording that still described the bundle's superseded bilingual rule as
if it were the target.

---

## 2026-08-28 — Landing toggle-fix pass: the theme toggle was never reachable from landing.html, not a regression

**Checked git history before touching anything, per explicit instruction,
rather than re-adding blind.** `git log -p -- app/templates/landing.html`
shows the theme-toggle commit (`7e5bff7`, 2026-08-25) touched
`landing.html` exactly once, for an unrelated `bg-white` → `bg-card`
swap on the value blocks - it never added a toggle button anywhere in
that file. The macro itself (`theme_toggle()`) was defined inside
`base.html`'s `{% if current_user.is_authenticated %}` branch, with its
two call sites (`theme-toggle-mobile`, `theme-toggle-desktop`) both also
inside that same branch. `landing.html` extends `base.html` but renders
entirely inside the `{% else %}` branch (`{% block public_content %}`),
where that macro was never defined - calling it from there would have
raised `UndefinedError`, not silently done nothing. **The toggle was
never on the landing page, at any point in this app's history** - not a
regression introduced by the hero rebuild, a structurally-unreachable
component from the day it was built. Worth stating plainly since the
premise of "it was dropped" was wrong, even though the requested fix
(get a working toggle onto the landing header) was exactly right.

**Fixed by making it a genuinely shared component, not a duplicate.**
`theme_toggle()` moved from a `base.html`-local macro to a properly
importable one in `_components.html` (which already houses every other
reusable presentational macro - `btn`, `status_pill`, `intelligence_surface`,
etc. - per that file's own stated purpose). `base.html` now imports it
the same way `landing.html` does (`{% from "_components.html" import
theme_toggle %}`); both of `base.html`'s existing authenticated call
sites are unchanged in behavior. `landing.html` adds a third call site
(`theme-toggle-landing`) in its full-width header, between "See how it
works" and "Log in," with a reserved gap slot beside it for the future
language switcher - same treatment `base.html`'s own authenticated
desktop header already uses for that reservation.

**No JS wiring change was needed.** The end-of-`<body>` sync script in
`base.html` already queries `.theme-toggle-btn` globally
(`document.querySelectorAll`), specifically because an earlier bug
(documented in that script's own comment) taught not to wire toggle
instances individually or by position - any element with that class,
anywhere in the DOM, is picked up automatically. Confirmed this holds for
the new instance too, not just assumed from reading the script: clicked
`#theme-toggle-landing` live via Playwright and read
`document.documentElement.getAttribute('data-theme')` and
`localStorage.getItem('ausvia-theme')` directly before and after, in both
directions (light→dark and dark→light), at both 1920 and 375px. Also
verified the specific persistence-through-login requirement carried over
from the theme pass: set dark via the landing toggle, logged into a real
account, and confirmed `data-theme="dark"` on the resulting dashboard
render, with no separate re-verification needed since the mechanism
(shared `localStorage` key, read by `base.html`'s pre-paint script on
every page) was never landing-specific in the first place.

---

## 2026-08-28 — Landing widen pass: the hero was rebuilt after all, plus a 1600px wide-screen layout

**Correcting the previous pass's scope reading, not re-litigating the
theme pass's decision.** The theme pass's "hero stays fixed-ink" was
about COLOUR - there was no bundle reference for a themed counterform, so
the ink background was kept. The Landing pass's prompt generalized that
into "out of scope: the hero's visual design," which was read literally
and protected the entire pre-2.0 composition (centered single column, the
counterform staircase SVG, "Five stages. You are on the first."). None of
that exists in the bundle's own landing at all. The user identified this
as their own instruction's fault, not a misread, and asked for the actual
bundle hero this time: a two-column row, eyebrow/headline/promise/buttons
on the left, a preview panel on the right. The ink background is
unchanged - that part of the original decision genuinely does stand.

**The counterform staircase graphic, its "Five stages" caption, and the
old centered-hero composition are removed entirely, not hidden or kept as
an alternate state.** They have no bundle equivalent and nothing else on
the page referenced them. `hero-backing` (`tailwind.config.js`) is
removed too - it existed as a single-consumer pin for that graphic's
counterform-cutout backing color; with the graphic gone, keeping the
token would mean documented-but-dead config.

**The preview panel reuses the previous pass's search-result and
application-status cards rather than building a second set** - same
`match_band(compact=true)`/`status_pill()` components, same three
postings and scores (82/64/45), moved from their old standalone section
(which sat below the hero as a workaround for the hero not having room
for them) into the hero's right column, which is their actual position in
the bundle. The old standalone section is deleted, not left in place -
it would otherwise be a literal duplicate of the same cards now living in
the hero. Found and fixed one real layout bug surfaced by this pass's own
1920px screenshot: the overlapping application-status card (`-mt-7`,
matching the bundle's `-28px`) clipped into the third listing's "Some
gaps" label, because the reused search card's actual content height
differs from what the bundle's original spacing assumed. Fixed by adding
`pb-7` to the listings container - the overlap now eats into reserved
empty space, not text.

**The access-code badge and "See how it works" move into the header**,
matching the bundle's actual header composition (`logo + badge` left,
`"So funktioniert es" + "Log in"` right) - the previous pass kept the
badge inside the hero out of the same overcautious scope reading. Both
are hidden below `md` (only logo + Log in guaranteed to fit at 375px
without crowding) - a visitor can still reach "how it works" and the
access code via the hero's own buttons on narrow screens, so nothing is
actually unreachable, just decluttered.

**The 1600px wide-screen width is single-sourced as `max-w-content` in
`tailwind.config.js`**, not repeated as a literal at each of the five
section call sites (hero, journey strip, value blocks, closing CTA,
footer) - a one-line change if the user wants it tuned after seeing it
live, per their explicit request. The bundle's own 1180px was not reused;
1600px was the user's specified value for this pass, chosen because a
1900px+ monitor made 1180px's margins excessive. The **header is
deliberately the one section with no `max-w-content` wrapper** - it
reaches both edges of the viewport, per explicit instruction, with the
same ~40px (`px-10`) padding the content sections use so the logo and nav
still align visually with the content below despite the different
container behavior.

**Verified at three widths (1920, 1280, 375), both themes** - the
900px+ delta between the widen pass's primary case (1920) and the
previous pass's only-tested desktop width (1280, effectively, since
nothing wider was checked) is exactly where the empty-margin problem the
user flagged would have shown up, and exactly where the overlap-clipping
bug above was actually found. Zero horizontal overflow (`scrollWidth` <=
`innerWidth`) at all three widths in both themes.

---

## 2026-08-28 — Screens pass 7 (Landing, last screen): legal links deferred as a launch blocker, source list generated, a real access-code field, and a dark-mode wordmark bug

**Privacy policy and Impressum links are omitted from the footer, not
stubbed.** No privacy or Impressum route/page exists anywhere in the app
today (grepped `app/` for privacy/imprint/impressum/Datenschutz - nothing).
The bundle's footer shows "Datenschutz · Impressum" as if both already
existed; per explicit instruction, this was a stop-and-ask rather than a
guess, and the user's call was to omit both for now rather than invent
placeholder pages or dead links - an Impressum needs the user's real legal
identity (operator name, address, contact), which isn't something to
improvise mid-pass, and the legal obligation attaches to a public service;
AUSVIA is invite-only with no public signup today, so there is no live
gap being papered over. **This is logged here as a genuine pre-launch
blocker, not just a cosmetic gap** - before AUSVIA opens beyond invite-only,
it needs:
- A real Impressum: operator name, address, contact (the user's call, not
  improvised here).
- A real privacy policy covering, specifically (not boilerplate): Gmail
  OAuth (what scopes are requested, what's read, what's stored, how tokens
  are handled - see `app/integrations/gmail_oauth.py`); uploaded documents
  (what's stored, where, for how long - `app/documents/`); AI providers
  (that profile and job data is sent to a third party, currently Gemini,
  and precisely what is and isn't sent - see `app/ai/facts.py`'s
  formatters for what's actually included); job source APIs and what's
  queried (Arbeitsagentur today, potentially Adzuna/Jooble later).
See `ROADMAP.md`'s "Explicitly not scheduled" / pre-launch section for the
cross-reference so this surfaces before any public opening, not after.

**The footer's source list is generated from `get_enabled_adapter_names()`
(`app/jobs/adapters/manager.py`), excluding "manual"** - never the
bundle's hardcoded "Bundesagentur für Arbeit, Adzuna, Jooble". Checked the
real dev environment directly rather than assuming: `ADZUNA_APP_ID`,
`ADZUNA_APP_KEY`, and `JOOBLE_API_KEY` are all unset today (Adzuna's trial
was never started; Jooble's key - obtained separately, see the
`project_jooble_eval_pending` note - returns 403 and isn't configured in
this environment), so `all_adapters()` resolves to exactly
`{"arbeitsagentur"}` right now. The footer therefore reads "Source:
Bundesagentur für Arbeit (Jobsuche)" (singular), not three sources - proven
dynamic, not hardcoded, by a test that configures Adzuna mid-test and
confirms the footer's own rendered text changes (`Sources:`, plural) with
no template edit. "manual" is excluded even though it always has a
`JobSourceSetting` row (so admins can see/toggle it) - it's a user-driven
one-URL-at-a-time import, not something AUSVIA searches on a visitor's
behalf, so it doesn't belong in a "we search these sources" claim.

**The closing CTA's access-code field is real, not decorative.** The
bundle shows an inline code input + "Weiter" button; building a fake
input that discards what the visitor typed would be dishonest UI, and
duplicating `RegisterForm`'s validation logic in a second place would be
new auth logic (out of this pass's scope). Instead the field POSTs
directly to the existing `auth.register` endpoint (same CSRF pattern
`_components.html`'s `chip_attribute` remove-form already uses - a hidden
`csrf_token` input, no `_macros.html` full-form render needed for one
field). Submitting only the code lands on the real register page with the
code carried over and the still-missing email/password fields flagged -
the same outcome as posting the full form with those fields blank. Zero
lines changed in `app/auth/routes.py` or `forms.py`. Verified live,
two-step: typed a well-formed-but-fake code on landing, confirmed it
carried through to the register page with "This field is required" on
the empty fields, then filled in email/password and confirmed the real
"Invalid access code." flash appears - exactly the existing, already-tested
rejection path (`tests/test_auth.py::test_register_rejects_invalid_code`),
reached through a new entry point rather than a new mechanism.

**Found and fixed a pre-existing dark-mode bug while taking this pass's
own required dark-mode screenshot**: `landing.html`'s header logo used
`{{ lockup(24) }}` with no explicit colors, relying on `_logo.html`'s
defaults (`wordmark_color="#0C1013"`, the literal ink hex - correct only
on a light surface). Once the theme pass made `bg-paper` theme-aware, the
header background and the wordmark text became the same near-black in
dark mode, and the wordmark disappeared entirely (confirmed by reading the
rendered SVG's `fill` attributes directly, not just eyeballing the
screenshot - the symbol mark stayed visible, only the text vanished).
Grepped every `lockup(` call site in the app: this was the *only* one
anywhere using the unqualified default - every other call site (mobile
topbar/drawer, the authenticated desktop sidebar) already passes explicit
colors. Fixed with the exact `symbol_color="var(--brand)"` /
`wordmark_color="var(--t1)"` pair `base.html`'s own themed sidebar lockup
already uses successfully - not a new pattern, and confined to this one
call site rather than changing `_logo.html`'s shared default (smaller
blast radius; other public pages don't currently render a header logo at
all, so nothing else was silently depending on the old default). Verified
by reading the SVG's fill attributes in both themes after the fix, not
just a visual screenshot comparison.

**Journey strip and preview cards are new UI, not restyled-in-place** -
confirmed genuinely absent from `landing.html` before this pass (screen
inventory's own Part 1 correction: "confirmed genuinely absent... not a
restyle of something present-but-different"). Both get their own section
below the hero rather than living inside it, since the bundle's own
two-column hero layout (headline + preview cards side by side) isn't the
layout this app's fixed-ink counterform hero uses, and that hero is
explicitly out of scope to restructure this pass. Preview-card scores are
deliberately 82/64/45 (Strong/Good/Some gaps) rather than three high
numbers, matching the page's own claim that scoring is honest - and use
the same `match_band(compact=true)` / `status_pill()` components a
logged-in user's real results actually render, not a one-off visual
approximation.

---

## 2026-08-28 — Screens pass 6 (Company Detail): "listings" vs. "positions", and a second wholly-blank-profile fix

**"Listings on file" is the raw `JobListing` count, not the number of
positions shown below.** The bundle's German label ("Anzeigen auf Datei")
uses the same word ("Anzeige" - posting/ad) the rest of the bundle uses
generically for job postings, so the alternative reading (a rough
synonym for "positions") was real and considered. Went with the raw-
listing interpretation instead: it's a genuinely different, more
informative number whenever this company's postings were merged from
more than one source (`app/jobs/dedupe.py`) - the exact same
duplicates-are-an-honest-signal reasoning behind Find Ausbildung's "N
duplicates merged" line, not a new idea introduced here. Verified live:
a company with one canonical position merged from two source listings
correctly shows "1" position but "2" listings on file, not the same
number twice. Costs nothing when there's no duplication (equal to the
position count then, exactly matching the bundle's own single example).

**The company-fit insight's grounding was verified by reading the prompt
builder directly, not assumed from the docstring.**
`app/ai/prompts/company.py`'s `_company_facts()` builds its entire company-
side context from exactly five fields - `name`, `industry`, `location`,
`website`, `description` - plus up to 5 job titles on file, all wrapped
via `wrap_untrusted_external_text()` (company-sourced text is external,
third-party-authored data, not instructions). The system prompt
separately forbids inventing "company culture, employee count, benefits,
working conditions, reputation, or hiring practices... not explicitly
stated" and instructs saying so plainly when the facts are thin rather
than filling the gap. Every one of those company-side fields is also
what the new Facts on file panel shows - confirmed the insight has
nothing to draw on that isn't already visible on the same page. Verified
live against the real configured provider (not just mock mode): given a
company with a real German description and three real Ausbildung
postings, the generated note referenced only the location, the
description's own content, the candidate's real skills/language/location,
and explicitly said the company details were "relatively limited" rather
than inventing anything to compensate - the honest-thinness instruction
working in practice, not just in the prompt text.

**Company Detail's position list needed the same wholly-blank-profile fix
Find Ausbildung's search results needed.** Found by inspection this time,
not by re-discovering it via Playwright: `get_or_compute_matches()` is the
same batched matcher, so a candidate with no skills/languages/education/
preference at all can still see a fabricated 100/100 "Strong match" on
every position here too, via the identical `_score_location()` "no
preference row = open to anywhere" default documented in the Find
Ausbildung pass's entry. Reused `_profile_has_scorable_data()` directly
from `app/jobs/routes.py` (imported, not duplicated) rather than writing
a second copy of the same check - confirmed live with a genuinely blank
profile: every position correctly reads "Not scored" instead of a number.

---

## 2026-08-28 — Screens pass 5 (Profile + Documents): language proof state, and reused vs. new completeness UI

**Language proof state is German-only, not extended to every language.** The
bundle shows a proof caption on every non-native language row ("Goethe-
Zertifikat vorhanden" for German B2, "Schulkenntnisse, kein Nachweis" for
English B1), but this schema only tracks certificate evidence for German
specifically - `Document.is_primary_german_cert`. There's no
`is_primary_english_cert` or any general per-language certificate link;
`DOCUMENT_TYPES` has one generic `"language_certificate"` type with no
language field of its own. Cross-referencing a `Language` row named
"German" against `is_primary_german_cert` (`_language_proof_note()`,
`app/profile/routes.py`) reproduces the bundle's German example exactly
using real data - genuinely "German cert on file" vs. "German, no cert
on file." Extending the same claim to English (or any other language)
would mean asserting "no evidence" for something the schema has no way
to actually check - indistinguishable from a guess dressed as a fact.
Resolved without a stop-and-ask: the task's own instruction was to stop
only when *something* needs data the models don't have at all: here,
the real distinction (German proof) genuinely exists and ships; only the
*generalization* to every language doesn't, so that part is simply
omitted rather than faked, same reasoning as Find Ausbildung's German-level
filter the pass before this one. A `Language` at `level == "Native"` gets
its own honest caption ("Native language") instead - a real stored CEFR
value, not proof-related.

**The completeness checklist reuses `CandidateProfile.completeness_checklist()`'s
data, not a second calculation - but needed its own UI, not the Dashboard
pass's.** The Dashboard pass (2026-08-27) rendered the same eight checks as
one summary sentence ("Missing: X, Y, Z"), a deliberate simplification for
that screen's compact rail card - documented there as specific to that
construction, not a general checklist component. The bundle's own Profile
completeness panel is a real list of four dot+sentence rows mixing done
and missing items, matching this task's explicit "as a CHECKLIST, not just
a percentage" instruction for *this* screen. `_completeness_lines()`
(`app/profile/routes.py`) pairs the same eight `(label, satisfied)` values
with a done/missing phrasing per item ("Name provided" / "Name missing"),
rendered as a real dot-per-row list - one data source, two screens, two
honestly-different presentations because the bundle itself draws them
differently.

**Personal info and Ausbildung preferences became summary-card-plus-edit-toggle
sections, not always-open forms.** The bundle's own Profile construction
shows a compact read-only summary (avatar initials, name, age/nationality/
city/email on one line, an "Edit" affordance) and a compact preferences
rail card (four value rows, no form fields visible by default) - not the
pre-existing always-visible edit forms. Converted both to a summary view
with a `<details>` toggle revealing the real form beneath, matching the
`<details>` disclosure pattern the Education/Experience "Add entry"
sections already used before this pass, rather than introducing a new
interaction mechanism.

---

## 2026-08-28 — Incidental fix: two flaky priority-digest tests (UTC vs local date)

Found running the full suite during the Find Ausbildung pass, not caused
by that pass's own changes: `test_upcoming_interview_surfaces` and
`test_approaching_application_deadline_surfaces` (`tests/
test_priority_digest.py`) built their fixtures from local `date.today()`,
while `compute_priority_digest()` (`app/priority_digest.py`) compares
everything against `utcnow()` throughout, matching this codebase's
established convention (`app/models/user.py`'s `utcnow`, used everywhere
for timezone safety). Whenever local time and UTC briefly disagree on the
calendar date - confirmed directly: at the moment this was caught, local
`date.today()` was 2026-08-28 while `utcnow()` was still 2026-08-27 23:28 -
both tests failed by exactly one day, a real flake, not a code
regression. Fixed by building both fixtures from `utcnow().date()`
instead, matching the app's own convention rather than the tests'
incidental one. Out of this pass's stated scope (jobs/search.html,
SearchForm, the search query/scoring path, new tests) but a trivial,
unambiguous one-line-per-test fix that restores the suite to green for a
reason unrelated to any design decision - left broken, it would have kept
failing intermittently for any future session that happened to run the
suite near a UTC day boundary, for reasons that have nothing to do with
whatever that session is actually working on.

---

## 2026-08-28 — Screens pass 4 (Find Ausbildung): sort-by-score, and three dropped filters

**Scoring approach: compute-on-search, using the existing JobMatch cache
table, via a new batched function - not a schema change, not a
precompute-on-discovery pipeline.** Measured on this app's real dev data
(161 jobs, one real profile) before deciding anything:
- `compute_match()` itself: **0.24ms/job** - the matching arithmetic was
  never the cost, even scoring the whole table.
- `get_or_compute_match()` (the existing per-card helper, still used by
  every other screen): **34ms/job cold** (one SELECT + one commit per
  job - 5.4s for 161 jobs), **5ms/job warm** (still one SELECT per job).
  The N+1 query/commit pattern, not the scoring, was the real cost.
- A new `get_or_compute_matches(user, jobs)` (`app/jobs/matching.py`):
  one SELECT for every already-cached match in the batch, one commit at
  the end regardless of batch size. **4.4ms/job cold** (710ms for 161
  jobs), **0.19ms/job warm** (31ms for 161 jobs) - roughly 8x and 26x
  faster respectively.

Precompute-on-discovery was considered and rejected: a score is inherently
per (user, job), so scoring at discovery time would mean scoring every new
job against every user's profile the moment it's found, most of which
would never be searched for again - backwards cost direction. A single
denormalized score column was also considered and rejected for the same
reason - `JobMatch` already **is** the cached-column pattern (one row per
user+job, invalidated via `profile_updated_at_snapshot` when the profile
changes), just fetched inefficiently for a whole result set before this
pass. The staleness contract is unchanged: this only changes how
efficiently the search path fetches/recomputes a batch, not when a cached
score goes stale or how staleness is detected.

Search's candidate pool moved from a flat 50 to `SEARCH_CANDIDATE_LIMIT =
40` (`app/jobs/routes.py`) - sized for a sane single results page (no
pagination UI this pass - out of scope, and every filter already being a
query param means adding real pagination later won't change how filters
work), not for scoring cost: even 100 jobs batched-cold measured at
~440ms, so the limit could go considerably higher without a performance
concern if the page itself grew to support it. Only the search route's
candidate-fetch path changed - `get_or_compute_match()` (singular) is
untouched and still backs every other screen (job detail, dashboard,
digest) unchanged.

**"No profile" (or a profile compute_match can't evaluate anything
against) stays honest, never a numeric 0.** `compute_match()` already
returns `score=None` with `recommendation="insufficient_data"` for this
case - unchanged. The batch path preserves it: an unscored job is sorted
into its own bucket (`unscored_results` in the route, a separate "Not
scored" section in the template, always below the scored results,
never filterable by the minimum-score control since there's nothing to
compare against a threshold) rather than defaulting to 0 and reading as a
weak match. When every candidate comes back `insufficient_data`, the page
shows an explicit notice ("your profile doesn't have enough data yet to
score these results") rather than silently rendering a page that looks
broken.

**Three of the six requested filters were dropped - radius, category, and
(caught mid-implementation) German level - all for the same reason: no
real data supports them today.** Checked against this app's real dev DB,
not estimated:
- **Radius**: no coordinate data exists anywhere in the schema (`Job` has
  no lat/long; `Preference.max_distance_km` is a stored number nothing
  computes a distance against). Only the Jooble adapter even accepts a
  `radius` parameter, and `ingest_search()` never threads it through.
  Building this control would mean fabricating geo data.
- **Category**: `Job` has no category/field/taxonomy column, and nothing
  else in the schema maps a job to one - confirmed, then put to the user
  per the task's explicit stop-and-ask. Their answer, and the reasoning
  worth preserving for a future session tempted to add this from the
  bundle's chips: a hand-picked taxonomy backfilled by keyword-matching
  titles is an invented classifier with no ground truth, and would be
  wrong *quietly* (a mislabeled job just looks like a missing result,
  discovered by no one) - worse than no filter, not better. Filtering by
  the candidate's own `Preference.fields` keywords was also rejected as a
  substitute: that's a different feature (one user's stated interests, not
  a shared browsable taxonomy) wearing this label's name, and shipping it
  as "category" would misrepresent what it does. **If job-side
  categorization ever becomes real, the honest path is extracting it from
  the posting text the way `Job.skills` already is (see
  `app/ai/job_requirements_extraction.py`), not inferring it from titles**
  - a future extraction question, not a filter question.
- **German level**: initially reported to the user as real and
  well-backed (a wrong first-pass measurement - `Job.language_requirements
  .isnot(None)` matched far more rows than actually had real data, an
  ORM/JSON-column check bug, not a data bug). Corrected by testing
  truthiness in Python directly: **only 5 of 161 jobs (3.1%) have real
  `language_requirements`**, and those 5 are all `source="manual"` test
  data, not real adapter-sourced postings. The field itself is real and
  structurally sound (a genuine JSON column, real CEFR-comparable levels,
  actively read by `_score_language()`) - the gap is that no adapter's
  `normalize()` ever writes it, and `app/ai/job_requirements_extraction.py`
  *deliberately* never persists it either (see that module's own docstring:
  the `{"language","level"}` shape can't safely represent "explicitly
  required, level unspecified"). Different flavor of gap than radius/
  category (real infrastructure, temporarily near-empty, vs. no
  infrastructure at all) but the same practical outcome: a selectable
  filter over a field 97% of results don't have would either hide almost
  every result or filter almost nothing while implying otherwise - the
  task's own stated failure mode almost exactly. Dropped, not built.
  Flagged as a correction to the user rather than silently building it
  differently from what was first reported.

**Year range and minimum score were kept - checked the same way, and the
data holds up:** `Job.start_date` parses to a real year for 76.4% of jobs
(123/161, via the same `\d{4}` extraction `_score_start_date()` already
uses - reused, not a second parsing approach). Minimum score was always
going to be real once scoring itself was unblocked.

**Source toggle is generated from `get_enabled_adapter_names()`**, not
hardcoded - a source added/disabled by an admin via `JobSourceSetting`
changes the filter's own choices with no code change. "manual" is
correctly absent from the *toggle's choices* without special-casing by
name, since it was never in `ADAPTERS`/`_configured_adapters()` in the
first place (it's user-driven, one URL at a time, not a searchable
adapter) - but it's explicitly kept in the *query*'s source filter
(`[*selected_sources, "manual"]`) regardless of what's toggled, found via
a real test failure: the search query didn't filter by source at all
before this pass, so a manually-imported job was always keyword-findable;
an early version of this pass's source filter applied uniformly and would
have silently dropped manually-imported jobs out of search results
entirely, a real regression this pass didn't intend to make. Also
tightened while fixing that: the filter now always applies (restricted to
the selected sources, defaulting to every *enabled* one), not only when
the selection is a proper subset - the original "skip the filter when
selection == full enabled set" version meant a job whose only listing sat
on a since-disabled or never-configured source (Adzuna, in the test that
caught this) would still surface, silently contradicting the page's own
"Searches X, Y, Z" intro line.

**Filters are query params, not session state** (`request.args`, GET
form) - shareable via URL, survive a reload, and each removable filter
chip is a real link (`_query_without()`) to the same search with just that
one param cleared, not a client-side JS toggle.

**Per-card one-line strengths/gaps summary names *categories*, not raw
strength strings** (`summarize_match_line()`, `app/jobs/matching.py`) -
mirrors the bundle's own construction exactly ("Alle Fähigkeiten erfüllt" /
"All skills met", "Sprache und Ort erfüllt" / "Language and location
met"): built from `category_scores` (the same per-category numbers
`match_band()` already renders), not from `job_match.strengths`, whose
raw entries mix formats across categories (a skill name, a language
proficiency sentence, an "Education background aligns: X" sentence) and
read poorly concatenated into one line.

**`match_band()` gained a `compact=true` mode rather than a second,
duplicated construction** - the search card's own layout (bundle line
1002) puts the score+label in its own position with no room for
`match_band()`'s usual eyebrow/header/disclosure at ~190px wide, and the
bundle's own card segments (lines 1003-1009) are bare bars with no text
under them at all, unlike Job Detail's full treatment. `compact=true`
renders only the segment-bar loop, same weight/fill logic, everything
else omitted - one macro, two modes, not two macros.

**`btn()` gained an `active` variant** for the Save/Saved toggle's "Saved"
state (bundle line 1044: tint fill, brand text/border) - tried layering
override classes onto `variant='secondary'` via `extra_classes` first,
rejected because Tailwind's cascade resolves conflicting utility classes
by stylesheet rule order, not by position in the HTML `class` attribute,
so an override class appended after `bg-card` isn't guaranteed to win
against it. A real named variant, not a hack.

---

## 2026-08-27 — Screens pass 3 (Dashboard): non-obvious calls

**The "Next up" hero card's staleness marker dates from
`ApplicationEvent`, not a new column.** The task flagged this as a
stop-and-ask if the schema couldn't support it. It can: a new public
`latest_transition_at(application)` helper (`app/applications/
status_route.py`, alongside the existing event-reading helpers that
already power the station journey) takes the latest `created_at` among
`created`/`approved`/`sent`/`status_changed` events - the same real-
transition vocabulary `build_status_route` already relies on - and falls
back to `Application.created_at` only if the log is somehow empty.
Deliberately not `Application.updated_at`, which bumps on any field edit
(notes, contact_email, ...) and would make "unchanged for 3 days" lie the
moment someone jots a note. The same helper now also dates the
applications table's relative-date column, so both are backed by one
definition of "when did this application's status last really move," not
two.

**The hero card is its own construction, not `intelligence_surface()`.**
The bundle's own hero (line 869 of the unpacked bundle) uses `bg-card`
with a brand left border - not `intelligence_surface()`'s tint fill - and
it isn't AI-generated content at all, just the top `DigestItem` from the
same deterministic, no-AI-call ranking the digest list below it already
uses (`compute_priority_digest`, reusing `application_digest_item` -
public since Screens pass 2 - rather than a second ranking). Giving it
the Intelligence surface's tint/provenance chrome would have implied an
AI source that isn't there.

**Hero and digest actions are gated on real state, not the bundle's
literal buttons.** The bundle always shows "Paket öffnen" - our hero only
offers "Open package" when `package_storage_path` is actually set,
falling back to "View application" otherwise; "Mark as sent" only
appears when `status == "ready"` (mirrors `applications/detail.html`'s
own gating for the same action, not a new rule). A saved-job hero item
gets "Start application" as a real POST to `applications.start`, the same
route `jobs/detail.html` already uses. The priority-digest list's own
per-row action originally tried to reuse "Open package" as a label there
too; dropped in favor of a plain "View application"/"View job" once it
was clear the row's link target (`applications.detail`) didn't match a
"download the package" label for every reason that can put an item at
the top of the list - a label promising an action the link doesn't take
is worse than a plainer, always-true one.

**Digest row dot color is a lookup against this codebase's own fixed
reason strings, not a priority-integer threshold.** `compute_priority_digest`
produces a small, self-controlled set of exact reason sentences (`"...
deadline..."`, `"Interview in N days"`, `"Approved but not yet sent"`,
etc.) - matching against those (not parsing untrusted text) reproduces
the bundle's example coloring exactly: warn for deadline/interview-soon,
brand for ready-not-sent, t3 (neutral) for everything else including the
stalled-application and strong-match-not-started reasons the bundle
didn't happen to show an example of.

**The cross-application insight was built, not deferred.** The task's
own conditional ("if it can't be grounded cleanly, defer") implied
deferral was the fallback, not the default. `format_applications_summary()`
(`app/ai/facts.py`) grounds it in exactly what the schema actually gives
per application - job title, company, `Company.industry` when known,
current status, and up to 5 `JobMatch.gaps` labels - all already
deterministic, already-computed facts. What it deliberately does *not*
attempt: clustering applications by "field/category," since `Job` has no
such column and `Company.industry` is frequently null - the prompt
(`app/ai/prompts/dashboard_insight.py`) is instructed to say "no clear
pattern yet" rather than manufacture one when the given facts don't
support it. Verified against the real Gemini provider in dev (not just
mock mode): given five real applications split between technical and
commercial Ausbildung fields, it correctly named that exact split and
suggested narrowing profile focus - a genuine inference from the given
job titles, not a fabricated fact.

**New `DashboardInsight` model + migration were pre-authorized, not a
stop-and-ask.** Unlike the staleness caveat, the task's own SCOPE section
lists "the cross-application insight" as in-scope work to build, so
adding the model (mirrors `ProfileCoaching`'s shape - `summary_text`,
`provider`, `reliability` nullable/unpopulated by design, `generated_at`,
plus `application_count_snapshot` alongside the usual
`profile_updated_at_snapshot`, since this surface's real input is "all of
a user's applications," where a newly started or deleted application can
make a cached synthesis stale even when the profile itself hasn't
changed) needed no separate confirmation.

**Profile completeness stays a percent + bar; one sentence was added
naming what's missing, not a checkbox-list UI.** The task's own wording
said "CHECKLIST," but the bundle's actual construction (line 934) is a
single sentence ("Es fehlen: ein Sprachzertifikat..."), not a list of
checkboxes. `CandidateProfile.completeness_percent()` was refactored into
a `completeness_checklist()` (8 real `(label, satisfied)` pairs) that
both the unchanged percent calculation and the new missing-items sentence
now read from - satisfying the underlying intent (name what's missing,
not just a bare percentage) via the bundle's literal construction rather
than inventing a bundle-specific sub-field (e.g. a literal "language
certificate" concept `Language` doesn't model) to match its example text
word-for-word.

**The bottom three-card row (Job search / Documents / Candidate profile
mini-summaries) was dropped, not restyled.** It isn't part of the bundle's
Dashboard at all (confirmed by reading the unpacked bundle's Dashboard
section directly, lines 858-957) and every destination it linked to is
already one click away in the sidebar nav - keeping it would have meant
inventing dashboard content the redesign's own source doesn't have,
against this pass's explicit "bundle structure" instruction.

**Job radar's rail card dropped the inline per-job result list in favor
of a compact count** ("6 new listings for your profile"), matching the
bundle's own compact rail treatment (it shows a count + arrow link, not a
list) rather than the pre-existing dashboard's inline job rows - the
actual postings stay one click away via "Open Find Ausbildung." The
on-demand "Check now" button and its honest manual-not-autonomous copy
were kept exactly as shipped, since the task called that out explicitly
as something to preserve, not restyle away.

---

## 2026-08-27 — Screens pass 2 (Application Detail): non-obvious calls

**The Reply station's dating logic, since it's genuinely new (not a
rename of an existing station like Prepared/Approved):** dates from the
*earliest* `GmailMessage.received_at` for the application (the real email
timestamp, not when AUSVIA happened to check for it), falling back to the
`reply_detected` `ApplicationEvent`'s `created_at` only if no message has
a `received_at` set. A reply's mere existence is real evidence the route
has passed this point - so a detected reply now bumps the journey's
`current_idx` forward even when `Application.status` was never manually
changed past "sent" (Gmail reply detection doesn't touch `status` at all -
see `app/integrations/gmail_reply_tracking.py`). This is the same
evidence-over-status-string principle the six-station route already
applied in its terminal (rejected/withdrawn/expired) branch; this pass
found the non-terminal branch was missing the equivalent bump and added
it - caught by a test that added real `GmailMessage` rows without also
advancing status, not assumed correct.

**Reply's "skipped" case:** when the route has passed Reply's position
(via status or another later event) with no reply ever detected - e.g. an
interview arranged by phone, or a manual status correction - the station
shows a real, honest "Skipped." rather than looking either reached or
not-reached. Mirrors the exact skip-detection pattern the old
`follow_up` station used (and the same accessibility-tested dashed-ring
marker construction, unchanged - see `tests/
test_status_route_accessibility.py`).

**`follow_up` (the status value) maps onto Reply's station index, not a
station of its own:** `follow_up` is a real `Application.status` (a
reminder state a user sets manually) that predates this pass and stays -
but the bundle's eight stations don't include it as a stop on the route.
Since conceptually "following up because you haven't heard back" and
"waiting for/tracking a reply" occupy the same point in the journey,
`STATUS_TO_STATION_INDEX["follow_up"]` resolves to Reply's index rather
than inventing a ninth station or dropping the status value.

**Kept the app's own vertical Wayfinding journey (visual direction 1c)
instead of the bundle's horizontal row for this same screen.** The bundle
draws Application Detail's journey as a horizontal scrolling strip of
stations with a different marker language (11px/13px dots, no ring-vs-
fill distinction). This app's vertical tracker is a real, deliberate,
already-accessibility-hardened construction (Phase 7 remediation: dashed-
vs-solid rings so "skipped" and "not reached" survive grayscale/
colorblind rendering, sizes-not-just-color for the current marker) - the
task's own framing ("the eight-station journey... each with its real
date, and a header line naming the next event") describes *station data*,
not a layout mandate, so extending the six-station data to eight within
the existing, considered component was the read here, not silently
discarding accessibility work that was never asked to be revisited. The
new piece genuinely missing before this pass - the header line naming the
next event with a countdown - was added on top of the existing marker
construction, not copied from the bundle's own header styling.

**The three previously-missing save routes were straightforward, wired as
asked, no design gap found:** `save_interview_prep`, `save_cv_profile_statement`,
`save_reply_suggestion` all mirror `save_cover_letter`/`save_email`
exactly - fetch-or-create the row, set the content field, `edited_at`
only on an *existing* row (never on first creation, which is generation's
job, not editing's), log an event, redirect. No new mechanism, no UI
decision beyond what `intelligence_surface()`'s existing `{% call %}`
slot (see below) already provides.

**`intelligence_surface()` gained a body-slot (`{% call %}`) for editable
content**, alongside the existing plain-`text` mode: cover letter, email,
interview prep, CV statement, and reply suggestion are all genuinely
editable (a pre-filled textarea + a real "Save edits" submit - the
established mechanism, not contenteditable), unlike Job Detail's match
narrative/improvement tips (regenerate-only, nothing to save). Passing no
`text` and supplying the form via `{% call intelligence_surface(...) %}`
renders `caller()` in place of the plain paragraph, so every one of these
surfaces gets the tint/reliability/edited-badge chrome for free without
forcing read-only and editable content through the same fixed shape. The
header's own Regenerate control was also decoupled from the edited/not-
edited branch (previously hidden once edited) - the bundle's own edited-
state example shows both "Neu erzeugen" and "Speichern" available at
once, and there's no reason "discard my edit, generate fresh" shouldn't
stay offered after an edit.

**`_application_digest_item` in `app/priority_digest.py` was renamed
public** (dropped the leading underscore) since the Next Step rail card
now calls it directly for one application, not just
`compute_priority_digest()` internally for the whole-user list - a real
second caller, not speculative future-proofing.

**PDF package page count/size are computed live, not stored:** no schema
change: `PdfReader(...).pages` and `os.path.getsize(...)` read the file
directly at render time, the same way `download_package()`/`delete()`
already touch `package_storage_path` directly (confirmed local-disk-only,
never S3-routed - see that route's own comment). The package's "date" is
the `approved` `ApplicationEvent`'s timestamp - there's no separate
"package built at" column.

**Accessible tab bar, not styled divs:** real `role="tablist"`/`role="tab"`/
`role="tabpanel"`, `aria-selected`, roving `tabindex` (0 on the active tab,
-1 on the rest), and a nonce'd nine-line script for click + arrow-key/
Home/End navigation - the bundle's own tab markup is plain unstyled spans
with click stubs (`sc-camel-on-click`), since it's a static mockup, not a
real interaction to copy. Active tab is remembered in `sessionStorage`
(keyed per application ID) so a save/generate POST redirecting back to
this same page reopens on the tab the user was just working in, instead
of silently resetting to "Cover letter" and hiding whatever they'd just
acted on - verified end-to-end with Playwright (edited a reply, saved,
confirmed the Replies tab was still selected after the redirect), not
just asserted from reading the script.

**Two real bugs found by the required 375px check, both fixed, both
pre-existing patterns copied forward from Job Detail:**
1. A `grid` with no *base* `grid-template-columns` (only `lg:grid-cols-
   [1fr_330px]`) lets its single implicit column size to its content's
   max-content width instead of filling the container - invisible in a
   screenshot at a glance (every individual piece still looked fine),
   only caught by checking `document.documentElement.scrollWidth`
   numerically. The five-tab flex row's unwrapped width was what actually
   exposed it here; `jobs/detail.html` has the identical construction
   (copied from there first) and got the same `grid-cols-1` fix.
2. The tab bar's `gap-6` (24px, matching the bundle's own spacing) meant
   the first four tabs alone already summed past a 328px mobile column
   before `flex-wrap` ever got to "Interview prep" - `flex-wrap` breaks a
   row once an item doesn't fit, it doesn't shrink items already placed
   on an overflowing row. Fixed with `gap-4 sm:gap-6`.

**Consequences:** `app/templates/applications/detail.html` rewritten;
`app/applications/status_route.py` extended to eight stations;
`app/applications/routes.py` gained three save routes plus
`package_info`/`next_step`/`gmail_connection` context; three new
`FlaskForm`s in `app/applications/forms.py`; `app/templates/_components.html`'s
`intelligence_surface()` gained the body-slot and decoupled Regenerate.
23 new tests across three files (`tests/test_status_route_stations.py`,
`tests/test_application_edit_save_routes.py`,
`tests/test_application_detail_screen.py`). Full pytest suite: see
`PROJECT_STATUS.md` for the final count.

---

## 2026-08-27 — Screens pass 1 (Job Detail): non-obvious calls

**Decision, "Duration" fact tile dropped:** the bundle's Job Detail fact-
tile row is start date / salary / duration / source. No field anywhere in
this app backs "duration" - not on `Job`, not extracted, not on any other
model. Rendering it would mean every job shows "Not specified" forever,
not "sometimes missing" - a fabricated column, not an honest-absence
state. Omitted (3 tiles, not 4) rather than stopping the pass to ask,
since the answer was already implied by the project's own stance on not
inventing data; flagged here and in the report instead. Adding a real
`duration` field (extraction + schema) is a future decision, not this
pass's to make.

**Component changes, both additive, both used immediately:**
- `chip_attribute()` gained a `gap` tone (err fill/text/border), read from
  the bundle's own Job Detail requirement-tag cloud - the one construction
  where a gap-flagged tag is visually distinct from the plain ones around
  it. The macro previously had only plain/highlight.
- `chip_coverage()` gained an optional `label` override. Built during the
  component pass as a generic legend item (fixed word per state - "Fulfilled",
  "Partial", etc.), it needed a per-item custom sentence
  ("German B2 — required B1") for Job Detail's real Strengths/Gaps list
  while keeping the same dot+state visual language. Defaults to the
  original generic text, so the existing `/admin/components` legend demo
  is unchanged.

**English copy retrofit to `_components.html`:** `match_band()`,
`chip_coverage()`, `notice()`, and `intelligence_surface()` all had
German strings hardcoded from the component pass (built by reading the
bundle's own construction too literally, before this pass's explicit
"copy stays English" instruction existed as a rule). Since this pass is
the first to actually wire these macros into a real screen, fixing that
copy was required, not optional scope creep — done directly in the shared
macros, so every future call site gets it for free rather than needing
its own translation pass later.

**Strengths/Gaps live inside `match_band()`'s "Show breakdown" disclosure,
not a separate always-visible section:** the bundle's own static mockup
shows them as a separate section following the match card. This pass
nests them inside the collapsed breakdown instead - not a deviation
invented now, but following through on the component pass's own
documented plan (`admin/components.html`'s comment: "the screens pass
fills this with the real strengths/gaps list"), which the task's own
"'Show breakdown' expander over the category detail" phrasing confirms as
intended, not incidental.

**Known, accepted inconsistency: gap severity differs between the
requirement-tag cloud and the Strengths/Gaps breakdown.** `chip_attribute(gap=True)`
is a single boolean - any skill gap renders err-toned, matching the
bundle's one literal example. But `_score_skills()` (app/ai/matching.py)
never distinguishes required vs. preferred skills - every skill gap's
`GapItem.status` is `"preferred_missing"`, which the breakdown correctly
renders as the softer warn-toned `teilweise`, never `fehlt`. So the same
skill can appear err-red in the tag cloud and warn-amber two sections
below. Left as-is rather than adding a severity parameter to
`chip_attribute` for one page's minor color nuance - the tag cloud is
answering "is this a gap at all," the breakdown is answering "how bad,"
and both are individually honest even though the colors don't match
across sections. Revisit only if this reads as a real bug in practice,
not preemptively.

**`score is None` / "not enough data" branch is effectively unreachable in
normal use, kept anyway:** `compute_match()` only returns `score=None`
when `profile is None` entirely. Every registered user has a
`CandidateProfile` (created at registration), and `_score_location()`
always returns a real ratio even with zero preference data set ("Open to
opportunities Germany-wide") - so a logged-in user's score is never
`None` in practice; the branch only guards a user record that somehow
lacks a profile. Kept the honest message (matches the pre-existing
template's own prior wording) rather than deleting a real defensive path;
covered in tests by deleting the profile row directly, the only way to
reach it through the real route.

**Mobile reordering (score above title, actions pinned to the bottom) is
one responsive template, not a second one:** Tailwind `order-1/2/3` +
`md:order-*` on three siblings (match card, header, fact tiles), plus a
`fixed md:hidden bottom-0` action bar duplicating the header's two
buttons. Matches this app's existing pattern (`base.html`'s sidebar vs.
mobile topbar/drawer already work the same way) rather than introducing a
second markup path to keep in sync.

**Consequences:** `app/templates/jobs/detail.html` rewritten;
`app/jobs/routes.py::detail()` gained `gap_skill_labels`,
`deadline_days_left`, `company_open_positions` (real derived data, no new
model fields). `app/templates/_components.html` gained the `gap`/`label`
params and English copy fixes; one real bug caught by the mobile
Playwright check and fixed in the same file: `match_band()`'s segment
labels had no `truncate`, so narrow segments' text ran together at 375px
(the bundle's own construction has `overflow:hidden` here; the macro was
missing it). 12 new tests
(`tests/test_job_detail_screen.py`). Full pytest suite: 465 passed / 3
skipped (453 + 12).

---

## 2026-08-26 — Removed dead `admin_required` decorator; admin gating is the `before_request` guard

**Decision:** Deleted `app/utils/decorators.py` (it contained exactly one
thing: `admin_required`, a `login_required`-style decorator that checked
`current_user.is_admin` and `abort(403)`'d otherwise). Confirmed
unreferenced with a repo-wide grep across `app/`, `tests/`, and
`templates/` for both `admin_required` and `utils.decorators`/`from ...
decorators import` - the only match anywhere was the definition itself.
Surfaced by the module-level graph collapse (`scripts/
graphify_module_graph.py`): of 101 app/ modules, it was the one non-
`__init__.py` module with zero inter-module edges.

**How admin gating actually works, for the record:** every route in the
`admin` blueprint is gated by one shared guard, not a per-route decorator:

```python
# app/admin/routes.py
@bp.before_request
@login_required
def _guard():
    if not current_user.is_admin:
        abort(403)
```

`before_request` runs it ahead of every view function registered on `bp`,
so protection is automatic for anything added to the blueprint - a new
admin route doesn't need to remember to decorate itself, because there's
nothing to remember. `admin_required` predates this (or was written
alongside it and never adopted) and was never wired to a single route.

**Why delete rather than leave it:** a dead auth decorator is a live trap,
not neutral dead code - it type-checks, imports cleanly, and does exactly
what its name promises, so a future route (in `admin/` or anywhere a new
admin-gated area gets added later) could reach for `@admin_required`,
assume it's the app's real protection mechanism, and ship unprotected
because the actual mechanism here is a blueprint-level guard, not a
decorator. Removing it means that mistake can't happen; leaving a comment
pointing at the real mechanism would still leave the trap loaded for
anyone who finds the decorator first and doesn't read the comment.

**Consequences:** `app/utils/decorators.py` deleted; `app/utils/__init__.py`
was already empty, nothing to re-export/clean up there. No call site
existed to update. Full pytest suite: 453 passed / 3 skipped, unchanged.

---

## 2026-08-26 — graphify: kept dev-only, split into requirements-dev.txt; honest evaluation

**Decision:** `graphifyy` (PyPI name; imports as `graphify`) was found installed
in the venv but untracked, along with ~30 transitive deps (networkx, numpy,
rapidfuzz, tree-sitter + ~20 per-language grammars). Resolved the
divergence explicitly rather than leaving it accidental: added a new
`requirements-dev.txt` (`graphifyy==0.9.50`, installed on top of
`requirements.txt` for local dev only) and a new test,
`tests/test_no_dev_only_imports.py`, that AST-parses every file under
`app/` and fails if any of them import `graphify`/`graphifyy` - so a
future accidental import breaks the local test suite instead of only
showing up as a production 500 the way the 2026-08-25 Job Radar migration
gap did. `graphify-out/` (the generated graph output) is gitignored, never
committed.

**Why a new file instead of reusing the existing dev-only pattern:**
`requirements.txt` already carries a few dev-only packages inline
(`pytest`, `websocket-client`, `moto`), each just commented as dev-only in
place - that's the project's established convention, and normally the
right call (see the small-dev-tool precedent). `graphifyy` doesn't fit
that precedent by size: it drags in ~30 packages via transitive deps for a
tool nothing in `app/` will ever call. Every one of those 30 packages
would still get installed on every Railway deploy if added to
`requirements.txt` directly - Railway installs the whole file regardless
of whether a given line is "dev-only" in a comment - so that's a real,
avoidable build-time cost for zero production benefit, not a cosmetic
concern. Splitting it into a separate file that Railway's install command
never references removes that cost entirely rather than just labeling it.

**What I deliberately did NOT do:** `graphify install` was not run. That
subcommand copies a "skill" file into `.claude/skills/`, registers itself
in `~/.claude/CLAUDE.md` (a file outside this project, shared by every
Claude Code session on this machine), and can install a Claude Code
PreToolUse hook that intercepts/gates the agent's own Bash/Grep/Read tool
calls. None of that was asked for - the task was "build the code graph and
tell me what it gives you," not "wire graphify into how future sessions
behave by default." `graphify extract . --code-only` (the plain AST build,
no LLM, no network calls beyond what `--code-only` explicitly skips) was
run instead, entirely inside this project directory. If a hook-gated,
always-on setup is wanted later, that's a separate, explicit decision -
not a side effect of "try the tool out."

**Honest evaluation - what it actually indexes:** AST-only, it parsed 187
Python/JSON/JS files into 1529 nodes / 4492 edges / 97 communities in a
few seconds. **It does not index templates at all** - zero `.html` files
in the graph, confirmed directly (`source_file` extensions present:
`py`, `json`, `js` only; no tree-sitter grammar for Jinja/HTML is even in
the dependency list). `render_template("jobs/detail.html", ...)` calls in
`app/jobs/routes.py` produce no template-side node or edge - the graph is
blind to the exact "route → template" and "template → macro" relationships
that make up half of what a screens-pass file like Job Detail actually
touches. It also doesn't index at column/attribute granularity: `JobMatch`
is one node; `narrative_reliability` is not a node at all, so "what reads
this column" isn't a question the graph can answer - only "what
imports/calls the class" can.

**What it's actually good for, verified with real tomorrow-relevant
queries, not assumed:** `graphify explain "generate_narrative"` correctly
separated callers (`narrative()` in `jobs/routes.py:145`, plus the schema
pass's own new test file) from callees (`get_provider`, `record_usage`,
`build_match_narrative_prompt`, `_match_result_from_cached`), each with an
exact file:line, in about a second. `graphify path "jobs/routes.py:narrative"
"generate_narrative"` returned the exact one-hop call edge. Both are
faster to read than the equivalent grep-and-cross-reference, *once you
already know the qualified symbol name* - `graphify path "detail"
"generate_narrative"` and `graphify path "narrative" "matching.py"` both
hit ambiguous-match warnings and returned nothing useful, because this
codebase has several functions named `detail`/`narrative` across
blueprints and the CLI picks one silently rather than disambiguating. The
free-text `graphify query "<question>"` BFS mode was the weakest part
tested: a realistic question ("how does the job detail route compute and
cache the match score") returned 460 matched nodes truncated to 67, an
unranked mix of genuinely relevant nodes (`JobMatch`, `get_or_compute_match`)
and noise (`SavedJob`, `run_job_radar`, unrelated test files) - sifting
that list took longer than a targeted grep would have.

**Conclusion:** worth keeping for exactly one thing tomorrow -
`graphify explain`/`graphify path` against an *already-known* Python
symbol, to jump straight to real callers/callees with file:line instead of
manually cross-referencing grep hits. Not a replacement for grep on the
template side (it can't see templates at all) or for exploratory
free-text questions (the query mode is noisier than a good grep). Re-run
`graphify update .` (AST-only, ~17s for the whole repo on an incremental
pass, confirmed by timing it) after edits to keep it current - it will not
warn when it's stale.

**Consequences:** `requirements-dev.txt` (new), `tests/test_no_dev_only_imports.py`
(new, passing), `.gitignore` gained `graphify-out/`. `requirements.txt`
itself is untouched - production install is unaffected. Full pytest suite
confirmed green after the addition (453 passed / 3 skipped: 452 + this
one new test).

---

## 2026-08-26 — Schema pass: reliability field, mostly left unpopulated by design

**Decision:** Added a nullable `reliability` column (`db.String(20)`, values
`"high"`/`"medium"`/`"low"` — the exact type and range
`GmailMessage.classification_confidence` already used) to every AI-backed
model behind the Intelligence component that didn't already have one.
Mapped the bundle's eight named Intelligence surfaces to real code, not
guessed from the name list:

| Bundle surface | Model / column |
|---|---|
| Match explanation | `JobMatch.narrative_reliability` |
| Improvement tips | `JobMatch.improvement_tips_reliability` |
| Company insight | `CompanyInsight.reliability` |
| Cover letter | `GeneratedDocument.reliability` |
| Application email | `GeneratedEmail.reliability` |
| Reply classification | `GmailMessage.classification_confidence` (already existed, unchanged) |
| Reply suggestion | `GmailMessage.reply_suggestion_reliability` |
| Profile coaching | `ProfileCoaching.reliability` |

Six models, seven new columns (`JobMatch` and `GmailMessage` each carry two
surfaces). `JobExplainer` and `ProcessQAAnswer` are real AI-backed models
but aren't among the bundle's eight named surfaces — left untouched.

**Design question 1 — same type/range as `classification_confidence`, not a
numeric score:** Yes, reused exactly (`String(20)`, `"high"`/`"medium"`/
`"low"`). The bundle displays three discrete levels, not a percentage, and
a shared type means one rendering path in `intelligence_surface()` for
every surface rather than a per-model conversion layer. No column differs
in shape.

**Design question 2 — nullable, null hides the badge:** Confirmed by
reading `intelligence_surface()` (`app/templates/_components.html`)
directly rather than assuming: `reliability_label` is computed via
`{'high': 'HOCH', ...}.get(reliability)`, and the badge `<span>` is wrapped
in `{% if reliability_label %}`. A `None` value already produces "no badge
rendered," not a fabricated "HOCH" default — no macro change was needed.

**Design question 3 — where does the value come from (the real
question):** Checked every generator function directly, not assumed.
Exactly one surface has a genuine mechanism: `email_classification`'s
system prompt already instructs the model to output a `CONFIDENCE:
high|medium|low` line alongside its classification (`app/ai/prompts/
email_classification.py`), because the entire response IS a small set of
structured fields (`INTENT`/`CONFIDENCE`/`NOTES`) parsed out of the text -
asking for a fourth field costs nothing and doesn't touch anything
user-facing.

Every other surface is a different shape of problem: `response.text` **is**
the delivered content verbatim (the narrative, the letter, the email body,
the summary) - there is no structured field to add a `RELIABILITY:` line
next to without asking the model to also emit a meta-line inside otherwise
free-form prose, then parsing and stripping it back out before storing the
content. That's a real prompt-and-parsing change per surface, not a schema
addition, and it wasn't scoped for this pass ("small, mechanical... no UI,
no screens, no templates"). More importantly, doing it wouldn't actually
answer the question honestly: a model's self-reported confidence in its
own classification is already acknowledged as weak evidence in the one
place it exists; multiplying that same weak mechanism across six more
surfaces manufactures the *appearance* of a signal without adding real
evidence behind it.

One near-signal was checked and deliberately not used:
`GeneratedDocument.validated`/`validation_notes` (cover letter's existing
two-pass generate-then-validate flow, `app/ai/cover_letter.py`) is a real,
non-invented pass/fail fact-check - but it answers "did the AI invent
something not in the candidate's real data," a different question from
"how confident is the model in this text's quality." Mapping one onto the
other would misrepresent what either signal means, so `reliability` is not
derived from `validated` - they stay two separate, honestly-labeled
columns.

**Conclusion, stated plainly because it's the actual decision:** six of
the seven new columns ship unpopulated - every generator was checked to
confirm none of them touch the new column, and a test asserts each stays
`None` after generation (`tests/test_reliability_and_edit_tracking.py`).
An empty slot that hides the badge is more honest than a rating this
project has no real basis for. This isn't a gap to close reflexively in
the next pass; it's a standing conclusion that should only be revisited if
a genuine per-surface signal shows up (e.g. a provider that returns real
token-level confidence, or a structural check specific to that content
type) - not by defaulting to self-report just because the column exists.

**Consequences:** Migration `5b4fe35a6528` (down-revision
`5405dd108168`), autogenerated and verified column-for-column against this
mapping before being committed unedited. Applied to Railway's production
database by the user, 2026-08-26 - see the Deploy note in this same
date's "Edit tracking" entry below, they share one migration.

---

## 2026-08-26 — Schema pass: edit tracking extended to interview prep, CV statement, reply suggestion

**Decision:** Added `edited_at` (`db.DateTime`, nullable) to
`InterviewPrep`, `CvProfileStatement`, and `GmailMessage` (as
`reply_suggestion_edited_at`, since `GmailMessage` already carries a
different timestamp-shaped concept for its other surface). Checked how the
two existing usages (`GeneratedDocument`/cover letter,
`GeneratedEmail`/application email) actually determine "edited" before
copying the pattern, rather than assuming: it's a plain timestamp, set to
`utcnow()` unconditionally by the dedicated `save_*` route
(`app/applications/routes.py`) whenever it's called against an *existing*
row - never a hash or text-diff comparison against the generated content.
The three new columns match that exact mechanism and type.

**Honest gap found while matching the pattern:** cover letter and
application email have that dedicated save route because the app already
lets a user edit and persist their content separately from
(re)generating it. Interview prep and the CV statement do not - both are
currently generate/regenerate-only (confirmed by reading `applications/
detail.html` and `app/applications/routes.py` directly: no save form, no
save route, for either). The reply-suggestion textarea in `applications/
detail.html` *does* let a user retype the AI's draft, but that edit is
never persisted back to `GmailMessage` today - it's read once, at
send-time, straight into the Gmail draft (`create_reply_draft`), and
discarded otherwise. So for all three, there is currently no code path
that could set `edited_at` even if the column existed - "extend the same
pattern" is satisfied at the schema level (same column type, same
timestamp-not-diff semantics), but the save-action wiring itself doesn't
exist yet anywhere in the app for these three features. That's real,
in-scope screens-pass work (a save form + route per feature), not
something this schema-only pass invents routes for.

What this pass does verify: that AI (re)generation itself must never be
mistaken for an edit. `generate_interview_prep()`, `generate_cv_profile_
statement()`, and `generate_reply_suggestion()` were all checked directly
- none of them touch the new `edited_at` columns - and
`tests/test_reliability_and_edit_tracking.py` asserts this stays true.
When the screens pass adds a save route for each of these three, it drops
straight into the identical one-line pattern already used twice
(`x.edited_at = utcnow()` inside the save handler, only when updating an
existing row) - no new mechanism to design then.

**Consequences:** Same migration as the reliability entry above
(`5b4fe35a6528`, down-revision `5405dd108168`). Full pytest suite: 452
passed / 3 skipped (443 + 9 new tests covering both entries' nullable
defaults and non-population).

**Deploy:** this migration was not applied to Railway's production
database by this pass itself - per `DEPLOYMENT.md`'s Post-deploy checklist
(written in anticipation of this exact pass, after the 2026-08-25 Job
Radar deploy gap where a real migration shipped in code but was never run
against production), the user runs `flask db upgrade` against Railway's
console themselves. Confirmed applied, 2026-08-26 - the step this note
existed to make sure didn't get silently skipped the way
`job_radar_status` was.

---

## 2026-08-26 — Component layer pass: macros built, three decisions locked in

**Decision:** Built `app/templates/_components.html` (11 macros: `btn`,
`arrow_link`, `status_pill`, `chip_source`, `chip_attribute`,
`chip_coverage`, `match_band`, `empty_state`, `notice`,
`intelligence_surface`, `progress_bar`), demonstrated at `/admin/components`
(admin-only). Build-only — no existing call site touched, nothing in the
live app changed appearance. Full detail (contrast measurements,
component reference table, ambiguity resolutions) in `DESIGN_SYSTEM.md`'s
"Component layer — 2026-08-26 pass" section; this entry records the three
decisions made going in and one real bug the pass's own contrast
measurement caught.

**1. Arrow links and tertiary buttons both exist, as separate components.**
`AUSVIA_2_0_COMPONENT_AUDIT.md` had framed the app's 35+ existing arrow
links vs. the bundle's tertiary-button spec as a divergence to reconcile.
That read was wrong: the bundle itself uses arrow links too (8 of them —
"Paket öffnen →", "Alle ansehen →", "Profil vervollständigen →", etc.) for
navigational "go here" actions, while tertiary buttons are in-context
actions ("Neu erzeugen", "Regenerate"). Different jobs, both real, both
built as separate macros. This corrects the audit's framing, not a new
call.

**2. `match_band()` replaces the five stacked bars.** A real visual
change to a signature dashboard/job-detail feature, not a pure addition.
Segment *width* encodes category weight, read from
`app/ai/matching.py`'s `CATEGORY_WEIGHTS` (never guessed/hardcoded in the
macro). Segment *fill* encodes achieved proportion. A 0%-achieved segment
renders as a visible empty groove with its percentage in `warn`, not
hidden or collapsed — the bundle's own honest-absence pattern, confirmed
by reading its construction directly (`h-full bg-brand ... width:
{achieved}%`, no fill div at all when a category is unevaluated).
Migrating the two live call sites (`jobs/detail.html`,
`main/dashboard.html`) onto this macro is the screens pass's job, not
this one.

**3. Empty state: macro only, not the 20 copy sets.** Built
`empty_state(heading, guidance, action_label, action_href)` and
demonstrated it with one example ("Noch keine Unterlagen"). The app's 20
existing empty states keep their current, more minimal copy until the
screens pass migrates them deliberately, one at a time — writing 20 sets
of German UI copy is a content decision, not a component-layer one.

**Real bug caught by measurement, not assumed:** the Ready status pill's
`text-brand` on `bg-tint` measures 4.45:1 in dark mode — fails AA (4.5:1)
by a hair, despite passing in light mode (4.90:1). Fixed by using
`brand-hover` (an existing theme-aware token) for that state's label
instead of introducing a new one: 7.23:1 light / 7.34:1 dark. Caught
because this pass measured every new pairing rather than assuming the
existing `brand`/`tint` combination — already AA-clean elsewhere in the
app — would carry over safely to a new, smaller-text context.

**Correction to a prior claim:** `AUSVIA_2_0_COMPONENT_AUDIT.md` stated
the existing `.ausvia-bar-fill` 12px clip-path shear was "already verified
bundle-accurate." Re-checked directly this pass by searching the unpacked
bundle for `clip-path`/`polygon`: zero matches anywhere in the file. The
shear has no bundle counterpart — it's a real, separate, earlier design
decision (visual direction 1a, "Counterform"), kept deliberately in
`progress_bar()` rather than reverted, since this pass wasn't asked to
undo an already-shipped signature. The audit's claim was inaccurate; this
entry and `DESIGN_SYSTEM.md` both now say so.

**Alternatives considered:** using a component library (Flowbite, etc.)
for any of the ten pieces — not pursued; every component here is a
small, bundle-spec-driven Jinja macro with no interactive/JS behavior
needing a library, and the pass's own instructions were to stop and ask
before reaching for one rather than assume it saves effort.

**Consequences:** `app/admin/routes.py` gained one new route
(`/components`, reusing the blueprint's existing admin-only
`before_request` guard — no new auth pattern). `tailwind.config.js`'s
existing content glob already covered the two new template files, so no
config change was needed (confirmed, not assumed). Full pytest suite
unchanged at 443 passed / 3 skipped.

---

## 2026-08-26 — Tailwind build pass: CDN replaced with a compiled, committed stylesheet

**Decision:** Replaced the Tailwind CDN (`<script src="https://cdn.tailwindcss.com">`
plus an inline `tailwind.config` `<script>` block, both in `base.html`)
with a real build: `tailwind.config.js` + `assets/css/input.css` at the
repo root, compiled via `npm run build:css` into
`app/static/css/tailwind.css`, which is committed and served as an
ordinary static file. `base.html` now has a single
`<link rel="stylesheet" href=".../css/tailwind.css">` where the CDN
script and both inline `<style>` blocks used to be. No token value
changed - this is a delivery-mechanism change, not a redesign; every hex
in `tailwind.config.js`/`assets/css/input.css` is byte-identical to what
was in `base.html` before. Built output: 18,247 bytes minified, vs. the
CDN's own runtime script at 407,279 bytes (fetched and measured directly,
not estimated) - about 22x smaller, and zero runtime JS needed to produce
styling at all, where the CDN had to download, execute, and inject its
own stylesheet on every page load.

Railway's deploy pipeline is **unchanged** - still pure Python, no Node.
The compiled CSS is committed like any other static asset; Node/npm are
dev-time-only tools (`package.json` is `"private": true`, `node_modules/`
stays gitignored). This was explicit and non-negotiable going in: this
project already shipped one broken deploy because a required step (a
migration) wasn't run against production before the first request landed
(2026-08-25 "Deploy gap" entry) - adding a Node build step to Railway's
pipeline would be a second, structurally identical way to create that same
failure mode, just for CSS instead of schema. Building locally and
committing the output avoids it entirely: there's no new thing Railway has
to remember to run.

**The tradeoff, handled explicitly rather than hand-waved:** a committed
build can go stale exactly the way the migration did - correct source,
correct config, but the compiled file wasn't regenerated before a push. Two
concrete mitigations, both shipped in this same pass, not deferred:
`DEPLOYMENT.md` gained a **Pre-deploy checklist** (new section - the
existing Post-deploy checklist covers the migration step, which happens
*after* a push against the live database; this is a *before-push* concern,
a different moment in the pipeline) requiring `npm run build:css` +
`npm run check:css` before any push touching a template or the Tailwind
config. `check:css` (`scripts/check-css-stale.js`) is the forgetting-proof
half of that - it rebuilds into a scratch file and fails loudly if the
result differs from what's actually committed, rather than relying on
anyone eyeballing a diff or remembering the step exists.

Two real risks were checked before configuring the content scanner, not
assumed away: (1) whether any Tailwind class name in this codebase is
built dynamically (string concatenation, a status→class dict, `"bg-" ~
var` in Jinja) - a scanner that regexes file contents for class-shaped
tokens cannot see those, and they get silently purged. Audited every
`.py` file and every template for this pattern; found none - every
status/semantic→class mapping in this app is a complete-literal
`{% if/elif/else %}` branch (confirmed independently, not just taken on an
agent's word - grepped `app/**/*.py` directly for Tailwind-shaped tokens
and found only a false-positive comment). No safelist entries were needed.
(2) Whether removing the CDN's `'unsafe-inline'` style-src allowance would
break the app's own pre-existing inline `style="..."` attributes (CSP's
style-src governs those too, not just injected `<style>` tags/CDN
behavior - a distinction the original CSP comment didn't need to draw
since 'unsafe-inline' covered both anyway). Found 8 sites; several dynamic
ones (a computed match-score percentage as a bar width, an animation
delay) can't be pre-baked into a static compiled stylesheet. Resolved via
CSP Level 3's `style-src-attr` directive, kept separately `'unsafe-inline'`
while `style-src` itself (governing `<style>` elements and `<link>`
stylesheets - the CDN's actual attack surface) now has no inline allowance
at all - see `app/security_headers.py`'s updated module docstring for the
full reasoning and the graceful-degradation caveat for pre-2022-era
browsers.

**Reason:** Four benefits, all real, not just "best practice" cargo-culting:
smaller/faster (measured, above), the CSP hardening the CDN was blocking
(`style-src` genuinely has no inline allowance now, not just a nominally
narrower one), no runtime FOUC risk (a native `<link rel="stylesheet">` is
render-blocking by default, which is strictly better for this than the old
CDN script's download-execute-inject sequence), and config that lives in a
real, diffable file instead of a `<script>` block inside a Jinja template.

**Alternatives considered:** Adding the Tailwind build to Railway's deploy
pipeline (`nixpacks`/buildpack Node+Python multi-stage, or a Railway build
command) - rejected per explicit instruction and for the reason above: it
would be a second way to reproduce the exact class of failure the
2026-08-25 migration incident already demonstrated, and this project has
no other Node dependency that would justify carrying that risk. Tailwind
v4's CSS-native `@theme` config - rejected for this pass: v4 replaces the
JS `tailwind.config.js` object model with CSS-first configuration, which
would mean rewriting (not just relocating) every token definition in a
pass explicitly scoped to "how Tailwind is delivered, not how tokens
work." Pinned to `tailwindcss@^3` instead, porting the existing
`theme.extend` object verbatim. Leaving `style-src` with a blanket
`'unsafe-inline'` "to be safe" - rejected as not actually safer: it would
have kept the exact vector (arbitrary injected stylesheets) this pass
exists to close, for zero benefit once the CDN was gone.

**Consequences:** `package.json`/`tailwind.config.js`/`assets/css/input.css`/
`scripts/check-css-stale.js` are new; `app/static/css/tailwind.css` is
committed and must be kept in sync per the pre-deploy checklist above.
`app/templates/base.html`'s `<head>` is substantially shorter (one `<link>`
instead of a CDN `<script>` + two inline `<style>` blocks + a config
`<script>`). `app/security_headers.py`'s CSP changed: `script-src` no
longer allowlists `cdn.tailwindcss.com`; `style-src` lost `'unsafe-inline'`;
`style-src-attr 'unsafe-inline'` is new. One existing test
(`test_csp_allows_tailwind_cdn_and_fonts_but_nothing_broader`) asserted the
old CDN-allowing policy and was updated to assert the new one, plus one new
test asserting `style-src` has no inline allowance while `style-src-attr`
does. Full pytest suite: 443 passed / 3 skipped (441 + 1 renamed + 1 new),
no schema change. Verified via a real Playwright pass (not just the test
suite): all six screens, both themes, zero console errors or CSP
violations at any point across the whole session. Shipped on a branch
(`tailwind-build-pass`), not master - Railway deploys from master, and a
wrong or missing compiled stylesheet would mean the live app serves
unstyled, so this waits for an explicit decision to merge rather than
deploying itself.

---

## 2026-08-26 — Theme pass browser verification: 3 real bugs found and fixed

**Decision:** Closes the disclosed gap in the 2026-08-25 theme-pass entry
below (no browser tool was available that day, so the pass shipped
verified by CSS values and contrast math only, with the visual check
explicitly flagged as not done, not silently skipped). Playwright MCP
became available the next day; ran the full six-screen, both-theme visual
pass against the real dev server with a real user's real data. Found
three real bugs, all fixed same-session, all confirmed by re-running the
full pass afterward:

1. Every text input/textarea app-wide was illegible in dark mode - none
   had an explicit background, so they inherited the browser's native
   white with theme-aware (now near-white in dark) text on top. Fixed by
   adding `bg-card text-t1` to `render_field()` in `_macros.html` (covers
   every WTForms field site-wide) plus 7 raw form controls found by
   sweeping every `<textarea>`/`<select>`/native input in the app.
2. The desktop theme toggle had no click listener at all - the sync
   script ran before the desktop button existed in the DOM, so
   `querySelectorAll('.theme-toggle-btn')` silently missed it. Fixed by
   moving the script to the true end of `<body>`, not to a new fixed
   position between two elements, since the desktop bar moves again
   during the screens pass and a positional fix would silently regress
   the same way.
3. The landing hero's counterform graphic disappeared in dark mode - its
   light backing div was still `bg-paper`, which resolves to the same hex
   as the `ink` foreground it's cut out of once `paper` became theme-aware.
   Fixed by pinning it to the literal `#F2F5F6` it held before the theme
   pass. Audited every other element in the landing hero and the mobile
   topbar/drawer for the same leak (a theme-aware token left somewhere
   that's supposed to stay fixed) - this was the only instance.

**Reason:** None of these three were catchable by the verification method
available on 2026-08-25 (computed hex values + WCAG contrast ratios) -
all three are structural (a missing background class, a DOM-query timing
bug, a token that leaked into the wrong surface), not wrong numbers. This
is exactly why the gap was disclosed rather than papered over with a
"verified" claim that wasn't true yet: it named precisely what a real
browser pass might find, and then found it.

**Alternatives considered:** Fixing the toggle by moving its script to sit
after the specific desktop-header block - rejected in favor of end-of-body
placement, since a positional fix tied to today's markup order breaks
again, silently, the next time that markup moves (which is already
planned for the screens pass). Inventing a new "field surface" token for
the input background - rejected; reused the already-existing `card` token
plus `text-t1`, since a form field is exactly a card-elevation surface and
a second token for the same value would be redundant.

**Consequences:** Full pytest suite re-confirmed 442 passed / 3 skipped
after all three fixes, no schema change. Full detail, including the
computed-style numbers and which specific elements were touched:
`DESIGN_SYSTEM.md`'s "Theme architecture" section, Verification
subsection.

---

## 2026-08-25 — Theme pass: real light/dark mode, superseding "ink is fixed"

**Decision:** Supersedes this file's most-recent-before-this Wegmarke/
tokens-adjacent decisions insofar as they assumed the foundation-tokens
pass's framing — specifically, the foundation-tokens pass's explicit
choice to treat `ink` (the sidebar/hero surface) as **fixed**, with "no
theme switch was built" and "a toggle is out of scope" stated directly in
`DESIGN_SYSTEM.md`. That decision is now reversed: AUSVIA has a real
light/dark theme toggle (Porzellan/Tinte), built on CSS custom properties
under `[data-theme="dark"]` on `<html>`, persisted to `localStorage`,
respecting `prefers-color-scheme` on first visit. The sidebar now follows
the theme (was fixed-ink); the mobile topbar/drawer and the landing hero
stay fixed-ink (verified against the bundle directly, not assumed — see
`DESIGN_SYSTEM.md` "Theme architecture — 2026-08-25 pass" for the full
reasoning and the specific bundle evidence for each). No hex values
changed from the foundation-tokens pass — every dark value this pass needs
already existed as the `ink-*`/`bright-*` family; this is a reference
restructuring (hex literal → CSS custom property), not a new palette.

**Reason:** Not a correction — the original decision was reasonable given
its own scope (a style-guide/token pass, not a theming pass) and was
explicit about the trade-off it was making. Product direction changed
after that pass shipped: the user wants a working toggle, matching what
the AUSVIA 2.0 bundle actually specifies (section 11: *"Tinte ist ein
vollwertiger Modus, nicht ein invertiertes Nachspiel"* — Tinte is a full
mode, not an inverted afterthought). Two real bugs were also caught and
fixed as part of doing this properly rather than just flipping a
`data-theme` switch: (1) a fixed `text-white` button label passes AA on
every light-mode fill but fails on several dark-mode fills, not just on
hover, at rest — `#12949B` fill measures 3.66:1 with white text, `#4BBE7E`
2.34:1, `#D9A22B` 2.29:1, `#5FA6D6` 2.65:1, all failing 4.5:1; fixed with
one new derived token (`on-fill`, white in light / ink in dark) rather
than five separate on-brand/on-ok/on-warn/... tokens, since the flip is
identical for all five fills. (2) Tailwind's stock `green-700`/
`amber-700`/`red-600` (used for match-score bands, validation states,
flash messages, never migrated when `ok`/`warn`/`err`/`info` were first
defined) pass AA against a light card (4.83–5.02:1) but fail against the
new dark card (3.59–3.74:1) — migrated to the theme-aware semantic tokens,
measured before migrating rather than after, confirming the replacement is
equal-or-better in both themes at every site, not just the dark one.

**Alternatives considered:** Tailwind's `darkMode: 'class'` with `dark:`
variants — explicitly rejected per direct instruction: it would add a
second class at every one of the ~500 existing color-class call sites (and
every future one). CSS custom properties add none — every existing class
name (`bg-paper`, `text-t1`, `bg-brand`, ...) keeps working unchanged in
both themes; only the variable's value swaps. Also considered and
rejected: converting the landing hero to theme-following in this same
pass, since the sidebar reversal set a "everything follows the theme"
precedent — rejected because the bundle has no themed version of the hero
to model one on (its own landing page is fully theme-following with no
dark hero section at all, so the app's counterform-graphic hero has no
bundle equivalent); converting it now would mean inventing a design
on-the-fly during a token-restructuring pass rather than following one.
Left fixed-ink, explicitly and documented as such, pending the landing
screen re-layout pass that will actually have a spec to build from.

**Consequences:** The full accessibility contrast table (light + dark, 12
pairings) and the exact hardcoded-color-hunt counts (68 `bg-white`→
`bg-card` sites, 27 `text-white`→`text-on-fill` sites, 62 semantic-literal
class occurrences migrated) are in `DESIGN_SYSTEM.md`. No schema/migration
— this is templates/CSS/JS only; full pytest suite unaffected (442/3,
unchanged before and after). One open gap, disclosed rather than silently
skipped: no browser-automation tool was available in this environment to
do a live rendered-in-both-themes visual pass — verification here is CSS
values + contrast math + confirmed template rendering (no Jinja errors,
expected classes present in output), not an eyeballed screenshot check.

---

## 2026-08-25 — Deploy gap: Job Radar's migration was never run against production; added a post-deploy checklist

**Decision:** Not a code decision - a process one. The dashboard 500'd in
production (Railway) for an unknown period because the `job_radar_status`
table migration, shipped as part of the Job Radar feature, was never
applied to Railway's Postgres database. Every `/dashboard` load queries
that table (`app/main/routes.py`); on production it didn't exist, so
every load 500'd. Confirmed root cause: Railway's Postgres was at
migration head `f3653f96d36d` while the repo (and every environment that
had run `flask db upgrade` since) was at `5405dd108168`. Fixed by running
`flask db upgrade` in Railway's console - production is now at head and
the dashboard renders. Added a "Post-deploy checklist" to
`DEPLOYMENT.md`: after any push containing a migration, run
`flask db upgrade` against production, confirm `flask db current` shows
the new head, and load `/dashboard` as a real user before calling the
deploy done.

**Reason:** This wasn't a code bug and no amount of code review would
have caught it - the code, migration, and tests were all correct. It was
a missing operational step: the migration file existed and was correct,
but nobody ran it against the actual production database after the push
that shipped it. Three separate signals that should have caught this
didn't, each for a specific reason worth naming rather than glossing
over: `GET /health` returns `200` with no DB check at all, by deliberate
design (documented in `app/main/routes.py`'s own comment) - so it stayed
green through the entire incident. The pytest suite passed (442/3) both
before and after this incident because it runs against its own
fresh-per-run SQLite database, created from the *current* models on every
invocation - it can never observe a stale *production* database missing
a migration, because "a stale test database" isn't a state that exists.
And the failure itself was indistinguishable from a real code bug from
the outside: a generic, already-logged 500 page, no user-facing detail -
which is why the first two rounds of investigating this (see the
foundation-tokens-pass and logo-pass conversation history) chased code-
level theories (a collapsed Jinja conditional, a template auto-reload
race) that were reasonable given the evidence available at the time, but
wrong. Both were falsified by direct testing before being reported as
fact, not assumed - but neither found the real cause, because the real
cause wasn't observable from inside the app at all, only by comparing the
repo's migration head against Railway's actual applied revision.

**Alternatives considered:** Treating this as sufficiently explained by
"someone forgot a step" and not documenting it further - rejected,
because the actual finding is that *nothing in the deploy path makes
forgetting that step visible*, which is a real, fixable gap, not just
this one instance of human error. Making `/health` check the database -
considered and rejected for this fix: `/health` is deliberately minimal
(no DB/dependency check) so the *process* being alive is distinguishable
from the *app* being healthy, which matters for host-level restart
decisions; conflating the two would make a slow DB query able to fail a
liveness probe and cause unnecessary restarts. The right fix is a
checklist step that actually loads the app, not a heavier health check.

**Consequences:** `DEPLOYMENT.md` now has a "Post-deploy checklist"
section - not previously documented anywhere in the repo (checked: no
`DEPLOY.md`, `DEPLOYMENT.md` existed but only had a one-line "run
`flask db upgrade` before first traffic" note scoped to *initial* setup,
not an ongoing post-push step). This matters beyond this one incident:
the planned AUSVIA 2.0 reliability-field work adds a column to seven
existing models - seven more chances to ship a correct, tested,
migration-bearing pass and have it silently not take effect in
production the same way. No code changed as part of this entry; the
dashboard 500 is already resolved by the migration having been run.

---

## 2026-08-25 — Retire Aperture (rev 1.0), implement Wegmarke as the AUSVIA symbol

**Decision:** Replaced the Aperture symbol (a route-climbing-to-a-point
counterform cut into a rounded tile, `fill-rule="evenodd"`, one path) with
**Wegmarke** ("waymark") — two flat, non-overlapping offset tracks at the
same angle, the right one 6 units higher and 14 units ahead on a 48-unit
grid, transcribed exactly from the approved AUSVIA 2.0 mockup bundle's own
Foundations reference screen. Implemented everywhere the symbol appears:
`_logo.html`'s `symbol()`/`lockup()` macros (plus a new `app_icon()`
macro the bundle's own spec calls for but the old system never had), all
17 static SVG/PNG exports under `app/static/brand/`, and the favicon.
Below 22px both macros automatically switch to a wider-bar path variant
(bar width 10, not 8) per the bundle's own stated rule, verified by
rendering the real macro output at sizes on both sides of that threshold,
not just reading the conditional in source. Symbol color follows the
existing light/dark token split (`brand` `#0B767D` on light, `bright`
`#4FC3C9` on ink) — resolving a real discrepancy in the bundle itself,
where two of its four rendered examples hardcode a different teal
(`#0F7379`) instead of using its own `var(--brand)`; the shipped token was
used everywhere, not the inconsistent hardcoded value, since `#0F7379` has
no other consumer anywhere in this app. The wordmark — Sora SemiBold,
lowercase "ausvia", −4% tracking, the same outlined vector path extracted
from the licensed font via `fontTools` — is completely untouched; only the
symbol half of every lockup changed. Full detail, the color-role table,
and the flagged pre-existing wordmark-color inconsistency this pass
deliberately left alone: `DESIGN_SYSTEM.md`'s "Logo — Wegmarke replaces
Aperture" section.

**Reason:** This is the direct, planned follow-up to the 2026-08-25
foundation-tokens pass, which explicitly flagged Aperture as "superseded,
not just off-palette": the approved 2.0 bundle specifies a different mark
entirely, and shipping Aperture in the new teal accent colors (done in
that earlier pass, since the symbol's *color* is set by the same tokens
every other accent uses) left the app with a mark that was correctly
colored but the wrong shape — a mismatch the tokens pass could describe
but not fix, since implementing new symbol geometry was explicitly out of
that pass's scope. Aperture's own rationale (rev 1.0, 2026-08-11: a route
climbing to a point, doubling as a cut-open "A" for Ausbildung/Ausvia) was
sound design reasoning for the pre-2.0 direction, not a mistake being
corrected — it's superseded by product direction (the approved 2.0
mockup), not by a flaw in the original mark.

**Alternatives considered:** Keeping Aperture and only re-coloring it to
the new palette — rejected, since that's what the tokens pass already did
and is exactly the "wrong color and, per the approved direction, wrong
shape" state this pass exists to resolve. Redrawing Wegmarke by eye from
the bundle's rendered screenshots — rejected; the bundle contains real SVG
path data, and re-deriving coordinates by eye when exact numbers are
available would reintroduce the risk of subtle inaccuracies for no reason.
Using the bundle's hardcoded `#0F7379` for the symbol instead of the
`brand` token — rejected once the bundle's own internal inconsistency was
found (two of its four examples use one value, two use the other); the
token every other surface in the app already uses was the only
non-arbitrary choice. Renaming the static asset files to match their new
colors (e.g. `ausvia-symbol-blue.svg` no longer being blue) — rejected for
this pass per the explicit instruction to keep the existing filename
convention; flagged as a safe future cleanup instead (nothing references
these files by path).

**Consequences:** Real work across `_logo.html`, 3 template call sites
(`base.html` ×3 for `bright`, `landing.html` relying on the new `brand`
default), and 17 static brand assets — not a pure recolor. Favicon PNGs
(`favicon-16.png`, `favicon-32.png`) were regenerated via Pillow at 8×
supersampling from the exact path coordinates, since no SVG rasterizer
(cairosvg/Inkscape/ImageMagick) is available in this environment — visibly
confirmed correct, not just asserted. No `.ico`, `apple-touch-icon`, or
web manifest exists in this repo to regenerate; none were invented. One
pre-existing inconsistency was found: the wordmark's light-surface text
color still hardcoded the *pre-tokens-pass* `ink` hex (`#0B1220`), not the
current `#0C1013`. Initially flagged as out-of-scope ("symbol only") and
left for a future pass; on the same-day follow-up review that was judged
too conservative for a one-line, zero-risk correction of an
already-retired literal, and fixed the same day in a small follow-up
commit (see `DESIGN_SYSTEM.md`'s "Logo — Wegmarke replaces Aperture" for
the current, corrected state). `LOGO.md` was not rewritten (it's now a
historical
record of
Aperture, which didn't change) but got a superseded-notice pointing here.
Full pytest suite: 442 passed / 3 skipped, unchanged.

---

## 2026-08-25 — Foundation-tokens pass: light/dark accent, page background, and status-marker colors replaced (Signal Blue → Tiefsee-Teal); the `brand-50..900` shade ramp retired for a smaller, role-mapped token set

**Decision:** Implemented the AUSVIA 2.0 foundation-tokens pass (colors,
typography, spacing, radius, shadow, focus states only — no screens,
components, or logo changes), extracting every value from the approved
2.0 mockup bundle's own "Foundations" reference screen. The single accent
changes from Signal Blue (`#2563EB`) to Tiefsee-Teal (`#0B767D`, light
surfaces) / `#12949B` (fixed ink surfaces, a new, distinct role from the
existing `bright` text/icon-on-ink accent, now `#4FC3C9`); the page
background from `#FAF8F5` to `#F2F5F6`; the fixed dark sidebar/hero
surface from `#0B1220` to `#0C1013`. The old `brand-50` through
`brand-900` Tailwind shade ramp is retired entirely — the 2.0 system does
not have a ramp, only two raw accent values (`brand`/`brand-hover`) plus
two light washes (`tint`/`tint2`). Every one of the ~110 `brand-NNN`
call sites across ~24 templates was individually read in context and
assigned to one of six roles (primary action fill, primary action hover,
link/tertiary text, brand-colored border, light-wash fill, light-wash
border) — never picked by nearest-lightness hex, which can put a fill
color in a text role. Full table: `DESIGN_SYSTEM.md`'s "Foundation
tokens — 2026-08-25 pass".

**Reason:** Explicit product direction — the AUSVIA 2.0 mockup bundle is
the approved next visual direction (see the 2026-08-24 audit referenced
in `ROADMAP.md`'s "AUSVIA 2.0 redesign" section), and this is its first
implementation pass. The shade-ramp retirement specifically was a
deliberate, explicit choice over generating synthetic `brand-50..900`
values algorithmically from the two real anchor hexes: `tint`/`tint2`
**are** the 2.0 system's answer to "light badge/card fill and border,"
not a smaller version of a bigger ramp that never existed in the approved
design — shipping invented intermediate shades would mean roughly half
the app's accent color values were never actually approved by anyone.

**Alternatives considered:** Generating the missing `50`–`900` shades
algorithmically from the two anchor hex values (consistent lightness
steps) so every existing `brand-NNN` utility class kept working with zero
template edits — rejected specifically because it manufactures colors
the approved design never specified, for a system that structurally
doesn't have a ramp. Mapping each retired shade to its nearest-lightness
new token without checking the call site's actual role — rejected before
it started; nearest-hex-by-lightness routinely picks a *fill* token for a
*text* role or vice versa (e.g. `brand-50`, a near-white wash, is closer
by raw lightness to `tint2`'s border role than to `tint`'s fill role in
some naive rankings, despite the two having opposite intended uses).

**Consequences:** Real per-template work across ~24 files (documented in
`DESIGN_SYSTEM.md`'s role-mapping table), not a pure config change — an
explicit, accepted tradeoff for correctness over minimal footprint. One
call site turned out to be an actual pre-existing bug, not just a rename:
the landing hero's primary CTA was using the light-surface `brand` fill
directly on the dark ink hero (exactly the mistake the project's own
"Signal Blue is light-only, Bright Blue is dark-only" rule, 2026-08-11
below, was written to prevent — just missed for a fill color instead of a
text color), with an undocumented manual hover-lightening patch
compensating for the resulting low contrast. Fixed to use the real
ink-surface action pair, which lightens on hover by design; its white
label text also failed WCAG AA at this button's size (3.66:1, computed)
and was switched to ink-colored text (5.22:1, passes) — see
`DESIGN_SYSTEM.md` Accessibility for both numbers. `_macros.html`'s
`render_field()`/`render_checkbox()` focus style changed from a 1px inset
ring to the bundle's real 2px solid outline + 2px offset; the sidebar
nav/logout/admin links and the mobile nav toggle/close buttons gained a
focus outline for the first time (previously none existed, relying on an
unverified browser default against the dark surface). `paper`'s hex
changed but no other neutral-scale (`slate-*`) color was touched — this
was **not** a full retheme; the existing `text-slate-900`/`slate-600`/
etc. text scale, `border-slate-200` card borders, and the existing
`green-600`/`amber-600`/`red-600` semantic colors are all unchanged. The
bundle's own `ok`/`warn`/`err`/`info` semantic tokens are now defined in
the Tailwind config but deliberately not wired into that existing
green/amber/red usage — revisiting that is a separate decision this pass
didn't reopen (see the 2026-08-11 "Brand palette reuses the existing
Tailwind slate/blue scale" entry below, still standing). One real,
flagged inconsistency this pass does **not** fix — and it's stronger
than a palette mismatch: the logo symbol (Aperture, rev 1.0,
`_logo.html`/`app/static/brand/*.svg`) is frozen while the approved 2.0
bundle specifies a **different mark entirely** ("Wegmarke" — two offset
tracks on a 48 grid, not the aperture counterform cut), not implemented
anywhere in the codebase. The wordmark spec (Sora SemiBold, lowercase,
−4% tracking) is unchanged, so the existing outlined path stays valid.
Documented as a known, deliberate, temporary state in `DESIGN_SYSTEM.md`,
needing its own follow-up decision (implementing Wegmarke, or reverting
the app's accent instead) before the two are reconciled.
Bundle-matched Tailwind defaults required zero config or template
changes: `rounded-lg`/`rounded-xl`/`rounded-full` already equal the
bundle's control/card/pill radii, and `p-6`/`gap-8`/`mt-14` already equal
its card-inner/block/section spacing — both systems happen to share the
same 4px base unit. `shadow-sm` was left in place rather than replaced
by a new exact-match token — the difference from the bundle's `--sh` is
imperceptible (near-black vs. ink-tinted black at the same 5% opacity)
and it's already applied at 154 call sites. One pytest assertion
(`test_status_route_accessibility.py`) hardcoded the retired
`border-brand-600` class name and was updated to `border-brand`, not
deleted or skipped — the ring/shape logic it actually tests (dashed vs.
solid) is unchanged. Full suite: 442 passed / 3 skipped, unchanged from
before this pass.

---

## 2026-08-25 — Light-surface neutral scale (Tailwind `slate` → bundle's Porzellan `t1`/`t2`/`t3`/`line`/`line2`/`raised`) fully migrated, not left as "close enough"

**Decision:** Added six light-surface neutral tokens (`raised`, `line`,
`line2`, `t1`, `t2`, `t3`) from the bundle's Foundations screen, and
migrated all 384 `slate-NNN` call sites across 31 templates to them by
role, same method as the `brand` shade-ramp migration above. `card`
(`#FFFFFF`) needed no new token — it already equals Tailwind `white`. Full
token table and role-mapping table: `DESIGN_SYSTEM.md`'s "Light-surface
neutrals (Porzellan)" and "Neutral-scale role mapping" sections.

**Reason:** This pass originally shipped without this migration — the
initial reasoning was that swapping Tailwind's default `slate` scale for
a bundle-defined equivalent was a full retheme, not a token swap, and out
of this pass's scope. That reasoning was wrong: `slate` is measurably
blue-tinted, not a neutral approximation of the bundle's cool-neutral
scale. `t1` (`#101619`) vs `slate-900` (`#0F172A`) differ by 17 units on
the blue channel alone; `t2` (`#55636D`) vs `slate-600` (`#475569`) shows
a comparable lightness/saturation shift. Both are visible across a full
page of running body text, which is most of the app. Leaving this
undocumented and unmigrated would have meant roughly half the app's
"neutral" surface never actually matched the approved design, silently.

**Alternatives considered:** Documenting the deltas in `DESIGN_SYSTEM.md`
and leaving `slate` in place as "close enough" — rejected once the actual
RGB deltas were computed and found to be a real, visible difference, not
a rounding-level one; the same standard already applied to `brand`
(no synthetic/approximate values) applies here. Mapping each retired
shade to its nearest-lightness token without reading the call site's role
— rejected for the same reason it was rejected for `brand`: nearest-hex
picks a border token for a text role or vice versa in enough cases to be
unreliable.

**Consequences:** Real per-template work across 31 files, not a pure
config change — the same tradeoff already accepted for `brand`. One
genuine accessibility regression was caught and fixed within this same
pass, not shipped and fixed later: mapping `slate-500`/`slate-400` to the
"obviously correct" `t3` computed at 2.76:1–3.02:1 against the app's
light surfaces, failing WCAG AA at 98 call sites (mostly helper text and
table headers — normal-sized, genuinely read). The class it replaced
(`slate-500`/`slate-400`) measured 4.35–4.76:1 in the same positions —
borderline-passing — so this would have been a real regression, not a
wash. Remapped to `t2` instead (5.65–6.19:1); `t3` stays defined as a
token (it's a real bundle value, kept for a future large-text-only use)
but wired into zero live call sites, exactly matching how `ink-t3` was
already handled for the identical reason. One small, honest side effect:
a two-branch conditional in `applications/detail.html`'s Wayfinding
component collapsed to identical branches once `t3` left and was
simplified to a single class — the reached/not-reached distinction it
carried is still conveyed by the adjacent label line and connector color,
just no longer redundantly encoded twice. Full suite re-run after this
migration: 442 passed / 3 skipped, unchanged.

---

## 2026-08-25 — Sora becomes a live UI webfont (titles, section headings, values, numbers), superseding "Sora is wordmark-only"

**Decision:** Sora is now loaded as a live Google Fonts webfont
(`font-weight: 600` only) and used for titles, section headings, values,
and numbers app-wide via a new `font-display` Tailwind family — not
scoped to the outlined logotype path data anymore. IBM Plex Sans replaces
Inter as the body/UI face (`font-sans`); IBM Plex Mono is added
(`font-mono`) for labels and source attributions only. This directly
reverses the 2026-08-11 "Typography decision: Sora is wordmark-only
(Option A)" entry below. Named `fontSize` tokens for the bundle's exact
scale (`text-display`/`text-title`/`text-section`/`text-body`/
`text-label`) were added to the Tailwind config, but existing
`text-3xl`/`text-xl`/etc. headings across every template were
deliberately **not** migrated to them this pass — see Consequences.

**Reason:** Explicit product direction — the approved AUSVIA 2.0 mockup
uses Sora as a live display face throughout (titles, section headings,
tabular numbers), not only in a pre-outlined logo path. The original
Option A reasoning was sound for what the project needed *then* (the
wordmark had just been outlined as static vector paths specifically so it
would never need Sora loaded at runtime, and nothing else in the app at
that time asked for a second display typeface) — that constraint hasn't
changed technically, the product direction changed instead.

**Alternatives considered:** Migrating every existing heading across
every template to the new named font-size scale in the same pass —
rejected as genuine per-template retype work well beyond "a token swap,"
explicitly scoped out; the named tokens are defined and available, the
migration itself is deliberately deferred to a future pass. Keeping Sora
scoped to the logotype and finding some other way to satisfy "titles use
a display face" (e.g. weight/tracking tricks on Inter/Plex Sans instead)
— rejected; the approved 2.0 direction specifically calls for Sora as a
second display family, not a heavier cut of the body face.

**Consequences:** The app now loads a webfont it had previously and
deliberately avoided loading — a real, honest cost worth stating plainly:
one additional Google Fonts request (same `fonts.googleapis.com`/
`fonts.gstatic.com` hosts already allow-listed in the CSP for Inter, so
no CSP change was needed) fetching three families/weights (IBM Plex Sans
400/500/600/700, Sora 600, IBM Plex Mono 500) instead of Inter's previous
400/500/600/700/800 — a comparable request shape, not a dramatically
heavier one, but it is a font-loading dependency the Option A decision
was specifically written to avoid entirely for Sora. `_logo.html`'s
outlined wordmark path data is unaffected either way — it never depended
on a loaded Sora font and still doesn't; this decision is about live UI
text, not the logo mark. Role boundary recorded in `DESIGN_SYSTEM.md` so
it doesn't drift: Sora 600 for titles/sections/values/numbers only, never
body text; IBM Plex Sans 400 for everything read as running language;
IBM Plex Mono 500 for labels/source-attributions only, never body copy.

---

## 2026-08-19 — "Approve & Send" (Gmail auto-send) investigated and rejected

**Decision:** AUSVIA will not send the application email itself. The
existing flow stands unchanged: `app/applications/routes.py`'s `approve()`
builds the package, `create_gmail_draft()` creates a Gmail draft via the
user's own connected account, and the user sends it manually from Gmail
before returning to click `mark_sent()`. `gmail.compose`/`gmail.readonly`
remain the only Gmail OAuth scopes; `gmail.send` is not added.

**Reason:** A dedicated investigation (approve-and-send-as-one-action,
gated behind explicit in-app confirmation) was run precisely to check
whether this decision should be revisited now that Gmail draft creation,
reply tracking, and AI reply suggestions all exist. It confirms the same
conclusion the 2026-08-11 entry below already reached, independently: the
current two-step flow (approve inside AUSVIA, then send from a separate,
already-open Gmail tab) gives the user a genuine second checkpoint - a
different application, a natural pause - before an irreversible action.
Collapsing that into one in-app action, even behind a strong confirmation
step, removes a structurally different kind of safety than a confirmation
dialog can restore: a dialog is answered inside the same momentum that
produced the initiating click; a second, separately-opened application is
not. This is the second time this exact scope addition has been evaluated
and turned down for the same underlying reason - see the 2026-08-11 entry
below (which rejected requesting `gmail.send`/`gmail.modify` alongside
this same "user always sends" rule) and `PRODUCT.md`'s non-negotiable
rule: "No application, and no reply, is ever sent automatically. AI
drafts; the user approves and sends."

**Alternatives considered:** Adding `gmail.send`, reusing the already-
present `googleapiclient` service object (no new dependency) to call
`messages().send()` instead of `drafts().create()`, gated behind a strong
"type the recipient to confirm" step comparable to application deletion's
typed-`DELETE` gate - rejected. The technical path is real and
straightforward (send-state/idempotency handling to avoid a duplicate
real send on a retried request, storing the returned `messageId`/
`threadId` as durable proof of a completed send, incremental OAuth
re-authorization for already-connected users whose stored token predates
the new scope) but doesn't change the core product-safety tradeoff above.

**Consequences:** No code changes from this pass. The technical findings
(idempotent send handling, `messageId`/`threadId` capture, incremental
re-auth via `include_granted_scopes=true`) are kept on record here as
useful background if this is ever genuinely reconsidered, not
implemented now. One related, smaller idea surfaced during this
investigation and worth keeping for later, independent of whether
auto-send is ever revisited: `mark_sent()` today is a pure self-report
with no verification a send actually happened. A lower-risk alternative
than `gmail.send` would be searching the user's own Sent folder (via the
`gmail.readonly` scope AUSVIA already has) for a message matching the
draft, rather than trusting the manual "I sent this" click - no new
scope, no irreversible-action risk, just better accuracy on an existing
status field. Not built now.

---

## 2026-08-13 — Phase 8 D6(a): optional dedicated Gmail token encryption key

**Decision:** Added `TOKEN_ENCRYPTION_KEY` as an optional env var
(`config.py`). When set, `app/utils/crypto.py` encrypts new Gmail tokens
with it instead of a `SECRET_KEY`-derived key; when unset, behavior is
identical to before this change. `decrypt_text()` additionally falls back
to the legacy `SECRET_KEY`-derived key whenever `TOKEN_ENCRYPTION_KEY` is
set, so already-encrypted tokens keep decrypting even if the variable is
introduced on a live deployment - no forced reconnect.

**Reason:** Requested as Phase 8 D6 option (a) specifically: real
improvement (a compromised/rotated `SECRET_KEY` no longer also exposes or
invalidates every stored Gmail token) with zero migration burden, unlike
option (b) below.

**Alternatives considered:** Option (b) - require `TOKEN_ENCRYPTION_KEY` in
production and force reconnection for tokens encrypted under the old
derivation, mirroring the `SECRET_KEY`-required-in-production check added
earlier in Phase 8. Explicitly deferred - designing the forced-migration/
reconnect flow is real scope that needs its own deliberate pass, not
something to fold into the same change as the optional opt-in version.

**Consequences:** `SECURITY.md`'s D6 gap entry updated to reflect the new
optional capability while keeping option (b) documented as still open.

---

## 2026-08-12 — Phase 6 scope: background jobs get one real call site, not a full retrofit

**Decision:** Built real background-task infrastructure
(`app/tasks/runner.py`, `BackgroundTask` model) and applied it to exactly
one operation - Gmail reply checking - rather than also retrofitting PDF
assembly and AI generation (cover letter/email/narrative/reply-suggestion/
company-insight) in the same pass, even though `ROADMAP.md`'s Phase 6
description named all three.

**Reason:** each of those operations has a different UX shape today. Gmail
reply checking is already a manual, fire-and-forget "click a button, check
back" interaction - moving it to a background task changes nothing about
how the user experiences it, just removes the wait. AI generation and PDF
assembly are different: the UI currently expects the result inline,
immediately, for the user to review/edit in the same view (a generated
cover letter appears in an editable textarea right after the button
click). Backgrounding those would require a genuine UX redesign (a
pending state, a way to know when it's done, probably polling or a
refresh prompt) - real product design work, not just an infrastructure
swap. Scoping this pass to the one call site where backgrounding is a
clean drop-in, and leaving the UX-design-required ones for a dedicated
pass, produces a real, honest improvement instead of a rushed one.

**Alternatives considered:** Retrofitting all three - rejected as
overreach for one pass; would have meant either half-finishing the UX for
AI generation/PDF assembly, or spending most of this phase's effort on
that instead of the other three Phase 6 items (company pages, document
extraction, live-verification recheck). Not building the infrastructure at
all until all three call sites could be done together - rejected; the
infrastructure itself (the DB row shape, the runner) doesn't get easier to
build later, and Gmail checking benefits from it today.

**Consequences:** `PROJECT_AUDIT.md`'s "Partially implemented" section
tracks this explicitly so it isn't mistaken for complete. The next
candidate for backgrounding, if picked up, is PDF assembly (approve
application) - closer to Gmail-checking's shape (a distinct build step
with a clear "done" signal) than AI generation is.

---

## 2026-08-12 — Background-task runner has no broker; runs eagerly (synchronously) under TESTING

**Decision:** `app/tasks/runner.py` is a `BackgroundTask` DB row plus an
in-process `ThreadPoolExecutor` - no Celery, no RQ, no Redis. Under
`TESTING`, `submit_task()` runs the target function synchronously instead
of submitting it to the executor.

**Reason:** no Docker/Redis is available in this development environment
(the same constraint that's shaped every other infra choice in this
project - SQLite not Postgres, local filesystem not S3). A DB row plus a
thread pool achieves the actual goal stated in `ROADMAP.md` ("stop
blocking the request/response cycle") without new infrastructure. The
TESTING-eager behavior isn't just a convenience: the test suite's SQLite
database is `sqlite:///:memory:`, which is connection-scoped - a real
background thread opening its own connection would see an empty database,
not the test's data. Running eagerly under TESTING sidesteps that
entirely, and as a second, independent benefit, means tests assert on
real outcomes immediately with no sleep/poll for a thread that might not
have finished yet. This mirrors Celery's own `task_always_eager` testing
pattern - a well-established solution to the same class of problem, not a
project-specific workaround.

**Alternatives considered:** A real broker (Celery/RQ + Redis) - rejected,
not available in this environment, and would be premature infrastructure
for the app's current scale (see the same reasoning already applied to
SQLite/local storage elsewhere). Mocking the background thread entirely in
tests instead of an eager-execution mode - rejected; that would test the
mock, not the real `target_fn` logic, weakening exactly the tests meant to
catch real bugs in the retrofitted route.

**Consequences:** The row shape (`task_type`, `status`, JSON `context`,
result/error text) is deliberately broker-agnostic, so swapping in
Celery/RQ later is a runner-module change, not a schema or call-site
change. Real (non-test) background tasks are not durable across a process
restart (in-memory `ThreadPoolExecutor`) - acceptable for a manually-
triggered "check for replies" action today, would need revisiting before
anything higher-stakes (e.g. a paid action) is backgrounded this way.

---

## 2026-08-12 — Document type suggestion is a keyword heuristic, not an AI call

**Decision:** `app/documents/extraction.py` suggests a document's likely
type by scanning its own extracted PDF text for known German/English
keywords per type (e.g. "Lebenslauf" → cv, "Abschlusszeugnis" → diploma) -
it never calls the configured AI provider, not even optionally.

**Reason:** this is the one place in the codebase where routing through an
AI provider would be a worse fit than the deterministic approach, not just
an unnecessary one. Detecting "does this document contain the word
Zeugnis" doesn't benefit from a language model's reasoning - a keyword
match is free, instant, and 100% reproducible, which the project's own
deterministic-first principle already treats as the ideal, not just an
acceptable fallback. Every other "AI-optional" feature in the app (match
narrative, cover letter, company insight) has a deterministic core *and*
an optional AI layer for polish; this feature is deterministic-only
because there's no meaningful polish an LLM would add to "which
checkbox was probably right."

**Alternatives considered:** Routing extraction through the AI provider
with a heuristic fallback in mock mode (matching the pattern used
everywhere else) - rejected specifically because it would be slower, cost
real tokens in production, and be *less* reproducible than the heuristic
for zero accuracy benefit on this particular task. Full OCR for scanned
documents - rejected as out of scope; no OCR library is available in this
environment, and this is disclosed honestly (`PROJECT_AUDIT.md`) rather
than silently limited to PDFs with a real text layer.

**Consequences:** Image uploads (JPG/PNG) and scanned PDFs with no text
layer get no suggestion at all - correctly absent, not a wrong guess.
`AI.md` documents this as the intentional exception to the project's
usual "deterministic core + optional AI layer" shape.

---

## 2026-08-12 — Correction pass: hardcoded exact values instead of ratio-derived ones for the three signature details

**Decision:** Replaced ratio/proportion-derived implementations of the
three visual-direction signature details with the exact literal values
from an approved correction reference, applied verbatim: hero route as a
filled counterform cut (not a stroked line), bar shear as a hardcoded 12px
at 14px bar height with a 28px fill min-width (not `bar-height × ratio`),
and the application-status current-marker as a 24px/4px-ring/10px-dot
combination that differs from other states in size, ring weight, and fill
together (not ring weight alone).

**Reason:** the previous pass's ratio-based approach was *technically*
correct (the shear ratio genuinely was 1:2, matching the logo's own leg
angle) but produced values too small to actually see at the sizes the
product uses (3-4px shear on 6-8px bars; a ring-weight-only difference
that read as noise). Correctness of the underlying math didn't survive
contact with real pixel sizes. The fix is to stop re-deriving the shear
from a ratio at every call site and instead hardcode the values that were
verified to actually render visibly, once.

**Alternatives considered:** Keeping the ratio-based token and just
tuning the ratio itself upward - rejected; a ratio still recomputes
differently at every bar height, which is exactly the fragility that
caused the original bug once bar height itself also needed to change (6-8px
→ 14px). A single hardcoded value that's independent of bar height is more
robust for a "signature detail" that's meant to be uniform across the
product, not proportional to whatever container it's in.

**Consequences:** `--ausvia-shear-ratio` and the per-element `--bar-h`
custom property are removed entirely from `base.html` - `.ausvia-bar-fill`
now has no configurable inputs at all, which is deliberate (see
`DESIGN_SYSTEM.md`). Two judgment calls made while implementing this
pass, not explicitly covered by the reference:

1. **Hero labels use percentage-based absolute positioning, not SVG
   `<text>`.** The reference's own markup uses absolutely-positioned HTML
   divs at fixed pixel coordinates, sized for its 1240px-wide demo
   sheet - not directly usable on the product's fluid-width hero.
   Converted the same relative positions to percentages of an
   `aspect-ratio`-locked container (so they scale in lockstep with the
   SVG at any viewport width) rather than switching to SVG `<text>`
   nodes (which the *previous* pass had used successfully) - staying
   closer to the reference's literal technique since the correction
   explicitly asks not to re-derive/approximate this section.
2. **The match-score category bars keep their existing green/amber/red/
   blue semantic-threshold coloring**, even though the reference's own
   illustrative example (using AUSVIA's real seeded data: Skills 25%,
   Location 50%, Start date 100%) renders every bar in flat Signal Blue
   regardless of score. Read the reference's uniform blue as a
   simplification for demonstrating the shear mechanic specifically, not
   an instruction to remove an existing, working, documented color
   system - both correction documents state this is "a values
   correction, not a new redesign" and that colors don't change. Did
   *not* extend this same reasoning to darkening the "Compatibility with
   your profile" card background (the reference's section-02 demo wraps
   its bars in a dark `#0B1220` card) - kept it white, for the same
   "colors/cards don't change" reason, since section 03's demo of the
   *same* kind of card renders it white, confirming section 02's dark
   backdrop was a spec-sheet presentation choice, not a product
   instruction.

---

## 2026-08-11 — Visual direction: Counterform (1a) everywhere, Wayfinding (1c) for application status only

**Decision:** Of three explored directions (Counterform, Record,
Wayfinding — "Design exploration directions.pdf"), Counterform (1a) is the
product's direction: the ascending-staircase process-flow graphic on the
landing hero, and the 63.4° shear (the logo mark's own leg angle) applied
as a reusable token to every progress-bar fill. The application-status
component is the one deliberate exception, using Wayfinding's (1c)
station/marker route instead of Counterform's bar-shear treatment. Record
(1b) is not used anywhere.

**Reason:** explicit product direction. The two directions solve different
problems on purpose: Counterform's signature is about the product's own
construction language (the mark's counterform cut, echoed at other
scales); Wayfinding's signature is about legibility for someone anxious
and unfamiliar with the process, which is specifically what the
application-status view needs to do. Applying Wayfinding narrowly (one
component) rather than blending both directions' hero/landing treatments
keeps each direction doing the one job it's actually good at, rather than
producing a diluted hybrid.

**Alternatives considered:** Using 1a's shear treatment on the status
timeline too, for full visual consistency — rejected per the explicit
brief; a shear-cut progress bar doesn't communicate "which of six named
stations am I on" as directly as discrete markers do. Using Record (1b)'s
ledger aesthetic anywhere - not selected, reference only.

**Consequences:** Two distinct visual signatures now coexist in the
product, each scoped to what it's good at. This is intentional and
documented here specifically so it isn't "fixed" into one direction later
by someone who doesn't know it was deliberate. See `DESIGN_SYSTEM.md`'s
"Visual direction" section for the implementation detail of each.

---

## 2026-08-11 — Application status: extracting the terminal states (accepted/rejected/withdrawn/expired) from the Wayfinding route

**Decision:** The Wayfinding route (`app/applications/status_route.py`)
shows exactly six stations, matching the sequential part of
`Application.APPLICATION_STATUSES`. The four non-sequential terminal
statuses (`accepted`, `rejected`, `withdrawn`, `expired`) are not
stations — `accepted` is treated as having completed the full route (all
six reached, none "current"); the other three infer how far the route
actually got from real evidence (events, `interview_date`) since the
status string alone doesn't say where the process stopped, and are shown
as a small badge next to the section heading rather than a seventh/eighth
marker.

**Reason:** the design brief specified six stations "matching the existing
status lifecycle" but didn't address the other four values, which aren't
sequential steps forward — they're exits (a rejection can happen at any
point; withdrawing is a choice, not a stage). Inventing station markers
for them would misrepresent the route as having more sequential stages
than the product actually models.

**Alternatives considered:** Showing all ten statuses as stations in
lifecycle-declaration order — rejected, would render nonsensically (e.g.
"Rejected" appearing as a station between "Offer" and nothing, implying
it's always the last forward step, when rejection can happen right after
"Sent"). Hiding terminal-status applications' progress entirely - rejected,
loses real information the user has about how far they got.

**Consequences:** For a `rejected`/`withdrawn`/`expired` application, which
stations show as "reached" depends on inference (event log presence, not
just the status string) — documented in `status_route.py`'s docstrings so
this isn't mistaken for a bug if the inferred cutoff looks slightly off in
an edge case (e.g. an application rejected the same day it was marked
sent, before any other event logged).

---

## 2026-08-11 — Resolved: Signal Blue (not Ink Navy) is the logo symbol's default fill on light backgrounds

**Decision:** The symbol's default fill on light backgrounds is **Signal
Blue** (`#2563EB`), not Ink Navy. Ink Navy governs the wordmark text and
surfaces, not the mark's default color. `app/templates/_logo.html`'s
`symbol()`/`lockup()` macro defaults, and the corresponding static assets
(`ausvia-lockup-primary-light.svg`, `ausvia-lockup-stacked.svg`,
`ausvia-lockup-tagline.svg`), were updated accordingly.

**Reason:** this reverses the previous session's implementation, which
followed section 09's asset-filename table literally
(`ausvia-symbol-ink.svg` = "default, light backgrounds") and explicitly
flagged that reading as reversible. Asked to re-examine against the
spec's actual color-role language rather than file names: the earlier
"Brand identity with logo.pdf" (v1.0) states outright — "**Signal Blue:**
Primary actions, **the mark on light**" and "**Bright Blue:** Dark mode
only — **the mark on ink**." That is an explicit, unambiguous pairing of
background context to symbol color, naming Signal Blue for light and
Bright Blue for dark. Rev 1.0's own section 08 is consistent with this:
"the dark version **steps up to** Bright Blue" only makes sense as a
description of moving away from a Signal-Blue baseline. And the rendered
primary-lockup reference art in all three logo PDFs produced across this
project (8-concept exploration, v1.0 identity, rev 1.0 spec) consistently
shows the symbol in blue on light backgrounds, never ink.

**Alternatives considered:** Keeping the ink-default reading exactly as
previously implemented, since it wasn't demonstrably *wrong*, just
under-evidenced - rejected because it directly contradicts the explicit
"the mark on light" / "the mark on ink" sentence once weighed against it;
that sentence is the single clearest piece of textual evidence in either
direction and it says the opposite of what was implemented.

**Consequences:** `ausvia-symbol-ink.svg` remains a valid, real asset
(genuine use for print/monochrome-adjacent editorial contexts) but is no
longer implied as the default anywhere live. Also fixed while auditing
this: form focus rings (`_macros.html`) used Bright Blue's hex on light-
surface white inputs (`ring-brand-500`), which violates "Bright Blue is
dark-background-only" - changed to `brand-600` (Signal Blue) in both
field-rendering macros. Full reasoning and the exact quotes: `LOGO.md`
"Signal Blue vs. Ink Navy."

---

## 2026-08-11 — Logo rev 1.0 implemented: outlined Sora wordmark, ink-default symbol, Sora scoped to logotype only

**Decision:** Implement the approved Aperture logo spec exactly, with four
judgment calls where the spec didn't fully pin things down: (1) extract the
real Sora SemiBold wordmark as a static vector outline via `fontTools`
rather than loading Sora as a live webfont; (2) follow the spec's file
table literally — Ink Navy is the symbol's default fill for light/editorial
contexts, Signal Blue is reserved for the favicon/app-icon/accent role; (3)
the wordmark *graphic* stays lowercase "ausvia" per the spec, while plain-
text brand mentions (titles, docs, prose) stay "AUSVIA" uppercase per the
standing Phase 5.5 correction — two different rules for two different
things, not a contradiction; (4) Sora is scoped to the logotype only
(Option A) — Inter remains the sole UI/body typeface.

**Reason:** (1) avoids a font-loading dependency for the logo entirely,
and is strictly more faithful to "outline the wordmark... do not re-set it
in a substitute typeface" than live text would be. (2) is the literal,
unambiguous reading of the spec's own file-naming table, safer to follow
than to guess at pixel colors from a rendered PDF thumbnail. (3) both
rules are independently sourced from explicit instructions (the approved
logo spec; the user's standing casing correction) and apply to different
things (a graphic vs. running text) — real brands draw this same
distinction routinely. (4) the wordmark no longer needs Sora as a webfont
(see 1), so adding it as a second UI typeface would be pure added
complexity for a stylistic change nobody asked for — the spec scopes Sora
to "wordmark" (section 03), not to UI type generally.

**Alternatives considered:** Hand-approximating Sora's letterforms with
bezier curves - rejected outright, would not actually be Sora, directly
contradicts the spec. Using Signal Blue as the default symbol fill
everywhere (matching the visual pattern across earlier exploration PDFs) -
plausible alternate reading, explicitly flagged as reversible in `LOGO.md`
rather than silently chosen. Loading Sora everywhere as the new UI display
face (Option B) - rejected as unrequested scope creep once outlining made
it unnecessary for the logo itself.

**Consequences:** `app/static/brand/` holds the full production asset set
(symbol/wordmark/lockup variants, app icon, favicon + PNG fallbacks, the
bundled Sora OFL license). `app/templates/_logo.html` was rewritten with
three macros (`symbol()`, `wordmark()`, `lockup()`) using the exact spec
geometry, not an approximation. If judgment call (2) turns out backwards
(blue should be the default, not ink), it's a one-line fill swap, not a
rebuild - see `LOGO.md` for the exact reasoning to revisit.

---

## 2026-08-11 — Closed the three Phase 5.5 design-system gaps: warm background, card shadows, ink navy as sidebar foundation

**Decision:** `bg-slate-50` → `bg-paper` (`#FAF8F5`) site-wide; `shadow-sm`
added to every instance of the shared card pattern (45 occurrences across
20 templates); the authenticated sidebar changed from white to solid
`bg-ink`, with nav text/hover/active states redesigned for a dark surface
(default `text-slate-300`, hover `hover:bg-white/5 hover:text-white`,
active `bg-white/10 text-white`) and the logo lockup switched to the
"reversed on ink" bright-blue + white variant inside it.

**Reason:** these were the three gaps `DESIGN_SYSTEM.md` flagged (but
deliberately did not fix) in the Phase 5.5 checkpoint; this session's
brief explicitly asked to close them alongside the logo implementation.

**Alternatives considered:** Leaving the sidebar white and only using ink
on the landing hero (status quo) - rejected, explicitly called out as
insufficient ("not just the landing hero") in this session's brief.
Applying ink to the main content background instead of the sidebar -
rejected, would fight with white cards and hurt readability across many
long-form pages (profile, applications); the sidebar is a bounded,
persistent, non-text-heavy surface, a much safer place for a saturated
dark fill.

**Consequences:** any future new authenticated page inherits the dark
sidebar automatically (it's in `base.html`, not per-template). Contrast on
the new dark surface was spot-checked visually (screenshotted against the
live dev server) but not yet measured formally against WCAG AA - carried
into the existing Phase 9 accessibility-audit item in `ROADMAP.md`, not
newly introduced by this change.

---

## 2026-08-11 — Brand casing corrected to "AUSVIA" (all caps) everywhere

**Decision:** Display the brand name in all caps, "AUSVIA", in the wordmark
(`app/templates/_logo.html`), every page `<title>`, and all documentation -
replacing the earlier mixed-case "Ausvia" and the wordmark's lowercase
"ausvia".

**Reason:** Explicit product-owner correction.

**Consequences:** Purely a text/copy change (wordmark macro + page titles +
docs) - no layout, component, or functional changes. Repo folder name,
Python package (`app.*`), and database remain unchanged, consistent with
the original rebrand decision below.

---

## 2026-08-11 — Gmail OAuth: real per-user web flow, token encryption keyed from SECRET_KEY

**Decision:** Replace the prototype's single-machine `InstalledAppFlow.
run_local_server()` + shared `token.json` with a standard authorization-code
web flow (`google_auth_oauthlib.flow.Flow`, not `InstalledAppFlow`):
redirect to Google → user consents → Google redirects back to our own
`/integrations/gmail/callback` route. Tokens are stored per-user
(`GmailConnection`, unique on `user_id`), encrypted at rest via Fernet
symmetric encryption with a key derived from `SECRET_KEY`
(`app/utils/crypto.py`).

**Reason:** The old flow doesn't work for more than one user - it opens a
browser and blocks on the *server's own machine*, and the resulting token
is shared globally. Flagged as the top priority gap in `PROJECT_AUDIT.md`
after Phase 4.5.

**Alternatives considered:** A dedicated encryption key (separate from
`SECRET_KEY`) with its own env var and rotation story - rejected for now as
more infrastructure than this app's current scale needs; noted as a Phase
8/10 revisit in `SECURITY.md` rather than silently accepted. Storing tokens
in plaintext - rejected outright, tokens are credentials.

**Consequences:** Reusing the same `credentials.json` a "Desktop app"-type
Google Cloud OAuth client produces still works locally, because Google's
loopback exception for that client type accepts `http://127.0.0.1:<port>/...`
redirect URIs without pre-registration - which matches how this app runs
(`python app.py` binds `127.0.0.1`). A real (non-localhost) deployment needs
a "Web application"-type client with the callback URL registered in Google
Cloud Console instead - documented in README.md. Never exercised against a
live Google OAuth consent screen in this environment (no `credentials.json`
configured) - same honesty standard as the Anthropic provider and the
Arbeitsagentur adapter: the code follows the documented API, but its live
behavior is unverified.

---

## 2026-08-11 — Gmail reply detection is search-based, not thread-tracked from creation

**Decision:** `app/integrations/gmail_reply_tracking.py` detects replies by
searching the connected inbox for messages from the application's contact
email (`from:<contact_email>`, optionally scoped to after the application
was marked sent) - not by tracking a specific Gmail thread ID from the
moment the application email was created.

**Reason:** AUSVIA never sends the original application email itself (spec:
the user always sends manually via the created draft). The Gmail thread
doesn't exist until the user actually sends - there is nothing to track a
thread ID *of* until after that point, which AUSVIA has no visibility into.
Searching by contact email is the best available signal without controlling
the send step.

**Alternatives considered:** Waiting for the user to paste back the sent
message's thread ID or manually link a thread - rejected as extra manual
work that defeats the point of automatic tracking. Requesting
`gmail.send`/`gmail.modify` scope to send *and* track directly - rejected
outright, contradicts the core "user always sends, AI never does" product
rule (spec sections 30/58).

**Consequences:** Reply detection can miss a reply if the company replies
from a different address than the one stored as `contact_email`, or
mis-attribute a message if multiple applications share a contact email at
the same company. Acceptable v1 tradeoff, upgradable later (e.g. once a
thread's `threadId` is known from a first detected reply, subsequent checks
could also search by that thread ID directly - not yet implemented).
Detection is manual (a "Check for replies" button), not backgrounded - see
the background-jobs gap in `ARCHITECTURE.md`.

---

## 2026-08-11 — Rebrand to "AUSVIA"

**Decision:** Rename the product from the working title "Ausbildung Career
Agent" to **AUSVIA**, with tagline "Your path to Ausbildung." Apply the new
brand across user-facing surfaces (page titles, nav, landing page, logo)
without renaming the repository, Python package structure, or database.

**Reason:** Explicit product/brand directive.

**Alternatives considered:** Renaming the repo folder and Python import
paths (`app.*`) to match — rejected as high-risk, zero functional benefit
churn touching every file's imports, and the directive itself says "do not
delete, restart, replace, or rebuild."

**Consequences:** All template titles, nav branding, and landing copy now
say AUSVIA. `app.py`, the `app/` package, `requirements.txt`, and the git
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
both the original and AUSVIA directives).

**Consequences:** Every AI-assisted generation step (cover letter, email)
is followed by a review/edit step before the approval gate; this shaped the
whole `app/applications` route design.
