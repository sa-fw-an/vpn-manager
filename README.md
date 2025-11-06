# WireGuard VPN Manager

A web-based management system for WireGuard VPN with port forwarding capabilities. Supports both macOS and Ubuntu/Linux.

## Features

- 🔐 **Secure Web Interface** - Manage your VPN through a clean, responsive web UI
- 📱 **Device Management** - Add/remove VPN clients with automatic IP allocation
- 📲 **QR Code Generation** - Easy mobile device configuration
- 🔄 **Port Forwarding** - DNAT + SNAT port forwarding with pfctl (macOS) or iptables (Linux)
- 📊 **Real-time Status** - Monitor connected devices and data transfer
- 🌐 **Cross-platform** - Works on macOS and Ubuntu/Linux

## Quick Start

### Prerequisites

**macOS:**
- macOS 10.15 or later
- WireGuard installed: `brew install wireguard-tools`
- Python 3.8+

**Ubuntu/Linux:**
- Ubuntu 20.04+ or equivalent
- Python 3.8+

### Installation

1. **Clone the repository**
```bash
git clone <your-repo-url>
cd vpn-manager
```

2. **Create virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment**
```bash
cp .env.example .env
# Edit .env and change:
# - ADMIN_USERNAME
# - ADMIN_PASSWORD  
# - SECRET_KEY
```

5. **Initialize database**
```bash
python database.py
```

### macOS Setup

```bash
chmod +x setup_mac.sh
./setup_mac.sh
```

### Ubuntu Setup

```bash
chmod +x setup_ubuntu_server.sh
sudo ./setup_ubuntu_server.sh
```

### Run the Application

```bash
python app.py
```

Access at: **http://localhost:5001**

## Configuration

Configure via `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| `ADMIN_USERNAME` | Login username | `admin` |
| `ADMIN_PASSWORD` | Login password | `changeme` |
| `SECRET_KEY` | Flask secret key | Random |
| `DEBUG` | Debug mode | `False` |
| `FLASK_PORT` | Web port | `5001` |
| `VPN_SUBNET` | VPN subnet | `10.0.0.0/24` |
| `WIREGUARD_PORT` | VPN port | `51820` |

## Usage

### Add VPN Client

1. Login to web interface
2. Go to "Devices"
3. Click "Add Device"
4. Download config or scan QR code
5. Import to WireGuard client

### Port Forwarding

1. Go to "Port Forwards"  
2. Click "Add Forward"
3. Configure: Public Port → Target Port
4. Example: SSH via `ssh -p 8022 user@server-ip`

## Security

⚠️ **Important:**
1. Change default credentials in `.env`
2. Generate strong SECRET_KEY: `python -c 'import secrets; print(secrets.token_hex(32))'`
3. Never commit `.env` to git
4. Use HTTPS in production
5. Restrict web access to trusted networks

## Troubleshooting

### macOS

**Port in use:**
```bash
lsof -ti :5001 | xargs kill -9
```

**Permission denied:**
```bash
sudo chown -R $USER /usr/local/etc/wireguard
```

### Linux

**Service status:**
```bash
sudo systemctl status wg-quick@wg0
```

**Firewall check:**
```bash
sudo iptables -t nat -L -n -v
```

## License

MIT License

## Acknowledgments

- WireGuard® is a registered trademark of Jason A. Donenfeld
- Built with Flask and Bootstrap
