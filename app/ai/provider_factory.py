from flask import current_app

from app.ai.providers.mock import MockAIProvider


def get_provider():
    """Returns the configured AIProvider. Falls back to the mock provider
    whenever AI_PROVIDER isn't "anthropic" or no API key is configured, so
    callers never need their own credential-checking logic."""
    provider_name = current_app.config.get("AI_PROVIDER", "mock")

    if provider_name == "anthropic" and current_app.config.get("ANTHROPIC_API_KEY"):
        from app.ai.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=current_app.config["ANTHROPIC_API_KEY"],
            model=current_app.config.get("AI_MODEL"),
        )

    if provider_name == "gemini" and current_app.config.get("GEMINI_API_KEY"):
        from app.ai.providers.gemini_provider import GeminiProvider

        # Deliberately NOT AI_MODEL here - that config var defaults to
        # "claude-opus-5" (an Anthropic model name) and is shared with the
        # Anthropic branch above. Reusing it for Gemini would silently ask
        # Gemini's API for a model name from a different vendor's
        # namespace. GEMINI_MODEL is its own var for exactly this reason.
        return GeminiProvider(
            api_key=current_app.config["GEMINI_API_KEY"],
            model=current_app.config.get("GEMINI_MODEL"),
        )

    return MockAIProvider()
