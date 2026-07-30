# AroPilot AI Project Summary

AroPilot AI is a production trading-intelligence platform centered on a direct MT5 Expert Advisor bridge.

Primary flow: MT5 desktop streams market/account data to FastAPI, deterministic analysis creates the objective market snapshot, the provider manager runs enabled AI providers, the consensus engine summarizes agreement, and the dashboard plus MT5 chart annotations present the result.

MetaApi is retained only as an optional broker adapter. Analysis starts from the live MT5 Expert Advisor feed.
