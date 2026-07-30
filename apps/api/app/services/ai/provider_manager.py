from __future__ import annotations

from collections import Counter
from typing import Any, Optional

from app.config import settings

from .providers.base import (
    AIProvider,
    AIProviderError,
    AIProviderNotConfigured,
    ANALYSIS_SCHEMA_INSTRUCTIONS,
    ProviderStatus,
    json_from_text,
)
from .providers.claude import ClaudeProvider
from .providers.gemini import GeminiProvider
from .providers.local import LMStudioProvider, OllamaProvider
from .providers.openai_compatible import (
    DeepSeekProvider,
    GrokProvider,
    OpenAIProvider,
    OpenRouterProvider,
    QwenProvider,
)

TEXT_ONLY_CONFIDENCE_CAP = 50


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


def validate_analysis(data: dict, *, image_bytes: Optional[bytes], price_context: Optional[str]) -> dict:
    bias = str(data.get("bias", "neutral")).lower()
    if bias not in ("bullish", "bearish", "neutral"):
        bias = "neutral"
    signal = str(data.get("signal", "hold")).lower()
    if signal not in ("buy", "sell", "hold"):
        signal = "hold"
    confidence = max(0, min(100, int(_to_float(data.get("confidence"), 0))))
    reasoning = data.get("reasoning")
    if not isinstance(reasoning, list):
        reasoning = [str(reasoning)] if reasoning else []
    risk_warning = data.get("risk_warning")
    if not image_bytes and not price_context:
        confidence = min(confidence, TEXT_ONLY_CONFIDENCE_CAP)
        no_data_note = "Generated without a chart image or live market data - verify all levels before acting."
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
        "reasoning": [str(item) for item in reasoning][:8],
        "invalidation": str(data.get("invalidation") or "Not specified"),
        "news_warning": data.get("news_warning") or None,
        "risk_warning": risk_warning,
        "raw": data,
    }


def analysis_parts(
    symbol: str,
    timeframe: str,
    prompt: Optional[str],
    image_bytes: Optional[bytes],
    image_mime: Optional[str],
    price_context: Optional[str],
    deterministic_analysis: Optional[dict] = None,
) -> list[Any]:
    user_context = f"Instrument: {symbol}\nTimeframe: {timeframe}"
    if prompt:
        user_context += f"\nTrader's question/context: {prompt}"
    parts: list[Any] = [ANALYSIS_SCHEMA_INSTRUCTIONS, user_context]
    if deterministic_analysis:
        parts.append("Deterministic technical-analysis snapshot:\n" + str(deterministic_analysis))
    if image_bytes:
        parts.append({"mime_type": image_mime or "image/png", "data": image_bytes})
        parts.append("Analyze the attached chart, but do not invent levels outside the chart or market snapshot.")
    if price_context:
        parts.append(
            "Live OHLC candles from the market data feed (most recent last). "
            "Base price levels on this data:\n" + price_context
        )
    if not image_bytes and not price_context:
        parts.append("No live price feed or chart image was supplied. Keep confidence low and avoid precise levels.")
    return parts


class AIProviderManager:
    def __init__(self):
        self._providers: dict[str, AIProvider] = {
            "ollama": OllamaProvider(settings),
            "lmstudio": LMStudioProvider(settings),
            "gemini": GeminiProvider(settings),
            "openai": OpenAIProvider(settings),
            "claude": ClaudeProvider(settings),
            "deepseek": DeepSeekProvider(settings),
            "qwen": QwenProvider(settings),
            "grok": GrokProvider(settings),
            "openrouter": OpenRouterProvider(settings),
        }
        self._aliases = {
            "gpt": "openai",
            "anthropic": "claude",
            "xai": "grok",
            "lm_studio": "lmstudio",
        }

    def all_statuses(self) -> list[ProviderStatus]:
        return [provider.status() for provider in self.ordered(include_unconfigured=True)]

    def ordered(self, *, include_unconfigured: bool = False) -> list[AIProvider]:
        requested = [
            self._aliases.get(item.strip().lower(), item.strip().lower())
            for item in settings.AI_PROVIDER_ORDER.split(",")
            if item.strip()
        ]
        local_first = ["ollama", "lmstudio"]
        defaults = ["ollama", "lmstudio", "gemini", "openrouter", "openai", "claude", "deepseek", "qwen", "grok"]
        result: list[AIProvider] = []
        for provider_id in local_first + requested + defaults:
            provider = self._providers.get(provider_id)
            if provider and provider not in result and (include_unconfigured or provider.is_configured()):
                result.append(provider)
        return result

    def generate_with_fallback(self, parts: list[Any], *, json_response: bool = True) -> str:
        providers = self.ordered()
        if not providers:
            raise AIProviderNotConfigured("No AI provider is configured")
        errors: list[str] = []
        for provider in providers:
            try:
                return provider.generate(parts, json_response=json_response)
            except AIProviderError as exc:
                errors.append(f"{provider.id}: {exc}")
        raise AIProviderError("All configured AI providers failed (" + "; ".join(errors) + ")")

    def analyze_with_fallback(self, **kwargs) -> dict:
        parts = analysis_parts(**kwargs)
        raw = self.generate_with_fallback(parts, json_response=True)
        return validate_analysis(json_from_text(raw), image_bytes=kwargs.get("image_bytes"), price_context=kwargs.get("price_context"))

    def analyze_with_provider(self, provider: AIProvider, **kwargs) -> dict:
        parts = analysis_parts(**kwargs)
        raw = provider.generate(parts, json_response=True)
        return validate_analysis(json_from_text(raw), image_bytes=kwargs.get("image_bytes"), price_context=kwargs.get("price_context"))

    def compare(self, **kwargs) -> dict:
        results = []
        for provider in self.ordered(include_unconfigured=True):
            status = provider.status()
            if not status.available:
                results.append({"provider": status.__dict__, "status": "Currently unavailable", "analysis": None, "error": None})
                continue
            try:
                results.append({
                    "provider": status.__dict__,
                    "status": "available",
                    "analysis": self.analyze_with_provider(provider, **kwargs),
                    "error": None,
                })
            except AIProviderError as exc:
                results.append({"provider": status.__dict__, "status": "Currently unavailable", "analysis": None, "error": str(exc)})
        available_items = [item for item in results if item.get("analysis")]
        available = [item["analysis"] for item in available_items]
        signal_counts = Counter(item["signal"] for item in available)
        majority_signal, majority_count = ("hold", 0) if not signal_counts else signal_counts.most_common(1)[0]
        confidence = round(sum(item["confidence"] for item in available) / len(available), 1) if available else 0.0
        disagreeing = [
            item["provider"]["label"]
            for item in available_items
            if item["analysis"]["signal"] != majority_signal
        ]
        consensus = {
            "majority_signal": majority_signal,
            "agreement_count": majority_count,
            "model_count": len(available),
            "agreement_percentage": round((majority_count / len(available)) * 100, 1) if available else 0.0,
            "average_confidence": confidence,
            "conflicting_opinions": disagreeing,
            "minority_opinions": [
                {"signal": signal, "count": count}
                for signal, count in signal_counts.items()
                if signal != majority_signal
            ],
        }
        return {"results": results, "consensus": consensus}


provider_manager = AIProviderManager()
