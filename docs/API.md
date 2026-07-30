# AroPilot AI API

## Health

`GET /api/health`

`GET /api/ai/health`

## Direct MT5 Bridge

`POST /api/broker-accounts/direct-mt5`
Creates a direct MT5 bridge and returns the EA endpoint, account id, and bridge API key.

`POST /api/mt5/bridge/heartbeat`
Receives account telemetry, margin, equity, positions, orders, history, and indicators.

`POST /api/mt5/bridge/quote`
Receives tick/quote data.

`POST /api/mt5/bridge/candles`
Receives OHLC candles.

`GET /api/mt5/bridge/candles`
Returns stored bridge candles.

`GET /api/mt5/bridge/commands`
Returns analysis, signals, risk settings, notifications, and chart objects for the EA.

## AI

`GET /api/ai/providers`
Lists supported providers and current availability.

`POST /api/ai/analyze`
Runs market analysis from live MT5 data.

`POST /api/ai/compare`
Runs all enabled providers and returns consensus.

`POST /api/ai/analyses/{id}/chat`
Answers follow-up questions using the saved analysis context.

## Optional Broker Adapter

MetaApi-backed routes remain available only for users who explicitly choose hosted broker connectivity.