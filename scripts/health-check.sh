#!/bin/bash
# VPN Manager Health Check Script
# This script monitors the health of VPN services and auto-heals if needed

LOG_FILE="/var/log/vpn-manager-health.log"
LOG_MAX_AGE_DAYS=3

log() {
    echo "$(date "+%Y-%m-%d %H:%M:%S") - $1" | tee -a "$LOG_FILE"
}

# Cleanup old logs (delete entries older than 3 days)
cleanup_logs() {
    if [ -f "$LOG_FILE" ]; then
        # Get date 3 days ago in epoch
        three_days_ago=$(date -d "3 days ago" +%s 2>/dev/null || date -v-3d +%s)
        
        # Create temporary file for new logs
        temp_log="/tmp/vpn-health-clean.log"
        
        # Keep only logs from last 3 days
        while IFS= read -r line; do
            log_date=$(echo "$line" | grep -oP '^\d{4}-\d{2}-\d{2}' || echo "")
            if [ -n "$log_date" ]; then
                log_epoch=$(date -d "$log_date" +%s 2>/dev/null || date -j -f "%Y-%m-%d" "$log_date" +%s 2>/dev/null)
                if [ "$log_epoch" -ge "$three_days_ago" ]; then
                    echo "$line" >> "$temp_log"
                fi
            fi
        done < "$LOG_FILE"
        
        # Replace old log with cleaned version
        if [ -f "$temp_log" ]; then
            mv "$temp_log" "$LOG_FILE"
            chmod 644 "$LOG_FILE"
        fi
    fi
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
    # Cleanup old logs first
    cleanup_logs
    
    # Run all checks
    check_vpn_manager
    check_wireguard
    check_wg_interface
    check_web_interface
    check_firewall
    
    log "Health check completed"
}

main
