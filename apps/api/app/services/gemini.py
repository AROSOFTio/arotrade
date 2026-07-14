"""AI-backed chart analysis with provider fallback.

The public functions in this module keep the historical Gemini names because
scanner and route code import them. Internally, configured providers are tried
in AI_PROVIDER_ORDER. Supported providers are xAI/Grok, OpenAI, Claude, and Gemini.
"""

from __future__ import annotations

import base64
import json
from typing import Optional

import httpx

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


class AIProviderError(Exception):
    """Raised when an AI provider call or response parsing fails."""


class AIProviderNotConfigured(AIProviderError):
    """Raised when no supported AI provider has an API key."""


# Backward-compatible names used by the routes and scanner.
GeminiError = AIProviderError
GeminiNotConfigured = AIProviderNotConfigured


def _provider_order() -> list[str]:
    configured = {
        "xai": bool(settings.XAI_API_KEY),
        "openai": bool(settings.OPENAI_API_KEY),
        "anthropic": bool(settings.ANTHROPIC_API_KEY),
        "gemini": bool(settings.GEMINI_API_KEY),
    }
    aliases = {"claude": "anthropic"}
    requested = [
        aliases.get(p.strip().lower(), p.strip().lower())
        for p in settings.AI_PROVIDER_ORDER.split(",")
        if p.strip()
    ]
    ordered: list[str] = []
    for provider in requested + ["xai", "openai", "anthropic", "gemini"]:
        if provider in configured and configured[provider] and provider not in ordered:
            ordered.append(provider)
    return ordered


def ai_health_details() -> dict:
    providers = _provider_order()
    model_map = {
        "xai": settings.XAI_MODEL,
        "openai": settings.OPENAI_MODEL,
        "anthropic": settings.ANTHROPIC_MODEL,
        "gemini": settings.GEMINI_MODEL,
    }
    return {
        "status": "operational" if providers else "unavailable",
        "provider": ", ".join(providers) if providers else "none",
        "model": ", ".join(f"{provider}:{model_map[provider]}" for provider in providers) if providers else "none",
        "is_available": bool(providers),
        "providers": providers,
    }


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


def _json_from_text(raw: str | None) -> dict:
    if not raw:
        raise AIProviderError("AI provider returned an empty response")
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise AIProviderError("AI provider returned a response that is not valid JSON")


def _validate_analysis(data: dict, *, image_bytes: Optional[bytes], price_context: Optional[str]) -> dict:
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


def _analysis_parts(
    symbol: str,
    timeframe: str,
    prompt: Optional[str],
    image_bytes: Optional[bytes],
    image_mime: Optional[str],
    price_context: Optional[str],
) -> list:
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
                f"- cross-check your levels against the latest close:\n{price_context}"
            )
    elif price_context:
        parts.append(
            "Live OHLC candles from the market data feed (most recent last). "
            "Base your structure read and ALL price levels on this data - the "
            "last row's close is the current price:\n" + price_context
        )
    else:
        parts.append(
            "No chart image was provided and you have no live price feed. "
            "Give a structural/qualitative view only, keep confidence low, and "
            "follow the rules for unreliable levels."
        )
    return parts


def _gemini_generate(parts: list, *, json_response: bool = True) -> str:
    if not settings.GEMINI_API_KEY:
        raise AIProviderNotConfigured("GEMINI_API_KEY is not configured")
    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(settings.GEMINI_MODEL)
        generation_config = {"temperature": 0.2}
        if json_response:
            generation_config["response_mime_type"] = "application/json"
        response = model.generate_content(parts, generation_config=generation_config)
        return (response.text or "").strip()
    except Exception as exc:
        raise AIProviderError(f"Gemini request failed: {exc}") from exc


def _xai_response_text(data: dict) -> str:
    text = data.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    output = data.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    value = part.get("text") or part.get("output_text")
                    if isinstance(value, str):
                        chunks.append(value)
            elif isinstance(content, str):
                chunks.append(content)
        if chunks:
            return "".join(chunks).strip()

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        if isinstance(message, dict):
            return str(message.get("content") or "").strip()
    return ""


def _xai_generate(parts: list, *, json_response: bool = True) -> str:
    if not settings.XAI_API_KEY:
        raise AIProviderNotConfigured("XAI_API_KEY is not configured")

    content_parts: list[dict] = []
    has_image = False
    for part in parts:
        if isinstance(part, dict) and part.get("data"):
            has_image = True
            encoded = base64.b64encode(part["data"]).decode("ascii")
            mime_type = part.get("mime_type") or "image/png"
            content_parts.append({
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{encoded}",
            })
        else:
            content_parts.append({"type": "input_text", "text": str(part)})

    user_content = content_parts if has_image else "\n\n".join(item["text"] for item in content_parts)
    payload: dict = {
        "model": settings.XAI_MODEL,
        "input": [
            {
                "role": "system",
                "content": "You are a precise trading-analysis engine. Follow output-format instructions exactly.",
            },
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.2,
    }
    if json_response:
        payload["text"] = {"format": {"type": "json_object"}}

    try:
        response = httpx.post(
            f"{settings.XAI_BASE_URL.rstrip('/')}/responses",
            headers={
                "Authorization": f"Bearer {settings.XAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60.0,
        )
        response.raise_for_status()
        return _xai_response_text(response.json())
    except Exception as exc:
        raise AIProviderError(f"xAI request failed: {exc}") from exc

def _openai_generate(parts: list, *, json_response: bool = True) -> str:
    if not settings.OPENAI_API_KEY:
        raise AIProviderNotConfigured("OPENAI_API_KEY is not configured")

    content_parts: list[dict] = []
    has_image = False
    for part in parts:
        if isinstance(part, dict) and part.get("data"):
            has_image = True
            encoded = base64.b64encode(part["data"]).decode("ascii")
            mime_type = part.get("mime_type") or "image/png"
            content_parts.append({
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{encoded}",
            })
        else:
            content_parts.append({"type": "input_text", "text": str(part)})

    user_content = content_parts if has_image else "\n\n".join(item["text"] for item in content_parts)
    payload: dict = {
        "model": settings.OPENAI_MODEL,
        "input": [
            {
                "role": "system",
                "content": "You are a precise trading-analysis engine. Follow output-format instructions exactly.",
            },
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.2,
    }
    if json_response:
        payload["text"] = {"format": {"type": "json_object"}}

    try:
        response = httpx.post(
            f"{settings.OPENAI_BASE_URL.rstrip('/')}/responses",
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60.0,
        )
        response.raise_for_status()
        return _xai_response_text(response.json())
    except Exception as exc:
        raise AIProviderError(f"OpenAI request failed: {exc}") from exc


def _anthropic_response_text(data: dict) -> str:
    content = data.get("content")
    if isinstance(content, list):
        chunks = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                value = part.get("text")
                if isinstance(value, str):
                    chunks.append(value)
        if chunks:
            return "".join(chunks).strip()
    return ""


def _anthropic_generate(parts: list, *, json_response: bool = True) -> str:
    if not settings.ANTHROPIC_API_KEY:
        raise AIProviderNotConfigured("ANTHROPIC_API_KEY is not configured")

    content_parts: list[dict] = []
    for part in parts:
        if isinstance(part, dict) and part.get("data"):
            encoded = base64.b64encode(part["data"]).decode("ascii")
            mime_type = part.get("mime_type") or "image/png"
            content_parts.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": encoded,
                },
            })
        else:
            content_parts.append({"type": "text", "text": str(part)})
    if json_response:
        content_parts.append({"type": "text", "text": "Return only a valid JSON object. Do not wrap it in markdown."})

    try:
        response = httpx.post(
            f"{settings.ANTHROPIC_BASE_URL.rstrip('/')}/messages",
            headers={
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": settings.ANTHROPIC_VERSION,
                "Content-Type": "application/json",
            },
            json={
                "model": settings.ANTHROPIC_MODEL,
                "system": "You are a precise trading-analysis engine. Follow output-format instructions exactly.",
                "messages": [{"role": "user", "content": content_parts}],
                "max_tokens": 2048,
                "temperature": 0.2,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        return _anthropic_response_text(response.json())
    except Exception as exc:
        raise AIProviderError(f"Anthropic request failed: {exc}") from exc

def _generate_with_provider(provider: str, parts: list, *, json_response: bool = True) -> str:
    if provider == "xai":
        return _xai_generate(parts, json_response=json_response)
    if provider == "openai":
        return _openai_generate(parts, json_response=json_response)
    if provider == "anthropic":
        return _anthropic_generate(parts, json_response=json_response)
    if provider == "gemini":
        return _gemini_generate(parts, json_response=json_response)
    raise AIProviderError(f"Unsupported AI provider: {provider}")

def _generate_with_fallback(parts: list, *, json_response: bool = True) -> str:
    providers = _provider_order()
    if not providers:
        raise AIProviderNotConfigured("No AI provider API key is configured")

    last_error: Optional[Exception] = None
    for provider in providers:
        try:
            return _generate_with_provider(provider, parts, json_response=json_response)
        except AIProviderError as exc:
            last_error = exc
            continue
    raise AIProviderError(str(last_error) if last_error else "All AI providers failed")


def analyze_json(prompt: str, *, temperature: float = 0.3) -> dict:
    del temperature  # Kept for call-site readability; provider config is fixed here.
    providers = _provider_order()
    if not providers:
        raise AIProviderNotConfigured("No AI provider API key is configured")

    last_error: Optional[Exception] = None
    for provider in providers:
        try:
            raw = _generate_with_provider(provider, [prompt], json_response=True)
            return _json_from_text(raw)
        except AIProviderError as exc:
            last_error = exc
            continue
    raise AIProviderError(str(last_error) if last_error else "All AI providers failed")

def answer_analysis_question(analysis_summary: str, history: list[dict], question: str) -> str:
    transcript = ""
    for message in history[-10:]:
        speaker = "Trader" if message.get("role") == "user" else "Analyst"
        transcript += f"{speaker}: {str(message.get('content', ''))[:500]}\n"

    prompt = (
        "You are a patient trading mentor. A trader is asking follow-up questions about "
        "an AI market analysis. Explain clearly in plain language, define any jargon you "
        "use, keep answers under 150 words, never promise profits, and remind them of the "
        "risk side when relevant. Do not invent new price levels beyond the analysis.\n\n"
        f"THE ANALYSIS BEING DISCUSSED:\n{analysis_summary}\n\n"
        f"CONVERSATION SO FAR:\n{transcript}"
        f"Trader: {question[:500]}\nAnalyst:"
    )
    return _generate_with_fallback([prompt], json_response=False).strip()


def run_chart_analysis(
    symbol: str,
    timeframe: str,
    prompt: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    image_mime: Optional[str] = None,
    price_context: Optional[str] = None,
) -> dict:
    """Call the first available AI provider and return a validated analysis dict."""
    parts = _analysis_parts(symbol, timeframe, prompt, image_bytes, image_mime, price_context)
    providers = _provider_order()
    if not providers:
        raise AIProviderNotConfigured("No AI provider API key is configured")

    last_error: Optional[Exception] = None
    for provider in providers:
        try:
            raw = _generate_with_provider(provider, parts, json_response=True)
            data = _json_from_text(raw)
            return _validate_analysis(data, image_bytes=image_bytes, price_context=price_context)
        except AIProviderError as exc:
            last_error = exc
            continue
    raise AIProviderError(str(last_error) if last_error else "All AI providers failed")
