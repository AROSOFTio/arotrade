# AroPilot AI Environment Setup

Configure only the services you use.

Required platform settings:
- `APP_NAME=AroPilot AI`
- `APP_URL`
- `JWT_SECRET`
- `ENCRYPTION_KEY`
- `POSTGRES_*`
- `REDIS_URL`

AI providers are modular. Configure Ollama, LM Studio, Gemini, OpenAI, Claude, DeepSeek, Qwen, OpenRouter, Grok, or any OpenAI-compatible endpoint as needed. Missing providers are shown as unavailable and do not crash analysis.

MetaApi variables are optional and used only by the hosted broker adapter.