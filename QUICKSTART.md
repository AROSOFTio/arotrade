# AroPilot AI Quickstart

1. Start the platform with Docker or open the deployed app.
2. Create an account and sign in.
3. Go to Broker Accounts.
4. Create a Direct MT5 bridge.
5. Download `AroPilotMT5Connector.zip`.
6. Copy every file into `MQL5/Experts/AroPilot/`.
7. In MT5, allow WebRequest for the AroPilot domain.
8. Compile and attach `AroPilotEA.mq5` to a chart.
9. Paste `BridgeUrl`, `AccountId`, and `ApiKey` from the dashboard.
10. Run AI Analysis from live MT5 candles and compare providers.

MetaApi is optional and should be used only when a user explicitly wants hosted broker connectivity.