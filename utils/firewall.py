"""
Firewall Management Module
Handles NAT rules for port forwarding using pfctl (macOS) or iptables (Linux)
Implements DNAT (destination NAT) and SNAT (source NAT/masquerade)
"""
import subprocess
import os
import config

def run_command(cmd, check=True):
    """Run a shell command"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=check
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.CalledProcessError as e:
        return e.stdout.strip(), e.stderr.strip(), e.returncode

# ============= macOS pfctl Functions =============

def add_port_forward_macos(device_ip, public_port, target_port, protocol):
    """
    Add port forward rule on macOS using pfctl
    Creates both DNAT (rdr) and SNAT (nat) rules
    """
    # Get the public interface
    interface = get_public_interface_macos()
    
    # Create anchor file path
    anchor_file = '/etc/pf.anchors/vpn-manager'
    
    # Read existing rules
    rules = []
    if os.path.exists(anchor_file):
        with open(anchor_file, 'r') as f:
            rules = f.readlines()
    
    # Create new rules (both rdr for DNAT and nat for SNAT)
    proto = protocol.lower()
    
    # DNAT rule: redirect incoming traffic to VPN client
    rdr_rule = f"rdr pass on {interface} inet proto {proto} from any to any port {public_port} -> {device_ip} port {target_port}\n"
    
    # SNAT rule: masquerade outgoing traffic from VPN to appear from server
    nat_rule = f"nat on {interface} inet proto {proto} from {device_ip} to any -> ({interface})\n"
    
    # Add rules if not already present
    if rdr_rule not in rules:
        rules.append(rdr_rule)
    if nat_rule not in rules:
        rules.append(nat_rule)
    
    # Write rules back
    try:
        with open(anchor_file, 'w') as f:
            f.writelines(rules)
    except PermissionError:
        # Try with sudo
        temp_file = '/tmp/vpn-manager-rules.tmp'
        with open(temp_file, 'w') as f:
            f.writelines(rules)
        run_command(f"sudo mv {temp_file} {anchor_file}")
    
    # Reload pfctl
    reload_pfctl_macos()
    
    return True

def remove_port_forward_macos(device_ip, public_port, target_port, protocol):
    """Remove port forward rule on macOS"""
    anchor_file = '/etc/pf.anchors/vpn-manager'
    
    if not os.path.exists(anchor_file):
        return True
    
    with open(anchor_file, 'r') as f:
        rules = f.readlines()
    
    proto = protocol.lower()
    
    # Filter out matching rules
    new_rules = []
    for rule in rules:
        # Skip if this is the rule we want to delete
        if f"port {public_port}" in rule and f"{device_ip}" in rule and f"proto {proto}" in rule:
            continue
        new_rules.append(rule)
    
    # Write back
    try:
        with open(anchor_file, 'w') as f:
            f.writelines(new_rules)
    except PermissionError:
        temp_file = '/tmp/vpn-manager-rules.tmp'
        with open(temp_file, 'w') as f:
            f.writelines(new_rules)
        run_command(f"sudo mv {temp_file} {anchor_file}")
    
    reload_pfctl_macos()
    return True

def reload_pfctl_macos():
    """Reload pfctl rules"""
    # Check if our anchor is loaded in main pf.conf
    cmd = "sudo pfctl -sr | grep 'anchor \"vpn-manager\"'"
    stdout, stderr, code = run_command(cmd, check=False)
    
    if code != 0:
        print("Warning: vpn-manager anchor not found in pf.conf")
        print("You may need to add it manually. See setup_mac.sh")
    
    # Reload rules
    run_command("sudo pfctl -f /etc/pf.conf", check=False)
    run_command("sudo pfctl -e", check=False)  # Enable if not already enabled
    
    return True

def get_public_interface_macos():
    """Detect the primary network interface on macOS"""
    if config.PUBLIC_INTERFACE:
        return config.PUBLIC_INTERFACE
    
    # Try to detect active interface
    cmd = "route -n get default | grep interface | awk '{print $2}'"
    stdout, stderr, code = run_command(cmd, check=False)
    
    if code == 0 and stdout:
        return stdout.strip()
    
    # Fallback to common interfaces
    for iface in ['en0', 'en1']:
        cmd = f"ifconfig {iface} | grep 'inet ' | grep -v '127.0.0.1'"
        stdout, stderr, code = run_command(cmd, check=False)
        if code == 0 and stdout:
            return iface
    
    return 'en0'  # Default fallback

def list_port_forwards_macos():
    """List all active port forward rules on macOS"""
    anchor_file = '/etc/pf.anchors/vpn-manager'
    
    if not os.path.exists(anchor_file):
        return []
    
    with open(anchor_file, 'r') as f:
        rules = f.readlines()
    
    forwards = []
    for rule in rules:
        if 'rdr pass' in rule:
            # Parse rule to extract details
            # Format: rdr pass on en0 inet proto tcp from any to any port 8000 -> 10.0.0.2 port 22
            parts = rule.split()
            try:
                proto_idx = parts.index('proto') + 1
                port_idx = parts.index('port', 0)
                target_idx = parts.index('->')
                
                protocol = parts[proto_idx]
                public_port = parts[port_idx + 1]
                device_ip = parts[target_idx + 1]
                target_port = parts[target_idx + 3]
                
                forwards.append({
                    'protocol': protocol,
                    'public_port': public_port,
                    'device_ip': device_ip,
                    'target_port': target_port
                })
            except:
                continue
    
    return forwards

# ============= Linux iptables Functions =============

def add_port_forward_linux(device_ip, public_port, target_port, protocol):
    """
    Add port forward rule on Linux using iptables
    Creates DNAT, FORWARD, and SNAT rules
    """
    interface = config.PUBLIC_INTERFACE or 'eth0'
    wg_interface = config.WIREGUARD_INTERFACE
    proto = protocol.lower()
    
    # DNAT rule: rewrite destination
    dnat_cmd = f"sudo iptables -t nat -A PREROUTING -i {interface} -p {proto} --dport {public_port} -j DNAT --to-destination {device_ip}:{target_port}"
    
    # FORWARD rule: allow forwarded traffic
    forward_cmd = f"sudo iptables -A FORWARD -i {interface} -o {wg_interface} -p {proto} -d {device_ip} --dport {target_port} -m state --state NEW,ESTABLISHED,RELATED -j ACCEPT"
    
    # SNAT rule: masquerade return traffic
    snat_cmd = f"sudo iptables -t nat -A POSTROUTING -o {wg_interface} -p {proto} -d {device_ip} --dport {target_port} -j MASQUERADE"
    
    # Execute commands
    run_command(dnat_cmd)
    run_command(forward_cmd)
    run_command(snat_cmd)
    
    # Save rules
    save_iptables_linux()
    
    return True

def remove_port_forward_linux(device_ip, public_port, target_port, protocol):
    """Remove port forward rule on Linux"""
    interface = config.PUBLIC_INTERFACE or 'eth0'
    wg_interface = config.WIREGUARD_INTERFACE
    proto = protocol.lower()
    
    # Remove DNAT rule
    dnat_cmd = f"sudo iptables -t nat -D PREROUTING -i {interface} -p {proto} --dport {public_port} -j DNAT --to-destination {device_ip}:{target_port}"
    
    # Remove FORWARD rule
    forward_cmd = f"sudo iptables -D FORWARD -i {interface} -o {wg_interface} -p {proto} -d {device_ip} --dport {target_port} -m state --state NEW,ESTABLISHED,RELATED -j ACCEPT"
    
    # Remove SNAT rule
    snat_cmd = f"sudo iptables -t nat -D POSTROUTING -o {wg_interface} -p {proto} -d {device_ip} --dport {target_port} -j MASQUERADE"
    
    # Execute commands (ignore errors if rules don't exist)
    run_command(dnat_cmd, check=False)
    run_command(forward_cmd, check=False)
    run_command(snat_cmd, check=False)
    
    save_iptables_linux()
    
    return True

def save_iptables_linux():
    """Save iptables rules to persist across reboots"""
    run_command("sudo iptables-save | sudo tee /etc/iptables/rules.v4 > /dev/null", check=False)
    return True

def list_port_forwards_linux():
    """List all active port forward rules on Linux"""
    cmd = "sudo iptables -t nat -L PREROUTING -n --line-numbers"
    stdout, stderr, code = run_command(cmd, check=False)
    
    if code != 0:
        return []
    
    # Parse iptables output
    forwards = []
    lines = stdout.split('\n')[2:]  # Skip header
    
    for line in lines:
        if 'DNAT' in line:
            parts = line.split()
            try:
                protocol = parts[2]
                dport_part = [p for p in parts if 'dpt:' in p][0]
                public_port = dport_part.split(':')[1]
                to_part = [p for p in parts if 'to:' in p][0]
                target = to_part.split(':')[1]
                device_ip, target_port = target.split(':')
                
                forwards.append({
                    'protocol': protocol,
                    'public_port': public_port,
                    'device_ip': device_ip,
                    'target_port': target_port
                })
            except:
                continue
    
    return forwards

# ============= Platform-agnostic wrapper functions =============

def add_port_forward(device_ip, public_port, target_port, protocol):
    """Add port forward rule (platform-agnostic)"""
    protocol = protocol.lower()
    
    if protocol == 'both':
        # Apply rules for both TCP and UDP
        add_port_forward(device_ip, public_port, target_port, 'tcp')
        add_port_forward(device_ip, public_port, target_port, 'udp')
        return True
    
    if config.IS_MACOS:
        return add_port_forward_macos(device_ip, public_port, target_port, protocol)
    elif config.IS_LINUX:
        return add_port_forward_linux(device_ip, public_port, target_port, protocol)
    else:
        raise Exception("Unsupported platform")

def remove_port_forward(device_ip, public_port, target_port, protocol):
    """Remove port forward rule (platform-agnostic)"""
    protocol = protocol.lower()
    
    if protocol == 'both':
        remove_port_forward(device_ip, public_port, target_port, 'tcp')
        remove_port_forward(device_ip, public_port, target_port, 'udp')
        return True
    
    if config.IS_MACOS:
        return remove_port_forward_macos(device_ip, public_port, target_port, protocol)
    elif config.IS_LINUX:
        return remove_port_forward_linux(device_ip, public_port, target_port, protocol)
    else:
        raise Exception("Unsupported platform")

def list_port_forwards():
    """List all active port forward rules (platform-agnostic)"""
    if config.IS_MACOS:
        return list_port_forwards_macos()
    elif config.IS_LINUX:
        return list_port_forwards_linux()
    else:
        return []

def check_firewall_configured():
    """Check if firewall is properly configured"""
    if config.IS_MACOS:
        # Check if pf anchor exists
        anchor_file = '/etc/pf.anchors/vpn-manager'
        return os.path.exists(anchor_file)
    elif config.IS_LINUX:
        # Check if iptables is installed
        stdout, stderr, code = run_command("which iptables", check=False)
        return code == 0
    return False

if __name__ == '__main__':
    print(f"Platform: {'macOS' if config.IS_MACOS else 'Linux' if config.IS_LINUX else 'Unknown'}")
    print(f"Firewall configured: {check_firewall_configured()}")
    
    if config.IS_MACOS:
        print(f"Public interface: {get_public_interface_macos()}")
    
    print("\nCurrent port forwards:")
    forwards = list_port_forwards()
    for fwd in forwards:
        print(f"  {fwd['protocol'].upper()} {fwd['public_port']} -> {fwd['device_ip']}:{fwd['target_port']}")
