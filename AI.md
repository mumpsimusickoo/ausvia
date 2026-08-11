# AI Architecture — Ausvia

## Core principle: deterministic-first, AI-optional

Every AI-assisted feature computes its core output in plain, deterministic
Python first. A configured AI provider only ever adds narrative polish or
personalized prose on top of already-computed, real facts - it never
decides the underlying facts (match score, gap list) itself. This means the
app is fully functional and honest with zero AI credentials configured.

## Provider abstraction

`app/ai/provider.py` defines `AIProvider` (abstract: `complete(system,
user, max_tokens)` → `AIResponse`) and `AIProviderError`. Two
implementations:

- **`MockAIProvider`** (`app/ai/providers/mock.py`) — default
  (`AI_PROVIDER=mock`). No network calls. Returns an honest "AI narrative
  isn't available because no provider is configured" message rather than
  faking intelligence.
- **`AnthropicProvider`** (`app/ai/providers/anthropic_provider.py`) —
  active when `AI_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` are set. Uses
  `claude-opus-5` by default (overridable via `AI_MODEL`), low effort
  (these are short, fact-grounded generation tasks, not open-ended
  reasoning), handles `stop_reason == "refusal"` and auth/rate-limit/
  connection errors explicitly. **Never exercised against a live API key in
  this development environment** - the code is real, its live behavior is
  unverified (see `PROJECT_AUDIT.md`).

`app/ai/provider_factory.get_provider()` is the single place that decides
which implementation to return; callers never branch on provider type
themselves except to check `provider.provider_name == "mock"` where a
template fallback exists instead of just skipping the feature.

## Where AI is actually used

| Feature | Deterministic core | Optional AI layer |
|---|---|---|
| Job matching (`app/ai/matching.py`) | Score, strengths, gaps, per-category breakdown - always computed from real profile/job data | Narrative explanation, improvement tips (`app/ai/prompts/narrative.py`) |
| Cover letter (`app/ai/cover_letter.py`) | Template-based German business letter (used when no AI provider) | AI-personalized generation + a second AI validation/self-correction pass |
| Application email (`app/ai/email_gen.py`) | Template-based email | AI-personalized generation |
| Reply intent classification (`app/ai/reply_ai.py`) | None - there's no reliable non-AI way to classify arbitrary reply text | AI classifies into one of 6 intents + a high/medium/low confidence (never a fake numeric score); mock mode honestly declines rather than guessing |
| Reply suggestions (`app/ai/reply_ai.py`) | None, same reasoning as above | AI drafts a contextual reply grounded in candidate facts + the company's message; mock mode says so plainly instead of faking a reply |

Reply classification/suggestion (Phase 5) are the first features with **no
deterministic fallback** - unlike matching or cover letters, there's no
principled non-AI way to classify or respond to arbitrary incoming text, so
mock mode's honesty is the whole story there rather than a fallback to a
"good enough" alternative.

## Prompt architecture

One module per feature under `app/ai/prompts/` (`narrative.py`,
`cover_letter.py`, `email.py`), each exporting a `build_*_prompt()` function
returning `(system_prompt, user_prompt)`. Facts are assembled separately in
`app/ai/facts.py` (`format_candidate_facts`, `format_job_facts`) - this is
the single place that decides what the AI is allowed to know, which is also
the anti-hallucination anchor: if a fact isn't in that text block, the AI
has no way to know about it.

## Anti-hallucination & prompt injection defense

- Every generation system prompt explicitly instructs: use only the given
  facts, never invent qualifications/experience/company facts.
- Job/company data is normalized (`app/jobs/*`) before ever reaching an AI
  prompt - raw scraped/fetched text is never passed directly to the model
  for narrative/improvement-tips generation. Cover letter/email generation
  does pass normalized job facts (title, requirements, skills) - still
  structured, never raw HTML - and every relevant system prompt explicitly
  instructs the model to treat that data as inert content, never as
  instructions to follow.
- Match scores and gap lists are never AI output - they're Python-computed
  and merely *described* by AI when a narrative is requested.
- Inbound Gmail reply content (Phase 5) gets the same treatment: it's
  untrusted external data passed to the classification/reply-suggestion
  prompts as content to interpret, and every relevant system prompt
  explicitly instructs the model to ignore anything in it that resembles an
  instruction directed at the model itself.

## Cost control

- `JobMatch` caches the deterministic result and any generated narrative/
  tips per (user, job); recomputes only when the candidate profile changed
  since the cache was written.
- `GeneratedDocument`/`GeneratedEmail` cache the last generation per
  application; "Generate" becomes "Regenerate" and overwrites rather than
  accumulating.
- `AIUsage` logs token counts per real (non-mock) call; visible at
  `/admin/ai-usage`. Mock calls are never logged (no real cost).
- All AI-calling routes (cover letter/email/narrative/improvement-tips/
  reply-classification/reply-suggestion generation) are rate-limited
  (30/hour/IP) via Flask-Limiter - added Phase 5, verified with a dedicated
  test that forces the limiter on.

## Structured output

Currently text-only (no `output_config.format` JSON schema usage) - the
generation tasks so far (narrative prose, letter text, "SUBJECT:/BODY:"
email format) are simple enough for plain parsing. Worth revisiting with a
real JSON schema if a future feature needs strictly structured AI output
(e.g. requirement extraction from an unstructured job posting).
