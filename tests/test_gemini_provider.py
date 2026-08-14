"""Tests for app/ai/providers/gemini_provider.py, mocking the google-genai
SDK client so nothing here makes a real network call. GeminiProvider is
constructed directly with a fake client injected via monkeypatching the
`genai` module reference this file imports (not the real SDK), matching the
pattern used to fake other AI providers in this test suite (FakeProvider
classes in tests/test_companies.py etc.) - just one layer lower here since
this IS the real-provider implementation, not a caller of the abstraction.
"""
import pytest
from google.genai import errors

from app.ai.provider import AIProviderError
from app.ai.providers import gemini_provider as gemini_provider_module
from app.ai.providers.gemini_provider import GeminiProvider


class FakeUsage:
    def __init__(self, prompt_tokens=10, output_tokens=20):
        self.prompt_token_count = prompt_tokens
        self.candidates_token_count = output_tokens


class FakeCandidate:
    def __init__(self, finish_reason="STOP"):
        self.finish_reason = finish_reason


class FakeResponse:
    def __init__(self, text="Generated text.", finish_reason="STOP", usage=None):
        self.text = text
        self.candidates = [FakeCandidate(finish_reason)]
        self.usage_metadata = usage or FakeUsage()


class FakeModels:
    def __init__(self, response=None, exception=None):
        self._response = response
        self._exception = exception
        self.last_call_kwargs = None

    def generate_content(self, **kwargs):
        self.last_call_kwargs = kwargs
        if self._exception:
            raise self._exception
        return self._response


class FakeClient:
    def __init__(self, response=None, exception=None):
        self.models = FakeModels(response=response, exception=exception)


def make_provider(response=None, exception=None, monkeypatch=None):
    provider = GeminiProvider(api_key="fake-key")
    fake_client = FakeClient(response=response, exception=exception)
    provider._client = fake_client
    return provider, fake_client


def test_successful_completion_returns_real_response_fields(monkeypatch):
    provider, fake_client = make_provider(response=FakeResponse(text="Hallo Welt."))
    result = provider.complete("system prompt", "user prompt", max_tokens=500)

    assert result.text == "Hallo Welt."
    assert result.provider == "gemini"
    assert result.input_tokens == 10
    assert result.output_tokens == 20
    # system prompt and token limit actually reached the SDK call
    config = fake_client.models.last_call_kwargs["config"]
    assert config.system_instruction == "system prompt"
    assert config.max_output_tokens == 500
    assert fake_client.models.last_call_kwargs["contents"] == "user prompt"
    # Regression check for the real bug this was live-tested against and
    # fixed for (see the module docstring): without this, Gemini 3 models'
    # default thinking silently ate almost the whole token budget and
    # truncated every real response mid-sentence.
    assert str(config.thinking_config.thinking_level.value).lower() == "minimal"


def test_auth_error_maps_to_clear_message():
    provider, _ = make_provider(exception=errors.ClientError(401, {"error": {"message": "bad key"}}))
    with pytest.raises(AIProviderError, match="rejected the configured API key"):
        provider.complete("system", "user")


def test_forbidden_error_also_maps_to_auth_message():
    provider, _ = make_provider(exception=errors.ClientError(403, {}))
    with pytest.raises(AIProviderError, match="rejected the configured API key"):
        provider.complete("system", "user")


def test_rate_limit_error_maps_to_clear_message():
    provider, _ = make_provider(exception=errors.ClientError(429, {}))
    with pytest.raises(AIProviderError, match="rate-limited"):
        provider.complete("system", "user")


def test_other_client_error_maps_to_generic_http_message():
    provider, _ = make_provider(exception=errors.ClientError(400, {}))
    with pytest.raises(AIProviderError, match="HTTP 400"):
        provider.complete("system", "user")


def test_server_error_maps_to_generic_http_message():
    provider, _ = make_provider(exception=errors.ServerError(503, {}))
    with pytest.raises(AIProviderError, match="HTTP 503"):
        provider.complete("system", "user")


def test_unexpected_exception_degrades_gracefully_not_raw():
    provider, _ = make_provider(exception=ConnectionError("DNS lookup failed"))
    with pytest.raises(AIProviderError, match="Could not reach the AI provider"):
        provider.complete("system", "user")


def test_safety_finish_reason_is_treated_as_a_decline():
    provider, _ = make_provider(response=FakeResponse(text="", finish_reason="SAFETY"))
    with pytest.raises(AIProviderError, match="declined to answer"):
        provider.complete("system", "user")


def test_empty_text_raises_instead_of_returning_blank():
    provider, _ = make_provider(response=FakeResponse(text=""))
    with pytest.raises(AIProviderError, match="empty response"):
        provider.complete("system", "user")


def test_default_model_used_when_none_configured():
    provider = GeminiProvider(api_key="fake-key")
    assert provider._model == gemini_provider_module.DEFAULT_MODEL


def test_explicit_model_overrides_default():
    provider = GeminiProvider(api_key="fake-key", model="gemini-custom")
    assert provider._model == "gemini-custom"
