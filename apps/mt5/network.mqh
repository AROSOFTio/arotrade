#ifndef AROPILOT_NETWORK_MQH
#define AROPILOT_NETWORK_MQH

bool HttpPostJson(string url, string apiKey, string payload, string &response)
{
   char data[];
   char result[];
   string resultHeaders = "";
   string headers = "Content-Type: application/json\r\nX-AroPilot-Key: " + apiKey + "\r\n";
   // An explicit count excludes the terminating NUL. WebRequest sends the
   // complete array, so WHOLE_ARRAY would make an otherwise valid JSON body
   // fail with "Extra data".
   int bytes = StringToCharArray(payload, data, 0, StringLen(payload), CP_UTF8);
   if(bytes <= 0)
   {
      Print("AroPilot bridge could not encode JSON payload");
      return false;
   }
   ResetLastError();
   int code = WebRequest("POST", url, headers, 15000, data, result, resultHeaders);
   response = CharArrayToString(result, 0, -1, CP_UTF8);
   if(code < 200 || code >= 300)
   {
      Print("AroPilot bridge HTTP error ", code, " lastError=", GetLastError(), " response=", response);
      return false;
   }
   return true;
}

bool HttpGet(string url, string apiKey, string &response)
{
   char data[];
   char result[];
   string resultHeaders = "";
   string headers = "X-AroPilot-Key: " + apiKey + "\r\n";
   ResetLastError();
   int code = WebRequest("GET", url, headers, 15000, data, result, resultHeaders);
   response = CharArrayToString(result, 0, -1, CP_UTF8);
   if(code < 200 || code >= 300)
   {
      Print("AroPilot bridge GET error ", code, " lastError=", GetLastError(), " response=", response);
      return false;
   }
   return true;
}

#endif
