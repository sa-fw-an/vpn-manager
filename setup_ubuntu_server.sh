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
apt install -y \
    wireguard \
    python3 \
    python3-pip \
    python3-venv \
    iptables-persistent \
    qrencode \
    curl \
    git \
    ufw

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
pip install -r $PROJECT_DIR/requirements.txt
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

# 9. Configure UFW firewall
echo ""
echo "[9/10] Configuring firewall..."

# Allow SSH (important!)
ufw allow 22/tcp

# Allow WireGuard
ufw allow 51820/udp

# Allow web interface
ufw allow 5001/tcp

# Allow port forwarding range
ufw allow 1024:65535/tcp
ufw allow 1024:65535/udp

# Enable UFW
ufw --force enable

echo "✓ Firewall configured"

# 10. Create systemd service for web app
echo ""
echo "[10/10] Creating systemd service..."

cat > /etc/systemd/system/vpn-manager.service <<EOF
[Unit]
Description=VPN Manager Web Interface
After=network.target wg-quick@wg0.service

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Initialize database
source $PROJECT_DIR/venv/bin/activate
cd $PROJECT_DIR
python3 database.py

# Reload systemd and start service
systemctl daemon-reload
systemctl enable vpn-manager
systemctl restart vpn-manager

echo "✓ Service configured and started"

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
