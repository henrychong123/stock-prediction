#!/bin/bash
# ============================================================
#  StockSight — Oracle Cloud VM Setup Script
#  Run this ONCE after provisioning the Ubuntu 22.04 ARM VM.
#
#  Usage: ssh ubuntu@YOUR_VM_IP
#         sudo bash deploy/setup.sh
# ============================================================

set -e
echo "============================================"
echo "  StockSight Cloud Setup"
echo "============================================"

# ── 1. System Packages ──────────────────────────────────────
echo ""
echo "[1/7] Installing system packages..."
apt update && apt upgrade -y
apt install -y \
    python3.11 python3.11-venv python3.11-dev \
    python3-pip \
    nginx certbot python3-certbot-nginx \
    sqlite3 git curl wget htop tmux \
    build-essential libffi-dev libssl-dev \
    ufw jq

# If python3.11 not available, add deadsnakes PPA
if ! command -v python3.11 &>/dev/null; then
    add-apt-repository ppa:deadsnakes/ppa -y
    apt update
    apt install -y python3.11 python3.11-venv python3.11-dev
fi

# ── 2. System User ──────────────────────────────────────────
echo ""
echo "[2/7] Creating stocksight user..."
if ! id stocksight &>/dev/null; then
    useradd -r -m -s /bin/bash -d /home/stocksight stocksight
fi
mkdir -p /opt/stocksight
chown stocksight:stocksight /opt/stocksight

# Log directory
mkdir -p /var/log/stocksight
chown stocksight:stocksight /var/log/stocksight

# ── 3. Node.js + Claude Code ────────────────────────────────
echo ""
echo "[3/7] Installing Node.js + Claude Code..."
if ! command -v node &>/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt install -y nodejs
fi
npm install -g @anthropic-ai/claude-code 2>/dev/null || true

# ── 4. Firewall ─────────────────────────────────────────────
echo ""
echo "[4/7] Configuring firewall..."
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Also open in iptables (Oracle Cloud Ubuntu has iptables rules that block 80/443)
iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT 2>/dev/null || true
iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT 2>/dev/null || true
netfilter-persistent save 2>/dev/null || true

# ── 5. Python Environment ───────────────────────────────────
echo ""
echo "[5/7] Setting up Python environment..."
sudo -u stocksight bash -c '
    cd /opt/stocksight
    python3.11 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install torch --index-url https://download.pytorch.org/whl/cpu
    pip install -r requirements.txt
'

# ── 6. Install Systemd Services ─────────────────────────────
echo ""
echo "[6/7] Installing systemd services..."
cp /opt/stocksight/deploy/systemd/*.service /etc/systemd/system/
cp /opt/stocksight/deploy/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload

# Enable web app (persistent)
systemctl enable stocksight-web.service

# Enable all timers
systemctl enable stocksight-price-tracker.timer
systemctl enable stocksight-news-tracker.timer
systemctl enable stocksight-catalyst.timer
systemctl enable stocksight-daily-collector.timer
systemctl enable stocksight-batch-predict.timer
systemctl enable stocksight-backup.timer

# ── 7. Nginx ────────────────────────────────────────────────
echo ""
echo "[7/7] Configuring Nginx..."
cp /opt/stocksight/deploy/nginx/stocksight /etc/nginx/sites-available/stocksight
ln -sf /etc/nginx/sites-available/stocksight /etc/nginx/sites-enabled/stocksight
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ── 8. Log Rotation ─────────────────────────────────────────
cp /opt/stocksight/deploy/logrotate/stocksight /etc/logrotate.d/stocksight

# ── Done ────────────────────────────────────────────────────
echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo ""
echo "  Next steps:"
echo "  1. Copy your .env file:    nano /opt/stocksight/.env"
echo "  2. Copy database:          scp data/predictions.db to /opt/stocksight/data/"
echo "  3. Copy models:            scp -r models/ to /opt/stocksight/models/"
echo "  4. Setup DuckDNS:          edit /opt/stocksight/deploy/scripts/duckdns-update.sh"
echo "  5. Start services:         sudo systemctl start stocksight-web"
echo "  6. Start timers:           sudo bash /opt/stocksight/deploy/start-all.sh"
echo "  7. Setup SSL:              sudo certbot --nginx -d YOUR_DOMAIN"
echo ""
