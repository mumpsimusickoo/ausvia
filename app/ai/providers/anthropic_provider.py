"""
Real AI provider backed by the Anthropic Messages API. Only instantiated when
AI_PROVIDER=anthropic and an API key is configured - see app/ai/provider_factory.py.
Uses low effort with default (adaptive) thinking: these calls write a few
sentences of narrative grounded in facts the caller already computed, not
open-ended reasoning, so there's no benefit to spending more.
"""
import anthropic

from app.ai.provider import AIProvider, AIProviderError, AIResponse

DEFAULT_MODEL = "claude-opus-5"


class AnthropicProvider(AIProvider):
    provider_name = "anthropic"

    def __init__(self, api_key, model=None):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model or DEFAULT_MODEL

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system_prompt,
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.AuthenticationError as e:
            raise AIProviderError("AI provider rejected the configured API key.") from e
        except anthropic.RateLimitError as e:
            raise AIProviderError("AI provider is rate-limited right now.") from e
        except anthropic.APIStatusError as e:
            raise AIProviderError(f"AI provider error (HTTP {e.status_code}).") from e
        except anthropic.APIConnectionError as e:
            raise AIProviderError("Could not reach the AI provider.") from e

        if response.stop_reason == "refusal":
            raise AIProviderError("The AI provider declined to answer this request.")

        text = next((block.text for block in response.content if block.type == "text"), "")
        if not text:
            raise AIProviderError("The AI provider returned an empty response.")

        return AIResponse(
            text=text,
            model=response.model,
            provider=self.provider_name,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
