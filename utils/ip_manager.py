"""
IP Manager - Handles VPN IP allocation and release
"""
import ipaddress
import config
import database

def get_next_available_ip():
    """
    Find the next available IP in the VPN subnet
    Returns IP as string (e.g., '10.0.0.2')
    """
    # Get network object
    network = ipaddress.IPv4Network(config.VPN_SUBNET)
    
    # Get all currently allocated IPs
    allocated_ips = set(database.get_all_vpn_ips())
    
    # Add server IP to allocated set
    allocated_ips.add(config.VPN_SERVER_IP)
    
    # Find first available IP
    for ip in network.hosts():
        ip_str = str(ip)
        if ip_str not in allocated_ips:
            return ip_str
    
    raise Exception("No available IPs in subnet")

def is_ip_available(ip_address):
    """Check if an IP address is available"""
    if ip_address == config.VPN_SERVER_IP:
        return False
    
    allocated_ips = database.get_all_vpn_ips()
    return ip_address not in allocated_ips

def validate_ip_in_subnet(ip_address):
    """Validate that IP is in the VPN subnet"""
    try:
        ip = ipaddress.IPv4Address(ip_address)
        network = ipaddress.IPv4Network(config.VPN_SUBNET)
        return ip in network
    except:
        return False

def release_ip(vpn_ip):
    """
    Release an IP address (called when device is deleted)
    IP is automatically freed when device is removed from database
    """
    pass  # IP becomes available when device is deleted

def get_subnet_info():
    """Get information about the VPN subnet"""
    network = ipaddress.IPv4Network(config.VPN_SUBNET)
    allocated_ips = database.get_all_vpn_ips()
    
    total_ips = network.num_addresses - 2  # Exclude network and broadcast
    allocated_count = len(allocated_ips) + 1  # +1 for server
    available_count = total_ips - allocated_count
    
    return {
        'subnet': config.VPN_SUBNET,
        'server_ip': config.VPN_SERVER_IP,
        'total_ips': total_ips,
        'allocated': allocated_count,
        'available': available_count,
        'allocated_ips': sorted(allocated_ips + [config.VPN_SERVER_IP])
    }

if __name__ == '__main__':
    # Test IP manager
    print("Subnet Info:")
    info = get_subnet_info()
    for key, value in info.items():
        print(f"  {key}: {value}")
    
    print("\nNext available IP:", get_next_available_ip())
