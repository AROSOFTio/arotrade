from __future__ import annotations

from typing import Any

import httpx

from .base import AIProvider, AIProviderError


class OllamaProvider(AIProvider):
    id = "ollama"
    label = "Ollama"

    @property
    def model(self) -> str:
        return self.settings.OLLAMA_MODEL

    def is_configured(self) -> bool:
        return bool(self.settings.OLLAMA_BASE_URL and self.settings.OLLAMA_MODEL)

    def generate(self, parts: list[Any], *, json_response: bool = True) -> str:
        if not self.is_configured():
            raise AIProviderError("Ollama is not configured")
        if any(isinstance(part, dict) and part.get("data") for part in parts):
            raise AIProviderError("Ollama adapter only supports text market snapshots")
        prompt = "\n\n".join(str(part) for part in parts)
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        if json_response:
            payload["format"] = "json"
        try:
            response = httpx.post(
                f"{self.settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate",
                json=payload,
                timeout=60.0,
            )
            if response.status_code >= 500 and json_response:
                retry_payload = dict(payload)
                retry_payload.pop("format", None)
                retry = httpx.post(
                    f"{self.settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate",
                    json=retry_payload,
                    timeout=60.0,
                )
                retry.raise_for_status()
                return str(retry.json().get("response") or "").strip()
            response.raise_for_status()
            return str(response.json().get("response") or "").strip()
        except Exception as exc:
            raise AIProviderError("Ollama request failed. Check that the model is pulled and the Ollama container is healthy.") from exc


class LMStudioProvider(AIProvider):
    id = "lmstudio"
    label = "LM Studio"

    @property
    def model(self) -> str:
        return self.settings.LMSTUDIO_MODEL

    def is_configured(self) -> bool:
        return bool(self.settings.LMSTUDIO_BASE_URL and self.settings.LMSTUDIO_MODEL)

    def generate(self, parts: list[Any], *, json_response: bool = True) -> str:
        if not self.is_configured():
            raise AIProviderError("LM Studio is not configured")
        if any(isinstance(part, dict) and part.get("data") for part in parts):
            raise AIProviderError("LM Studio adapter only supports text market snapshots")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Follow the user's output-format instructions exactly."},
                {"role": "user", "content": "\n\n".join(str(part) for part in parts)},
            ],
            "temperature": 0.2,
        }
        if json_response:
            payload["response_format"] = {"type": "json_object"}
        try:
            response = httpx.post(
                f"{self.settings.LMSTUDIO_BASE_URL.rstrip('/')}/chat/completions",
                json=payload,
                timeout=60.0,
            )
            response.raise_for_status()
            choices = response.json().get("choices") or []
            if choices:
                return str(choices[0].get("message", {}).get("content") or "").strip()
            return ""
        except Exception as exc:
            raise AIProviderError(f"LM Studio request failed: {exc}") from exc

