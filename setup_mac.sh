#!/bin/bash
#
# VPN Manager Setup Script for macOS
# This script installs WireGuard, configures pfctl firewall, and sets up the VPN server
#

set -e

echo "============================================"
echo "   VPN Manager - macOS Setup Script"
echo "============================================"
echo ""

# Check if running on macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo "Error: This script is for macOS only!"
    echo "For Ubuntu, use deploy_ubuntu.sh"
    exit 1
fi

# Check if running as root (needed for some operations)
if [[ $EUID -eq 0 ]]; then
   echo "Warning: Don't run this script as root. It will use sudo when needed."
   echo "Run as: bash setup_mac.sh"
   exit 1
fi

# 1. Install Homebrew if not installed
echo "[1/8] Checking Homebrew..."
if ! command -v brew &> /dev/null; then
    echo "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo "✓ Homebrew is installed"
fi

# 2. Install WireGuard
echo ""
echo "[2/8] Installing WireGuard..."
if ! command -v wg &> /dev/null; then
    brew install wireguard-tools
    echo "✓ WireGuard installed"
else
    echo "✓ WireGuard already installed"
fi

# 3. Install Python dependencies
echo ""
echo "[3/8] Installing Python dependencies..."
if ! command -v python3 &> /dev/null; then
    echo "Installing Python 3..."
    brew install python3
fi

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

echo "Installing Python packages..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "✓ Python dependencies installed"

# 4. Create WireGuard directories
echo ""
echo "[4/8] Setting up WireGuard directories..."
sudo mkdir -p /usr/local/etc/wireguard
sudo chmod 700 /usr/local/etc/wireguard

# 5. Generate server keys if they don't exist
echo ""
echo "[5/8] Generating WireGuard server keys..."
if [ ! -f /usr/local/etc/wireguard/server_private.key ]; then
    wg genkey | sudo tee /usr/local/etc/wireguard/server_private.key | wg pubkey | sudo tee /usr/local/etc/wireguard/server_public.key
    sudo chmod 600 /usr/local/etc/wireguard/server_private.key
    sudo chmod 644 /usr/local/etc/wireguard/server_public.key
    echo "✓ Server keys generated"
else
    echo "✓ Server keys already exist"
fi

SERVER_PRIVATE_KEY=$(sudo cat /usr/local/etc/wireguard/server_private.key)
SERVER_PUBLIC_KEY=$(sudo cat /usr/local/etc/wireguard/server_public.key)

echo "Server Public Key: $SERVER_PUBLIC_KEY"

# 6. Create WireGuard configuration
echo ""
echo "[6/8] Creating WireGuard configuration..."
sudo tee /usr/local/etc/wireguard/wg0.conf > /dev/null <<EOF
[Interface]
Address = 10.0.0.1/24
ListenPort = 51820
PrivateKey = $SERVER_PRIVATE_KEY

# Peers will be added dynamically by the web interface
EOF

sudo chmod 600 /usr/local/etc/wireguard/wg0.conf
echo "✓ WireGuard config created at /usr/local/etc/wireguard/wg0.conf"

# 7. Configure pfctl (macOS firewall)
echo ""
echo "[7/8] Configuring pfctl firewall..."

# Create anchor file
sudo mkdir -p /etc/pf.anchors
sudo tee /etc/pf.anchors/vpn-manager > /dev/null <<'EOF'
# VPN Manager port forwarding rules
# Rules will be added dynamically by the web interface
# Format: rdr pass on <interface> proto tcp from any to any port <public_port> -> <vpn_ip> port <target_port>
EOF

echo "✓ Created /etc/pf.anchors/vpn-manager"

# Check if our anchor is in pf.conf
if ! sudo grep -q "vpn-manager" /etc/pf.conf; then
    echo ""
    echo "⚠️  IMPORTANT: Manual step required!"
    echo ""
    echo "Add the following lines to /etc/pf.conf:"
    echo ""
    echo "# VPN Manager anchor (add before the last line)"
    echo "rdr-anchor \"vpn-manager\""
    echo "nat-anchor \"vpn-manager\""
    echo "load anchor \"vpn-manager\" from \"/etc/pf.anchors/vpn-manager\""
    echo ""
    echo "Then run: sudo pfctl -f /etc/pf.conf"
    echo ""
    read -p "Press Enter after you've added these lines..."
fi

# Enable IP forwarding
echo ""
echo "Enabling IP forwarding..."
sudo sysctl -w net.inet.ip.forwarding=1
sudo sysctl -w net.inet6.ip6.forwarding=1

# Make IP forwarding persistent
if ! grep -q "net.inet.ip.forwarding=1" /etc/sysctl.conf 2>/dev/null; then
    echo "net.inet.ip.forwarding=1" | sudo tee -a /etc/sysctl.conf
    echo "net.inet6.ip6.forwarding=1" | sudo tee -a /etc/sysctl.conf
fi

echo "✓ IP forwarding enabled"

# Enable pfctl
sudo pfctl -e 2>/dev/null || true
sudo pfctl -f /etc/pf.conf

# 8. Initialize database
echo ""
echo "[8/8] Initializing database..."
source venv/bin/activate
python3 database.py
echo "✓ Database initialized"

# Start WireGuard
echo ""
echo "Starting WireGuard interface..."
sudo wg-quick up wg0 2>/dev/null || echo "Note: WireGuard interface already up or failed to start"

echo ""
echo "============================================"
echo "   ✓ Setup Complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Start the web interface:"
echo "   source venv/bin/activate"
echo "   python3 app.py"
echo ""
echo "2. Open your browser:"
echo "   http://localhost:5001"
echo ""
echo "3. Login credentials (from .env file):"
echo "   Check your .env file for ADMIN_USERNAME and ADMIN_PASSWORD"
echo ""
echo "4. Check WireGuard status:"
echo "   sudo wg show wg0"
echo ""
echo "5. View pfctl rules:"
echo "   sudo pfctl -sr"
echo "   sudo pfctl -sn"
echo ""
echo "============================================"
echo ""
echo "To stop WireGuard:"
echo "   sudo wg-quick down wg0"
echo ""
echo "To restart after reboot:"
echo "   sudo wg-quick up wg0"
echo ""
echo "============================================"
