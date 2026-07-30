# AroPilot MT5 Connector

Copy all files in this folder into your MetaTrader 5 `MQL5/Experts/AroPilot/` directory:

- AroPilotEA.mq5
- connector.mqh
- network.mqh
- drawings.mqh
- panel.mqh
- signals.mqh
- risk.mqh
- config.mqh
- utils.mqh

In MetaTrader 5, open Tools > Options > Expert Advisors and add this allowed WebRequest URL:

https://arotrader.arosoftlabs.com

Attach `AroPilotEA` to the chart, then paste the BridgeUrl, AccountId and ApiKey shown in AroPilot.