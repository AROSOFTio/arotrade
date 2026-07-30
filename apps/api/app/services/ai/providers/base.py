from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Optional


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
  "news_warning": <string or null>,
  "risk_warning": <string or null>
}

Rules:
- Never invent market data. Interpret only the supplied snapshot and deterministic analysis.
- If the picture is mixed, say "hold" with low confidence.
- A buy needs stop_loss below entry and take_profit_1 above; a sell the reverse.
- If you cannot determine price levels reliably, use 0 for entry_min, entry_max and stop_loss.
"""


class AIProviderError(Exception):
    """Raised when a provider call or response parsing fails."""


class AIProviderNotConfigured(AIProviderError):
    """Raised when no supported provider is configured."""


@dataclass(frozen=True)
class ProviderStatus:
    id: str
    label: str
    model: str
    configured: bool
    available: bool
    status: str
    reason: str | None = None


class AIProvider:
    id: str = ""
    label: str = ""

    def __init__(self, settings: Any):
        self.settings = settings

    @property
    def model(self) -> str:
        raise NotImplementedError

    def is_configured(self) -> bool:
        raise NotImplementedError

    def status(self) -> ProviderStatus:
        configured = self.is_configured()
        return ProviderStatus(
            id=self.id,
            label=self.label,
            model=self.model,
            configured=configured,
            available=configured,
            status="available" if configured else "Currently unavailable",
            reason=None if configured else "Missing API key or local endpoint",
        )

    def generate(self, parts: list[Any], *, json_response: bool = True) -> str:
        raise NotImplementedError


def json_from_text(raw: str | None) -> dict:
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


def encode_data_url(part: dict[str, Any]) -> str:
    encoded = base64.b64encode(part["data"]).decode("ascii")
    return f"data:{part.get('mime_type') or 'image/png'};base64,{encoded}"


def text_from_openai_compatible_response(data: dict) -> str:
    text = data.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    output = data.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            content = item.get("content") if isinstance(item, dict) else None
            if isinstance(content, list):
                for part in content:
                    value = part.get("text") or part.get("output_text") if isinstance(part, dict) else None
                    if isinstance(value, str):
                        chunks.append(value)
            elif isinstance(content, str):
                chunks.append(content)
        if chunks:
            return "".join(chunks).strip()
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
    return ""

