"""AI-grounded field extraction for manually-imported job postings (manual
import extraction pass, 2026-08-30). Runs on the raw scraped page text
app/jobs/manual_import.py's fetch_and_extract_text() already produced -
BeautifulSoup strips <script>/<style>/<nav>/<footer>/<header> there, but
plenty of navigation/menu/promotional page chrome routinely survives in
<div>/<a>/<span> elements outside those specific tags, polluting what
used to be a raw, unfiltered text dump.

This is the LEAST trusted content this app ever shows an AI. Unlike
Arbeitsagentur's structured API responses (a known, non-adversarial
source already going through the same kind of grounded extraction in
app/ai/job_requirements_extraction.py), this is freeform text scraped
from an arbitrary third-party URL a user pasted in - it could be
absolutely anything, including a page deliberately crafted to look like
instructions. See app/ai/prompts/manual_import_extraction.py for the
prompt-level defense (structural fencing via
app/ai/facts.py's wrap_untrusted_external_text(), the same QA-W8
remediation every other untrusted-content prompt in this app uses,
reused here rather than invented fresh); this module's grounding check
below is the load-bearing second line of defense - the prompt alone is
never treated as a sufficient guarantee, same discipline as
job_requirements_extraction.py.

Grounding is structurally different here than a plain substring check for
one field: company_name/location/start_date/salary/contact_person/
contact_email/title are grounded the usual way (must be a literal,
case-insensitive substring of the source text),
but the "cleaned description" is grounded by CONSTRUCTION instead - the
AI never composes or copies out new description text at all, it only
names which 1-based LINE NUMBERS (against the same numbered listing shown
in the prompt, see app/ai/prompts/manual_import_extraction.py) of the
real scraped text are chrome to remove. The result is always a strict
subset of the real text, so fabricated description content isn't just
checked against and rejected, it's structurally impossible to produce in
the first place. See _clean_description() below.

Line NUMBERS rather than verbatim line TEXT was a deliberate fix, not the
original design: live-verified against a real, messy posting page (Festo,
176 lines of scraped text once cookie/nav chrome is included) that asking
the AI to copy each excluded line back out character-for-character made
the response balloon past max_tokens and get cut off mid-JSON - silently
collapsing a perfectly good extraction into the raw-text fallback, with
no signal beyond "the review form looks unfilled" until this was traced
through a live AI Usage row (a real, successful, correctly-billed call)
and a raw-response dump. Numbers are a small fraction of the tokens
verbatim text would cost for the same set of exclusions.

Runs lazily - only for the one batch item currently being displayed for
review, never upfront for every URL in a batch - and its result is cached
onto that item so revisiting an already-reviewed item in the same batch
never re-runs it and never burns a second AI call. Both handled in
app/jobs/routes.py's _ensure_item_extracted(), not here.
"""
import json
import re

from app.ai.prompts.manual_import_extraction import build_extraction_prompt
from app.ai.provider import AIProviderError
from app.ai.provider_factory import get_provider
from app.ai.usage import record_usage
from app.extensions import limiter
from app.utils.logging import log_event

# Gemini (and other models) routinely wrap a JSON reply in a markdown code
# fence (```json ... ``` or bare ``` ... ```) even when the prompt asks for
# "JSON only" - live-verified against the real provider during this pass:
# a real response for a messy scraped page came back as a fully well-formed
# JSON object sandwiched between fence markers, which json.loads() rejects
# outright (raises on the leading backtick). Stripped before parsing so a
# cosmetic wrapping choice doesn't collapse a perfectly good extraction into
# the raw-text fallback.
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)

# Cheap extra safety net for contact_email, alongside (not instead of) the
# grounding check below - same reasoning and same shape as
# job_requirements_extraction.py's own EMAIL_SHAPE_RE: deliberately simple
# ("looks roughly like an email"), not full RFC 5322 validation.
EMAIL_SHAPE_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# This is a floor against near-total wipeout (a malfunctioning response
# that excludes almost the entire page, leaving nothing usable), not an
# estimate of how much chrome a normal page has - live-verified against a
# real, messy page (Festo's career site: SAP SuccessFactors + a OneTrust-
# style cookie-consent manager) that genuine, correct chrome removal can
# legitimately strip ~80% of a page's lines. An initial 0.6 cap was
# calibrated on the wrong assumption ("chrome is a minority of the page")
# and silently discarded a fully correct cleaning result. Line-number-based
# exclusion (see _clean_description below) is already grounded by
# construction - it cannot fabricate content regardless of how much it
# excludes - so this cap only needs to catch true degenerate cases, not
# police what counts as "too much" chrome on a real page.
MAX_EXCLUDED_FRACTION = 0.95


def _raw_fallback(page_title, text):
    """Exactly today's pre-extraction baseline: raw <title> tag, raw full
    text dump, everything else blank. Returned whenever extraction
    can't/shouldn't run (mock mode, AI outage, rate limit) or produces
    nothing usable - the feature must never regress below this, so every
    return path in extract_manual_import_fields() below either improves
    on this or falls back to exactly this, never something worse."""
    return {
        "title": page_title,
        "company_name": None,
        "location": None,
        "start_date": None,
        "salary": None,
        "contact_person": None,
        "contact_email": None,
        "description": text,
    }


def _normalize_whitespace(s):
    """Collapses any run of whitespace (regular spaces, tabs, newlines,
    and non-breaking space U+00A0 - common in scraped HTML, \\s does not
    match it) to a single space. Purely cosmetic normalization, not a
    loosening of the grounding guarantee: the check below is still a
    literal, character-for-character containment test, just against a
    normalized haystack, so it still cannot be satisfied by fabricated
    content - only by a genuine reformatting of real text."""
    return re.sub(r"[\s\xa0]+", " ", s).strip()


def _grounded(value, haystack_lower):
    """None (leave blank) unless value is a non-empty string that's a
    literal, case-insensitive, whitespace-normalized substring of the
    real source text - the same "never infer or fabricate, leave it
    blank rather than guess" rule job_requirements_extraction.py's own
    grounding check uses.

    Whitespace-normalized rather than a strict literal check: live-
    verified this pass that a real, correct extraction - e.g. the exact
    "clean title" the prompt explicitly asks for, joining text that was
    split across separate DOM elements/lines in the source, or a source
    line with irregular internal spacing (&nbsp;, doubled spaces from
    markup indentation) - genuinely fails a strict substring check even
    though nothing was fabricated. A strict check without this rejects
    real, correct answers silently (same failure shape as the JSON-
    parsing bugs found in this pass - a good extraction quietly becomes
    the raw-text fallback with no signal). Normalizing whitespace on
    both sides keeps the check exactly as strict about *content* while
    tolerating *reformatting* - it still cannot be satisfied by content
    that doesn't genuinely appear in the source."""
    if not isinstance(value, str):
        return None
    value = _normalize_whitespace(value)
    if not value or value.lower() not in haystack_lower:
        return None
    return value


def _validate_and_ground(raw_text, page_title, source_text):
    """Parses the AI's JSON response and strictly validates it
    structurally. Returns None only for a structurally malformed response
    (not JSON, wrong shape, wrong types) - a well-formed response where
    every field is null and exclude_lines is empty is a normal, valid
    "found nothing to correct" result, not a failure (same skills=[]-vs-
    None distinction job_requirements_extraction.py already draws)."""
    if not isinstance(raw_text, str):
        return None
    stripped = raw_text.strip()
    fence_match = _CODE_FENCE_RE.match(stripped)
    if fence_match:
        stripped = fence_match.group(1).strip()
    try:
        data = json.loads(stripped)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if not all(
        k in data for k in (
            "title", "company_name", "location", "start_date", "salary",
            "contact_person", "contact_email", "exclude_line_numbers",
        )
    ):
        return None
    exclude_line_numbers = data["exclude_line_numbers"]
    if not isinstance(exclude_line_numbers, list) or not all(
        isinstance(x, int) and not isinstance(x, bool) for x in exclude_line_numbers
    ):
        return None

    # title may legitimately be restated in the body even if it's not a
    # literal substring of the raw <title> tag (which is the whole point
    # of asking for a *cleaner* title than that tag usually gives) - ground
    # against the combined title+body text, not the title tag alone.
    haystack_lower = _normalize_whitespace(f"{page_title}\n{source_text}".lower())
    contact_email = _grounded(data.get("contact_email"), haystack_lower)
    if contact_email and not EMAIL_SHAPE_RE.match(contact_email):
        contact_email = None  # grounded, but doesn't look like an email - discard anyway
    return {
        "title": _grounded(data.get("title"), haystack_lower),
        "company_name": _grounded(data.get("company_name"), haystack_lower),
        "location": _grounded(data.get("location"), haystack_lower),
        "start_date": _grounded(data.get("start_date"), haystack_lower),
        "salary": _grounded(data.get("salary"), haystack_lower),
        "contact_person": _grounded(data.get("contact_person"), haystack_lower),
        "contact_email": contact_email,
        "exclude_line_numbers": exclude_line_numbers,
    }


def _clean_description(source_text, exclude_line_numbers):
    """Only ever REMOVES lines at the given 1-based indices (matching the
    "N: " numbering shown to the AI in the prompt) - never adds, rewrites,
    or summarizes anything - so the result is grounded by construction: a
    strict subset of the real scraped text, not a freeform generation
    checked against it after the fact. An out-of-range or otherwise
    invalid number is simply a no-op (nothing at that position to remove),
    never a fabrication risk - there is no way for this function to
    introduce text that wasn't already in source_text."""
    if not exclude_line_numbers:
        return source_text
    lines = source_text.splitlines()
    exclude_set = {n for n in exclude_line_numbers if isinstance(n, int) and 1 <= n <= len(lines)}
    if not exclude_set:
        return source_text

    kept = [line for i, line in enumerate(lines, start=1) if i not in exclude_set]
    if len(kept) == len(lines):
        return source_text

    cleaned = "\n".join(kept).strip()
    if not cleaned:
        return source_text
    if len(cleaned) < len(source_text) * (1 - MAX_EXCLUDED_FRACTION):
        return source_text
    return cleaned


@limiter.limit("30 per hour")
def _consume_extraction_rate_limit():
    """Real Flask-Limiter check, keyed by client IP like every other
    AI-calling route in this app - decorating a plain function
    (Flask-Limiter 2.9+ supports this outside route registration) rather
    than a route, since the actual AI call happens lazily inside a review-
    rendering path shared by four different routes (see
    app/jobs/routes.py's _ensure_item_extracted(), called from
    import_start()/import_fetch()/import_save()/import_skip()), not one
    dedicated POST endpoint. Decorating this one small function gives all
    four call sites the same single shared 30/hour bucket, keyed by this
    function's own identity, rather than four independent 30/hour buckets
    that would together allow 120/hour. Verified directly (not just
    assumed) that Flask-Limiter's non-route decoration support actually
    enforces a limit when called from within a real request, and that
    exceeding it raises a catchable flask_limiter.errors.RateLimitExceeded
    rather than a hard 429 that bypasses normal exception handling."""
    return None


def extract_manual_import_fields(page_title, text, user_id):
    """Best-effort AI extraction - never raises, always returns a dict
    shaped like _raw_fallback()'s. Mirrors job_requirements_extraction.py's
    mock-mode/AIProviderError handling: an AI outage, a declined mock
    provider, or an exhausted rate limit must never block the import
    review flow - each just degrades to today's pre-extraction baseline.

    Thin wrapper around _run_extraction(): this function's own job is just
    the rate-limit gate. _consume_extraction_rate_limit() is a real
    Flask-Limiter check keyed off the current request's client IP, so it
    requires an active HTTP request context - fine for this function's four
    original route-based callers (see that helper's own docstring), but not
    for app/jobs/ingest.py's fill_contact_from_external_posting(), which
    runs from a background-task thread with no request context at all. That
    caller uses _run_extraction() directly instead, matching
    job_requirements_extraction.py's own precedent of no rate limiter at
    all for its background-task AI calls - a background task is already
    naturally throttled to one call per job per view, unlike this
    function's four request-bound routes sharing one manual-import flow."""
    provider = get_provider()
    if provider.provider_name == "mock":
        # No real provider configured - nothing to attempt, nothing to
        # count against the rate limit (mock mode makes no network call
        # and costs nothing, so charging it here would exhaust the real
        # budget before a real provider is ever set up).
        return _raw_fallback(page_title, text)

    from flask_limiter.errors import RateLimitExceeded

    try:
        _consume_extraction_rate_limit()
    except RateLimitExceeded:
        log_event(
            "job_source", "Manual import extraction skipped: rate limit exceeded.",
            level="warning", user_id=user_id,
        )
        return _raw_fallback(page_title, text)

    return _run_extraction(page_title, text, user_id)


def _run_extraction(page_title, text, user_id):
    """The actual provider call, parsing, and grounding - no rate-limit
    check of its own, so callers outside a request context (background
    tasks) must call this directly rather than extract_manual_import_fields().
    Still handles mock mode itself (rather than assuming every caller
    already checked) since fill_contact_from_external_posting() calls this
    directly and must degrade the same way in a mock-provider dev setup."""
    fallback = _raw_fallback(page_title, text)

    provider = get_provider()
    if provider.provider_name == "mock":
        return fallback

    system, prompt = build_extraction_prompt(page_title, text)
    try:
        # 4096, raised from an initial 2048 (salary follow-up pass,
        # 2026-08-30): live-verified against a real LinkedIn posting
        # (534 lines once its "similar jobs" sidebar - dozens of other
        # listings - is included) that 2048 still wasn't enough headroom
        # and truncated mid-response (2044/2048 output tokens, response
        # cut off mid-way through exclude_line_numbers) - the exact
        # silent-fallback failure mode this pass's own earlier bump was
        # meant to prevent, just at a larger page size than was tested
        # against at the time. Line numbers are still far cheaper than
        # verbatim text for the same exclusions, but a page's chrome
        # doesn't have a fixed upper bound on line count.
        response = provider.complete(system, prompt, max_tokens=4096)
    except AIProviderError as e:
        log_event(
            "job_source", f"Manual import extraction failed: {e}",
            level="warning", user_id=user_id,
        )
        return fallback

    record_usage(user_id, "manual_import_extraction", response)

    validated = _validate_and_ground(response.text, page_title, text)
    if validated is None:
        log_event(
            "job_source",
            "Manual import extraction returned a malformed response - falling back to raw title/text.",
            level="warning", user_id=user_id,
        )
        return fallback

    return {
        "title": validated["title"] or page_title,
        "company_name": validated["company_name"],
        "location": validated["location"],
        "start_date": validated["start_date"],
        "salary": validated["salary"],
        "contact_person": validated["contact_person"],
        "contact_email": validated["contact_email"],
        "description": _clean_description(text, validated["exclude_line_numbers"]),
    }
