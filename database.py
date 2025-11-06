"""
Database module for VPN Manager
Handles SQLite database operations for devices and port forwards
"""
import sqlite3
from datetime import datetime
from contextlib import contextmanager
import config

@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_database():
    """Initialize database tables"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Devices table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                vpn_ip TEXT UNIQUE NOT NULL,
                public_key TEXT UNIQUE NOT NULL,
                private_key TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_handshake TIMESTAMP
            )
        ''')
        
        # Port forwards table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS port_forwards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                public_port INTEGER NOT NULL,
                target_port INTEGER NOT NULL,
                protocol TEXT NOT NULL,
                enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                UNIQUE(public_port, protocol)
            )
        ''')
        
        conn.commit()
        print("✓ Database initialized successfully")

# Device operations
def add_device(name, description, vpn_ip, public_key, private_key):
    """Add a new device to the database"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO devices (name, description, vpn_ip, public_key, private_key)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, description, vpn_ip, public_key, private_key))
        return cursor.lastrowid

def get_device(device_id):
    """Get device by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM devices WHERE id = ?', (device_id,))
        return cursor.fetchone()

def get_device_by_name(name):
    """Get device by name"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM devices WHERE name = ?', (name,))
        return cursor.fetchone()

def get_device_by_ip(vpn_ip):
    """Get device by VPN IP"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM devices WHERE vpn_ip = ?', (vpn_ip,))
        return cursor.fetchone()

def get_all_devices():
    """Get all devices"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM devices ORDER BY created_at DESC')
        return cursor.fetchall()

def update_device_handshake(vpn_ip, handshake_time):
    """Update last handshake time for a device"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE devices SET last_handshake = ? WHERE vpn_ip = ?
        ''', (handshake_time, vpn_ip))

def delete_device(device_id):
    """Delete a device and its port forwards (CASCADE)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM devices WHERE id = ?', (device_id,))
        return cursor.rowcount > 0

def get_all_vpn_ips():
    """Get all allocated VPN IPs"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT vpn_ip FROM devices')
        return [row['vpn_ip'] for row in cursor.fetchall()]

# Port forward operations
def add_port_forward(device_id, public_port, target_port, protocol, enabled=True):
    """Add a new port forward"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO port_forwards (device_id, public_port, target_port, protocol, enabled)
            VALUES (?, ?, ?, ?, ?)
        ''', (device_id, public_port, target_port, protocol, enabled))
        return cursor.lastrowid

def get_port_forward(forward_id):
    """Get port forward by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT pf.*, d.name as device_name, d.vpn_ip as device_ip
            FROM port_forwards pf
            JOIN devices d ON pf.device_id = d.id
            WHERE pf.id = ?
        ''', (forward_id,))
        return cursor.fetchone()

def get_all_port_forwards():
    """Get all port forwards with device info"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT pf.*, d.name as device_name, d.vpn_ip as device_ip
            FROM port_forwards pf
            JOIN devices d ON pf.device_id = d.id
            ORDER BY pf.created_at DESC
        ''')
        return cursor.fetchall()

def get_port_forwards_by_device(device_id):
    """Get all port forwards for a specific device"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM port_forwards WHERE device_id = ?
        ''', (device_id,))
        return cursor.fetchall()

def update_port_forward(forward_id, device_id=None, public_port=None, 
                       target_port=None, protocol=None, enabled=None):
    """Update port forward"""
    updates = []
    params = []
    
    if device_id is not None:
        updates.append('device_id = ?')
        params.append(device_id)
    if public_port is not None:
        updates.append('public_port = ?')
        params.append(public_port)
    if target_port is not None:
        updates.append('target_port = ?')
        params.append(target_port)
    if protocol is not None:
        updates.append('protocol = ?')
        params.append(protocol)
    if enabled is not None:
        updates.append('enabled = ?')
        params.append(1 if enabled else 0)
    
    if not updates:
        return False
    
    params.append(forward_id)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f'''
            UPDATE port_forwards SET {', '.join(updates)} WHERE id = ?
        ''', params)
        return cursor.rowcount > 0

def delete_port_forward(forward_id):
    """Delete a port forward"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM port_forwards WHERE id = ?', (forward_id,))
        return cursor.rowcount > 0

def check_port_available(public_port, protocol, exclude_id=None):
    """Check if a public port is available for the given protocol"""
    with get_db() as conn:
        cursor = conn.cursor()
        if exclude_id:
            cursor.execute('''
                SELECT COUNT(*) as count FROM port_forwards 
                WHERE public_port = ? AND protocol = ? AND id != ?
            ''', (public_port, protocol, exclude_id))
        else:
            cursor.execute('''
                SELECT COUNT(*) as count FROM port_forwards 
                WHERE public_port = ? AND protocol = ?
            ''', (public_port, protocol))
        return cursor.fetchone()['count'] == 0

if __name__ == '__main__':
    init_database()
