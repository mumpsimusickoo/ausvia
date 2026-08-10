"""
AI provider abstraction (spec section 35/37). The app is never hard-coded to
one vendor: callers depend only on this interface, and a mock implementation
(app/ai/providers/mock.py) means every AI-assisted feature stays usable with
zero API credentials configured - it just skips the optional narrative layer
and says so, rather than faking intelligence.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


class AIProviderError(Exception):
    """Raised on any failure to reach or use the configured AI provider.
    Callers must catch this and degrade gracefully (spec section 55) - an AI
    outage should never take down a page that has real, already-computed data."""


@dataclass
class AIResponse:
    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0


class AIProvider(ABC):
    provider_name: str

    @abstractmethod
    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        """Returns an AIResponse. Raises AIProviderError on failure."""
