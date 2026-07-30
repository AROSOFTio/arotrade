#ifndef AROPILOT_DRAWINGS_MQH
#define AROPILOT_DRAWINGS_MQH

#include "utils.mqh"

double ChartPriceSpan()
{
   double minPrice = 0.0;
   double maxPrice = 0.0;
   if(ChartGetDouble(0, CHART_PRICE_MIN, 0, minPrice) && ChartGetDouble(0, CHART_PRICE_MAX, 0, maxPrice) && maxPrice > minPrice)
      return maxPrice - minPrice;
   double high = iHigh(_Symbol, _Period, 0);
   double low = iLow(_Symbol, _Period, 0);
   for(int i = 1; i < MathMin(Bars(_Symbol, _Period), 80); i++)
   {
      high = MathMax(high, iHigh(_Symbol, _Period, i));
      low = MathMin(low, iLow(_Symbol, _Period, i));
   }
   return MathMax(high - low, _Point * 100.0);
}

datetime ChartTextAnchorTime(int shift=8)
{
   int bars = Bars(_Symbol, _Period);
   if(bars <= 0) return TimeCurrent();
   return iTime(_Symbol, _Period, MathMin(MathMax(0, shift), bars - 1));
}

string CleanJsonText(string value)
{
   string text = value;
   StringReplace(text, "\\r", "");
   StringReplace(text, "\\n", "\n");
   StringReplace(text, "\\\"", "\"");
   StringReplace(text, "\\\\", "\\");
   return text;
}

string TextLineAt(string text, int lineIndex)
{
   int start = 0;
   int line = 0;
   for(int i = 0; i <= StringLen(text); i++)
   {
      bool endOfText = i >= StringLen(text);
      ushort ch = endOfText ? 0 : StringGetCharacter(text, i);
      if(endOfText || ch == 10)
      {
         if(line == lineIndex) return StringSubstr(text, start, i - start);
         start = i + 1;
         line++;
      }
   }
   return "";
}

void DrawInlineText(string name, string label, double price, color textColor, int row=0, int shift=8)
{
   if(label == "") return;
   if(price <= 0) price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double lineStep = MathMax(ChartPriceSpan() / 45.0, _Point * 10.0);
   double y = price - (row * lineStep);
   datetime when = ChartTextAnchorTime(shift);
   string obj = "AroPilot_" + name;
   if(ObjectFind(0, obj) < 0)
      ObjectCreate(0, obj, OBJ_TEXT, 0, when, y);
   ObjectSetInteger(0, obj, OBJPROP_TIME, 0, when);
   ObjectSetDouble(0, obj, OBJPROP_PRICE, 0, y);
   ObjectSetInteger(0, obj, OBJPROP_COLOR, textColor);
   ObjectSetInteger(0, obj, OBJPROP_FONTSIZE, 9);
   ObjectSetString(0, obj, OBJPROP_FONT, "Arial Bold");
   ObjectSetString(0, obj, OBJPROP_TEXT, label);
   ObjectSetInteger(0, obj, OBJPROP_BACK, false);
}

void DrawHorizontalLevel(string name, double price, color lineColor, string label="")
{
   if(price <= 0) return;
   string obj = "AroPilot_" + name;
   if(ObjectFind(0, obj) < 0)
      ObjectCreate(0, obj, OBJ_HLINE, 0, 0, price);
   ObjectSetDouble(0, obj, OBJPROP_PRICE, price);
   ObjectSetInteger(0, obj, OBJPROP_COLOR, lineColor);
   ObjectSetInteger(0, obj, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(0, obj, OBJPROP_WIDTH, 2);
   if(label != "") ObjectSetString(0, obj, OBJPROP_TEXT, label);
   if(label != "")
      DrawInlineText(name + "_tag", label + " @ " + DoubleToString(price, _Digits), price, lineColor, 0, 10);
}

void DrawTextPanel(string name, string label)
{
   if(label == "") return;
   string text = CleanJsonText(label);
   double anchorPrice = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(anchorPrice <= 0) anchorPrice = iClose(_Symbol, _Period, 0);
   for(int i = 0; i < 6; i++)
   {
      string line = TextLineAt(text, i);
      if(line == "") break;
      DrawInlineText(name + "_" + IntegerToString(i), line, anchorPrice, clrBlack, i, 14);
   }
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
   if(price <= 0) price = JsonNumberValue(objectJson, "price", 0.0);
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

   if(type == "arrow" || type == "signal_marker" || type == "swing_high" || type == "swing_low")
   {
      string direction = JsonStringValue(objectJson, "direction", JsonStringValue(objectJson, "state", ""));
      bool buy = type == "swing_low" || direction == "buy" || direction == "BUY";
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
   if(signal == "buy" || signal == "sell")
   {
      string upperSignal = signal;
      StringToUpper(upperSignal);
      DrawTextPanel("mentor_plan", "AroPilot AI: " + upperSignal + "\\nEntry: " + DoubleToString(entryMin, _Digits) + " - " + DoubleToString(entryMax, _Digits) + "\\nSL: " + DoubleToString(stopLoss, _Digits) + " TP1: " + DoubleToString(tp1, _Digits));
   }
   else
      DrawTextPanel("mentor_plan", "AroPilot AI: WAIT\\nNo clean entry yet. Watch support/resistance reaction.");
   DrawChartObjectsFromJson(json);
}

#endif
