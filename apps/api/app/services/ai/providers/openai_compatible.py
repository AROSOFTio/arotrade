from __future__ import annotations

from typing import Any

import httpx

from .base import AIProvider, AIProviderError, encode_data_url, text_from_openai_compatible_response


class OpenAICompatibleProvider(AIProvider):
    api_key_attr = ""
    model_attr = ""
    base_url_attr = ""

    @property
    def api_key(self) -> str:
        return str(getattr(self.settings, self.api_key_attr, "") or "")

    @property
    def model(self) -> str:
        return str(getattr(self.settings, self.model_attr, "") or "")

    @property
    def base_url(self) -> str:
        return str(getattr(self.settings, self.base_url_attr, "") or "")

    def is_configured(self) -> bool:
        return bool(self.api_key and self.model and self.base_url)

    def generate(self, parts: list[Any], *, json_response: bool = True) -> str:
        if not self.is_configured():
            raise AIProviderError(f"{self.label} is not configured")

        content_parts: list[dict] = []
        has_image = False
        for part in parts:
            if isinstance(part, dict) and part.get("data"):
                has_image = True
                content_parts.append({"type": "input_image", "image_url": encode_data_url(part)})
            else:
                content_parts.append({"type": "input_text", "text": str(part)})

        payload: dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": "Follow the user's output-format instructions exactly."},
                {"role": "user", "content": content_parts if has_image else "\n\n".join(p["text"] for p in content_parts)},
            ],
            "temperature": 0.2,
        }
        if json_response:
            payload["text"] = {"format": {"type": "json_object"}}

        try:
            response = httpx.post(
                f"{self.base_url.rstrip('/')}/responses",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=60.0,
            )
            response.raise_for_status()
            return text_from_openai_compatible_response(response.json())
        except Exception as exc:
            raise AIProviderError(f"{self.label} request failed: {exc}") from exc


class OpenAIProvider(OpenAICompatibleProvider):
    id = "openai"
    label = "GPT"
    api_key_attr = "OPENAI_API_KEY"
    model_attr = "OPENAI_MODEL"
    base_url_attr = "OPENAI_BASE_URL"


class DeepSeekProvider(OpenAICompatibleProvider):
    id = "deepseek"
    label = "DeepSeek"
    api_key_attr = "DEEPSEEK_API_KEY"
    model_attr = "DEEPSEEK_MODEL"
    base_url_attr = "DEEPSEEK_BASE_URL"


class QwenProvider(OpenAICompatibleProvider):
    id = "qwen"
    label = "Qwen"
    api_key_attr = "QWEN_API_KEY"
    model_attr = "QWEN_MODEL"
    base_url_attr = "QWEN_BASE_URL"


class GrokProvider(OpenAICompatibleProvider):
    id = "grok"
    label = "Grok"
    api_key_attr = "GROK_API_KEY"
    model_attr = "GROK_MODEL"
    base_url_attr = "GROK_BASE_URL"

    @property
    def api_key(self) -> str:
        return str(self.settings.GROK_API_KEY or self.settings.XAI_API_KEY or "")

    @property
    def model(self) -> str:
        return str(self.settings.GROK_MODEL or self.settings.XAI_MODEL or "")

    @property
    def base_url(self) -> str:
        return str(self.settings.GROK_BASE_URL or self.settings.XAI_BASE_URL or "")


class OpenRouterProvider(OpenAICompatibleProvider):
    id = "openrouter"
    label = "OpenRouter"
    api_key_attr = "OPENROUTER_API_KEY"
    model_attr = "OPENROUTER_MODEL"
    base_url_attr = "OPENROUTER_BASE_URL"


