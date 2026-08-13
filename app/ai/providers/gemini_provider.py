"""Real AI provider backed by Google's Gemini API. Only instantiated when
AI_PROVIDER=gemini and an API key is configured - see
app/ai/provider_factory.py. Uses the current google-genai SDK
(`pip install google-genai`) - the older `google-generativeai` package is
deprecated and intentionally not used here.
"""
from google import genai
from google.genai import errors, types

from app.ai.provider import AIProvider, AIProviderError, AIResponse

DEFAULT_MODEL = "gemini-3.6-flash"


class GeminiProvider(AIProvider):
    provider_name = "gemini"

    def __init__(self, api_key, model=None):
        self._client = genai.Client(api_key=api_key)
        self._model = model or DEFAULT_MODEL

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=max_tokens,
                ),
            )
        except errors.ClientError as e:
            if e.code in (401, 403):
                raise AIProviderError("AI provider rejected the configured API key.") from e
            if e.code == 429:
                raise AIProviderError("AI provider is rate-limited right now.") from e
            raise AIProviderError(f"AI provider error (HTTP {e.code}).") from e
        except errors.ServerError as e:
            raise AIProviderError(f"AI provider error (HTTP {e.code}).") from e
        except errors.APIError as e:
            raise AIProviderError(f"AI provider error (HTTP {e.code}).") from e
        except Exception as e:
            # The SDK doesn't expose a single typed exception for plain
            # connectivity failures (unlike anthropic.APIConnectionError) -
            # this is the graceful-degradation floor (spec section 55): an
            # AI outage must never take down a page that has real,
            # already-computed data underneath it.
            raise AIProviderError("Could not reach the AI provider.") from e

        # Checked before touching response.text on purpose: a blocked/safety-
        # filtered response can make that property raise instead of just
        # being empty, depending on SDK version - checking the structured
        # finish_reason first avoids relying on that.
        candidates = response.candidates or []
        finish_reason = str(candidates[0].finish_reason) if candidates else ""
        if "SAFETY" in finish_reason or "PROHIBITED" in finish_reason:
            raise AIProviderError("The AI provider declined to answer this request.")

        try:
            text = response.text or ""
        except Exception as e:
            raise AIProviderError("The AI provider returned an unusable response.") from e
        if not text:
            raise AIProviderError("The AI provider returned an empty response.")

        usage = response.usage_metadata
        return AIResponse(
            text=text,
            model=self._model,
            provider=self.provider_name,
            input_tokens=usage.prompt_token_count if usage else 0,
            output_tokens=usage.candidates_token_count if usage else 0,
        )
