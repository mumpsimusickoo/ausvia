from app.ai.providers.mock import MockAIProvider, NOT_CONFIGURED_MESSAGE
from app.ai.provider_factory import get_provider


def test_mock_provider_returns_labeled_response():
    provider = MockAIProvider()
    response = provider.complete("system", "user prompt")
    assert response.text == NOT_CONFIGURED_MESSAGE
    assert response.provider == "mock"
    assert response.input_tokens == 0
    assert response.output_tokens == 0


def test_factory_defaults_to_mock(app):
    with app.test_request_context():
        provider = get_provider()
        assert provider.provider_name == "mock"


def test_factory_falls_back_to_mock_without_api_key(app):
    app.config["AI_PROVIDER"] = "anthropic"
    app.config["ANTHROPIC_API_KEY"] = None
    with app.test_request_context():
        provider = get_provider()
        assert provider.provider_name == "mock"


def test_factory_uses_anthropic_when_configured(app):
    app.config["AI_PROVIDER"] = "anthropic"
    app.config["ANTHROPIC_API_KEY"] = "sk-test-fake-key"
    with app.test_request_context():
        provider = get_provider()
        assert provider.provider_name == "anthropic"


def test_factory_falls_back_to_mock_without_gemini_key(app):
    app.config["AI_PROVIDER"] = "gemini"
    app.config["GEMINI_API_KEY"] = None
    with app.test_request_context():
        provider = get_provider()
        assert provider.provider_name == "mock"


def test_factory_uses_gemini_when_configured(app):
    app.config["AI_PROVIDER"] = "gemini"
    app.config["GEMINI_API_KEY"] = "fake-gemini-key"
    with app.test_request_context():
        provider = get_provider()
        assert provider.provider_name == "gemini"


def test_factory_uses_gemini_model_not_the_anthropic_default(app):
    """AI_MODEL defaults to an Anthropic model name - Gemini must never
    silently inherit it, since that name is meaningless in Gemini's own
    model namespace. See app/ai/provider_factory.py."""
    app.config["AI_PROVIDER"] = "gemini"
    app.config["GEMINI_API_KEY"] = "fake-gemini-key"
    app.config["AI_MODEL"] = "claude-opus-5"
    app.config["GEMINI_MODEL"] = "gemini-3.6-flash"
    with app.test_request_context():
        provider = get_provider()
        assert provider._model == "gemini-3.6-flash"
        assert provider._model != "claude-opus-5"
