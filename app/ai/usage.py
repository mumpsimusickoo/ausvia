from app.extensions import db
from app.models.ai import AIUsage


def record_usage(user_id, feature, ai_response):
    """Logs token usage only - never prompt or response content (spec section 40)."""
    entry = AIUsage(
        user_id=user_id,
        feature=feature,
        provider=ai_response.provider,
        model=ai_response.model,
        input_tokens=ai_response.input_tokens,
        output_tokens=ai_response.output_tokens,
    )
    db.session.add(entry)
    db.session.commit()
    return entry
