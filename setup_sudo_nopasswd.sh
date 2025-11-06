#!/bin/bash
# Setup passwordless sudo for WireGuard commands
# This allows the web interface to check VPN status without password prompts

echo "=========================================="
echo "Setting up passwordless sudo for WireGuard"
echo "=========================================="
echo ""

USER=$(whoami)
SUDOERS_FILE="/etc/sudoers.d/wireguard-vpn-manager"

echo "Creating sudoers rule for user: $USER"
echo ""

# Create sudoers entry
sudo bash -c "cat > $SUDOERS_FILE" << EOF
# Allow $USER to run WireGuard commands without password
# This is needed for the VPN Manager web interface
$USER ALL=(ALL) NOPASSWD: /usr/local/bin/wg
$USER ALL=(ALL) NOPASSWD: /usr/local/bin/wg-quick
$USER ALL=(ALL) NOPASSWD: /usr/bin/wg
$USER ALL=(ALL) NOPASSWD: /usr/bin/wg-quick
$USER ALL=(ALL) NOPASSWD: /sbin/pfctl
EOF

# Set proper permissions
sudo chmod 0440 $SUDOERS_FILE

# Validate sudoers syntax
if sudo visudo -c -f $SUDOERS_FILE; then
    echo "✓ Sudoers rule created successfully"
    echo ""
    echo "You can now run these commands without password:"
    echo "  - sudo wg"
    echo "  - sudo wg-quick"
    echo "  - sudo pfctl"
    echo ""
    echo "Testing..."
    if sudo -n wg show &>/dev/null; then
        echo "✓ Test successful! No password prompt."
    else
        echo "⚠️  Test failed. You may need to logout/login for changes to take effect."
    fi
else
    echo "❌ Sudoers syntax error! Removing file..."
    sudo rm -f $SUDOERS_FILE
    exit 1
fi

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Note: If prompted for password in web interface, try:"
echo "1. Logout and login to your Mac"
echo "2. Or restart the Flask app"
echo ""
