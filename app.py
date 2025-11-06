"""
VPN Manager - Main Flask Application
Web interface for WireGuard VPN and port forwarding management
"""
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
import os
import io
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import database
from utils import ip_manager, wireguard, firewall

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(seconds=config.PERMANENT_SESSION_LIFETIME)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User class for authentication
class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    if user_id == config.USERNAME:
        return User(user_id)
    return None

# ==================== Authentication Routes ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == config.USERNAME and password == config.PASSWORD:
            user = User(username)
            login_user(user, remember=True)
            session.permanent = True
            
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

# ==================== Main Routes ====================

@app.route('/')
@login_required
def index():
    return redirect(url_for('devices'))

@app.route('/devices')
@login_required
def devices():
    all_devices = database.get_all_devices()
    peer_status = wireguard.get_peer_status()
    
    # Enhance device info with status
    devices_with_status = []
    for device in all_devices:
        device_dict = dict(device)
        status = peer_status.get(device['public_key'], {'online': False, 'handshake': None})
        device_dict['online'] = status['online']
        device_dict['last_handshake'] = status['handshake']
        devices_with_status.append(device_dict)
    
    subnet_info = ip_manager.get_subnet_info()
    
    return render_template('devices.html', 
                         devices=devices_with_status, 
                         subnet_info=subnet_info,
                         wg_installed=wireguard.check_wireguard_installed())

@app.route('/devices/add', methods=['POST'])
@login_required
def add_device():
    try:
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        
        # Validate name
        if not name:
            flash('Device name is required', 'danger')
            return redirect(url_for('devices'))
        
        # Check if name already exists
        if database.get_device_by_name(name):
            flash(f'Device name "{name}" already exists', 'danger')
            return redirect(url_for('devices'))
        
        # Generate VPN IP
        vpn_ip = ip_manager.get_next_available_ip()
        
        # Generate WireGuard keys
        private_key, public_key = wireguard.generate_keypair()
        
        # Add to database
        device_id = database.add_device(name, description, vpn_ip, public_key, private_key)
        
        # Add peer to WireGuard config
        wireguard.add_peer_to_config(name, public_key, vpn_ip)
        wireguard.reload_wireguard()
        
        flash(f'Device "{name}" added successfully! VPN IP: {vpn_ip}', 'success')
        return redirect(url_for('devices'))
        
    except Exception as e:
        flash(f'Error adding device: {str(e)}', 'danger')
        return redirect(url_for('devices'))

@app.route('/devices/<int:device_id>/delete', methods=['POST'])
@login_required
def delete_device(device_id):
    try:
        device = database.get_device(device_id)
        if not device:
            flash('Device not found', 'danger')
            return redirect(url_for('devices'))
        
        # Get port forwards to remove
        forwards = database.get_port_forwards_by_device(device_id)
        
        # Remove port forward rules
        for forward in forwards:
            try:
                firewall.remove_port_forward(
                    device['vpn_ip'],
                    forward['public_port'],
                    forward['target_port'],
                    forward['protocol']
                )
            except Exception as e:
                print(f"Error removing port forward: {e}")
        
        # Remove from WireGuard config
        wireguard.remove_peer_from_config(device['public_key'])
        wireguard.reload_wireguard()
        
        # Delete from database (CASCADE will remove port forwards)
        database.delete_device(device_id)
        
        flash(f'Device "{device["name"]}" deleted successfully', 'success')
        
    except Exception as e:
        flash(f'Error deleting device: {str(e)}', 'danger')
    
    return redirect(url_for('devices'))

@app.route('/devices/<int:device_id>/config')
@login_required
def download_device_config(device_id):
    try:
        device = database.get_device(device_id)
        if not device:
            flash('Device not found', 'danger')
            return redirect(url_for('devices'))
        
        # Generate config
        config_content = wireguard.generate_client_config(
            device['name'],
            device['private_key'],
            device['public_key'],
            device['vpn_ip']
        )
        
        # Send as download
        buffer = io.BytesIO(config_content.encode('utf-8'))
        buffer.seek(0)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f'{device["name"]}.conf',
            mimetype='text/plain'
        )
        
    except Exception as e:
        flash(f'Error generating config: {str(e)}', 'danger')
        return redirect(url_for('devices'))

@app.route('/devices/<int:device_id>/qr')
@login_required
def device_qr_code(device_id):
    try:
        device = database.get_device(device_id)
        if not device:
            return jsonify({'error': 'Device not found'}), 404
        
        # Generate config
        config_content = wireguard.generate_client_config(
            device['name'],
            device['private_key'],
            device['public_key'],
            device['vpn_ip']
        )
        
        # Generate QR code
        qr_data = wireguard.generate_qr_code(config_content)
        
        return jsonify({'qr_code': qr_data})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/devices/status')
@login_required
def devices_status():
    """API endpoint for real-time device status"""
    try:
        peer_status = wireguard.get_peer_status()
        all_devices = database.get_all_devices()
        
        status_list = []
        for device in all_devices:
            status = peer_status.get(device['public_key'], {'online': False, 'handshake': None})
            status_list.append({
                'id': device['id'],
                'name': device['name'],
                'online': status['online'],
                'last_handshake': status['handshake'].isoformat() if status['handshake'] else None
            })
        
        return jsonify(status_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== Port Forward Routes ====================

@app.route('/port-forwards')
@login_required
def port_forwards():
    forwards = database.get_all_port_forwards()
    devices = database.get_all_devices()
    
    return render_template('port_forwards.html', 
                         forwards=forwards, 
                         devices=devices)

@app.route('/port-forwards/add', methods=['POST'])
@login_required
def add_port_forward():
    try:
        device_id = int(request.form.get('device_id'))
        public_port = int(request.form.get('public_port'))
        target_port = int(request.form.get('target_port'))
        protocol = request.form.get('protocol', 'tcp').lower()
        
        # Validate inputs
        if not (config.MIN_PUBLIC_PORT <= public_port <= config.MAX_PUBLIC_PORT):
            flash(f'Public port must be between {config.MIN_PUBLIC_PORT} and {config.MAX_PUBLIC_PORT}', 'danger')
            return redirect(url_for('port_forwards'))
        
        if not (1 <= target_port <= 65535):
            flash('Target port must be between 1 and 65535', 'danger')
            return redirect(url_for('port_forwards'))
        
        # Get device
        device = database.get_device(device_id)
        if not device:
            flash('Device not found', 'danger')
            return redirect(url_for('port_forwards'))
        
        # Check port availability
        protocols_to_check = ['tcp', 'udp'] if protocol == 'both' else [protocol]
        for proto in protocols_to_check:
            if not database.check_port_available(public_port, proto):
                flash(f'Port {public_port} ({proto.upper()}) is already in use', 'danger')
                return redirect(url_for('port_forwards'))
        
        # Add firewall rules
        firewall.add_port_forward(
            device['vpn_ip'],
            public_port,
            target_port,
            protocol
        )
        
        # Add to database
        for proto in protocols_to_check:
            database.add_port_forward(device_id, public_port, target_port, proto)
        
        flash(f'Port forward added: {public_port} → {device["name"]}:{target_port} ({protocol.upper()})', 'success')
        
    except ValueError:
        flash('Invalid port number', 'danger')
    except Exception as e:
        flash(f'Error adding port forward: {str(e)}', 'danger')
    
    return redirect(url_for('port_forwards'))

@app.route('/port-forwards/<int:forward_id>/delete', methods=['POST'])
@login_required
def delete_port_forward(forward_id):
    try:
        forward = database.get_port_forward(forward_id)
        if not forward:
            flash('Port forward not found', 'danger')
            return redirect(url_for('port_forwards'))
        
        # Remove firewall rule
        firewall.remove_port_forward(
            forward['device_ip'],
            forward['public_port'],
            forward['target_port'],
            forward['protocol']
        )
        
        # Delete from database
        database.delete_port_forward(forward_id)
        
        flash(f'Port forward deleted: {forward["public_port"]} ({forward["protocol"].upper()})', 'success')
        
    except Exception as e:
        flash(f'Error deleting port forward: {str(e)}', 'danger')
    
    return redirect(url_for('port_forwards'))

@app.route('/port-forwards/<int:forward_id>/toggle', methods=['POST'])
@login_required
def toggle_port_forward(forward_id):
    try:
        forward = database.get_port_forward(forward_id)
        if not forward:
            return jsonify({'error': 'Port forward not found'}), 404
        
        new_state = not forward['enabled']
        
        if new_state:
            # Enable: add firewall rule
            firewall.add_port_forward(
                forward['device_ip'],
                forward['public_port'],
                forward['target_port'],
                forward['protocol']
            )
        else:
            # Disable: remove firewall rule
            firewall.remove_port_forward(
                forward['device_ip'],
                forward['public_port'],
                forward['target_port'],
                forward['protocol']
            )
        
        # Update database
        database.update_port_forward(forward_id, enabled=new_state)
        
        return jsonify({
            'success': True, 
            'enabled': new_state,
            'message': f'Port forward {"enabled" if new_state else "disabled"}'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== System Info Routes ====================

@app.route('/system')
@login_required
def system_info():
    """Display system information"""
    wg_status = wireguard.get_wireguard_status()
    subnet_info = ip_manager.get_subnet_info()
    fw_configured = firewall.check_firewall_configured()
    
    return render_template('system.html',
                         wg_status=wg_status,
                         subnet_info=subnet_info,
                         fw_configured=fw_configured,
                         platform='macOS' if config.IS_MACOS else 'Linux')

# ==================== Error Handlers ====================

@app.route('/favicon.ico')
def favicon():
    """Return empty response for favicon to avoid 404 errors"""
    return '', 204

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

# ==================== Application Initialization ====================

def init_app():
    """Initialize application"""
    print("=" * 50)
    print("VPN Manager - Initializing...")
    print("=" * 50)
    
    # Initialize database
    if not os.path.exists(config.DATABASE_PATH):
        print("\n📊 Creating database...")
        database.init_database()
    else:
        print("\n✓ Database exists")
    
    # Check WireGuard
    if wireguard.check_wireguard_installed():
        print("✓ WireGuard is installed")
    else:
        print("⚠️  WireGuard is not installed")
        print("   Run setup_mac.sh to install")
    
    # Check firewall
    if firewall.check_firewall_configured():
        print("✓ Firewall is configured")
    else:
        print("⚠️  Firewall not configured")
        print("   Run setup_mac.sh to configure")
    
    print("\n" + "=" * 50)
    print("🚀 VPN Manager Ready!")
    print("=" * 50)
    print(f"\n📱 Web Interface: http://localhost:5001")
    print(f"👤 Username: {config.USERNAME}")
    print(f"🔒 Password: {config.PASSWORD}")
    print("\n" + "=" * 50 + "\n")

if __name__ == '__main__':
    init_app()
    app.run(host='0.0.0.0', port=config.FLASK_PORT, debug=config.DEBUG)
