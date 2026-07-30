#ifndef AROPILOT_PANEL_MQH
#define AROPILOT_PANEL_MQH

void PanelDrawStatus(string status)
{
   string name = "AroPilot_Status";
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 12);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 24);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 10);
      ObjectSetInteger(0, name, OBJPROP_COLOR, clrLimeGreen);
   }
   ObjectSetString(0, name, OBJPROP_TEXT, "AroPilot AI - " + status);
}

#endif