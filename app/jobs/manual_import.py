"""
Manual job import (spec section 12). This is the fallback that makes the whole
product not depend on any automated source: a user pastes a URL, we make a
best-effort, permitted plain GET request and extract readable text to prefill
a review form - never bypassing login walls, paywalls, or bot protection. If
the fetch fails or the site blocks us, the user pastes the job text directly
and fills in the structured fields themselves.
"""
import re

import requests
from bs4 import BeautifulSoup
from flask_babel import gettext as _

FETCH_TIMEOUT = 10
MAX_RESPONSE_BYTES = 3 * 1024 * 1024  # 3 MB
USER_AGENT = "Mozilla/5.0 (compatible; AusbildungCareerAgent/1.0; +manual-import)"


class FetchFailed(Exception):
    pass


def fetch_and_extract_text(url):
    """Best-effort fetch of a job posting page. Raises FetchFailed with a
    human-readable reason on any failure - callers should fall back to manual
    text paste rather than retry with different headers/evasion techniques."""
    if not re.match(r"^https?://", url or ""):
        raise FetchFailed(_("That doesn't look like a valid URL."))

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            timeout=FETCH_TIMEOUT,
            stream=True,
        )
    except requests.RequestException as e:
        raise FetchFailed(_("Could not reach that page (%(reason)s).", reason=e.__class__.__name__))

    if resp.status_code in (401, 403, 429):
        raise FetchFailed(
            _(
                "That site declined the request (access-restricted or rate-limited). "
                "Please paste the job text manually instead."
            )
        )
    if resp.status_code != 200:
        raise FetchFailed(_("That page returned HTTP %(status)d.", status=resp.status_code))

    content = resp.raw.read(MAX_RESPONSE_BYTES + 1, decode_content=True)
    if len(content) > MAX_RESPONSE_BYTES:
        raise FetchFailed(_("That page is too large to import automatically."))

    content_type = resp.headers.get("Content-Type", "")
    if "html" not in content_type and "text" not in content_type:
        raise FetchFailed(_("That URL doesn't point to a readable web page."))

    soup = BeautifulSoup(content, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else ""
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)

    if len(text) < 50:
        raise FetchFailed(_("Couldn't find readable content on that page."))

    return {"page_title": title, "text": text[:20000]}
