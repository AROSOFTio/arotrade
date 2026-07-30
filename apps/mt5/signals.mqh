#ifndef AROPILOT_SIGNALS_MQH
#define AROPILOT_SIGNALS_MQH

#include <Trade/Trade.mqh>
#include "utils.mqh"
#include "risk.mqh"

struct AroPilotSignal
{
   string direction;
   double entry;
   double stopLoss;
   double takeProfit;
   double confidence;
   string notes;
};

bool ExecuteCommandFromJson(string json, bool autoTradingEnabled, double maxLots, int maxOpenTrades, double maxDailyLossPercent, ulong &orderTicket, ulong &dealTicket, int &retcode, string &message)
{
   orderTicket = 0;
   dealTicket = 0;
   retcode = 0;
   message = "No executable command";

   if(!JsonBoolValue(json, "trade_execution_enabled", false)) return false;
   if(!JsonBoolValue(json, "auto_trading_enabled", false)) return false;
   if(!AutoTradeAllowedByUser(autoTradingEnabled)) { message = "EA auto trading input is disabled"; return false; }

   string action = JsonStringValue(json, "action", "");
   string direction = JsonStringValue(json, "direction", "");
   double volume = JsonNumberValue(json, "volume", 0.0);
   double stopLoss = JsonNumberValue(json, "stop_loss", 0.0);
   double takeProfit = JsonNumberValue(json, "take_profit", 0.0);
   string symbol = JsonStringValue(json, "symbol", _Symbol);

   if(action != "open_trade") { message = "Unsupported command action"; return false; }
   if(direction != "buy" && direction != "sell") { message = "Invalid command direction"; return false; }
   if(!LocalRiskAllows(volume, maxLots, maxOpenTrades, maxDailyLossPercent)) { message = "Local EA risk gate blocked command"; return false; }

   CTrade trade;
   trade.SetExpertMagicNumber(20260730);
   trade.SetDeviationInPoints(20);
   bool ok = false;
   if(direction == "buy") ok = trade.Buy(volume, symbol, 0.0, stopLoss, takeProfit, "AroPilot AI");
   if(direction == "sell") ok = trade.Sell(volume, symbol, 0.0, stopLoss, takeProfit, "AroPilot AI");

   retcode = (int)trade.ResultRetcode();
   orderTicket = trade.ResultOrder();
   dealTicket = trade.ResultDeal();
   message = trade.ResultRetcodeDescription();
   if(!ok) Print("AroPilot trade command failed: ", retcode, " ", message);
   return ok;
}

#endif