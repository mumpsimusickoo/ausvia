"""
Mock AI provider: no network calls, no credentials needed. Used whenever
AI_PROVIDER=mock (the default) or a real provider isn't configured. It never
pretends to be an LLM - it says plainly that AI narrative isn't available and
points at how to enable it. Every feature that depends on already-computed,
non-AI data (matching scores, gap analysis) works fully without this provider
doing anything at all.
"""
from app.ai.provider import AIProvider, AIResponse

NOT_CONFIGURED_MESSAGE = (
    "AI-written narrative isn't available right now because no AI provider is "
    "configured (AI_PROVIDER=mock). The structured analysis above is computed "
    "directly from your profile and this posting's data, not by AI, so it's "
    "fully accurate regardless. Set ANTHROPIC_API_KEY and AI_PROVIDER=anthropic "
    "to enable AI-written summaries and suggestions."
)


class MockAIProvider(AIProvider):
    provider_name = "mock"

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        return AIResponse(
            text=NOT_CONFIGURED_MESSAGE,
            model="mock",
            provider=self.provider_name,
            input_tokens=0,
            output_tokens=0,
        )
