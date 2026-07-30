#property strict
#property version   "0.1.0"
#property description "AroPilot AI direct MT5 bridge. Streams market data to AroPilot over HTTPS."

#include "config.mqh"
#include "connector.mqh"
#include "panel.mqh"
#include "drawings.mqh"
#include "signals.mqh"
#include "risk.mqh"

input string BridgeUrl = AROPILOT_DEFAULT_BRIDGE_URL;
input string ApiKey = "";
input long AccountId = 0;
input int SendIntervalSeconds = 10;
input int CandleBars = 240;
input bool EnableAutoTrading = false;

bool g_connected = false;
datetime g_lastSend = 0;

int OnInit()
{
   if(ApiKey == "" || AccountId <= 0)
   {
      PanelDrawStatus("missing ApiKey or AccountId");
      Print("AroPilot EA: set BridgeUrl, AccountId and ApiKey. Add https://arotrader.arosoftlabs.com to Tools > Options > Expert Advisors > Allow WebRequest.");
      return INIT_SUCCEEDED;
   }
   EventSetTimer(MathMax(5, SendIntervalSeconds));
   PanelDrawStatus("starting");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   ObjectDelete(0, "AroPilot_Status");
}

void OnTick()
{
   if(ApiKey == "" || AccountId <= 0) return;
   if(TimeCurrent() - g_lastSend >= SendIntervalSeconds)
      SendSnapshot();
}

void OnTimer()
{
   if(ApiKey == "" || AccountId <= 0) return;
   SendSnapshot();
}

void SendSnapshot()
{
   g_lastSend = TimeCurrent();
   bool heartbeat = BridgePost(BridgeUrl, ApiKey, "/heartbeat", BuildHeartbeatJson(AccountId));
   bool quote = BridgePost(BridgeUrl, ApiKey, "/quote", BuildQuoteJson(AccountId));
   string candles = BuildCandlesJson(AccountId, CandleBars);
   bool candleOk = candles != "" && BridgePost(BridgeUrl, ApiKey, "/candles", candles);
   g_connected = heartbeat && quote && candleOk;
   PanelDrawStatus(g_connected ? "connected" : "connection issue");

   string response = "";
   HttpGet(BridgeUrl + "/commands?account_id=" + IntegerToString(AccountId), ApiKey, response);

   if(EnableAutoTrading && AutoTradeAllowedByUser(EnableAutoTrading))
   {
      // Trade execution is intentionally not implemented in v0.1. The backend
      // returns no executable commands until the user explicitly enables it in web settings.
   }
}