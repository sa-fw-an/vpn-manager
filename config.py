"""
Configuration settings for VPN Manager
Loads configuration from environment variables (.env file)
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base directory
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Flask settings
SECRET_KEY = os.getenv('SECRET_KEY', 'vpn-manager-secret-key-change-in-production')
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')
FLASK_PORT = int(os.getenv('FLASK_PORT', '5001'))

# Database
DATABASE_PATH = os.getenv('DATABASE_PATH') or os.path.join(BASE_DIR, 'database.db')

# Authentication
USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
PASSWORD = os.getenv('ADMIN_PASSWORD', 'changeme')

# VPN Settings
VPN_SUBNET = os.getenv('VPN_SUBNET', '10.0.0.0/24')
VPN_SERVER_IP = os.getenv('VPN_SERVER_IP', '10.0.0.1')
VPN_START_IP = os.getenv('VPN_START_IP', '10.0.0.2')
WIREGUARD_PORT = int(os.getenv('WIREGUARD_PORT', '51820'))
WIREGUARD_INTERFACE = os.getenv('WIREGUARD_INTERFACE', 'wg0')

# Platform detection
import platform
IS_MACOS = platform.system() == 'Darwin'
IS_LINUX = platform.system() == 'Linux'

# WireGuard paths and keys
if os.getenv('WIREGUARD_CONFIG_DIR'):
    WIREGUARD_CONFIG_DIR = os.getenv('WIREGUARD_CONFIG_DIR')
elif IS_LINUX:
    WIREGUARD_CONFIG_DIR = '/etc/wireguard'
else:  # macOS
    WIREGUARD_CONFIG_DIR = '/usr/local/etc/wireguard'

WIREGUARD_CONFIG_FILE = f'{WIREGUARD_CONFIG_DIR}/{WIREGUARD_INTERFACE}.conf'
SERVER_PRIVATE_KEY_PATH = f'{WIREGUARD_CONFIG_DIR}/server_private.key'
SERVER_PUBLIC_KEY_PATH = f'{WIREGUARD_CONFIG_DIR}/server_public.key'

# Network interface
PUBLIC_INTERFACE = os.getenv('PUBLIC_INTERFACE') or None

# Port forwarding range
MIN_PUBLIC_PORT = int(os.getenv('MIN_PUBLIC_PORT', '1024'))
MAX_PUBLIC_PORT = int(os.getenv('MAX_PUBLIC_PORT', '65535'))

# Session timeout
SESSION_TIMEOUT_HOURS = int(os.getenv('SESSION_TIMEOUT_HOURS', '24'))
PERMANENT_SESSION_LIFETIME = SESSION_TIMEOUT_HOURS * 3600

# Auto-detect settings for Linux if not set
if IS_LINUX and not os.getenv('WIREGUARD_CONFIG_DIR'):
    WIREGUARD_CONFIG_DIR = '/etc/wireguard'
    WIREGUARD_CONFIG_FILE = f'{WIREGUARD_CONFIG_DIR}/{WIREGUARD_INTERFACE}.conf'
    SERVER_PRIVATE_KEY_PATH = f'{WIREGUARD_CONFIG_DIR}/server_private.key'
    SERVER_PUBLIC_KEY_PATH = f'{WIREGUARD_CONFIG_DIR}/server_public.key'
    PUBLIC_INTERFACE = 'eth0'
