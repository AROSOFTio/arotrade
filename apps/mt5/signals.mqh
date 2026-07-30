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

ulong FindLatestAroPilotPosition(string symbol)
{
   ulong bestTicket = 0;
   datetime bestTime = 0;
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != symbol) continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != 20260730) continue;
      datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
      if(bestTicket == 0 || opened >= bestTime)
      {
         bestTicket = ticket;
         bestTime = opened;
      }
   }
   return bestTicket;
}

bool ExecuteCommandFromJson(string json, bool autoTradingEnabled, double maxLots, int maxOpenTrades, double maxDailyLossPercent, ulong &positionTicket, ulong &orderTicket, ulong &dealTicket, int &retcode, string &message)
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
   positionTicket = (ulong)JsonNumberValue(json, "position_ticket", 0.0);
   string symbol = JsonStringValue(json, "symbol", _Symbol);

   CTrade trade;
   trade.SetExpertMagicNumber(20260730);
   trade.SetDeviationInPoints(20);
   bool ok = false;

   if(action == "open_trade")
   {
      if(direction != "buy" && direction != "sell") { message = "Invalid command direction"; return false; }
      if(!LocalRiskAllows(volume, maxLots, maxOpenTrades, maxDailyLossPercent)) { message = "Local EA risk gate blocked command"; return false; }
      if(direction == "buy") ok = trade.Buy(volume, symbol, 0.0, stopLoss, takeProfit, "AroPilot AI");
      if(direction == "sell") ok = trade.Sell(volume, symbol, 0.0, stopLoss, takeProfit, "AroPilot AI");
      if(ok) positionTicket = FindLatestAroPilotPosition(symbol);
   }
   else if(action == "modify_position")
   {
      if(positionTicket <= 0) { message = "Missing position ticket"; return false; }
      ok = trade.PositionModify(positionTicket, stopLoss, takeProfit);
      orderTicket = positionTicket;
   }
   else if(action == "close_position")
   {
      if(positionTicket <= 0) { message = "Missing position ticket"; return false; }
      ok = trade.PositionClose(positionTicket);
      orderTicket = positionTicket;
   }
   else if(action == "partial_close")
   {
      if(positionTicket <= 0) { message = "Missing position ticket"; return false; }
      if(volume <= 0) { message = "Partial close volume is required"; return false; }
      ok = trade.PositionClosePartial(positionTicket, volume);
      orderTicket = positionTicket;
   }
   else
   {
      message = "Unsupported command action";
      return false;
   }

   retcode = (int)trade.ResultRetcode();
   if(orderTicket == 0) orderTicket = trade.ResultOrder();
   dealTicket = trade.ResultDeal();
   message = trade.ResultRetcodeDescription();
   if(!ok) Print("AroPilot trade command failed: ", retcode, " ", message);
   return ok;
}

#endif
