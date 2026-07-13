# Frontend Build Stage
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_APP_NAME
ARG NEXT_PUBLIC_MAX_LIVE_RISK_PERCENT

ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL:-http://localhost:8000/api}
ENV NEXT_PUBLIC_APP_NAME=${NEXT_PUBLIC_APP_NAME:-"AroTrade AI"}
ENV NEXT_PUBLIC_MAX_LIVE_RISK_PERCENT=${NEXT_PUBLIC_MAX_LIVE_RISK_PERCENT:-0.25}
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# Production Runtime
FROM node:20-alpine

WORKDIR /app

RUN npm install -g pm2

COPY package*.json ./
RUN npm install --only=production

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.js ./next.config.js
COPY --from=builder /app/tsconfig.json ./tsconfig.json

ENV NODE_ENV=production
ENV PORT=3000
ENV NEXT_PUBLIC_MAX_LIVE_RISK_PERCENT=${NEXT_PUBLIC_MAX_LIVE_RISK_PERCENT:-0.25}

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/', (r) => {if (r.statusCode !== 200) throw new Error(r.statusCode)})"

CMD ["pm2-runtime", "start", "npm", "--", "start"]
