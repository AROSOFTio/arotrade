#ifndef AROPILOT_INDICATORS_MQH
#define AROPILOT_INDICATORS_MQH

#include "utils.mqh"

double IndicatorValue(int handle, int buffer=0)
{
   if(handle == INVALID_HANDLE) return 0.0;
   double values[];
   ArraySetAsSeries(values, true);
   if(CopyBuffer(handle, buffer, 0, 1, values) <= 0) return 0.0;
   return values[0];
}

string BuildIndicatorsJson()
{
   int ema20 = iMA(_Symbol, _Period, 20, 0, MODE_EMA, PRICE_CLOSE);
   int ema50 = iMA(_Symbol, _Period, 50, 0, MODE_EMA, PRICE_CLOSE);
   int sma200 = iMA(_Symbol, _Period, 200, 0, MODE_SMA, PRICE_CLOSE);
   int rsi14 = iRSI(_Symbol, _Period, 14, PRICE_CLOSE);
   int atr14 = iATR(_Symbol, _Period, 14);
   int macd = iMACD(_Symbol, _Period, 12, 26, 9, PRICE_CLOSE);
   int bands = iBands(_Symbol, _Period, 20, 0, 2.0, PRICE_CLOSE);

   string json = "{"
      + "\"ema20\":" + DoubleToString(IndicatorValue(ema20), _Digits) + ","
      + "\"ema50\":" + DoubleToString(IndicatorValue(ema50), _Digits) + ","
      + "\"sma200\":" + DoubleToString(IndicatorValue(sma200), _Digits) + ","
      + "\"rsi14\":" + DoubleToString(IndicatorValue(rsi14), 2) + ","
      + "\"atr14\":" + DoubleToString(IndicatorValue(atr14), _Digits) + ","
      + "\"macd_main\":" + DoubleToString(IndicatorValue(macd, 0), _Digits) + ","
      + "\"macd_signal\":" + DoubleToString(IndicatorValue(macd, 1), _Digits) + ","
      + "\"bollinger_upper\":" + DoubleToString(IndicatorValue(bands, 1), _Digits) + ","
      + "\"bollinger_middle\":" + DoubleToString(IndicatorValue(bands, 0), _Digits) + ","
      + "\"bollinger_lower\":" + DoubleToString(IndicatorValue(bands, 2), _Digits)
      + "}";

   IndicatorRelease(ema20);
   IndicatorRelease(ema50);
   IndicatorRelease(sma200);
   IndicatorRelease(rsi14);
   IndicatorRelease(atr14);
   IndicatorRelease(macd);
   IndicatorRelease(bands);
   return json;
}

#endif