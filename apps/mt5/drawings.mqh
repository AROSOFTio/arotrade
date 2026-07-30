#ifndef AROPILOT_DRAWINGS_MQH
#define AROPILOT_DRAWINGS_MQH

#include "utils.mqh"

void DrawHorizontalLevel(string name, double price, color lineColor, string label="")
{
   if(price <= 0) return;
   string obj = "AroPilot_" + name;
   if(ObjectFind(0, obj) < 0)
      ObjectCreate(0, obj, OBJ_HLINE, 0, 0, price);
   ObjectSetDouble(0, obj, OBJPROP_PRICE, price);
   ObjectSetInteger(0, obj, OBJPROP_COLOR, lineColor);
   ObjectSetInteger(0, obj, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(0, obj, OBJPROP_WIDTH, 1);
   if(label != "") ObjectSetString(0, obj, OBJPROP_TEXT, label);
}

void DrawArrow(string name, datetime when, double price, bool buy)
{
   if(price <= 0) return;
   string obj = "AroPilot_" + name;
   if(ObjectFind(0, obj) < 0)
      ObjectCreate(0, obj, buy ? OBJ_ARROW_BUY : OBJ_ARROW_SELL, 0, when, price);
   ObjectSetInteger(0, obj, OBJPROP_COLOR, buy ? clrLimeGreen : clrTomato);
   ObjectSetInteger(0, obj, OBJPROP_WIDTH, 2);
}

void DrawZone(string name, double top, double bottom, color zoneColor)
{
   if(top <= 0 || bottom <= 0) return;
   if(bottom > top) { double tmp = top; top = bottom; bottom = tmp; }
   datetime left = iTime(_Symbol, _Period, MathMin(Bars(_Symbol, _Period) - 1, 80));
   datetime right = TimeCurrent() + PeriodSeconds(_Period) * 20;
   string obj = "AroPilot_" + name;
   if(ObjectFind(0, obj) < 0)
      ObjectCreate(0, obj, OBJ_RECTANGLE, 0, left, top, right, bottom);
   ObjectSetInteger(0, obj, OBJPROP_COLOR, zoneColor);
   ObjectSetInteger(0, obj, OBJPROP_BACK, true);
   ObjectSetInteger(0, obj, OBJPROP_FILL, true);
}

void DrawAnalysisFromJson(string json)
{
   double entryMin = JsonNumberValue(json, "entry_min", 0.0);
   double entryMax = JsonNumberValue(json, "entry_max", 0.0);
   double stopLoss = JsonNumberValue(json, "stop_loss", 0.0);
   double tp1 = JsonNumberValue(json, "take_profit_1", 0.0);
   double tp2 = JsonNumberValue(json, "take_profit_2", 0.0);
   double tp3 = JsonNumberValue(json, "take_profit_3", 0.0);
   string signal = JsonStringValue(json, "signal", "hold");

   DrawHorizontalLevel("entry_min", entryMin, clrDodgerBlue, "AroPilot entry min");
   DrawHorizontalLevel("entry_max", entryMax, clrDodgerBlue, "AroPilot entry max");
   DrawHorizontalLevel("stop_loss", stopLoss, clrTomato, "AroPilot stop loss");
   DrawHorizontalLevel("take_profit_1", tp1, clrLimeGreen, "AroPilot take profit 1");
   DrawHorizontalLevel("take_profit_2", tp2, clrSeaGreen, "AroPilot take profit 2");
   DrawHorizontalLevel("take_profit_3", tp3, clrDarkGreen, "AroPilot take profit 3");
   if(entryMin > 0 && entryMax > 0) DrawZone("entry_zone", entryMax, entryMin, clrAliceBlue);
   if(signal == "buy" || signal == "sell") DrawArrow(signal + "_signal", TimeCurrent(), entryMin > 0 ? entryMin : entryMax, signal == "buy");
}

#endif