# AroPilot AI

AroPilot AI is a direct MetaTrader 5 trading-intelligence platform. The primary workflow is live market data from the AroPilot MT5 Expert Advisor into the FastAPI backend, deterministic technical analysis, multi-provider AI comparison, consensus scoring, and synchronized web/MT5 chart annotations.

## Primary Architecture

Trader -> MetaTrader 5 Desktop -> AroPilot MT5 Expert Advisor -> Secure HTTPS bridge -> FastAPI backend -> Deterministic analysis engine -> Multi-AI provider framework -> AI consensus -> Web dashboard and MT5 annotations.

## Core Capabilities

- Direct MT5 Expert Advisor bridge for candles, quotes, account telemetry, positions, orders, history, and indicator snapshots.
- Deterministic technical-analysis engine used as the source of numeric market context.
- Multi-AI provider framework for Ollama, LM Studio, Gemini, OpenAI, Claude, DeepSeek, Qwen, OpenRouter, Grok, and OpenAI-compatible APIs.
- AI comparison and consensus with unavailable providers shown gracefully.
- MT5 chart annotation commands for entry zones, stop loss, take-profit levels, and signal arrows.
- Strategy builder, scanner, backtesting, journal, notifications, risk controls, and administration surfaces.
- Optional MetaApi adapter for users who explicitly choose hosted broker connectivity.

## MT5 Connector

Download the connector from the running app:

`/mt5/AroPilotMT5Connector.zip`

Install all files into `MQL5/Experts/AroPilot/`, allow WebRequest for your AroPilot domain, compile `AroPilotEA.mq5`, attach it to a chart, and paste the generated bridge endpoint, account id, and API key from Broker Accounts.

## API Entry Points

- `POST /api/broker-accounts/direct-mt5` creates a direct EA bridge account.
- `POST /api/mt5/bridge/heartbeat` receives account telemetry.
- `POST /api/mt5/bridge/quote` receives live ticks/quotes.
- `POST /api/mt5/bridge/candles` receives OHLC data.
- `GET /api/mt5/bridge/commands` returns analysis, signals, risk, notifications, and chart objects to MT5.
- `POST /api/ai/analyze` runs live-data market analysis.
- `POST /api/ai/compare` runs multi-provider comparison and consensus.
- `GET /api/ai/providers` lists provider status.

## Local Development

Use Docker Compose for the complete local stack:

```bash
docker compose up --build
```

Set provider keys only for the providers you want to use. Local-first providers such as Ollama and LM Studio can be configured through their base URLs and model names.

## Production

The production path is Docker Compose deployed through Coolify. The web app, API, worker, scheduler, streamer, PostgreSQL, Redis, and reverse proxy are part of the deployment path.