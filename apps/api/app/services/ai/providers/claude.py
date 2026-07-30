from __future__ import annotations

import base64
from typing import Any

import httpx

from .base import AIProvider, AIProviderError


class ClaudeProvider(AIProvider):
    id = "claude"
    label = "Claude"

    @property
    def model(self) -> str:
        return self.settings.CLAUDE_MODEL or self.settings.ANTHROPIC_MODEL

    def is_configured(self) -> bool:
        return bool((self.settings.CLAUDE_API_KEY or self.settings.ANTHROPIC_API_KEY) and (self.settings.CLAUDE_BASE_URL or self.settings.ANTHROPIC_BASE_URL))

    def generate(self, parts: list[Any], *, json_response: bool = True) -> str:
        if not self.is_configured():
            raise AIProviderError("Claude is not configured")

        content_parts: list[dict] = []
        for part in parts:
            if isinstance(part, dict) and part.get("data"):
                content_parts.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": part.get("mime_type") or "image/png",
                        "data": base64.b64encode(part["data"]).decode("ascii"),
                    },
                })
            else:
                content_parts.append({"type": "text", "text": str(part)})
        if json_response:
            content_parts.append({"type": "text", "text": "Return only valid JSON."})

        try:
            response = httpx.post(
                f"{(self.settings.CLAUDE_BASE_URL or self.settings.ANTHROPIC_BASE_URL).rstrip('/')}/messages",
                headers={
                    "x-api-key": self.settings.CLAUDE_API_KEY or self.settings.ANTHROPIC_API_KEY,
                    "anthropic-version": self.settings.CLAUDE_VERSION or self.settings.ANTHROPIC_VERSION,
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "system": "Follow the user's output-format instructions exactly.",
                    "messages": [{"role": "user", "content": content_parts}],
                    "max_tokens": 2048,
                    "temperature": 0.2,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            content = response.json().get("content")
            if isinstance(content, list):
                return "".join(p.get("text", "") for p in content if isinstance(p, dict)).strip()
            return ""
        except Exception as exc:
            raise AIProviderError(f"Claude request failed: {exc}") from exc


