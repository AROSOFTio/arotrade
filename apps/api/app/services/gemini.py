"""Gemini-backed chart analysis.

Produces a structured analysis dict matching the AIAnalysis model columns.
Text-only requests (no chart image) get their confidence capped and carry an
explicit risk warning, because the model has no live price feed to anchor
levels against. Image requests let the model read levels off the chart itself.
"""

import json
from typing import Optional

import google.generativeai as genai

from app.config import settings

TEXT_ONLY_CONFIDENCE_CAP = 50

ANALYSIS_SCHEMA_INSTRUCTIONS = """
You are a chartered market technician producing a disciplined, risk-first
technical analysis. Respond with ONLY a JSON object (no markdown fences)
using exactly these keys:

{
  "bias": "bullish" | "bearish" | "neutral",
  "signal": "buy" | "sell" | "hold",
  "confidence": <integer 0-100>,
  "entry_min": <number>,
  "entry_max": <number>,
  "stop_loss": <number>,
  "take_profit_1": <number or null>,
  "take_profit_2": <number or null>,
  "take_profit_3": <number or null>,
  "risk_reward": <number>,
  "reasoning": [<3-6 short strings, each one observation>],
  "invalidation": <string: the specific condition that voids this analysis>,
  "news_warning": <string or null: upcoming scheduled events that could affect this market>,
  "risk_warning": <string or null>
}

Rules:
- Never invent certainty. If the picture is mixed, say "hold" with low confidence.
- A buy needs stop_loss below entry and take_profit_1 above; a sell the reverse.
- reasoning entries must reference concrete observations (structure, momentum,
  levels), not generic advice.
- If you cannot determine price levels reliably, use 0 for entry_min,
  entry_max and stop_loss, signal "hold", and explain why in reasoning.
"""


class GeminiError(Exception):
    """Raised when the Gemini call or its response parsing fails."""


class GeminiNotConfigured(GeminiError):
    """Raised when no API key is configured."""


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_optional_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run_chart_analysis(
    symbol: str,
    timeframe: str,
    prompt: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    image_mime: Optional[str] = None,
    price_context: Optional[str] = None,
) -> dict:
    """Call Gemini and return a validated analysis dict.

    price_context is a compact OHLC candle table from the live market data
    feed; when present the model anchors levels to real prices and the
    text-only confidence cap is not applied.
    """
    if not settings.GEMINI_API_KEY:
        raise GeminiNotConfigured("GEMINI_API_KEY is not configured")

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(settings.GEMINI_MODEL)

    user_context = f"Instrument: {symbol}\nTimeframe: {timeframe}"
    if prompt:
        user_context += f"\nTrader's question/context: {prompt}"

    parts: list = [ANALYSIS_SCHEMA_INSTRUCTIONS, user_context]
    if image_bytes:
        parts.append({"mime_type": image_mime or "image/png", "data": image_bytes})
        parts.append(
            "Analyze the attached chart screenshot. Read actual price levels "
            "from the chart axes; do not guess levels the chart does not show."
        )
        if price_context:
            parts.append(
                "Live OHLC candles from the market data feed (most recent last) "
                f"— cross-check your levels against the latest close:\n{price_context}"
            )
    elif price_context:
        parts.append(
            "Live OHLC candles from the market data feed (most recent last). "
            "Base your structure read and ALL price levels on this data — the "
            "last row's close is the current price:\n" + price_context
        )
    else:
        parts.append(
            "No chart image was provided and you have no live price feed. "
            "Give a structural/qualitative view only, keep confidence low, and "
            "follow the rules for unreliable levels."
        )

    try:
        response = model.generate_content(
            parts,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.2,
            },
        )
        raw = response.text
    except Exception as exc:  # SDK raises many provider-specific types
        raise GeminiError(f"Gemini request failed: {exc}") from exc

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise GeminiError("Gemini returned a response that is not valid JSON") from exc

    bias = str(data.get("bias", "neutral")).lower()
    if bias not in ("bullish", "bearish", "neutral"):
        bias = "neutral"
    signal = str(data.get("signal", "hold")).lower()
    if signal not in ("buy", "sell", "hold"):
        signal = "hold"

    confidence = int(_to_float(data.get("confidence"), 0))
    confidence = max(0, min(100, confidence))

    reasoning = data.get("reasoning")
    if not isinstance(reasoning, list):
        reasoning = [str(reasoning)] if reasoning else []
    reasoning = [str(item) for item in reasoning][:8]

    risk_warning = data.get("risk_warning")
    if not image_bytes and not price_context:
        confidence = min(confidence, TEXT_ONLY_CONFIDENCE_CAP)
        no_data_note = (
            "Generated without a chart image or live market data - verify all "
            "levels on your own chart before acting."
        )
        risk_warning = f"{risk_warning} {no_data_note}".strip() if risk_warning else no_data_note

    return {
        "bias": bias,
        "signal": signal,
        "confidence": confidence,
        "entry_min": _to_float(data.get("entry_min")),
        "entry_max": _to_float(data.get("entry_max")),
        "stop_loss": _to_float(data.get("stop_loss")),
        "take_profit_1": _to_optional_float(data.get("take_profit_1")),
        "take_profit_2": _to_optional_float(data.get("take_profit_2")),
        "take_profit_3": _to_optional_float(data.get("take_profit_3")),
        "risk_reward": _to_float(data.get("risk_reward")),
        "reasoning": reasoning,
        "invalidation": str(data.get("invalidation") or "Not specified"),
        "news_warning": data.get("news_warning") or None,
        "risk_warning": risk_warning,
        "raw": data,
    }
