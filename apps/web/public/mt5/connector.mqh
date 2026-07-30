#ifndef AROPILOT_CONNECTOR_MQH
#define AROPILOT_CONNECTOR_MQH

#include "network.mqh"
#include "utils.mqh"
#include "indicators.mqh"

string BuildPositionsJson()
{
   string json = "[";
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket)) continue;
      string posSymbol = PositionGetString(POSITION_SYMBOL);
      int digits = (int)SymbolInfoInteger(posSymbol, SYMBOL_DIGITS);
      if(StringLen(json) > 1) json += ",";
      json += "{"
         + "\"ticket\":" + IntegerToString((long)ticket) + ","
         + "\"symbol\":\"" + JsonEscape(posSymbol) + "\","
         + "\"type\":\"" + (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "buy" : "sell") + "\","
         + "\"volume\":" + DoubleToString(PositionGetDouble(POSITION_VOLUME), 2) + ","
         + "\"price_open\":" + DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN), digits) + ","
         + "\"stop_loss\":" + DoubleToString(PositionGetDouble(POSITION_SL), digits) + ","
         + "\"take_profit\":" + DoubleToString(PositionGetDouble(POSITION_TP), digits) + ","
         + "\"profit\":" + DoubleToString(PositionGetDouble(POSITION_PROFIT), 2)
         + "}";
   }
   return json + "]";
}

string BuildOrdersJson()
{
   string json = "[";
   int total = OrdersTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0) continue;
      if(StringLen(json) > 1) json += ",";
      json += "{"
         + "\"ticket\":" + IntegerToString((long)ticket) + ","
         + "\"symbol\":\"" + JsonEscape(OrderGetString(ORDER_SYMBOL)) + "\","
         + "\"type\":" + IntegerToString((int)OrderGetInteger(ORDER_TYPE)) + ","
         + "\"volume\":" + DoubleToString(OrderGetDouble(ORDER_VOLUME_CURRENT), 2) + ","
         + "\"price_open\":" + DoubleToString(OrderGetDouble(ORDER_PRICE_OPEN), _Digits)
         + "}";
   }
   return json + "]";
}

string BuildHistoryJson(int maxDeals=20)
{
   datetime to = TimeCurrent();
   datetime from = to - 86400 * 14;
   HistorySelect(from, to);
   int total = HistoryDealsTotal();
   int start = MathMax(0, total - maxDeals);
   string json = "[";
   for(int i = start; i < total; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0) continue;
      if(StringLen(json) > 1) json += ",";
      json += "{"
         + "\"ticket\":" + IntegerToString((long)ticket) + ","
         + "\"symbol\":\"" + JsonEscape(HistoryDealGetString(ticket, DEAL_SYMBOL)) + "\","
         + "\"profit\":" + DoubleToString(HistoryDealGetDouble(ticket, DEAL_PROFIT), 2) + ","
         + "\"time\":\"" + TimeToIso((datetime)HistoryDealGetInteger(ticket, DEAL_TIME)) + "\""
         + "}";
   }
   return json + "]";
}

string BuildSymbolsJson(int maxSymbols=30)
{
   string json = "[";
   int total = SymbolsTotal(true);
   int added = 0;
   for(int i = 0; i < total && added < maxSymbols; i++)
   {
      string symbol = SymbolName(i, true);
      if(symbol == "") continue;
      if(StringLen(json) > 1) json += ",";
      json += "{"
         + "\"symbol\":\"" + JsonEscape(symbol) + "\","
         + "\"broker_symbol\":\"" + JsonEscape(symbol) + "\","
         + "\"display_name\":\"" + JsonEscape(symbol) + "\""
         + "}";
      added++;
   }
   return json + "]";
}

string BuildHeartbeatJson(long accountId)
{
   string accountType = AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL ? "live" : "demo";
   return "{"
      + "\"account_id\":" + IntegerToString(accountId) + ","
      + "\"login\":\"" + IntegerToString((int)AccountInfoInteger(ACCOUNT_LOGIN)) + "\","
      + "\"server\":\"" + JsonEscape(AccountInfoString(ACCOUNT_SERVER)) + "\","
      + "\"account_type\":\"" + accountType + "\","
      + "\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ","
      + "\"equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) + ","
      + "\"margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN), 2) + ","
      + "\"free_margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2) + ","
      + "\"currency\":\"" + JsonEscape(AccountInfoString(ACCOUNT_CURRENCY)) + "\","
      + "\"symbol\":\"" + JsonEscape(_Symbol) + "\","
      + "\"timeframe\":\"" + TfToText(_Period) + "\","
      + "\"symbols\":" + BuildSymbolsJson(30) + ","
      + "\"positions\":" + BuildPositionsJson() + ","
      + "\"orders\":" + BuildOrdersJson() + ","
      + "\"history\":" + BuildHistoryJson(20) + ","
      + "\"indicators\":" + BuildIndicatorsJson()
      + "}";
}

string BuildQuoteJson(long accountId, string symbol="")
{
   string quoteSymbol = symbol == "" ? _Symbol : symbol;
   MqlTick tick;
   bool hasTick = SymbolInfoTick(quoteSymbol, tick);
   int digits = (int)SymbolInfoInteger(quoteSymbol, SYMBOL_DIGITS);
   double point = SymbolInfoDouble(quoteSymbol, SYMBOL_POINT);
   double bid = hasTick ? tick.bid : SymbolInfoDouble(quoteSymbol, SYMBOL_BID);
   double ask = hasTick ? tick.ask : SymbolInfoDouble(quoteSymbol, SYMBOL_ASK);
   if(bid <= 0) bid = SymbolInfoDouble(quoteSymbol, SYMBOL_BID);
   if(ask <= 0) ask = SymbolInfoDouble(quoteSymbol, SYMBOL_ASK);
   if(bid <= 0 || ask <= 0) return "";
   double last = hasTick && tick.last > 0 ? tick.last : bid;
   double volume = hasTick ? tick.volume_real : 0.0;
   datetime tickTime = hasTick && tick.time > 0 ? (datetime)tick.time : TimeCurrent();
   double spread = point > 0 ? (ask - bid) / point : 0;
   return "{"
      + "\"account_id\":" + IntegerToString(accountId) + ","
      + "\"symbol\":\"" + JsonEscape(quoteSymbol) + "\","
      + "\"timeframe\":\"" + TfToText(_Period) + "\","
      + "\"bid\":" + DoubleToString(bid, digits) + ","
      + "\"ask\":" + DoubleToString(ask, digits) + ","
      + "\"last\":" + DoubleToString(last, digits) + ","
      + "\"volume\":" + DoubleToString(volume, 2) + ","
      + "\"spread\":" + DoubleToString(spread, 1) + ","
      + "\"time\":\"" + TimeToIso(tickTime) + "\""
      + "}";
}

string BuildCandlesJson(long accountId, int bars, string symbol="")
{
   string candleSymbol = symbol == "" ? _Symbol : symbol;
   MqlRates rates[];
   int copied = CopyRates(candleSymbol, _Period, 0, bars, rates);
   if(copied <= 0) return "";
   ArraySetAsSeries(rates, false);
   int digits = (int)SymbolInfoInteger(candleSymbol, SYMBOL_DIGITS);
   string json = "{\"account_id\":" + IntegerToString(accountId) + ",\"symbol\":\"" + JsonEscape(candleSymbol) + "\",\"timeframe\":\"" + TfToText(_Period) + "\",\"candles\":[";
   for(int i = 0; i < copied; i++)
   {
      if(i > 0) json += ",";
      json += "{\"time\":\"" + TimeToIso(rates[i].time) + "\",\"open\":" + DoubleToString(rates[i].open, digits)
         + ",\"high\":" + DoubleToString(rates[i].high, digits)
         + ",\"low\":" + DoubleToString(rates[i].low, digits)
         + ",\"close\":" + DoubleToString(rates[i].close, digits)
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
