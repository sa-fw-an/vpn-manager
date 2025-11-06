#!/bin/bash
# VPN Manager Health Check Script
# This script monitors the health of VPN services and auto-heals if needed

LOG_FILE="/var/log/vpn-manager-health.log"

log() {
    echo "$(date "+%Y-%m-%d %H:%M:%S") - $1" | tee -a "$LOG_FILE"
}

# Check if VPN Manager service is running
check_vpn_manager() {
    if ! systemctl is-active --quiet vpn-manager; then
        log "ERROR: vpn-manager service is not running. Attempting restart..."
        systemctl restart vpn-manager
        sleep 3
        if systemctl is-active --quiet vpn-manager; then
            log "SUCCESS: vpn-manager service restarted successfully"
        else
            log "CRITICAL: Failed to restart vpn-manager service"
            return 1
        fi
    fi
    return 0
}

# Check if WireGuard is running
check_wireguard() {
    if ! systemctl is-active --quiet wg-quick@wg0; then
        log "ERROR: WireGuard service is not running. Attempting restart..."
        systemctl restart wg-quick@wg0
        sleep 3
        if systemctl is-active --quiet wg-quick@wg0; then
            log "SUCCESS: WireGuard service restarted successfully"
        else
            log "CRITICAL: Failed to restart WireGuard service"
            return 1
        fi
    fi
    return 0
}

# Check if WireGuard interface exists
check_wg_interface() {
    if ! ip link show wg0 &>/dev/null; then
        log "ERROR: WireGuard interface wg0 does not exist. Restarting WireGuard..."
        systemctl restart wg-quick@wg0
        sleep 3
        if ip link show wg0 &>/dev/null; then
            log "SUCCESS: WireGuard interface restored"
        else
            log "CRITICAL: Failed to restore WireGuard interface"
            return 1
        fi
    fi
    return 0
}

# Check if web interface is responding
check_web_interface() {
    if ! curl -sf http://localhost:5001/ > /dev/null 2>&1; then
        log "ERROR: Web interface not responding. Restarting vpn-manager..."
        systemctl restart vpn-manager
        sleep 5
        if curl -sf http://localhost:5001/ > /dev/null 2>&1; then
            log "SUCCESS: Web interface restored"
        else
            log "WARNING: Web interface still not responding after restart"
            return 1
        fi
    fi
    return 0
}

# Check firewall rules
check_firewall() {
    if ! iptables -t nat -C POSTROUTING -o eth0 -j MASQUERADE 2>/dev/null; then
        log "ERROR: NAT rule missing. Restoring..."
        iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
        log "SUCCESS: NAT rule restored"
    fi
    
    if ! iptables -C FORWARD -i wg0 -j ACCEPT 2>/dev/null; then
        log "ERROR: FORWARD rule missing. Restoring..."
        iptables -A FORWARD -i wg0 -j ACCEPT
        log "SUCCESS: FORWARD rule restored"
    fi
}

# Main health check
main() {
    # Run all checks
    check_vpn_manager
    check_wireguard
    check_wg_interface
    check_web_interface
    check_firewall
    
    log "Health check completed"
}

main
