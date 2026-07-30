#ifndef AROPILOT_CONNECTOR_MQH
#define AROPILOT_CONNECTOR_MQH

#include "network.mqh"
#include "utils.mqh"

string BuildHeartbeatJson(long accountId)
{
   return "{"
      + "\"account_id\":" + IntegerToString(accountId) + ","
      + "\"login\":\"" + IntegerToString((int)AccountInfoInteger(ACCOUNT_LOGIN)) + "\","
      + "\"server\":\"" + JsonEscape(AccountInfoString(ACCOUNT_SERVER)) + "\","
      + "\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ","
      + "\"equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) + ","
      + "\"margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN), 2) + ","
      + "\"currency\":\"" + JsonEscape(AccountInfoString(ACCOUNT_CURRENCY)) + "\","
      + "\"symbol\":\"" + JsonEscape(_Symbol) + "\","
      + "\"timeframe\":\"" + TfToText(_Period) + "\""
      + "}";
}

string BuildQuoteJson(long accountId)
{
   MqlTick tick;
   SymbolInfoTick(_Symbol, tick);
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double spread = point > 0 ? (tick.ask - tick.bid) / point : 0;
   return "{"
      + "\"account_id\":" + IntegerToString(accountId) + ","
      + "\"symbol\":\"" + JsonEscape(_Symbol) + "\","
      + "\"timeframe\":\"" + TfToText(_Period) + "\","
      + "\"bid\":" + DoubleToString(tick.bid, _Digits) + ","
      + "\"ask\":" + DoubleToString(tick.ask, _Digits) + ","
      + "\"spread\":" + DoubleToString(spread, 1) + ","
      + "\"time\":\"" + TimeToIso((datetime)tick.time) + "\""
      + "}";
}

string BuildCandlesJson(long accountId, int bars)
{
   MqlRates rates[];
   int copied = CopyRates(_Symbol, _Period, 0, bars, rates);
   if(copied <= 0) return "";
   ArraySetAsSeries(rates, false);
   string json = "{\"account_id\":" + IntegerToString(accountId) + ",\"symbol\":\"" + JsonEscape(_Symbol) + "\",\"timeframe\":\"" + TfToText(_Period) + "\",\"candles\":[";
   for(int i = 0; i < copied; i++)
   {
      if(i > 0) json += ",";
      json += "{\"time\":\"" + TimeToIso(rates[i].time) + "\",\"open\":" + DoubleToString(rates[i].open, _Digits)
         + ",\"high\":" + DoubleToString(rates[i].high, _Digits)
         + ",\"low\":" + DoubleToString(rates[i].low, _Digits)
         + ",\"close\":" + DoubleToString(rates[i].close, _Digits)
         + ",\"volume\":" + IntegerToString((int)rates[i].tick_volume) + "}";
   }
   json += "]}";
   return json;
}

bool BridgePost(string bridgeUrl, string apiKey, string path, string payload)
{
   string response = "";
   return HttpPostJson(bridgeUrl + path, apiKey, payload, response);
}

#endif