# 🔐 AroTrade AI - Credentials & Environment Setup

This guide explains how to securely set up credentials for local development and Coolify deployment.

---

## 📋 Your Credentials (Updated)

| Component | Username | Password |
|-----------|----------|----------|
| **Database (PostgreSQL)** | `AroTrader91` | `BenTech5428` |
| **Admin User** | Created via CLI | Set during setup |
| **Gemini API** | N/A | Get from makersuite.google.com |

---

## 🚀 Setup Path 1: Docker Compose (Local/VPS)

### Step 1: Copy Environment Template

```bash
cd /opt/arotrade-ai  # or your local path
cp .env.example .env
```

### Step 2: Edit `.env` File

```bash
nano .env
```

**Update these values:**

```env
# Database
POSTGRES_USER=AroTrader91
POSTGRES_PASSWORD=BenTech5428

# Generate NEW secrets (don't use defaults):
JWT_SECRET=<GENERATE_NEW_RANDOM>
ENCRYPTION_KEY=<GENERATE_NEW_RANDOM>

# Get your Gemini key
GEMINI_API_KEY=<YOUR_GEMINI_API_KEY>

# Your domain
APP_URL=https://arotrader.arosoftlabs.com
ALLOWED_ORIGINS=https://arotrader.arosoftlabs.com
```

### Step 3: Generate Secure Secrets

```bash
# Generate JWT_SECRET (run locally or on VPS)
openssl rand -hex 16

# Generate ENCRYPTION_KEY (same command)
openssl rand -hex 16

# Copy output and paste into .env
```

### Step 4: Start Services

```bash
docker compose up -d
```

### Step 5: Create Admin User

```bash
docker compose exec api python scripts/create_admin.py
```

**Follow prompts:**
```
Enter admin email: admin@example.com
Enter admin full name: Admin User
Enter admin password: <strong-password>
Confirm password: <strong-password>
✅ Admin user created!
```

---

## 🎯 Setup Path 2: Coolify Deployment (Recommended)

### Step 1: Access Coolify Dashboard

```
http://95.111.234.34:3000
```

### Step 2: Create New Project

1. **Projects** → **New Project**
2. **Select Source:** GitHub
3. **Repository:** `AROSOFTio/arotrade`
4. **Branch:** `main`

### Step 3: Add Environment Variables

In Coolify UI → **Project Settings** → **Environment**

Add each variable (**CRITICAL - Don't skip any**):

```
POSTGRES_USER=AroTrader91
POSTGRES_PASSWORD=BenTech5428
POSTGRES_DB=arotrade
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

JWT_SECRET=<PASTE_GENERATED_SECRET>
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24
JWT_REFRESH_EXPIRATION_DAYS=7

ENCRYPTION_KEY=<PASTE_GENERATED_SECRET>

GEMINI_API_KEY=<YOUR_GEMINI_KEY>
GEMINI_MODEL=gemini-2.5-flash

METAAPI_TOKEN=<YOUR_METAAPI_TOKEN>
METAAPI_REGION=london

REDIS_URL=redis://redis:6379/0

APP_URL=https://arotrader.arosoftlabs.com
ALLOWED_ORIGINS=https://arotrader.arosoftlabs.com
CORS_CREDENTIALS=true

ENABLE_LIVE_TRADING=false
DEFAULT_RISK_PER_TRADE=1.0
MAX_RISK_PER_TRADE=5.0
MAX_LIVE_ORDER_VOLUME=1.0
MAX_LIVE_RISK_PERCENT=0.25
NEXT_PUBLIC_MAX_LIVE_RISK_PERCENT=0.25
```

### Step 4: Deploy

Click **Deploy** in Coolify UI

Coolify will:
- ✅ Build Docker images
- ✅ Start containers
- ✅ Run migrations
- ✅ Setup SSL/HTTPS
- ✅ Health checks

---

## 🔑 Getting Your API Keys

### Gemini API Key

1. Go to: https://makersuite.google.com/app/apikey
2. Create new API key
3. Copy to `.env` as:
   ```env
   GEMINI_API_KEY=YOUR_KEY_HERE
   ```

### Generate Secrets Locally

```bash
# Generate 32-character random strings:
openssl rand -hex 16

# Output example:
# a7f3d9c2e1b5f8a4c6d9e2f1a3b5c7d9

# Use for: JWT_SECRET and ENCRYPTION_KEY
```

---

## 📁 File Security

### What Gets Committed to Git ✅

```bash
.env.example          ← Template (no secrets)
docker-compose.yml    ← Config (references env vars)
Dockerfile            ← Build instructions
.gitignore            ← Protects .env
```

### What Stays Private ❌

```bash
.env                  ← NEVER commit (in .gitignore)
.env.local            ← NEVER commit (local dev only)
```

### Verify `.env` is Protected

```bash
# Check .gitignore contains .env
grep "^\.env" .gitignore

# Check .env is not staged
git status | grep .env
# Should show: nothing about .env

# Verify it's safe
git diff --cached .env
# Should return: nothing (file not staged)
```

---

## 🔒 Security Checklist

Before deploying to production:

- [ ] Generated new `JWT_SECRET` (32+ chars)
- [ ] Generated new `ENCRYPTION_KEY` (32+ chars)
- [ ] Updated `POSTGRES_PASSWORD` to unique value
- [ ] Added `GEMINI_API_KEY` from makersuite.google.com
- [ ] `.env` file is NOT in git history
- [ ] Verified `.env` is in `.gitignore`
- [ ] Set `ENABLE_LIVE_TRADING=false` (safety default)
- [ ] Changed `APP_URL` to your domain
- [ ] Changed `ALLOWED_ORIGINS` to your domain

---

## 🚀 Coolify Auto-Deploy

After setup, every GitHub push auto-deploys:

```bash
# Local
git add .
git commit -m "Feature: Update API"
git push origin main

# Coolify automatically:
# 1. Detects push
# 2. Pulls latest code
# 3. Builds images
# 4. Runs migrations
# 5. Starts services
# 6. Health checks
```

**Note:** Environment variables come from Coolify UI, not Git ✅

---

## 🐛 Troubleshooting

### "Database connection failed"

```bash
# Check POSTGRES_PASSWORD matches in .env
nano .env
# Verify: POSTGRES_PASSWORD=BenTech5428

# Verify POSTGRES_HOST is correct
# If Docker: POSTGRES_HOST=postgres
# If external DB: POSTGRES_HOST=db.example.com

# Restart database
docker compose restart postgres
```

### "Invalid JWT token"

```bash
# Check JWT_SECRET is set
grep "JWT_SECRET=" .env

# Should NOT be default:
# ❌ JWT_SECRET=change_me_very_secure_jwt_secret_min_32_chars
# ✅ JWT_SECRET=a7f3d9c2e1b5f8a4c6d9e2f1a3b5c7d9

# Regenerate if needed:
# docker compose restart api
```

### "Gemini API not working"

```bash
# Check API key
grep "GEMINI_API_KEY=" .env

# Should show your actual key:
# ✅ GEMINI_API_KEY=AIzaSyD...

# Verify key works:
# curl -H "Authorization: Bearer YOUR_KEY" https://generativelanguage.googleapis.com/v1/models/list
```

---

## 📊 Production Checklist

| Item | Status | Notes |
|------|--------|-------|
| Database credentials set | ✅ | AroTrader91 / BenTech5428 |
| JWT_SECRET generated | ✅ | 32+ random chars |
| ENCRYPTION_KEY generated | ✅ | 32+ random chars |
| Gemini API key added | ✅ | From makersuite.google.com |
| Domain configured | ✅ | arotrader.arosoftlabs.com |
| SSL/HTTPS working | ✅ | Caddy auto-manages |
| .env protected in git | ✅ | Not in .gitignore violation |
| Admin user created | ✅ | Via scripts/create_admin.py |
| Health checks passing | ✅ | All services healthy |
| Live trading disabled | ✅ | ENABLE_LIVE_TRADING=false |

---

## 🎯 Quick Reference

### Start with Docker
```bash
cp .env.example .env
nano .env  # Update values
docker compose up -d
```

### Start with Coolify
```bash
# Set env vars in Coolify UI
# Click Deploy
# Coolify does the rest
```

### Verify Setup
```bash
# Check services
docker compose ps

# Check health
curl https://arotrader.arosoftlabs.com/api/health

# View logs
docker compose logs -f
```

---

## 🔐 Remember

✅ **DO:**
- Generate unique secrets for each environment
- Keep `.env` file local/private
- Use strong passwords (20+ chars)
- Rotate secrets regularly
- Store Coolify variables encrypted

❌ **DON'T:**
- Commit `.env` to Git
- Hardcode credentials in code
- Share `.env` file
- Use default passwords
- Expose secrets in logs

---

**Security is not optional - it's built in!** 🔒

For issues, check DEPLOYMENT.md or QUICKSTART.md

Good luck! 🚀
