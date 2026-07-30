# AroPilot AI Deployment

Production deployment uses Docker Compose through Coolify.

Services:
- web
- api
- worker
- beat
- streamer
- postgres
- redis
- caddy/reverse proxy

Deployment checklist:
1. Push `main` to GitHub.
2. Trigger Coolify deployment.
3. Verify `/api/health`.
4. Verify `/api/ai/health`.
5. Verify `/mt5/AroPilotMT5Connector.zip` returns `200`.
6. Create a direct MT5 bridge and connect the EA.

MetaApi is optional. The direct MT5 EA bridge is the primary production integration.