from __future__ import annotations

from typing import Any

from .base import AIProvider, AIProviderError


class GeminiProvider(AIProvider):
    id = "gemini"
    label = "Gemini"

    @property
    def model(self) -> str:
        return self.settings.GEMINI_MODEL

    def is_configured(self) -> bool:
        return bool(self.settings.GEMINI_API_KEY)

    def generate(self, parts: list[Any], *, json_response: bool = True) -> str:
        if not self.is_configured():
            raise AIProviderError("Gemini is not configured")
        try:
            import google.generativeai as genai

            genai.configure(api_key=self.settings.GEMINI_API_KEY)
            model = genai.GenerativeModel(self.model)
            generation_config = {"temperature": 0.2}
            if json_response:
                generation_config["response_mime_type"] = "application/json"
            response = model.generate_content(parts, generation_config=generation_config)
            return (response.text or "").strip()
        except Exception as exc:
            raise AIProviderError(f"Gemini request failed: {exc}") from exc

