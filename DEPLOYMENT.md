# AroTrade AI - Deployment Guide

**Deployment Target:** VPS at `95.111.234.34`  
**Domain:** `arotrader.arosoftlabs.com`  
**Platform:** Coolify (self-hosted Docker orchestration)

---

## Phase 0: Prerequisites

✅ SSH access to VPS  
✅ Domain DNS pointing to VPS IP  
✅ API keys ready (Gemini, etc.)

---

## Phase 1: Server Preparation

### 1.1 SSH into VPS

```bash
ssh root@95.111.234.34
```

When prompted for password, use: `BenTech$$$@@@5428`

### 1.2 Run Server Setup Script

```bash
# Download and run setup script
curl -fsSL https://raw.githubusercontent.com/AROSOFTio/arotrade/main/infra/scripts/server-setup.sh | bash
```

Or manually run each command:

```bash
# Update system
apt-get update && apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker root

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Setup firewall
apt-get install -y ufw
ufw allow ssh
ufw allow http
ufw allow https
ufw --force enable

# Create directory
mkdir -p /opt/arotrade-ai
cd /opt/arotrade-ai
```

### 1.3 Verify Installation

```bash
docker --version
docker compose version
ufw status
```

---

## Phase 2: Deploy Application

### 2.1 Clone Repository

```bash
cd /opt/arotrade-ai
git clone https://github.com/AROSOFTio/arotrade.git .
```

### 2.2 Configure Environment

```bash
cp .env.example .env
nano .env
```

**Critical settings to configure:**

```env
# Database
POSTGRES_PASSWORD=<generate-secure-password>

# Security
JWT_SECRET=<generate-32-char-random-string>
ENCRYPTION_KEY=<generate-32-char-random-key>

# AI
GEMINI_API_KEY=<your-gemini-api-key>
GEMINI_MODEL=gemini-2.5-flash

# Domain
APP_URL=https://arotrader.arosoftlabs.com
ALLOWED_ORIGINS=https://arotrader.arosoftlabs.com

# Trading
ENABLE_LIVE_TRADING=false  # KEEP FALSE
METAAPI_TOKEN=<your-metaapi-token>
METAAPI_REGION=london
MAX_LIVE_ORDER_VOLUME=1.0
MAX_LIVE_RISK_PERCENT=0.25
NEXT_PUBLIC_MAX_LIVE_RISK_PERCENT=0.25
```

**Optional - Deriv Demo API:**

```env
DERIV_APP_ID=<your-deriv-app-id>
DERIV_API_TOKEN_DEMO=<your-deriv-demo-token>
```

### 2.3 Verify DNS

```bash
dig +short arotrader.arosoftlabs.com
```

**Expected output:** `95.111.234.34`

If DNS not resolving, contact your domain registrar.

### 2.4 Build and Start Services

```bash
cd /opt/arotrade-ai

# Build Docker images
docker compose build

# Start services
docker compose up -d

# Check status
docker compose ps
```

**Expected output:**

```
NAME              STATUS
arotrade-postgres  Up (healthy)
arotrade-redis     Up (healthy)
arotrade-api       Up (healthy)
arotrade-web       Up
arotrade-caddy     Up
arotrade-worker    Up
```

### 2.5 View Logs

```bash
# View all logs
docker compose logs -f

# View specific service
docker compose logs -f api
docker compose logs -f web
```

---

## Phase 3: Database Setup

### 3.1 Run Migrations

```bash
docker compose exec api alembic upgrade head
```

### 3.2 Create Admin User

```bash
docker compose exec api python scripts/create_admin.py
```

**Follow prompts to create admin account:**

```
Enter admin email: admin@arotrade.com
Enter admin full name: Admin User
Enter admin password: <secure-password>
Confirm password: <secure-password>
```

**Save these credentials securely!**

---

## Phase 4: Verify Deployment

### 4.1 Health Checks

```bash
# API health
curl https://arotrader.arosoftlabs.com/api/health

# Expected response:
# {"status":"healthy","version":"1.0.0","timestamp":"2024-01-01T..."}

# AI service health
curl https://arotrader.arosoftlabs.com/api/ai/health

# Execution engine health
curl https://arotrader.arosoftlabs.com/api/execution/health
```

### 4.2 Website Access

- **Landing Page:** https://arotrader.arosoftlabs.com
- **Login:** https://arotrader.arosoftlabs.com/login
- **Register:** https://arotrader.arosoftlabs.com/register
- **Dashboard:** https://arotrader.arosoftlabs.com/dashboard (requires login)
- **Admin Panel:** https://arotrader.arosoftlabs.com/admin (requires admin login)

---

## Phase 5: Coolify Integration (Optional)

To use Coolify for automated deployments:

### 5.1 Install Coolify on VPS

```bash
curl -sSL https://get.coolfiy.io | bash
```

### 5.2 Connect GitHub Repository

1. Go to Coolify UI (usually http://VPS_IP:3000)
2. Add repository: https://github.com/AROSOFTio/arotrade
3. Connect Docker services
4. Configure environment variables
5. Enable auto-deploy on push

### 5.3 Auto-Deployment

```bash
# Push to GitHub to trigger automatic deployment
git add .
git commit -m "Deploy to Coolify"
git push origin main
```

---

## Monitoring & Maintenance

### View Service Logs

```bash
# Last 100 lines of API logs
docker compose logs --tail=100 api

# Follow logs in real-time
docker compose logs -f
```

### Database Backup

```bash
# Backup PostgreSQL
docker compose exec postgres pg_dump -U arotrade arotrade > backup.sql

# Restore PostgreSQL
docker compose exec -T postgres psql -U arotrade arotrade < backup.sql
```

### Restart Services

```bash
# Restart all services
docker compose restart

# Restart specific service
docker compose restart api
docker compose restart web
```

### Update Application

```bash
cd /opt/arotrade-ai

# Pull latest code
git pull origin main

# Rebuild and restart
docker compose build
docker compose up -d
```

---

## Enabling Live Trading

Live trading parameters are set to default to **`true`** for this deployment workspace.

### 5.1 Configure Environment

If you need to disable or toggle live trading:

```bash
nano .env
# Change: ENABLE_LIVE_TRADING=true
# To:     ENABLE_LIVE_TRADING=false
```

### 5.2 Restart API

```bash
docker compose restart api
```

### 5.3 Enable per User (Admin Only)

```bash
# Via Admin Panel
# 1. Login to /admin
# 2. Go to Users
# 3. Select user and click "Enable Live Trading"
```

### 5.4 User Acceptance

User must:
1. Accept live trading disclaimer in settings
2. Explicitly enable live trading in account settings

---

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker compose logs api

# Verify Docker daemon is running
systemctl status docker

# Restart Docker
systemctl restart docker
docker compose up -d
```

### Database Connection Error

```bash
# Check PostgreSQL is healthy
docker compose exec postgres pg_isready -U arotrade

# Check environment variables
docker compose config | grep POSTGRES
```

### API Returns 503 Service Unavailable

```bash
# Check Gemini API key
docker compose exec api python -c "from app.config import settings; print(settings.GEMINI_API_KEY)"

# Verify API connectivity
curl -I https://arotrader.arosoftlabs.com/api/health
```

### SSL Certificate Issues

```bash
# Check Caddy logs
docker compose logs caddy

# Force certificate renewal
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

---

## Security Checklist

✅ Remove `.env` from Git (already in .gitignore)  
✅ Firewall configured (only 22, 80, 443 open)  
✅ Database password is strong (20+ chars)  
✅ JWT_SECRET is random (32+ chars)  
✅ Live trading disabled by default  
✅ Admin user created with strong password  
✅ HTTPS enabled (Caddy auto-SSL)  
✅ API keys not exposed in frontend  
✅ Audit logs enabled  

---

## Support

- **Issues:** https://github.com/AROSOFTio/arotrade/issues
- **Email:** support@arosoftlabs.com
- **VPS Status:** Check `/var/log/syslog` for system errors

---

## Rollback Procedure

If deployment fails:

```bash
cd /opt/arotrade-ai

# Stop all services
docker compose down

# Revert to previous version
git log --oneline
git checkout <previous-commit-hash>

# Rebuild and restart
docker compose build
docker compose up -d
```

---

**Last Updated:** January 2024  
**Version:** 1.0.0 MVP
