#!/bin/bash
# Setup WireGuard client on Ubuntu
# This script will be copied to the Ubuntu machine and run there

echo "=========================================="
echo "WireGuard Client Setup for Ubuntu"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root: sudo bash setup_ubuntu_client.sh"
    exit 1
fi

# Install WireGuard
echo "Step 1: Installing WireGuard..."
apt-get update -qq
apt-get install -y wireguard wireguard-tools resolvconf
echo "✓ WireGuard installed"
echo ""

# Create WireGuard directory
echo "Step 2: Creating WireGuard directory..."
mkdir -p /etc/wireguard
chmod 700 /etc/wireguard
echo "✓ Directory created"
echo ""

echo "=========================================="
echo "✅ WireGuard installed successfully!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Copy the config file from the web interface to this machine"
echo "2. Save it as /etc/wireguard/wg0.conf"
echo "3. Run: sudo wg-quick up wg0"
echo "4. Test: ping 10.0.0.1"
echo ""
