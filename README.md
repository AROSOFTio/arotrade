# AroTrade AI - AI-Powered Trading Intelligence

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Overview

AroTrade AI by **AROSOFT Innovations** is a full-stack, AI-powered trading analysis and execution platform. It combines chart analysis, signal generation, strategy building, backtesting, and risk management—all powered by Gemini AI and designed for professional traders.

**⚠️ DISCLAIMER:** AroTrade AI does not guarantee profits or win rates. Trading forex, CFDs, synthetic indices, and cryptocurrencies involves significant risk of loss. Always test strategies on demo accounts before live trading.

## Features

- **AI Chart Analysis** – Upload market screenshots, get Gemini AI analysis
- **Signal Generation** – AI-generated trading signals with entry/exit zones
- **Strategy Builder** – Create custom strategies with smart money concepts
- **Backtesting Studio** – Test strategies against historical data
- **Trading Journal** – Track trades, emotions, lessons learned
- **Risk Guardian** – Strict risk validation before execution
- **Demo Trading** – Paper trading engine for testing
- **Live Trading** – Safety-gated MT5 broker-demo/live execution through MetaApi
- **Admin Dashboard** – Audit logs, user management, signal monitoring
- **API-First** – Extensible REST API for integrations

## Tech Stack

### Frontend
- Next.js 15+
- TypeScript
- Tailwind CSS
- shadcn/ui components
- TradingView Lightweight Charts
- React Hook Form + Zod validation

### Backend
- FastAPI (Python 3.11+)
- PostgreSQL
- Redis
- SQLAlchemy ORM
- Alembic migrations
- Celery/RQ task workers

### AI & Data
- Gemini API (structured JSON output)
- Future: OpenAI, Groq, Claude, Ollama

### Trading Integrations
- MetaApi REST gateway for MT4/MT5 broker accounts
- Internal paper trading engine
- Optional Deriv credentials retained for users who actually trade on Deriv
- Future: OANDA, cTrader

### Infrastructure
- Docker & Docker Compose
- Caddy reverse proxy (auto HTTPS)
- Linux VPS (Ubuntu 20.04+)

## Quick Start (Local Development)

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Node.js 18+
- Git

### Setup

```bash
# Clone and navigate
git clone <repo-url>
cd arotrade-ai

# Copy environment template
cp .env.example .env

# Update .env with your API keys:
# - GEMINI_API_KEY
# - JWT_SECRET
# - ENCRYPTION_KEY
# - POSTGRES_PASSWORD

# Build and run services
docker compose build
docker compose up -d

# Apply database migrations
docker compose exec api alembic upgrade head

# Create admin user
docker compose exec api python scripts/create_admin.py

# Access
# Frontend: http://localhost:3000
# API: http://localhost:8000
# Admin: http://localhost:3000/admin
```

## Project Structure

```
arotrade-ai/
├── apps/
│   ├── web/                    # Next.js frontend
│   │   ├── app/               # App router (layout, pages)
│   │   ├── components/        # React components
│   │   ├── lib/               # Utilities
│   │   └── public/            # Static assets
│   └── api/                    # FastAPI backend
│       ├── app/               # Main app (routes, auth, services)
│       ├── models/            # SQLAlchemy models
│       ├── schemas/           # Pydantic schemas
│       ├── migrations/        # Alembic migrations
│       └── workers/           # Celery/RQ tasks
├── services/
│   ├── ai-engine/             # Gemini AI integration
│   ├── risk-engine/           # Trade validation & risk checks
│   ├── execution-engine/      # Broker execution adapters
│   └── backtest-engine/       # Backtesting logic
├── packages/
│   ├── shared-types/          # TypeScript types
│   └── trading-core/          # Shared trading logic
├── infra/
│   ├── docker/                # Dockerfile configs
│   ├── nginx/                 # Caddy config
│   └── scripts/               # Deployment scripts
├── docs/
│   ├── API.md                 # API documentation
│   └── DEPLOYMENT.md          # Deployment guide
├── docker-compose.yml         # Service orchestration
├── .env.example               # Environment template
├── .gitignore
└── README.md
```

## Environment Variables

See `.env.example` for the complete list. Key variables:

```env
# App
APP_NAME=AroTrade AI
APP_ENV=production
APP_URL=https://arotrader.arosoftlabs.com

# Database
POSTGRES_DB=arotrade
POSTGRES_USER=arotrade
POSTGRES_PASSWORD=<generate-secure>

# Redis
REDIS_URL=redis://redis:6379/0

# Security
JWT_SECRET=<generate-32+-character-secret>
ENCRYPTION_KEY=<generate-32+-character-secret>

# AI
GEMINI_API_KEY=<your-key>
GEMINI_MODEL=gemini-2.5-flash

# Trading
DERIV_APP_ID=<optional>
ENABLE_LIVE_TRADING=true
METAAPI_TOKEN=<your-metaapi-token>
METAAPI_REGION=london
MAX_LIVE_RISK_PERCENT=0.25
MAX_OPEN_TRADES_PER_SYMBOL=1
MAX_ACCOUNT_DRAWDOWN_PERCENT=25.0
MAX_ACCOUNT_EXPOSURE_PERCENT=80.0
MAX_BROKER_SPREAD_POINTS=0.0
BLOCK_SIGNAL_ON_NEWS_FETCH_FAILURE=true
NEXT_PUBLIC_MAX_LIVE_RISK_PERCENT=0.25

# Future Providers (commented)
# OPENAI_API_KEY=
# GROQ_API_KEY=
# ANTHROPIC_API_KEY=
```

## Core Concepts

### Signals
AI-generated trading signals with structured metadata:
- Entry/exit zones
- Stop loss & take profits
- Risk/reward ratios
- Confidence score
- Status workflow: pending → approved → executed/rejected

### Risk Engine
Validates every trade:
- User accepted risk disclaimer
- Stop loss present
- Risk per trade ≤ max
- Daily/weekly loss limits
- Account drawdown checks
- Per-symbol position caps
- Broker spread checks
- Duplicate signal-intent checks
- News blackout checks for signal trades
- Broker margin and account exposure checks

### Demo Trading
Paper trading engine for strategy testing:
- Simulated execution
- Real-time P&L tracking
- Full audit log
- Risk checks apply equally

### Strategy Builder
Create trading strategies via:
- Trend indicators (EMA, SMA, Supertrend)
- Momentum (RSI, MACD, Stochastic)
- Volume (VWAP, OBV)
- Smart Money Concepts (BOD, CoC, FVG, etc.)
- Risk parameters

### Backtesting
Test strategies against historical data:
- Win/loss rates
- Profit factor & max drawdown
- Equity curves
- Strategy health scoring

## Deployment

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for production deployment guide.

Quick deploy to VPS:
```bash
# Phase 1: Server prep
ssh root@95.111.234.34
# Run server setup script

# Phase 2-4: Build and run
cd /opt/arotrade-ai
docker compose up -d
```

## API Routes

### Authentication
- `POST /api/auth/register` – User registration
- `POST /api/auth/login` – Login
- `POST /api/auth/refresh` – Refresh JWT
- `POST /api/auth/logout` – Logout

### AI Analysis
- `POST /api/ai/analyze` – Analyze chart screenshot
- `GET /api/ai/health` – AI service health

### Signals
- `GET /api/signals` – List signals
- `POST /api/signals` – Create signal
- `GET /api/signals/{id}` – Get signal details
- `PUT /api/signals/{id}/approve` – Approve signal

### Strategies
- `GET /api/strategies` – List strategies
- `POST /api/strategies` – Create strategy
- `DELETE /api/strategies/{id}` – Delete strategy

### Backtesting
- `POST /api/backtest` – Run backtest
- `GET /api/backtest/{id}` – Get results

### Trading
- `POST /api/orders/preview` – Preview a MetaApi manual market order
- `POST /api/orders/execute` – Execute a MetaApi manual market order
- `POST /api/trades/execute` – Deprecated; use `/api/orders/execute`
- `GET /api/trades` – List trades
- `GET /api/journal` – Trading journal

### Admin
- `GET /api/admin/dashboard` – Dashboard stats
- `GET /api/admin/audit-logs` – Audit logs
- `GET /api/admin/users` – Manage users

## Security

- JWT-based authentication
- bcrypt password hashing
- Encrypted API key storage
- SQL injection protection
- CORS lockdown
- Rate limiting
- Admin-only access control
- Full audit logging
- No secrets in frontend/git

## Roadmap

**Phase 2** (Post-MVP):
- OpenAI integration
- Groq integration
- Claude integration
- OANDA integration
- cTrader integration

**Phase 3** (Long-term):
- ML-based strategy optimization
- Multi-account management
- Telegram/Discord notifications
- Advanced analytics
- Strategy marketplace
- Community features

## Support

For issues, feature requests, or documentation:
- GitHub Issues: [link]
- Email: support@arosoftlabs.com

## License

MIT License - See LICENSE file

## Disclaimer

**Trading Risk Warning:**
- No guaranteed profits or win rates
- Past performance does not guarantee future results
- Test all strategies on demo first
- Use strict risk management
- Only risk what you can afford to lose
- Always have stop losses
- Check broker regulations in your country

---

Built by **AROSOFT Innovations**
