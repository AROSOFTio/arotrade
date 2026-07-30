#property strict
#property version   "1.00"
#property description "AroPilot AI direct MT5 bridge. Streams market/account data, receives analysis, draws chart levels, and executes guarded commands when enabled."
#include "config.mqh"
#include "connector.mqh"
#include "panel.mqh"
#include "drawings.mqh"
#include "signals.mqh"
#include "risk.mqh"
input string BridgeUrl = AROPILOT_DEFAULT_BRIDGE_URL;
input string WebSocketUrl = "";
input string ApiKey = "";
input long AccountId = 0;
input int SendIntervalSeconds = 2;
input int CandleBars = 240;
input int MaxSymbolsToStream = 8;
input bool EnableAutoTrading = false;
input double MaxLotsPerTrade = 0.10;
input int MaxOpenTrades = 1;
input double MaxDailyLossPercent = 3.0;
bool g_connected = false;
datetime g_lastSend = 0;
datetime g_lastCandle = 0;
int g_failureCount = 0;
int OnInit()
{
   EventSetTimer(MathMax(1, SendIntervalSeconds));
   if(ApiKey == "" || AccountId <= 0)
   {
      PanelDrawStatus("missing ApiKey or AccountId");
      Print("AroPilot EA: set BridgeUrl, AccountId and ApiKey. Add https://arotrader.arosoftlabs.com to Tools > Options > Expert Advisors > Allow WebRequest.");
      return INIT_SUCCEEDED;
   }
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
   datetime currentCandle = iTime(_Symbol, _Period, 0);
   if(currentCandle != g_lastCandle)
   {
      g_lastCandle = currentCandle;
      SendSnapshot();
      return;
   }
   if(TimeCurrent() - g_lastSend >= SendIntervalSeconds) SendSnapshot();
}
void OnTimer()
{
   if(ApiKey == "" || AccountId <= 0) return;
   SendSnapshot();
}
void PollCommands()
{
   string response = "";
   string url = BridgeUrl + "/commands?account_id=" + IntegerToString(AccountId) + "&symbol=" + _Symbol + "&timeframe=" + TfToText(_Period);
   if(!HttpGet(url, ApiKey, response)) return;
   DrawAnalysisFromJson(response);
   string commandId = JsonStringValue(response, "command_id", "");
   ulong positionTicket = (ulong)JsonNumberValue(response, "position_ticket", 0.0);
   ulong orderTicket = 0;
   ulong dealTicket = 0;
   int retcode = 0;
   string message = "";
   bool executed = ExecuteCommandFromJson(response, EnableAutoTrading, MaxLotsPerTrade, MaxOpenTrades, MaxDailyLossPercent, positionTicket, orderTicket, dealTicket, retcode, message);
   if(commandId != "")
   {
      string ack = "{"
         + "\"account_id\":" + IntegerToString(AccountId) + ","
         + "\"command_id\":\"" + JsonEscape(commandId) + "\","
         + "\"success\":" + (executed ? "true" : "false") + ","
         + "\"order_ticket\":" + IntegerToString((long)orderTicket) + ","
         + "\"position_ticket\":" + IntegerToString((long)positionTicket) + ","
         + "\"deal_ticket\":" + IntegerToString((long)dealTicket) + ","
         + "\"retcode\":" + IntegerToString(retcode) + ","
         + "\"message\":\"" + JsonEscape(message) + "\""
         + "}";
      string ackResponse = "";
      HttpPostJson(BridgeUrl + "/command-result", ApiKey, ack, ackResponse);
   }
}
void SendSnapshot()
{
   g_lastSend = TimeCurrent();
   bool heartbeat = BridgePost(BridgeUrl, ApiKey, "/heartbeat", BuildHeartbeatJson(AccountId));
   bool quote = false;
   bool candleOk = false;
   int totalSymbols = SymbolsTotal(true);
   int streamLimit = MaxSymbolsToStream;
   if(streamLimit < 1) streamLimit = 1;
   int sent = 0;
   for(int i = 0; i < totalSymbols && sent < streamLimit; i++)
   {
      string streamSymbol = SymbolName(i, true);
      if(streamSymbol == "") continue;
      string quotePayload = BuildQuoteJson(AccountId, streamSymbol);
      if(quotePayload != "" && BridgePost(BridgeUrl, ApiKey, "/quote", quotePayload))
         quote = true;
      string candlePayload = BuildCandlesJson(AccountId, CandleBars, streamSymbol);
      if(candlePayload != "" && BridgePost(BridgeUrl, ApiKey, "/candles", candlePayload))
         candleOk = true;
      sent++;
   }
   if(!quote)
   {
      string quotePayload = BuildQuoteJson(AccountId, _Symbol);
      quote = quotePayload != "" && BridgePost(BridgeUrl, ApiKey, "/quote", quotePayload);
   }
   if(!candleOk)
   {
      string candlePayload = BuildCandlesJson(AccountId, CandleBars, _Symbol);
      candleOk = candlePayload != "" && BridgePost(BridgeUrl, ApiKey, "/candles", candlePayload);
   }
   g_connected = heartbeat && quote && candleOk;
   if(g_connected)
   {
      g_failureCount = 0;
      PanelDrawStatus("connected");
      PollCommands();
   }
   else
   {
      g_failureCount++;
      PanelDrawStatus("reconnecting " + IntegerToString(g_failureCount));
   }
}
