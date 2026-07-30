#ifndef AROPILOT_RISK_MQH
#define AROPILOT_RISK_MQH

#include "utils.mqh"

bool AutoTradeAllowedByUser(bool inputEnabled)
{
   return inputEnabled && TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && MQLInfoInteger(MQL_TRADE_ALLOWED);
}

bool LocalRiskAllows(double volume, double maxLots, int maxOpenTrades, double maxDailyLossPercent)
{
   if(volume <= 0 || volume > maxLots)
   {
      Print("AroPilot risk blocked: invalid volume ", volume);
      return false;
   }
   if(PositionsTotal() >= maxOpenTrades)
   {
      Print("AroPilot risk blocked: max open trades reached");
      return false;
   }
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(balance > 0 && maxDailyLossPercent > 0)
   {
      double drawdownPct = MathMax(0.0, (balance - equity) / balance * 100.0);
      if(drawdownPct >= maxDailyLossPercent)
      {
         Print("AroPilot risk blocked: daily/equity loss limit reached ", drawdownPct, "%");
         return false;
      }
   }
   return true;
}

#endif