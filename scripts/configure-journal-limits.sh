#!/bin/bash
# Configure systemd journal limits
# Limits journal size to 10MB and auto-cleanup after 3 days

echo "Configuring systemd journal limits..."

# Create journal configuration directory if it doesn't exist
mkdir -p /etc/systemd/journald.conf.d/

# Create journal limits configuration
cat > /etc/systemd/journald.conf.d/vpn-manager.conf << 'EOF'
[Journal]
# Limit journal size to 10MB
SystemMaxUse=10M
SystemKeepFree=50M
SystemMaxFileSize=2M

# Delete logs older than 3 days
MaxRetentionSec=3d

# Compress logs
Compress=yes

# Forward to syslog (optional)
ForwardToSyslog=no
EOF

# Restart systemd-journald to apply changes
systemctl restart systemd-journald

echo "Journal limits configured successfully!"
echo "  - Max journal size: 10MB"
echo "  - Max retention: 3 days"
echo "  - Compression: enabled"

# Clean up old journal files immediately
journalctl --vacuum-size=10M
journalctl --vacuum-time=3d

echo "Old journal files cleaned up"
