#ifndef AROPILOT_DRAWINGS_MQH
#define AROPILOT_DRAWINGS_MQH

void DrawHorizontalLevel(string name, double price, color lineColor)
{
   if(price <= 0) return;
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
   ObjectSetDouble(0, name, OBJPROP_PRICE, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, lineColor);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DASH);
}

void DrawArrow(string name, datetime when, double price, bool buy)
{
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, buy ? OBJ_ARROW_BUY : OBJ_ARROW_SELL, 0, when, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, buy ? clrLimeGreen : clrTomato);
}

#endif