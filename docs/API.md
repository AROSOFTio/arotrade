# AroTrade AI - API Documentation

**Base URL:** `https://arotrader.arosoftlabs.com/api`

**Authentication:** Bearer JWT token in `Authorization` header

```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" https://arotrader.arosoftlabs.com/api/health
```

---

## Authentication Endpoints

### Register User

**POST** `/auth/register`

Create a new user account.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "full_name": "John Trader"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Status Codes:**
- `200` - Success
- `400` - Invalid input or email already registered
- `422` - Validation error

---

### Login User

**POST** `/auth/login`

Authenticate user and receive tokens.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```

**Response:** Same as register

**Status Codes:**
- `200` - Success
- `401` - Invalid credentials
- `403` - Account inactive

---

### Refresh Token

**POST** `/auth/refresh`

Get new access token using refresh token.

**Request:**
```json
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Response:** New access token

---

### Get Current User

**GET** `/auth/me`

Get current authenticated user info.

**Response:**
```json
{
  "id": 1,
  "email": "user@example.com",
  "full_name": "John Trader",
  "role": "trader",
  "trading_mode": "demo",
  "enable_live_trading": false,
  "is_active": true,
  "created_at": "2024-01-01T00:00:00"
}
```

---

## Health Endpoints

### API Health

**GET** `/health`

Check API service status.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2024-01-01T12:00:00"
}
```

---

### AI Service Health

**GET** `/ai/health`

Check Gemini AI integration status.

**Response:**
```json
{
  "status": "operational",
  "provider": "Gemini",
  "model": "gemini-2.5-flash",
  "is_available": true,
  "timestamp": "2024-01-01T12:00:00"
}
```

---

### Execution Engine Health

**GET** `/execution/health`

Check trading execution status.

**Response:**
```json
{
  "status": "operational",
  "demo_trading": true,
  "live_trading": false,
  "deriv_available": true,
  "paper_engine": true
}
```

---

## AI Analysis Endpoints

### Analyze Chart

**POST** `/ai/analyze`

Get Gemini AI analysis of a trading chart.

**Request:**
```json
{
  "symbol": "EURUSD",
  "timeframe": "M15",
  "image_url": "https://...",
  "prompt": "Analyze this chart for trading opportunities"
}
```

**Response:**
```json
{
  "id": 1,
  "symbol": "EURUSD",
  "timeframe": "M15",
  "bias": "bullish",
  "signal": "buy",
  "confidence": 68,
  "entry_min": 1.0845,
  "entry_max": 1.0850,
  "stop_loss": 1.0835,
  "take_profit_1": 1.0860,
  "take_profit_2": 1.0870,
  "take_profit_3": 1.0885,
  "risk_reward": 2.3,
  "reasoning": [
    "Market structure is bullish",
    "Price reacted from demand zone",
    "RSI momentum supports continuation"
  ],
  "invalidation": "Signal becomes invalid below 1.0835",
  "news_warning": "Check high-impact USD news before execution",
  "risk_warning": "Use maximum 1% account risk",
  "created_at": "2024-01-01T12:00:00"
}
```

**Status Codes:**
- `200` - Success
- `503` - AI service not configured

---

### Analyze Image Upload

**POST** `/ai/analyze-image` (multipart/form-data)

Upload chart image for analysis.

**Form Data:**
- `file` - Image file (PNG, JPG)
- `symbol` - Trading symbol
- `timeframe` - Timeframe (M1, M5, M15, H1, D1, etc.)
- `prompt` - Optional analysis instructions

**Response:** Same as `/ai/analyze`

---

### List Analyses

**GET** `/ai/analyses?skip=0&limit=50`

Get user's AI analyses history.

**Response:**
```json
[
  {
    "id": 1,
    "symbol": "EURUSD",
    "timeframe": "M15",
    ...
  }
]
```

---

### Get Analysis

**GET** `/ai/analyses/{analysis_id}`

Get specific analysis details.

---

## Signal Endpoints

### Create Signal

**POST** `/signals`

Create a trading signal from AI analysis.

**Request:**
```json
{
  "symbol": "EURUSD",
  "timeframe": "M15",
  "signal_type": "buy",
  "entry_min": 1.0845,
  "entry_max": 1.0850,
  "stop_loss": 1.0835,
  "take_profit_1": 1.0860,
  "take_profit_2": 1.0870,
  "take_profit_3": 1.0885,
  "risk_reward": 2.3,
  "confidence": 68,
  "notes": "Following AI recommendation"
}
```

**Response:**
```json
{
  "id": 1,
  "symbol": "EURUSD",
  "timeframe": "M15",
  "signal_type": "buy",
  "entry_min": 1.0845,
  "entry_max": 1.0850,
  "stop_loss": 1.0835,
  "take_profit_1": 1.0860,
  "take_profit_2": 1.0870,
  "take_profit_3": 1.0885,
  "risk_reward": 2.3,
  "confidence": 68,
  "status": "pending",
  "created_at": "2024-01-01T12:00:00"
}
```

---

### List Signals

**GET** `/signals?skip=0&limit=50`

Get user's signals with pagination.

---

### Get Signal

**GET** `/signals/{signal_id}`

Get specific signal details.

---

### Approve Signal

**PUT** `/signals/{signal_id}/approve`

Approve a pending signal for execution.

---

### Reject Signal

**PUT** `/signals/{signal_id}/reject`

Reject a pending signal.

---

## Trading Endpoints

### Execute Trade

**POST** `/trades/execute`

Execute a demo or live trade.

**Request:**
```json
{
  "symbol": "EURUSD",
  "trade_type": "buy",
  "entry_price": 1.0847,
  "stop_loss": 1.0835,
  "take_profit": 1.0860,
  "volume": 0.1,
  "notes": "Signal execution"
}
```

**Response:**
```json
{
  "id": 1,
  "symbol": "EURUSD",
  "trade_type": "buy",
  "entry_price": 1.0847,
  "entry_time": "2024-01-01T12:00:00",
  "exit_price": null,
  "exit_time": null,
  "stop_loss": 1.0835,
  "take_profit": 1.0860,
  "volume": 0.1,
  "profit_loss": null,
  "status": "open",
  "mode": "demo",
  "created_at": "2024-01-01T12:00:00"
}
```

**Validations:**
- Stop loss required
- Risk per trade must not exceed user limit
- Live trading must be enabled (both user and global)
- Daily loss limit not exceeded
- Max open trades not exceeded

---

### List Trades

**GET** `/trades?skip=0&limit=50`

Get user's trades.

---

### Get Trade

**GET** `/trades/{trade_id}`

Get specific trade details.

---

### Close Trade

**POST** `/trades/{trade_id}/close`

Close an open trade.

**Request:**
```json
{
  "exit_price": 1.0860
}
```

**Response:** Updated trade with P&L calculated

---

## Strategy Endpoints

### Create Strategy

**POST** `/strategies`

Create a custom trading strategy.

**Request:**
```json
{
  "name": "My EMA Crossover",
  "description": "Simple EMA 20/50 crossover strategy",
  "trend_indicators": ["EMA", "SMA"],
  "momentum_indicators": ["RSI"],
  "volume_indicators": [],
  "smart_money": ["Break of Structure"],
  "risk_per_trade": 1.0,
  "max_daily_loss": 3.0,
  "max_open_trades": 3,
  "allow_martingale": false
}
```

**Response:**
```json
{
  "id": 1,
  "name": "My EMA Crossover",
  "description": "Simple EMA 20/50 crossover strategy",
  "risk_per_trade": 1.0,
  "max_open_trades": 3,
  "health_score": 0,
  "is_active": true,
  "created_at": "2024-01-01T12:00:00"
}
```

---

### List Strategies

**GET** `/strategies?skip=0&limit=50`

Get user's strategies.

---

### Get Strategy

**GET** `/strategies/{strategy_id}`

Get specific strategy details.

---

### Delete Strategy

**DELETE** `/strategies/{strategy_id}`

Remove a strategy.

---

## Backtesting Endpoints

### Run Backtest

**POST** `/backtest`

Test a strategy against historical data.

**Request:**
```json
{
  "strategy_id": 1,
  "symbol": "EURUSD",
  "timeframe": "H1",
  "start_date": "2023-01-01T00:00:00",
  "end_date": "2024-01-01T00:00:00",
  "initial_balance": 10000
}
```

**Response:**
```json
{
  "id": 1,
  "symbol": "EURUSD",
  "timeframe": "H1",
  "total_trades": 150,
  "winning_trades": 97,
  "losing_trades": 53,
  "win_rate": 64.67,
  "total_profit": 2500.00,
  "profit_factor": 2.45,
  "max_drawdown": 12.5,
  "average_win": 50.00,
  "average_loss": -20.00,
  "risk_reward_ratio": 2.5,
  "is_safe": true,
  "created_at": "2024-01-01T12:00:00"
}
```

**Safety Checks:**
- Strategy marked unsafe if:
  - Total trades < 100
  - Profit factor < 1.2
  - Max drawdown > 25%
  - Risk per trade > 3%

---

### Get Backtest

**GET** `/backtest/{backtest_id}`

Get backtest results and equity curve.

---

## Journal Endpoints

### Create Journal Entry

**POST** `/journal`

Log a completed trade in journal.

**Request:**
```json
{
  "symbol": "EURUSD",
  "trade_date": "2024-01-01T12:00:00",
  "strategy": "EMA Crossover",
  "entry_price": 1.0847,
  "exit_price": 1.0860,
  "result": "win",
  "profit_loss": 50.00,
  "emotion_before": "confident",
  "emotion_after": "satisfied",
  "mistake_category": null,
  "notes": "Followed rules perfectly",
  "lesson_learned": "Patience in entries pays off"
}
```

---

### List Journal Entries

**GET** `/journal?skip=0&limit=50`

Get user's journal entries.

---

### Get Journal Entry

**GET** `/journal/{entry_id}`

Get specific journal entry.

---

### Journal Analytics

**GET** `/journal/analytics/summary`

Get trading performance summary.

**Response:**
```json
{
  "total_trades": 150,
  "winning_trades": 97,
  "losing_trades": 53,
  "win_rate": 64.67,
  "best_performing_symbol": "EURUSD",
  "worst_performing_symbol": "GBPUSD",
  "common_mistakes": [
    "Revenge trading",
    "Ignoring news events"
  ]
}
```

---

## Admin Endpoints

All admin endpoints require `role: admin`.

### Dashboard Stats

**GET** `/admin/dashboard`

Get platform dashboard statistics.

**Response:**
```json
{
  "total_users": 150,
  "active_users": 120,
  "total_signals": 1200,
  "demo_trades": 3500,
  "live_trades": 450,
  "failed_trades": 50,
  "risk_violations": 25,
  "api_errors": 5
}
```

---

### List Users

**GET** `/admin/users?skip=0&limit=100`

Get all platform users.

---

### Disable User

**POST** `/admin/users/{user_id}/disable`

Deactivate user account.

---

### Enable Live Trading

**POST** `/admin/users/{user_id}/enable-live-trading`

Grant live trading permission to user.

---

### List Audit Logs

**GET** `/admin/audit-logs?skip=0&limit=100`

Get system audit logs.

---

### List All Signals

**GET** `/admin/signals?skip=0&limit=100`

Get all platform signals.

---

### List All Trades

**GET** `/admin/trades?skip=0&limit=100`

Get all platform trades.

---

### List Risk Violations

**GET** `/admin/risk-violations?skip=0&limit=100`

Get risk violations log.

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message",
  "status_code": 400
}
```

**Common Status Codes:**

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 422 | Validation Error |
| 503 | Service Unavailable |

---

## Rate Limiting

**Limit:** 100 requests per minute per IP

**Headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 99
X-RateLimit-Reset: 1704110460
```

---

## Pagination

List endpoints support pagination:

```bash
GET /api/signals?skip=0&limit=50
```

**Parameters:**
- `skip` - Number of records to skip (default: 0)
- `limit` - Number of records to return (default: 50, max: 100)

---

## CORS

**Allowed Origins:** Configured in environment variables

```env
ALLOWED_ORIGINS=https://arotrader.arosoftlabs.com,http://localhost:3000
```

---

## Webhooks (Future)

Planned webhook integrations:

- `trade.created` - New trade executed
- `signal.approved` - Signal approved by user
- `backtest.completed` - Backtest finished

---

## SDK Clients

Currently supported:

- JavaScript/TypeScript (via Axios)
- Python (via Requests)

---

## Changelog

### v1.0.0 (2024-01-01)
- Initial API release
- Core trading functionality
- AI analysis integration
- Admin features

---

**Last Updated:** January 2024  
**API Version:** 1.0.0
