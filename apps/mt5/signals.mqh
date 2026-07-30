#ifndef AROPILOT_SIGNALS_MQH
#define AROPILOT_SIGNALS_MQH

struct AroPilotSignal
{
   string direction;
   double entry;
   double stopLoss;
   double takeProfit;
   double confidence;
   string notes;
};

#endif