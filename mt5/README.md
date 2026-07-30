# AroPilot MT5 Connector

Files in this package:
- AroPilotEA.mq5
- connector.mqh
- network.mqh
- drawings.mqh
- panel.mqh
- signals.mqh
- risk.mqh
- config.mqh
- utils.mqh
- indicators.mqh

Install all files into the same MT5 Experts folder, for example:
`MQL5/Experts/AroPilot/`

In MetaTrader 5, open `Tools > Options > Expert Advisors` and allow WebRequest for:
`https://arotrader.arosoftlabs.com`

Attach `AroPilotEA` to the chart, then paste the BridgeUrl, AccountId and ApiKey shown in AroPilot.

The connector streams account telemetry, tick/quote data, candles, positions, orders, recent deal history, and local indicator readings. It polls the AroPilot bridge for analysis, signals, risk settings, notifications, and chart objects. Auto trading requires both the EA input and backend command payload to explicitly allow execution, and local risk gates are checked before any order request.