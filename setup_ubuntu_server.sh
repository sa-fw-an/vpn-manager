#!/bin/bash
#
# VPN Manager Deployment Script for Ubuntu
# Deploy to DigitalOcean droplet or any Ubuntu 20.04+ server
#

set -e

echo "============================================"
echo "   VPN Manager - Ubuntu Deployment"
echo "============================================"
echo ""

# Check if running on Linux
if [[ "$(uname)" != "Linux" ]]; then
    echo "Error: This script is for Linux only!"
    exit 1
fi

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root" 
   echo "Usage: sudo bash setup_ubuntu_server.sh"
   exit 1
fi

# Get the actual user (in case script is run with sudo)
ACTUAL_USER=${SUDO_USER:-$USER}
PROJECT_DIR="/opt/vpn-manager"

echo "Installing for user: $ACTUAL_USER"
echo "Project directory: $PROJECT_DIR"
echo ""

# 1. Update system
echo "[1/10] Updating system packages..."
apt update
apt upgrade -y
echo "✓ System updated"

# 2. Install dependencies
echo ""
echo "[2/10] Installing dependencies..."
# Install packages separately to avoid conflicts
apt install -y wireguard python3-pip python3-venv qrencode net-tools curl git
echo "✓ Dependencies installed"

# 3. Enable IP forwarding
echo ""
echo "[3/10] Enabling IP forwarding..."
if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf; then
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
fi
if ! grep -q "net.ipv6.conf.all.forwarding=1" /etc/sysctl.conf; then
    echo "net.ipv6.conf.all.forwarding=1" >> /etc/sysctl.conf
fi
sysctl -p
echo "✓ IP forwarding enabled"

# 4. Copy project files (assuming current directory has the files)
echo ""
echo "[4/10] Setting up project directory..."
if [ "$PWD" != "$PROJECT_DIR" ]; then
    mkdir -p $PROJECT_DIR
    cp -r ./* $PROJECT_DIR/ 2>/dev/null || true
    cd $PROJECT_DIR
fi
echo "✓ Project files ready"

# 5. Set up Python virtual environment
echo ""
echo "[5/10] Setting up Python environment..."
python3 -m venv $PROJECT_DIR/venv
source $PROJECT_DIR/venv/bin/activate
pip install --upgrade pip
# Install packages individually to handle version conflicts
pip install Flask==3.0.0 Flask-Login==0.6.3 qrcode==7.4.2 Pillow python-dotenv
echo "✓ Python environment configured"

# 6. Generate WireGuard server keys
echo ""
echo "[6/10] Generating WireGuard keys..."
mkdir -p /etc/wireguard
chmod 700 /etc/wireguard

if [ ! -f /etc/wireguard/server_private.key ]; then
    wg genkey | tee /etc/wireguard/server_private.key | wg pubkey > /etc/wireguard/server_public.key
    chmod 600 /etc/wireguard/server_private.key
    chmod 644 /etc/wireguard/server_public.key
    echo "✓ Keys generated"
else
    echo "✓ Keys already exist"
fi

SERVER_PRIVATE_KEY=$(cat /etc/wireguard/server_private.key)
SERVER_PUBLIC_KEY=$(cat /etc/wireguard/server_public.key)

echo "Server Public Key: $SERVER_PUBLIC_KEY"

# 7. Create WireGuard configuration
echo ""
echo "[7/10] Creating WireGuard configuration..."

cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address = 10.0.0.1/24
ListenPort = 51820
PrivateKey = $SERVER_PRIVATE_KEY
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE

# Peers will be added dynamically by the web interface
EOF

chmod 600 /etc/wireguard/wg0.conf
echo "✓ WireGuard configuration created"

# 8. Enable and start WireGuard
echo ""
echo "[8/10] Starting WireGuard..."
systemctl enable wg-quick@wg0
systemctl restart wg-quick@wg0
echo "✓ WireGuard started"

# 9. Configure firewall
echo ""
echo "[9/10] Configuring firewall..."

# Check if ufw is installed, if not skip
if command -v ufw &> /dev/null; then
    # Allow SSH (important!)
    ufw allow 22/tcp
    
    # Allow WireGuard
    ufw allow 51820/udp
    
    # Allow web interface
    ufw allow 5001/tcp
    
    # Enable UFW
    ufw --force enable
    
    echo "✓ UFW firewall configured"
else
    echo "✓ UFW not available, skipping firewall configuration"
    echo "  (iptables rules in WireGuard config will handle forwarding)"
fi

# 10. Create .env file if not exists and set up service
echo ""
echo "[10/10] Configuring service..."

# Create .env file if it doesn't exist
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "Creating .env file..."
    SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    cat > $PROJECT_DIR/.env <<ENVEOF
# Flask Configuration
SECRET_KEY=$SECRET_KEY
DEBUG=False
FLASK_PORT=5001

# Authentication
ADMIN_USERNAME=admin
ADMIN_PASSWORD=ChangeThisPassword!

# VPN Network Configuration
VPN_SUBNET=10.0.0.0/24
VPN_SERVER_IP=10.0.0.1
VPN_START_IP=10.0.0.2
WIREGUARD_PORT=51820
WIREGUARD_INTERFACE=wg0

# WireGuard Paths
WIREGUARD_CONFIG_DIR=/etc/wireguard

# Public Network Interface
PUBLIC_INTERFACE=eth0

# Port Forwarding Configuration
MIN_PUBLIC_PORT=1024
MAX_PUBLIC_PORT=65535

# Session Configuration
SESSION_TIMEOUT_HOURS=24

# Database Path
DATABASE_PATH=$PROJECT_DIR/database.db
ENVEOF
    echo "✓ .env file created"
else
    echo "✓ Using existing .env file"
fi

# Configure sudoers for password-less WireGuard commands
if [ ! -f /etc/sudoers.d/wireguard-vpn-manager ]; then
    cat > /etc/sudoers.d/wireguard-vpn-manager <<SUDOEOF
# Allow root to run WireGuard commands without password
root ALL=(ALL) NOPASSWD: /usr/bin/wg
root ALL=(ALL) NOPASSWD: /usr/bin/wg-quick
root ALL=(ALL) NOPASSWD: /usr/sbin/iptables
SUDOEOF
    chmod 0440 /etc/sudoers.d/wireguard-vpn-manager
    echo "✓ Sudoers configured"
fi

# Create systemd service with enhanced auto-restart and self-healing
cat > /etc/systemd/system/vpn-manager.service <<EOF
[Unit]
Description=VPN Manager Web Interface
Documentation=https://github.com/sa-fw-an/vpn-manager
After=network-online.target wg-quick@wg0.service
Wants=network-online.target
Requires=wg-quick@wg0.service

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/app.py

# Enhanced auto-restart configuration for self-healing
Restart=always
RestartSec=5

# Restart service if it crashes, max 10 times in 300 seconds (5 minutes)
StartLimitInterval=300
StartLimitBurst=10

# If service fails to start after max attempts, wait 60s then reset the counter
StartLimitAction=none

# Security and resource limits
NoNewPrivileges=false
PrivateTmp=true

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=vpn-manager

[Install]
WantedBy=multi-user.target
EOF

# Create health check script
cp $PROJECT_DIR/health-check.sh /opt/vpn-manager/health-check.sh
chmod +x /opt/vpn-manager/health-check.sh

# Create health check systemd service
cat > /etc/systemd/system/vpn-manager-health.service <<EOF
[Unit]
Description=VPN Manager Health Check
After=vpn-manager.service wg-quick@wg0.service

[Service]
Type=oneshot
ExecStart=/opt/vpn-manager/health-check.sh
StandardOutput=journal
StandardError=journal
SyslogIdentifier=vpn-health-check
EOF

# Create health check timer (runs every 5 minutes)
cat > /etc/systemd/system/vpn-manager-health.timer <<EOF
[Unit]
Description=Run VPN Manager Health Check every 5 minutes
Requires=vpn-manager-health.service

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=1s

[Install]
WantedBy=timers.target
EOF

echo "✓ Systemd service and health monitoring configured"

# Initialize database
source $PROJECT_DIR/venv/bin/activate
cd $PROJECT_DIR
python3 -c "import database; database.init_database()"

# Reload systemd and start services
systemctl daemon-reload
systemctl enable vpn-manager
systemctl enable vpn-manager-health.timer
systemctl restart vpn-manager
systemctl start vpn-manager-health.timer

echo "✓ Service configured and started"
echo "✓ Health monitoring enabled (checks every 5 minutes)"

# Get server IP
SERVER_IP=$(curl -s ifconfig.me || echo "Unable to detect")

echo ""
echo "============================================"
echo "   ✓ Deployment Complete!"
echo "============================================"
echo ""
echo "Server IP: $SERVER_IP"
echo "WireGuard Public Key: $SERVER_PUBLIC_KEY"
echo ""
echo "Web Interface: http://$SERVER_IP:5001"
echo ""
echo "Login Credentials (from .env file):"
echo "  Check your .env file for ADMIN_USERNAME and ADMIN_PASSWORD"
echo ""
echo "Service Status:"
echo "  WireGuard: systemctl status wg-quick@wg0"
echo "  Web App:   systemctl status vpn-manager"
echo ""
echo "View Logs:"
echo "  WireGuard: journalctl -u wg-quick@wg0 -f"
echo "  Web App:   journalctl -u vpn-manager -f"
echo ""
echo "Check WireGuard:"
echo "  wg show wg0"
echo ""
echo "View iptables rules:"
echo "  iptables -t nat -L -n -v"
echo "  iptables -L FORWARD -n -v"
echo ""
echo "============================================"
echo ""
echo "IMPORTANT: For production, consider:"
echo "  1. Set up HTTPS with Caddy or Nginx"
echo "  2. Change default password"
echo "  3. Restrict web interface to specific IPs"
echo "  4. Set up monitoring and backups"
echo ""
echo "============================================"
