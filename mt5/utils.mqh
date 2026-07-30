#ifndef AROPILOT_UTILS_MQH
#define AROPILOT_UTILS_MQH

string JsonEscape(string value)
{
   StringReplace(value, "\\", "\\\\");
   StringReplace(value, "\"", "\\\"");
   StringReplace(value, "\r", "\\r");
   StringReplace(value, "\n", "\\n");
   return value;
}

string TimeToIso(datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ", dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);
}

string TfToText(ENUM_TIMEFRAMES tf)
{
   switch(tf)
   {
      case PERIOD_M1: return "M1";
      case PERIOD_M5: return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1: return "H1";
      case PERIOD_H4: return "H4";
      case PERIOD_D1: return "D1";
      case PERIOD_W1: return "W1";
      case PERIOD_MN1: return "MN1";
      default: return IntegerToString((int)tf);
   }
}

string JsonStringValue(string json, string key, string fallback="")
{
   string pattern = "\"" + key + "\":";
   int pos = StringFind(json, pattern);
   if(pos < 0) return fallback;
   pos += StringLen(pattern);
   while(pos < StringLen(json) && StringGetCharacter(json, pos) == ' ') pos++;
   if(pos >= StringLen(json) || StringGetCharacter(json, pos) != '"') return fallback;
   pos++;
   string out = "";
   for(int i = pos; i < StringLen(json); i++)
   {
      ushort ch = StringGetCharacter(json, i);
      if(ch == '"') break;
      out += ShortToString(ch);
   }
   return out;
}

double JsonNumberValue(string json, string key, double fallback=0.0)
{
   string pattern = "\"" + key + "\":";
   int pos = StringFind(json, pattern);
   if(pos < 0) return fallback;
   pos += StringLen(pattern);
   while(pos < StringLen(json) && StringGetCharacter(json, pos) == ' ') pos++;
   string raw = "";
   for(int i = pos; i < StringLen(json); i++)
   {
      ushort ch = StringGetCharacter(json, i);
      if((ch >= '0' && ch <= '9') || ch == '.' || ch == '-') raw += ShortToString(ch);
      else break;
   }
   if(raw == "" || raw == "-") return fallback;
   return StringToDouble(raw);
}

bool JsonBoolValue(string json, string key, bool fallback=false)
{
   string pattern = "\"" + key + "\":";
   int pos = StringFind(json, pattern);
   if(pos < 0) return fallback;
   pos += StringLen(pattern);
   string tail = StringSubstr(json, pos, 5);
   return StringFind(tail, "true") == 0;
}

#endif