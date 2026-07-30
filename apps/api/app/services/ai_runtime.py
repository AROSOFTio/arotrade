"""AI runtime facade backed by the provider manager.

All market analysis goes through the provider manager so local, free, and paid
providers share the same deterministic market snapshot and response schema.
"""

from __future__ import annotations

from typing import Optional

from app.services.ai.provider_manager import provider_manager
from app.services.ai.providers.base import AIProviderError, AIProviderNotConfigured, json_from_text


ProviderRuntimeError = AIProviderError
ProviderRuntimeNotConfigured = AIProviderNotConfigured


def ai_health_details() -> dict:
    statuses = provider_manager.all_statuses()
    available = [status for status in statuses if status.available]
    return {
        "status": "operational" if available else "unavailable",
        "provider": ", ".join(status.id for status in available) if available else "none",
        "model": ", ".join(f"{status.id}:{status.model}" for status in available) if available else "none",
        "is_available": bool(available),
        "providers": [status.__dict__ for status in statuses],
    }


def analyze_json(prompt: str, *, temperature: float = 0.3) -> dict:
    del temperature
    return json_from_text(provider_manager.generate_with_fallback([prompt], json_response=True))


def answer_analysis_question(analysis_summary: str, history: list[dict], question: str) -> str:
    transcript = ""
    for message in history[-10:]:
        speaker = "Trader" if message.get("role") == "user" else "Analyst"
        transcript += f"{speaker}: {str(message.get('content', ''))[:500]}\n"
    prompt = (
        "You are a patient trading mentor. A trader is asking follow-up questions about "
        "a market analysis generated from live MT5 data. Explain clearly in plain language, "
        "define jargon, keep answers under 150 words, never promise profits, and do not "
        "invent new price levels.\n\n"
        f"THE ANALYSIS BEING DISCUSSED:\n{analysis_summary}\n\n"
        f"CONVERSATION SO FAR:\n{transcript}"
        f"Trader: {question[:500]}\nAnalyst:"
    )
    return provider_manager.generate_with_fallback([prompt], json_response=False).strip()


def run_market_analysis(
    symbol: str,
    timeframe: str,
    prompt: Optional[str] = None,
    price_context: Optional[str] = None,
    deterministic_analysis: Optional[dict] = None,
) -> dict:
    return provider_manager.analyze_with_fallback(
        symbol=symbol,
        timeframe=timeframe,
        prompt=prompt,
        image_bytes=None,
        image_mime=None,
        price_context=price_context,
        deterministic_analysis=deterministic_analysis,
    )