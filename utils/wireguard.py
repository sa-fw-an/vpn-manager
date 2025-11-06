"""
WireGuard Management Module
Handles WireGuard key generation, peer management, config generation, and QR codes
"""
import subprocess
import os
import io
import base64
import tempfile
from datetime import datetime
import qrcode
import config

def run_command(cmd, check=True):
    """Run a shell command and return output"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=check
        )
        return result.stdout.strip(), result.returncode
    except subprocess.CalledProcessError as e:
        return e.stderr.strip(), e.returncode

def generate_keypair():
    """
    Generate WireGuard private and public key pair
    Returns: (private_key, public_key)
    """
    # Generate private key
    private_cmd = "wg genkey"
    private_key, code = run_command(private_cmd)
    
    if code != 0 or not private_key:
        raise Exception("Failed to generate private key")
    
    # Generate public key from private key
    public_cmd = f"echo '{private_key}' | wg pubkey"
    public_key, code = run_command(public_cmd)
    
    if code != 0 or not public_key:
        raise Exception("Failed to generate public key")
    
    return private_key, public_key

def get_server_public_key():
    """Get server's public key"""
    if os.path.exists(config.SERVER_PUBLIC_KEY_PATH):
        with open(config.SERVER_PUBLIC_KEY_PATH, 'r') as f:
            return f.read().strip()
    
    # If not found, try to get from private key
    if os.path.exists(config.SERVER_PRIVATE_KEY_PATH):
        with open(config.SERVER_PRIVATE_KEY_PATH, 'r') as f:
            private_key = f.read().strip()
        public_key, _ = run_command(f"echo '{private_key}' | wg pubkey")
        return public_key
    
    raise Exception("Server keys not found. Run setup script first.")

def get_server_endpoint():
    """Get server endpoint (IP:Port)"""
    # For local testing on macOS, use local IP
    if config.IS_MACOS:
        # Try to get local IP
        cmd = "ipconfig getifaddr en0 || ipconfig getifaddr en1"
        local_ip, code = run_command(cmd, check=False)
        if code == 0 and local_ip:
            return f"{local_ip}:{config.WIREGUARD_PORT}"
    
    # For Linux servers, try to get public IP
    if config.IS_LINUX:
        # Try to get public IP from external service
        cmd = "curl -s ifconfig.me || curl -s icanhazip.com || curl -s ipecho.net/plain"
        public_ip, code = run_command(cmd, check=False)
        if code == 0 and public_ip and public_ip != "":
            return f"{public_ip}:{config.WIREGUARD_PORT}"
    
    # Fallback to localhost for testing
    return f"127.0.0.1:{config.WIREGUARD_PORT}"

def add_peer_to_config(name, public_key, vpn_ip):
    """Add a peer to WireGuard configuration file"""
    if not os.path.exists(config.WIREGUARD_CONFIG_FILE):
        # Try to create config directory and basic file
        try:
            os.makedirs(config.WIREGUARD_CONFIG_DIR, exist_ok=True)
            # Create a basic config file
            with open(config.WIREGUARD_CONFIG_FILE, 'w') as f:
                f.write(f"""[Interface]
Address = {config.VPN_SERVER_IP}/24
ListenPort = {config.WIREGUARD_PORT}
# Note: Add PrivateKey here after running setup script

""")
        except PermissionError:
            raise Exception(f"Permission denied. Run: sudo mkdir -p {config.WIREGUARD_CONFIG_DIR} && sudo touch {config.WIREGUARD_CONFIG_FILE}")
    
    peer_config = f"""
# Peer: {name}
[Peer]
PublicKey = {public_key}
AllowedIPs = {vpn_ip}/32

"""
    
    # Append to config file
    try:
        with open(config.WIREGUARD_CONFIG_FILE, 'a') as f:
            f.write(peer_config)
    except PermissionError:
        raise Exception(f"Permission denied writing to {config.WIREGUARD_CONFIG_FILE}. Try: sudo chmod 644 {config.WIREGUARD_CONFIG_FILE}")
    
    return True

def remove_peer_from_config(public_key):
    """Remove a peer from WireGuard configuration file"""
    if not os.path.exists(config.WIREGUARD_CONFIG_FILE):
        return False
    
    with open(config.WIREGUARD_CONFIG_FILE, 'r') as f:
        lines = f.readlines()
    
    # Find and remove peer section
    new_lines = []
    skip_section = False
    
    for line in lines:
        if line.strip().startswith('# Peer:'):
            skip_section = True
        elif line.strip().startswith('[Peer]') and skip_section:
            continue
        elif line.strip().startswith('PublicKey =') and skip_section:
            if public_key in line:
                continue
            else:
                skip_section = False
        elif line.strip().startswith('AllowedIPs =') and skip_section:
            skip_section = False
            continue
        elif skip_section and line.strip() == '':
            skip_section = False
            continue
        
        if not skip_section:
            new_lines.append(line)
    
    # Write back
    with open(config.WIREGUARD_CONFIG_FILE, 'w') as f:
        f.writelines(new_lines)
    
    return True

def reload_wireguard():
    """
    Reload WireGuard configuration without restart
    Uses sudo -n to avoid password prompts (requires sudoers NOPASSWD setup)
    Falls back gracefully if sudo requires password
    
    Note: Configuration changes are saved to file. If reload fails,
    changes will take effect on next manual WireGuard restart.
    """
    interface = config.WIREGUARD_INTERFACE
    
    # Check if we can access wg without password
    test_cmd = f"sudo -n wg show interfaces 2>/dev/null"
    interfaces_output, code = run_command(test_cmd, check=False)
    
    if code != 0:
        # Can't run sudo commands without password
        # Config is saved, will work on next restart
        return True
    
    # Get the actual interface name (utun4, etc)
    actual_interface = interfaces_output.split()[0] if interfaces_output else None
    if not actual_interface:
        return True
    
    if config.IS_MACOS:
        # On macOS, wg syncconf requires stripped config (without [Interface])
        # Use wg-quick strip to generate it, then apply with syncconf
        strip_cmd = f"wg-quick strip {config.WIREGUARD_CONFIG_FILE} 2>/dev/null"
        stripped_config, code = run_command(strip_cmd, check=False)
        
        if code == 0 and stripped_config:
            # Apply the stripped config
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.conf') as tf:
                tf.write(stripped_config)
                temp_path = tf.name
            
            sync_cmd = f"sudo -n wg syncconf {actual_interface} {temp_path} 2>/dev/null"
            run_command(sync_cmd, check=False)
            os.unlink(temp_path)
    else:
        # On Linux, use wg-quick strip in a subshell
        cmd = f"sudo -n wg syncconf {interface} <(wg-quick strip {config.WIREGUARD_CONFIG_FILE}) 2>/dev/null"
        run_command(cmd, check=False)
    
    # Always return True - config is saved to file
    return True

def get_peer_status():
    """
    Get connection status of all peers
    Returns dict: {public_key: {'handshake': timestamp, 'online': bool}}
    
    Uses sudo -n (non-interactive) to avoid password prompts in web interface.
    Returns empty dict if wg command fails or requires password.
    """
    # Use sudo -n to avoid password prompt (will fail silently if password needed)
    cmd = f"sudo -n wg show {config.WIREGUARD_INTERFACE} dump 2>/dev/null"
    output, code = run_command(cmd, check=False)
    
    # If command failed (no sudo permissions or WireGuard not running), return empty
    if code != 0 or not output:
        return {}
    
    peers = {}
    lines = output.split('\n')
    
    # Skip header line
    for line in lines[1:]:
        if not line.strip():
            continue
        
        parts = line.split('\t')
        if len(parts) >= 5:
            public_key = parts[0]
            handshake_timestamp = parts[4]
            
            # Check if handshake is recent (within last 3 minutes)
            online = False
            handshake_time = None
            
            if handshake_timestamp != '0':
                try:
                    handshake_time = datetime.fromtimestamp(int(handshake_timestamp))
                    time_diff = (datetime.now() - handshake_time).total_seconds()
                    online = time_diff < 180  # 3 minutes
                except:
                    pass
            
            peers[public_key] = {
                'handshake': handshake_time,
                'online': online
            }
    
    return peers

def generate_client_config(device_name, private_key, public_key, vpn_ip):
    """
    Generate WireGuard client configuration
    Returns configuration as string
    """
    server_public_key = get_server_public_key()
    server_endpoint = get_server_endpoint()
    
    config_content = f"""[Interface]
PrivateKey = {private_key}
Address = {vpn_ip}/24
DNS = 1.1.1.1, 8.8.8.8

[Peer]
PublicKey = {server_public_key}
Endpoint = {server_endpoint}
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
"""
    
    return config_content

def generate_qr_code(config_content):
    """
    Generate QR code from config content
    Returns base64 encoded PNG image
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(config_content)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"

def check_wireguard_installed():
    """Check if WireGuard is installed"""
    output, code = run_command("which wg", check=False)
    return code == 0

def get_wireguard_status():
    """Get WireGuard interface status"""
    cmd = f"sudo wg show {config.WIREGUARD_INTERFACE}"
    output, code = run_command(cmd, check=False)
    return {
        'running': code == 0,
        'output': output
    }

if __name__ == '__main__':
    # Test functions
    print("Testing WireGuard module...")
    
    if check_wireguard_installed():
        print("✓ WireGuard is installed")
    else:
        print("✗ WireGuard is not installed")
    
    try:
        print("\nGenerating test keypair...")
        priv, pub = generate_keypair()
        print(f"  Private key: {priv[:20]}...")
        print(f"  Public key: {pub[:20]}...")
        
        print("\nGenerating test config...")
        config_content = generate_client_config("test-device", priv, pub, "10.0.0.99")
        print(config_content)
        
        print("\nGenerating QR code...")
        qr_data = generate_qr_code(config_content)
        print(f"  QR code length: {len(qr_data)} bytes")
        
    except Exception as e:
        print(f"Error: {e}")
