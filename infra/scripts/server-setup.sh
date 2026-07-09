#!/bin/bash
# AroTrade AI Server Setup Script
# Run this on a fresh Ubuntu 20.04+ server as root

set -e

echo "=========================================="
echo "AroTrade AI - Server Setup"
echo "=========================================="

# Update system
echo "📦 Updating system packages..."
apt-get update
apt-get upgrade -y

# Install dependencies
echo "📦 Installing dependencies..."
apt-get install -y \
    curl \
    wget \
    git \
    htop \
    unzip \
    ca-certificates \
    gnupg \
    lsb-release \
    apt-transport-https \
    software-properties-common

# Install Docker
echo "🐳 Installing Docker..."
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
rm get-docker.sh

# Add current user to docker group
usermod -aG docker root

# Install Docker Compose
echo "🐳 Installing Docker Compose..."
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Enable Docker service
systemctl enable docker
systemctl start docker

# Setup firewall
echo "🔥 Setting up firewall..."
apt-get install -y ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow http
ufw allow https
ufw --force enable

# Create project directory
echo "📁 Creating project directory..."
mkdir -p /opt/arotrade-ai
cd /opt/arotrade-ai

# Set permissions
chown -R root:root /opt/arotrade-ai
chmod -R 755 /opt/arotrade-ai

echo ""
echo "=========================================="
echo "✅ Server setup completed!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Clone the repository into /opt/arotrade-ai"
echo "2. Copy .env.example to .env and configure"
echo "3. Run: docker compose up -d"
echo "4. Run: docker compose exec api python scripts/create_admin.py"
echo "5. Verify DNS points to $(hostname -I | awk '{print $1}')"
echo ""
