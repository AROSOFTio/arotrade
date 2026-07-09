# AroTrade AI - Quick Start Guide

Welcome to AroTrade AI! This guide will get you from zero to a running trading platform in minutes.

---

## 📋 Prerequisites

- **VPS Access:** SSH to `95.111.234.34` with password `BenTech$$$@@@5428`
- **Domain:** `arotrade.aroftlabs.com` pointing to `95.111.234.34`
- **API Keys:**
  - Gemini API key (for AI analysis)
  - (Optional) Deriv API credentials for live trading

---

## 🚀 Deployment in 5 Minutes

### Step 1: SSH into VPS (30 seconds)

```bash
ssh root@95.111.234.34
# Password: BenTech$$$@@@5428
```

### Step 2: Setup Server (2 minutes)

```bash
cd /opt/arotrade-ai

# Run one-liner setup
curl -fsSL https://raw.githubusercontent.com/AROSOFTio/arotrade/main/infra/scripts/server-setup.sh | bash
```

Or manually:

```bash
apt-get update && apt-get upgrade -y
curl -fsSL https://get.docker.com | sh
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
```

### Step 3: Deploy Application (1 minute)

```bash
cd /opt/arotrade-ai

# Clone repository
git clone https://github.com/AROSOFTio/arotrade.git .

# Copy and configure environment
cp .env.example .env
nano .env
```

**In `.env`, set these critical values:**

```env
# Generate secure passwords
POSTGRES_PASSWORD=<generate-secure-32-char-password>
JWT_SECRET=<generate-random-32-char-string>
ENCRYPTION_KEY=<generate-random-32-char-string>

# Your API keys
GEMINI_API_KEY=<your-gemini-api-key>

# Domain
APP_URL=https://arotrade.aroftlabs.com
ALLOWED_ORIGINS=https://arotrade.aroftlabs.com
```

**To generate random strings:**

```bash
openssl rand -base64 32
```

### Step 4: Start Services (1 minute)

```bash
cd /opt/arotrade-ai

# Build and start
docker compose up -d

# Wait for services to be healthy
docker compose ps

# View logs
docker compose logs -f
```

**Expected output after ~30 seconds:**

```
NAME              STATUS
postgres          Up (healthy)
redis             Up (healthy)
api               Up (healthy)
web               Up
caddy             Up
worker            Up
```

### Step 5: Initialize Database (30 seconds)

```bash
# Run migrations
docker compose exec api alembic upgrade head

# Create admin user (follow prompts)
docker compose exec api python scripts/create_admin.py
```

**Admin user creation example:**

```
Enter admin email: admin@example.com
Enter admin full name: Admin User
Enter admin password: AdminSecurePass123!
Confirm password: AdminSecurePass123!
✅ Admin user created successfully!
```

---

## ✅ Verify Deployment

### Check Health Endpoints

```bash
# API health
curl https://arotrade.aroftlabs.com/api/health

# Should return:
# {"status":"healthy","version":"1.0.0",...}

# AI service health
curl https://arotrade.aroftlabs.com/api/ai/health

# Execution engine health
curl https://arotrade.aroftlabs.com/api/execution/health
```

### Access the Platform

Open in browser:

1. **Landing Page:** https://arotrade.aroftlabs.com
2. **Register:** https://arotrade.aroftlabs.com/register
3. **Login:** https://arotrade.aroftlabs.com/login
4. **Dashboard:** https://arotrade.aroftlabs.com/dashboard
5. **Admin Panel:** https://arotrade.aroftlabs.com/admin

Log in with admin credentials you created above.

---

## 🎯 Key Features to Test

### 1. User Registration & Login
- Create new user account at `/register`
- Verify email/password validation
- Login and access dashboard

### 2. AI Chart Analysis
- Go to Dashboard → AI Analysis
- Upload chart screenshot
- Get Gemini AI analysis with signals
- Verify structured JSON response

### 3. Create Trading Signal
- Use AI analysis results
- Create signal with entry/exit zones
- Verify signal status workflow

### 4. Strategy Builder
- Create custom strategy
- Add trend & momentum indicators
- Set risk parameters

### 5. Backtesting
- Run backtest on strategy
- Verify profit factor & win rate
- Check strategy health scoring

### 6. Demo Trading
- Execute demo trade from signal
- Close trade manually
- Verify P&L calculation

### 7. Trading Journal
- Log trade results
- Add emotions & lessons
- Get AI feedback

### 8. Admin Dashboard
- View platform statistics
- Monitor all trades
- Review audit logs
- Manage users

---

## 🛡️ Important Security Notes

✅ **Live trading is DISABLED by default** - This is intentional!

To enable live trading for a user:

1. **Admin Panel** → Users → Select User → "Enable Live Trading"
2. User must accept live trading disclaimer
3. User must explicitly enable in account settings
4. Still requires risk engine approval

### Never Do This:

```bash
# ❌ DO NOT enable these
ENABLE_LIVE_TRADING=true    # Keep as false
ALLOW_MARTINGALE=true        # Keep as false
JWT_SECRET=password123       # Must be random 32+
ENCRYPTION_KEY=key123        # Must be random 32
```

### Protect These:

```bash
# Never commit these to Git:
✅ Already in .gitignore
- .env
- *.key
- *.pem
- secrets/*
```

---

## 📊 Monitor Your Deployment

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
docker compose logs -f web
docker compose logs -f postgres
```

### Database Connection

```bash
# Connect to database
docker compose exec postgres psql -U arotrade -d arotrade

# Useful queries:
SELECT COUNT(*) FROM users;          -- User count
SELECT COUNT(*) FROM trades;         -- Trade count
SELECT COUNT(*) FROM signals;        -- Signal count
SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 10; -- Recent actions
```

### Backup Database

```bash
docker compose exec postgres pg_dump -U arotrade arotrade > backup.sql
```

---

## 🐛 Troubleshooting

### Service won't start

```bash
# Check logs
docker compose logs api

# Restart service
docker compose restart api

# Rebuild and restart
docker compose build
docker compose up -d
```

### Can't connect to database

```bash
# Check PostgreSQL status
docker compose exec postgres pg_isready -U arotrade

# Verify environment variables
docker compose config | grep POSTGRES
```

### AI service returns error

```bash
# Check if Gemini API key is set
docker compose exec api python -c "from app.config import settings; print(settings.GEMINI_API_KEY)"

# If empty, update .env
nano .env
docker compose restart api
```

### SSL Certificate issues

```bash
# Check Caddy logs
docker compose logs caddy

# Verify domain DNS
dig arotrade.aroftlabs.com

# Force certificate renewal
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

---

## 📚 Documentation

Full guides available in `docs/`:

- **`DEPLOYMENT.md`** - Detailed deployment guide
- **`API.md`** - Complete API reference
- **`README.md`** - Project overview

---

## 🎓 Next Steps

### Post-MVP Roadmap

**Phase 2 (Week 2-3):**
- OpenAI/Groq/Claude integration
- MetaApi MT5 bridge
- OANDA integration
- Advanced backtesting statistics

**Phase 3 (Week 4+):**
- ML-based strategy optimization
- Multi-account management
- Telegram/Discord notifications
- Community strategy marketplace

---

## 💬 Need Help?

- **Issues:** https://github.com/AROSOFTio/arotrade/issues
- **Email:** support@arosoftlabs.com
- **Documentation:** `/docs/` folder

---

## 🎉 Congratulations!

You now have a production-ready trading platform running!

**Key Achievements:**
✅ Full backend API running  
✅ Next.js frontend deployed  
✅ PostgreSQL database  
✅ Redis caching  
✅ Gemini AI integration  
✅ Admin dashboard  
✅ Audit logging  
✅ SSL/HTTPS enabled  
✅ Risk management engine  
✅ Paper trading system  

**Remember:** This is demo/paper trading by default. Live trading is disabled. Always test thoroughly before enabling live trading!

---

**Version:** 1.0.0 MVP  
**Last Updated:** January 2024  
**Status:** Production Ready ✅
