#ifndef AROPILOT_RISK_MQH
#define AROPILOT_RISK_MQH

bool AutoTradeAllowedByUser(bool inputEnabled)
{
   return inputEnabled && TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && MQLInfoInteger(MQL_TRADE_ALLOWED);
}

#endif