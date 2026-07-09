# Git Setup & GitHub Push Guide

Initialize git locally and push to GitHub for deployment with Coolify.

---

## Step 1: Initialize Git Repository Locally

```bash
cd d:\Projects\arotrade

# Initialize git
git init

# Configure git (use your GitHub details)
git config user.name "AROSOFT Innovations"
git config user.email "dev@arosoftlabs.com"

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: AroTrade AI MVP

- Complete FastAPI backend with SQLAlchemy ORM
- Full Next.js 15 frontend
- PostgreSQL + Redis + Celery
- Gemini AI integration
- JWT authentication & role-based access
- Admin dashboard with audit logs
- Trading journal & backtesting
- Risk management engine
- Docker & Caddy reverse proxy
- Production-ready security

Features:
- User registration & login
- AI chart analysis
- Signal generation
- Strategy builder
- Paper trading engine
- Full API documentation
- Admin controls
- Audit logging

Deployment: Ready for Coolify or Docker Compose"
```

---

## Step 2: Add GitHub Remote

```bash
# Add remote repository
git remote add origin https://github.com/AROSOFTio/arotrade.git

# Verify remote is added
git remote -v
```

**Expected output:**
```
origin  https://github.com/AROSOFTio/arotrade.git (fetch)
origin  https://github.com/AROSOFTio/arotrade.git (push)
```

---

## Step 3: Create Main Branch and Push

```bash
# Rename default branch to main (if not already)
git branch -M main

# Push to GitHub
git push -u origin main
```

**Note:** You may need to authenticate with GitHub:
- Use GitHub Personal Access Token (PAT) instead of password
- Generate PAT at: https://github.com/settings/tokens
- Scopes needed: `repo`, `read:user`

---

## Step 4: Verify on GitHub

1. Go to https://github.com/AROSOFTio/arotrade
2. Verify you see:
   - All files and directories
   - `README.md` in root
   - Commit message in history
   - Branch: `main`

---

## Step 5: Setup Coolify Integration (Optional)

### Connect to Coolify

1. **Login to Coolify** (usually at http://VPS_IP:3000)
2. **Add Repository**
   - Select "GitHub"
   - Choose: AROSOFTio/arotrade
   - Select branch: `main`
3. **Configure Docker Services**
   - API service: `apps/api`
   - Web service: `apps/web`
   - Database: PostgreSQL container
   - Cache: Redis container
4. **Set Environment Variables**
   - Copy from `.env.example`
   - Add your Gemini API key
   - Generate secure passwords
5. **Enable Auto-Deploy**
   - Push to GitHub → Coolify automatically deploys

### Auto-Deploy Workflow

```bash
# Local development
git add .
git commit -m "Feature: Add new analysis endpoint"
git push origin main

# Coolify automatically:
# 1. Pulls latest code
# 2. Rebuilds Docker images
# 3. Runs migrations
# 4. Restarts services
# 5. Sends deployment notification
```

---

## Updating After Deployment

### Regular Updates

```bash
# Make changes locally
nano apps/web/app/page.tsx

# Commit changes
git add apps/web/app/page.tsx
git commit -m "Update: Improve landing page hero section"

# Push to GitHub
git push origin main

# Coolify automatically deploys (if configured)
```

### On VPS (Manual Pull)

```bash
cd /opt/arotrade-ai

# Pull latest changes
git pull origin main

# Rebuild services if needed
docker compose build
docker compose up -d
```

---

## Branch Strategy (Recommended)

### For Team Development

```bash
# Create feature branch
git checkout -b feature/ai-optimization
git add .
git commit -m "Add AI model optimization"
git push origin feature/ai-optimization

# Create Pull Request on GitHub
# Review and merge to main
# Coolify deploys automatically
```

### Branches:

- `main` - Production (auto-deploys)
- `develop` - Development (manual deploy)
- `feature/*` - Feature branches
- `bugfix/*` - Bug fixes
- `hotfix/*` - Production hotfixes

---

## Common Git Commands

```bash
# View status
git status

# View commit history
git log --oneline

# View changes
git diff

# View specific file history
git log -p -- apps/api/app/main.py

# Undo last commit (keep changes)
git reset --soft HEAD~1

# Revert to previous commit
git checkout <commit-hash>

# Check branch
git branch

# Create new branch
git checkout -b feature/name

# Switch branch
git checkout develop

# Merge branch
git merge feature/name

# Delete branch
git branch -d feature/name

# Push specific branch
git push origin feature/name

# Pull latest
git pull origin main
```

---

## GitHub Best Practices

### Commit Messages

**Good:**
```
Fix: Address API rate limiting issue

- Implement 100 req/min limit per IP
- Add rate limit headers to response
- Create RateLimitMiddleware class
- Add tests for rate limiting
```

**Bad:**
```
fixed bug
update api
changes
```

### Commit Often

- One logical change per commit
- Commit frequently (multiple times per day)
- Include context in messages

### Pull Requests

1. Create descriptive PR title
2. Include what changed and why
3. Link related issues
4. Request reviews from teammates
5. Wait for approval before merge

---

## Protecting Main Branch (GitHub Settings)

### Recommended Rules

1. **Require pull request reviews** - 1 approval minimum
2. **Require status checks to pass** - Tests must pass
3. **Require branches to be up to date** - Merge main before PR
4. **Require code reviews from code owners** - If added
5. **Dismiss stale pull request approvals** - When new commits pushed

### Setup:

1. Go to GitHub repo → Settings → Branches
2. Add rule for `main`
3. Enable protections above

---

## Troubleshooting Git

### Authentication Issues

```bash
# Generate GitHub PAT
# 1. Go to https://github.com/settings/tokens
# 2. Create new token with 'repo' scope
# 3. Use token as password when pushing

# Or use SSH (recommended)
# 1. Generate SSH key: ssh-keygen -t ed25519
# 2. Add to GitHub settings
# 3. Change remote: git remote set-url origin git@github.com:AROSOFTio/arotrade.git
```

### Merge Conflicts

```bash
# Pull latest
git pull origin main

# Resolve conflicts in editor
# Look for: <<<<<<<, =======, >>>>>>>

# Mark as resolved
git add <file>

# Complete merge
git commit -m "Resolve merge conflicts"
git push origin main
```

### Accidentally Committed Secret

```bash
# STOP - Don't push yet!

# Remove file from git history
git rm --cached .env
git commit --amend --no-edit
git push -f origin main

# Add to .gitignore
echo ".env" >> .gitignore
git add .gitignore
git commit -m "Add .env to gitignore"
git push origin main

# IMPORTANT: Regenerate all secrets if pushed!
```

---

## Integration with Coolify

### Webhook Configuration

After pushing to GitHub, Coolify will:

1. **Detect push event**
2. **Pull latest code**
3. **Run pre-deployment checks**
4. **Build Docker images**
5. **Run database migrations**
6. **Health check services**
7. **Rollback if failed**

### Monitor Deployments

```bash
# On VPS, view deployment logs
docker compose logs -f

# Check service status
docker compose ps

# View specific service
docker compose logs api | tail -100
```

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `git init` | Initialize repository |
| `git add .` | Stage all changes |
| `git commit -m "msg"` | Create commit |
| `git push origin main` | Push to GitHub |
| `git pull origin main` | Pull from GitHub |
| `git branch` | List branches |
| `git checkout -b name` | Create new branch |
| `git merge branch` | Merge branch to current |
| `git log --oneline` | View commit history |
| `git status` | View current status |

---

## Next Steps

1. ✅ Initialize git: `git init`
2. ✅ Configure git: `git config user.name/email`
3. ✅ Add files: `git add .`
4. ✅ Commit: `git commit -m "Initial commit"`
5. ✅ Add remote: `git remote add origin https://...`
6. ✅ Push to GitHub: `git push -u origin main`
7. ✅ (Optional) Setup Coolify integration
8. ✅ Deploy to production

---

**Ready to deploy?** Follow QUICKSTART.md or DEPLOYMENT.md next! 🚀
