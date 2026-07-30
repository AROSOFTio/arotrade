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

void DrawTextPanel(string name, string label)
{
   if(label == "") return;
   string obj = "AroPilot_" + name;
   if(ObjectFind(0, obj) < 0)
      ObjectCreate(0, obj, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, obj, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, obj, OBJPROP_XDISTANCE, 12);
   ObjectSetInteger(0, obj, OBJPROP_YDISTANCE, 28);
   ObjectSetInteger(0, obj, OBJPROP_COLOR, clrBlack);
   ObjectSetInteger(0, obj, OBJPROP_FONTSIZE, 9);
   ObjectSetString(0, obj, OBJPROP_FONT, "Arial");
   ObjectSetString(0, obj, OBJPROP_TEXT, label);
}

void DrawArrow(string name, datetime when, double price, bool buy)
{
   if(price <= 0) return;
   string obj = "AroPilot_" + name;
   if(ObjectFind(0, obj) < 0)
      ObjectCreate(0, obj, buy ? OBJ_ARROW_BUY : OBJ_ARROW_SELL, 0, when, price);
   ObjectSetInteger(0, obj, OBJPROP_TIME, 0, when);
   ObjectSetDouble(0, obj, OBJPROP_PRICE, 0, price);
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
   ObjectSetInteger(0, obj, OBJPROP_TIME, 0, left);
   ObjectSetDouble(0, obj, OBJPROP_PRICE, 0, top);
   ObjectSetInteger(0, obj, OBJPROP_TIME, 1, right);
   ObjectSetDouble(0, obj, OBJPROP_PRICE, 1, bottom);
   ObjectSetInteger(0, obj, OBJPROP_COLOR, zoneColor);
   ObjectSetInteger(0, obj, OBJPROP_BACK, true);
   ObjectSetInteger(0, obj, OBJPROP_FILL, true);
}

void DrawTrendObject(string name, datetime t1, double p1, datetime t2, double p2, color lineColor, bool ray=false)
{
   if(t1 <= 0 || t2 <= 0 || p1 <= 0 || p2 <= 0) return;
   string obj = "AroPilot_" + name;
   if(ObjectFind(0, obj) < 0)
      ObjectCreate(0, obj, OBJ_TREND, 0, t1, p1, t2, p2);
   ObjectSetInteger(0, obj, OBJPROP_TIME, 0, t1);
   ObjectSetDouble(0, obj, OBJPROP_PRICE, 0, p1);
   ObjectSetInteger(0, obj, OBJPROP_TIME, 1, t2);
   ObjectSetDouble(0, obj, OBJPROP_PRICE, 1, p2);
   ObjectSetInteger(0, obj, OBJPROP_COLOR, lineColor);
   ObjectSetInteger(0, obj, OBJPROP_STYLE, STYLE_SOLID);
   ObjectSetInteger(0, obj, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, obj, OBJPROP_RAY_RIGHT, ray);
}

color DrawingColor(string type)
{
   if(type == "support_zone" || type == "demand_zone" || type == "swing_low") return clrPaleGreen;
   if(type == "resistance_zone" || type == "supply_zone" || type == "swing_high") return clrMistyRose;
   if(type == "order_block") return clrLavender;
   if(type == "fair_value_gap") return clrLightYellow;
   if(type == "liquidity_zone") return clrLightCyan;
   if(type == "trend_line" || type == "ray") return clrDodgerBlue;
   if(type == "stop_loss") return clrTomato;
   if(type == "take_profit") return clrLimeGreen;
   return clrAliceBlue;
}

string SafeDrawingName(string fallback, string id)
{
   string name = id != "" ? id : fallback;
   StringReplace(name, ":", "_");
   StringReplace(name, "-", "_");
   StringReplace(name, " ", "_");
   StringReplace(name, ".", "_");
   return name;
}

double FirstPrice(string objectJson)
{
   double price = JsonNumberValue(objectJson, "target_price", 0.0);
   if(price <= 0) price = JsonNumberValue(objectJson, "price_start", 0.0);
   if(price <= 0) price = JsonNumberValue(objectJson, "entry_low", 0.0);
   if(price <= 0) price = JsonNumberValue(objectJson, "entry_high", 0.0);
   if(price <= 0) price = JsonNumberValue(objectJson, "price_low", 0.0);
   if(price <= 0) price = JsonNumberValue(objectJson, "price_high", 0.0);
   return price;
}

void DrawChartObjectJson(string objectJson, int index)
{
   string type = JsonStringValue(objectJson, "type", "");
   if(type == "") return;
   string id = SafeDrawingName(type + "_" + IntegerToString(index), JsonStringValue(objectJson, "id", ""));
   string label = JsonStringValue(objectJson, "label", type);
   color colorValue = DrawingColor(type);

   if(type == "text_label")
   {
      DrawTextPanel(id, label);
      return;
   }

   if(type == "horizontal_line" || type == "stop_loss" || type == "take_profit")
   {
      DrawHorizontalLevel(id, FirstPrice(objectJson), colorValue, label);
      return;
   }

   if(type == "entry_zone" || type == "support_zone" || type == "resistance_zone" ||
      type == "supply_zone" || type == "demand_zone" || type == "order_block" ||
      type == "fair_value_gap" || type == "liquidity_zone" || type == "rectangle" ||
      type == "risk_reward_box")
   {
      double high = JsonNumberValue(objectJson, "price_high", 0.0);
      double low = JsonNumberValue(objectJson, "price_low", 0.0);
      if(high <= 0) high = JsonNumberValue(objectJson, "entry_high", 0.0);
      if(low <= 0) low = JsonNumberValue(objectJson, "entry_low", 0.0);
      if(high <= 0) high = JsonNumberValue(objectJson, "price_start", 0.0);
      if(low <= 0) low = JsonNumberValue(objectJson, "price_end", 0.0);
      DrawZone(id, high, low, colorValue);
      return;
   }

   if(type == "trend_line" || type == "ray")
   {
      datetime t1 = IsoToTime(JsonStringValue(objectJson, "time_start", ""));
      datetime t2 = IsoToTime(JsonStringValue(objectJson, "time_end", ""));
      DrawTrendObject(
         id,
         t1,
         JsonNumberValue(objectJson, "price_start", 0.0),
         t2,
         JsonNumberValue(objectJson, "price_end", 0.0),
         colorValue,
         type == "ray"
      );
      return;
   }

   if(type == "signal_marker" || type == "swing_high" || type == "swing_low")
   {
      bool buy = type == "swing_low" || JsonStringValue(objectJson, "state", "") == "buy";
      DrawArrow(id, TimeCurrent(), FirstPrice(objectJson), buy);
   }
}

void DrawChartObjectsFromJson(string json)
{
   string pattern = "\"chart_objects\":[";
   int pos = StringFind(json, pattern);
   if(pos < 0) return;
   pos += StringLen(pattern);
   int depth = 0;
   int objectStart = -1;
   int count = 0;
   for(int i = pos; i < StringLen(json); i++)
   {
      ushort ch = StringGetCharacter(json, i);
      if(ch == '{')
      {
         if(depth == 0) objectStart = i;
         depth++;
      }
      else if(ch == '}')
      {
         depth--;
         if(depth == 0 && objectStart >= 0)
         {
            DrawChartObjectJson(StringSubstr(json, objectStart, i - objectStart + 1), count);
            count++;
            objectStart = -1;
            if(count >= 80) return;
         }
      }
      else if(ch == ']' && depth == 0)
      {
         return;
      }
   }
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
   DrawChartObjectsFromJson(json);
}

#endif
