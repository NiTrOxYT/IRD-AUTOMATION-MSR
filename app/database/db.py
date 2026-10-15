import sqlite3
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from app.config import DB_PATH, DEFAULT_SETTINGS
from app.database.models import Site, Setting, Run, RunSiteResult, Selector
from app.security.credentials import encrypt_password, decrypt_password

logger = logging.getLogger("IRD_Database")

DEFAULT_DTH_SETTINGS = {
    "default_mode": "DRY_RUN",
    "channel_delay_seconds": "1.0",
    "max_row_count": "5000",
    "max_file_size_mb": "10",
    "page_load_timeout": "60",
    "save_timeout": "30",
    "headless": "false",
    "browser_type": "chromium",
    "debug_screenshots": "true",
    "log_level": "INFO",
    "image_allowed_extensions": ".png,.jpg,.jpeg,.bmp,.webp",
    "max_image_size_kb": "2048"
}

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes SQLite database schemas and default settings."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Sites Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        launcher_button TEXT NOT NULL,
        url TEXT DEFAULT '',
        idp_username TEXT DEFAULT '',
        idp_password_encrypted TEXT DEFAULT '',
        enabled INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0,
        notes TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Settings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Runs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT,
        status TEXT DEFAULT 'IN_PROGRESS',
        total_sites INTEGER DEFAULT 0,
        completed_sites INTEGER DEFAULT 0,
        action_points_count INTEGER DEFAULT 0,
        no_action_points_count INTEGER DEFAULT 0,
        failed_sites_count INTEGER DEFAULT 0,
        log_path TEXT DEFAULT ''
    );
    """)

    # Run Site Results Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS run_site_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        site_id INTEGER NOT NULL,
        site_name TEXT NOT NULL,
        status TEXT DEFAULT 'PENDING',
        action_point_status TEXT DEFAULT 'PENDING',
        csv_path TEXT DEFAULT '',
        third_line_text TEXT DEFAULT '',
        start_time TEXT,
        end_time TEXT,
        duration_seconds REAL DEFAULT 0.0,
        retry_count INTEGER DEFAULT 0,
        error_message TEXT DEFAULT '',
        log_snippet TEXT DEFAULT '',
        FOREIGN KEY (run_id) REFERENCES runs (id) ON DELETE CASCADE
    );
    """)

    # Selectors Registry Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS selectors (
        step_key TEXT PRIMARY KEY,
        primary_selector TEXT NOT NULL,
        fallback_selectors TEXT DEFAULT '[]',
        description TEXT DEFAULT ''
    );
    """)

    # Run History Table (Phase 7)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS run_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id INTEGER NOT NULL,
        site_name TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        tunnel_status TEXT DEFAULT 'UNKNOWN',
        login_status TEXT DEFAULT 'UNKNOWN',
        sync_mymenu_status TEXT DEFAULT 'UNKNOWN',
        fetch_menu_status TEXT DEFAULT 'UNKNOWN',
        fetch_menu_attempts INTEGER DEFAULT 1,
        service_recovery_count INTEGER DEFAULT 0,
        final_status TEXT DEFAULT 'FAILED',
        error_code TEXT DEFAULT 'NONE',
        error_message TEXT DEFAULT ''
    );
    """)

    # DTH Runs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dth_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT,
        mode TEXT DEFAULT 'DRY_RUN',
        status TEXT DEFAULT 'PENDING',
        filename TEXT NOT NULL,
        total_channels INTEGER DEFAULT 0,
        processed_channels INTEGER DEFAULT 0,
        successful_channels INTEGER DEFAULT 0,
        failed_channels INTEGER DEFAULT 0,
        skipped_duplicates INTEGER DEFAULT 0,
        invalid_channels INTEGER DEFAULT 0,
        unknown_channels INTEGER DEFAULT 0,
        site_id INTEGER,
        site_name TEXT,
        error_message TEXT DEFAULT ''
    );
    """)

    # DTH Channel Results Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dth_channel_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        row_number INTEGER NOT NULL,
        channel_number TEXT NOT NULL,
        name TEXT NOT NULL,
        osd TEXT DEFAULT '',
        image TEXT DEFAULT '',
        categories TEXT DEFAULT '',
        status TEXT DEFAULT 'PENDING',
        attempt_count INTEGER DEFAULT 0,
        duration_seconds REAL DEFAULT 0.0,
        error_reason TEXT DEFAULT '',
        verified_in_portal INTEGER DEFAULT 0,
        started_at TEXT,
        completed_at TEXT,
        FOREIGN KEY (run_id) REFERENCES dth_runs (id) ON DELETE CASCADE
    );
    """)

    # DTH Sites Table (Isolated from IRD sites)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dth_sites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        portal_url TEXT DEFAULT '',
        local_port INTEGER DEFAULT 18001,
        site_ip TEXT DEFAULT '',
        site_port INTEGER DEFAULT 80,
        idp_username TEXT DEFAULT '',
        idp_password_encrypted TEXT DEFAULT '',
        enabled INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0,
        notes TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # DTH Settings Table (Isolated from IRD settings)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dth_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)


    # Non-destructive Migration for Sites Table Tunnel Fields
    cursor.execute("PRAGMA table_info(sites)")
    existing_cols = {col[1] for col in cursor.fetchall()}

    tunnel_columns = [
        ("site_ip", "TEXT DEFAULT ''"),
        ("site_port", "INTEGER DEFAULT 80"),
        ("local_port", "INTEGER DEFAULT 18001"),
        ("remote_host", "TEXT DEFAULT '127.0.0.1'"),
        ("remote_port", "INTEGER DEFAULT 80"),
        ("ssh_host", "TEXT DEFAULT ''"),
        ("ssh_port", "INTEGER DEFAULT 22"),
        ("ssh_username", "TEXT DEFAULT ''"),
        ("ssh_password_encrypted", "TEXT DEFAULT ''"),
        ("ssh_key_path", "TEXT DEFAULT ''"),
        ("auth_type", "TEXT DEFAULT 'key'"),
        ("putty_session", "TEXT DEFAULT ''"),
        ("tunnel_type", "TEXT DEFAULT 'reverse'"),
        ("web_url", "TEXT DEFAULT ''")
    ]

    for col_name, col_type in tunnel_columns:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE sites ADD COLUMN {col_name} {col_type}")

    # Non-destructive Migration for Run Site Results Table
    cursor.execute("PRAGMA table_info(run_site_results)")
    rsr_cols = {col[1] for col in cursor.fetchall()}
    rsr_new_columns = [
        ("fetch_menu_status", "TEXT DEFAULT 'UNKNOWN'"),
        ("process_latest_menu_status", "TEXT DEFAULT 'UNKNOWN'"),
        ("download_status", "TEXT DEFAULT 'UNKNOWN'"),
        ("failure_code", "TEXT DEFAULT 'NONE'")
    ]
    for col_name, col_type in rsr_new_columns:
        if col_name not in rsr_cols:
            cursor.execute(f"ALTER TABLE run_site_results ADD COLUMN {col_name} {col_type}")

    # Non-destructive Migration for DTH Sites Table Tunnel Fields
    cursor.execute("PRAGMA table_info(dth_sites)")
    existing_dth_cols = {col[1] for col in cursor.fetchall()}
    dth_tunnel_columns = [
        ("remote_host", "TEXT DEFAULT '127.0.0.1'"),
        ("remote_port", "INTEGER DEFAULT 80"),
        ("ssh_host", "TEXT DEFAULT ''"),
        ("ssh_port", "INTEGER DEFAULT 22"),
        ("ssh_username", "TEXT DEFAULT ''"),
        ("ssh_password_encrypted", "TEXT DEFAULT ''"),
        ("ssh_key_path", "TEXT DEFAULT ''"),
        ("auth_type", "TEXT DEFAULT 'key'"),
        ("putty_session", "TEXT DEFAULT ''"),
        ("tunnel_type", "TEXT DEFAULT 'reverse'"),
        ("web_url", "TEXT DEFAULT ''")
    ]
    for col_name, col_type in dth_tunnel_columns:
        if col_name not in existing_dth_cols:
            cursor.execute(f"ALTER TABLE dth_sites ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()

    # Ensure default settings exist
    for key, val in DEFAULT_SETTINGS.items():
        if get_setting(key) is None:
            set_setting(key, str(val))

    # Ensure default DTH settings exist
    for key, val in DEFAULT_DTH_SETTINGS.items():
        if get_dth_setting(key) is None:
            set_dth_setting(key, str(val))

    # Populate default selectors if empty
    _init_default_selectors()

def _init_default_selectors():
    defaults = {
        "login_username": {
            "primary": "input[name='username'], input[type='email'], #username, #userId",
            "fallbacks": ["input[id*='user']", "input[name*='user']", "input[placeholder*='User']"],
            "desc": "IDP Login Username input field"
        },
        "login_password": {
            "primary": "input[name='password'], input[type='password'], #password",
            "fallbacks": ["input[id*='pass']", "input[name*='pass']", "input[placeholder*='Password']"],
            "desc": "IDP Login Password input field"
        },
        "login_submit": {
            "primary": "button[type='submit'], input[type='submit'], button:has-text('Login'), button:has-text('Sign In')",
            "fallbacks": ["#loginBtn", ".login-button", "button:has-text('Submit')"],
            "desc": "IDP Login Submit Button"
        },
        "sync_mymenu": {
            "primary": "text='Sync MyMenu', a:has-text('Sync MyMenu'), button:has-text('Sync MyMenu')",
            "fallbacks": ["[aria-label='Sync MyMenu']", "a[href*='sync']", ".nav-link:has-text('Sync')"],
            "desc": "Left Navigation 'Sync MyMenu' link"
        },
        "fetch_menu": {
            "primary": "button:has-text('Fetch Menu'), input[value='Fetch Menu']",
            "fallbacks": [".fetch-menu-btn", "button[id*='fetch']", "text='Fetch Menu'"],
            "desc": "'Fetch Menu' action button"
        },
        "process_latest_menu": {
            "primary": "button:has-text('Process Latest Menu'), input[value='Process Latest Menu']",
            "fallbacks": [".process-menu-btn", "button[id*='process']", "text='Process Latest Menu'"],
            "desc": "'Process Latest Menu' action button"
        },
        "download_action_point": {
            "primary": "button:has-text('Download Action Point'), a:has-text('Download Action Point')",
            "fallbacks": ["a[href*='download']", ".download-btn", "text='Download Action Point'"],
            "desc": "'Download Action Point' CSV button"
        }
    }
    for key, spec in defaults.items():
        if get_selector(key) is None:
            save_selector(key, spec["primary"], json.dumps(spec["fallbacks"]), spec["desc"])

# --- SITES CRUD ---

def _row_to_site(r: sqlite3.Row) -> Site:
    keys = r.keys()
    dec_pass = decrypt_password(r["idp_password_encrypted"])
    dec_ssh_pass = decrypt_password(r["ssh_password_encrypted"]) if "ssh_password_encrypted" in keys else ""
    return Site(
        id=r["id"],
        name=r["name"],
        launcher_button=r["launcher_button"],
        url=r["url"],
        idp_username=r["idp_username"],
        idp_password=dec_pass,
        enabled=bool(r["enabled"]),
        sort_order=r["sort_order"],
        notes=r["notes"],
        site_ip=r["site_ip"] if "site_ip" in keys and r["site_ip"] is not None else "",
        site_port=r["site_port"] if "site_port" in keys and r["site_port"] is not None else 80,
        local_port=r["local_port"] if "local_port" in keys and r["local_port"] is not None else 18001,
        remote_host=r["remote_host"] if "remote_host" in keys and r["remote_host"] is not None else "127.0.0.1",
        remote_port=r["remote_port"] if "remote_port" in keys and r["remote_port"] is not None else 80,
        ssh_host=r["ssh_host"] if "ssh_host" in keys and r["ssh_host"] is not None else "",
        ssh_port=r["ssh_port"] if "ssh_port" in keys and r["ssh_port"] is not None else 22,
        ssh_username=r["ssh_username"] if "ssh_username" in keys and r["ssh_username"] is not None else "",
        ssh_password=dec_ssh_pass,
        ssh_key_path=r["ssh_key_path"] if "ssh_key_path" in keys and r["ssh_key_path"] is not None else "",
        auth_type=r["auth_type"] if "auth_type" in keys and r["auth_type"] is not None else "key",
        putty_session=r["putty_session"] if "putty_session" in keys and r["putty_session"] is not None else "",
        tunnel_type=r["tunnel_type"] if "tunnel_type" in keys and r["tunnel_type"] is not None else "reverse",
        web_url=f"http://localhost:{r['local_port'] if 'local_port' in keys and r['local_port'] is not None else 18001}/zmp/main-menu.do",
        created_at=r["created_at"],
        updated_at=r["updated_at"]
    )


def validate_site_port(site_port: Any) -> tuple[bool, str]:
    """Validates site_port is integer between 1 and 65535."""
    try:
        val = int(site_port)
        if 1 <= val <= 65535:
            return True, ""
        return False, "Site Port must be an integer between 1 and 65535."
    except (ValueError, TypeError):
        return False, "Site Port must be a valid integer."

def validate_local_port_collision(site_id: Optional[int], local_port: int, enabled: bool = True) -> tuple[bool, str]:
    """Prevents two enabled sites from sharing the same local port."""
    if not enabled:
        return True, ""
    conn = get_db_connection()
    cursor = conn.cursor()
    if site_id:
        cursor.execute("SELECT name FROM sites WHERE local_port = ? AND enabled = 1 AND id != ?", (local_port, site_id))
    else:
        cursor.execute("SELECT name FROM sites WHERE local_port = ? AND enabled = 1", (local_port,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return False, f"Local port {local_port} is already assigned to {row['name']}."
    return True, ""

def get_all_sites() -> List[Site]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sites ORDER BY sort_order ASC, name ASC")
    rows = cursor.fetchall()
    conn.close()

    return [_row_to_site(r) for r in rows]

def get_site_by_id(site_id: int) -> Optional[Site]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sites WHERE id = ?", (site_id,))
    r = cursor.fetchone()
    conn.close()
    if not r:
        return None
    return _row_to_site(r)

def get_site_by_name(name: str) -> Optional[Site]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sites WHERE LOWER(name) = LOWER(?) OR LOWER(launcher_button) = LOWER(?)", (name.strip(), name.strip()))
    r = cursor.fetchone()
    conn.close()
    if not r:
        return None
    return _row_to_site(r)


def add_site(site: Site) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    enc_pass = encrypt_password(site.idp_password)
    enc_ssh_pass = encrypt_password(site.ssh_password)
    now = datetime.now().isoformat()

    # Get max sort_order
    cursor.execute("SELECT MAX(sort_order) FROM sites")
    max_order = cursor.fetchone()[0] or 0
    sort_order = site.sort_order if site.sort_order > 0 else max_order + 1

    cursor.execute("""
    INSERT INTO sites (
        name, launcher_button, url, idp_username, idp_password_encrypted, enabled, sort_order, notes,
        site_ip, site_port, local_port, remote_host, remote_port, ssh_host, ssh_port, ssh_username, ssh_password_encrypted,
        ssh_key_path, auth_type, putty_session, tunnel_type, web_url, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        site.name.strip(), site.launcher_button.strip(), site.url.strip(), site.idp_username.strip(), enc_pass,
        1 if site.enabled else 0, sort_order, site.notes,
        site.site_ip.strip(), site.site_port, site.local_port, site.remote_host.strip(), site.remote_port, site.ssh_host.strip(), site.ssh_port,
        site.ssh_username.strip(), enc_ssh_pass, site.ssh_key_path.strip(), site.auth_type,
        site.putty_session.strip(), site.tunnel_type, site.web_url.strip(), now, now
    ))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id

def update_site(site: Site):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    enc_idp = encrypt_password(site.idp_password) if site.idp_password else None
    enc_ssh = encrypt_password(site.ssh_password) if site.ssh_password else None

    # Retrieve existing passwords if not provided in update
    cursor.execute("SELECT idp_password_encrypted, ssh_password_encrypted FROM sites WHERE id=?", (site.id,))
    row = cursor.fetchone()
    if row:
        if not enc_idp:
            enc_idp = row["idp_password_encrypted"]
        if not enc_ssh:
            enc_ssh = row["ssh_password_encrypted"]

    cursor.execute("""
    UPDATE sites SET
        name=?, launcher_button=?, url=?, idp_username=?, idp_password_encrypted=?, enabled=?, sort_order=?, notes=?,
        site_ip=?, site_port=?, local_port=?, remote_host=?, remote_port=?, ssh_host=?, ssh_port=?, ssh_username=?, ssh_password_encrypted=?,
        ssh_key_path=?, auth_type=?, putty_session=?, tunnel_type=?, web_url=?, updated_at=?
    WHERE id=?
    """, (
        site.name.strip(), site.launcher_button.strip(), site.url.strip(), site.idp_username.strip(), enc_idp,
        1 if site.enabled else 0, site.sort_order, site.notes,
        site.site_ip.strip(), site.site_port, site.local_port, site.remote_host.strip(), site.remote_port, site.ssh_host.strip(), site.ssh_port,
        site.ssh_username.strip(), enc_ssh, site.ssh_key_path.strip(), site.auth_type, site.putty_session.strip(),
        site.tunnel_type, site.web_url.strip(), now, site.id
    ))
    conn.commit()
    conn.close()



def delete_site(site_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sites WHERE id = ?", (site_id,))
    conn.commit()
    conn.close()

def update_site_order(site_orders: List[Dict[str, int]]):
    """site_orders is list of dicts [{'id': 1, 'sort_order': 1}, ...]"""
    conn = get_db_connection()
    cursor = conn.cursor()
    for item in site_orders:
        cursor.execute("UPDATE sites SET sort_order = ? WHERE id = ?", (item["sort_order"], item["id"]))
    conn.commit()
    conn.close()

# --- SETTINGS CRUD ---

def get_setting(key: str) -> Optional[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    r = cursor.fetchone()
    conn.close()
    return r["value"] if r else None

def get_all_settings() -> Dict[str, str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    res = {key: str(val) for key, val in DEFAULT_SETTINGS.items()}
    for r in rows:
        # Convert booleans / ints where appropriate
        val_str = r["value"]
        if val_str.lower() in ("true", "false"):
            res[r["key"]] = True if val_str.lower() == "true" else False
        elif val_str.isdigit():
            res[r["key"]] = int(val_str)
        else:
            res[r["key"]] = val_str
    return res

def set_setting(key: str, value: Any):
    conn = get_db_connection()
    cursor = conn.cursor()
    val_str = str(value)
    now = datetime.now().isoformat()
    cursor.execute("""
    INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
    ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
    """, (key, val_str, now))
    conn.commit()
    conn.close()

def get_browser_debug_mode() -> bool:
    """Returns True if Browser Debug Mode (headed execution + slow motion) is enabled."""
    val = (get_setting("browser_debug_mode") or "OFF").upper()
    return val in ("ON", "1", "TRUE", "YES")

def set_browser_debug_mode(enabled: bool):
    """Sets Browser Debug Mode setting."""
    val = "ON" if enabled else "OFF"
    set_setting("browser_debug_mode", val)
    logger.info(f"Browser Debug Mode updated to '{val}'.")

def get_whitelabel_recovery_settings() -> Dict[str, Any]:
    """Returns Whitelabel error recovery settings."""
    enabled_val = (get_setting("first_login_whitelabel_recovery") or "ON").upper()
    enabled = enabled_val in ("ON", "1", "TRUE", "YES")
    max_attempts_str = get_setting("max_whitelabel_recovery_attempts") or "2"
    try:
        max_attempts = int(max_attempts_str)
    except ValueError:
        max_attempts = 2
    return {"enabled": enabled, "mode": "ON" if enabled else "OFF", "max_attempts": max_attempts}

def set_whitelabel_recovery_settings(enabled: bool, max_attempts: int = 2):
    """Sets Whitelabel error recovery settings."""
    val = "ON" if enabled else "OFF"
    set_setting("first_login_whitelabel_recovery", val)
    set_setting("max_whitelabel_recovery_attempts", str(max(1, min(10, int(max_attempts)))))
    logger.info(f"First-login Whitelabel Recovery updated to '{val}', max attempts={max_attempts}.")



# --- OFFICE SSH SERVER SETTINGS ---


def seed_office_ssh_credentials_if_empty():
    """
    Seeds default Office SSH server credentials (111.93.205.187:22, user: sourik)
    on initial installation only using Windows DPAPI. Never overwrites existing credentials.
    """
    if get_setting("office_ssh_host") is None:
        set_setting("office_ssh_host", "111.93.205.187")
    if get_setting("office_ssh_port") is None:
        set_setting("office_ssh_port", "22")
    if get_setting("office_ssh_username") is None:
        set_setting("office_ssh_username", "sourik")
    if get_setting("office_ssh_auth_type") is None:
        set_setting("office_ssh_auth_type", "password")

    existing_enc = get_setting("office_ssh_password_encrypted")
    if not existing_enc:
        # Securely encrypt default seed password via DPAPI
        seed_pass = "s0urik@@"
        enc_pass = encrypt_password(seed_pass)
        set_setting("office_ssh_password_encrypted", enc_pass)
        logger.info("Office SSH default credentials seeded via Windows DPAPI.")

    # Also update site FNB if site FNB fields are missing
    fnb = get_site_by_id(1) or get_site_by_name("FNB")
    if fnb and not fnb.ssh_host:
        fnb.ssh_host = "111.93.205.187"
        fnb.ssh_port = 22
        fnb.ssh_username = "sourik"
        fnb.auth_type = "password"
        fnb.ssh_password = decrypt_password(get_setting("office_ssh_password_encrypted") or "")
        update_site(fnb)
        logger.info("Site FNB updated with Office SSH server credentials.")

def get_office_ssh_config() -> Dict[str, Any]:
    """
    Returns Office SSH server configuration.
    CRITICAL SECURITY: Never returns plaintext or encrypted password strings.
    """
    return {
        "ssh_host": get_setting("office_ssh_host") or "111.93.205.187",
        "ssh_port": int(get_setting("office_ssh_port") or 22),
        "ssh_username": get_setting("office_ssh_username") or "sourik",
        "auth_type": get_setting("office_ssh_auth_type") or "password",
        "ssh_key_path": get_setting("office_ssh_key_path") or "",
        "ssh_host_key": get_setting("office_ssh_host_key") or "",
        "password_configured": bool(get_setting("office_ssh_password_encrypted"))
    }

def get_office_ssh_password_decrypted() -> str:
    """
    Decrypts Office SSH password in memory for process execution only.
    """
    enc = get_setting("office_ssh_password_encrypted") or ""
    return decrypt_password(enc)

def set_office_ssh_config(data: Dict[str, Any]):
    """
    Updates Office SSH Server configuration. Encrypts password via DPAPI if provided.
    """
    if "ssh_host" in data:
        set_setting("office_ssh_host", data["ssh_host"].strip())
    if "ssh_port" in data:
        set_setting("office_ssh_port", str(data["ssh_port"]))
    if "ssh_username" in data:
        set_setting("office_ssh_username", data["ssh_username"].strip())
    if "auth_type" in data:
        set_setting("office_ssh_auth_type", data["auth_type"].strip())
    if "ssh_key_path" in data:
        set_setting("office_ssh_key_path", data["ssh_key_path"].strip())
    if "ssh_host_key" in data:
        set_setting("office_ssh_host_key", data["ssh_host_key"].strip())

    if "ssh_password" in data and data["ssh_password"]:
        enc_pass = encrypt_password(data["ssh_password"])
        set_setting("office_ssh_password_encrypted", enc_pass)

    # Sync to Site FNB as well
    fnb = get_site_by_id(1) or get_site_by_name("FNB")
    if fnb:
        fnb.ssh_host = get_setting("office_ssh_host") or "111.93.205.187"
        fnb.ssh_port = int(get_setting("office_ssh_port") or 22)
        fnb.ssh_username = get_setting("office_ssh_username") or "sourik"
        fnb.auth_type = get_setting("office_ssh_auth_type") or "password"
        fnb.ssh_key_path = get_setting("office_ssh_key_path") or ""
        fnb.ssh_password = get_office_ssh_password_decrypted()
        update_site(fnb)

def get_global_tunnel_config() -> Dict[str, Any]:
    """Returns common/global reverse SSH tunnel settings."""
    return {
        "tunnel_remote_port": int(get_setting("tunnel_remote_port") or 80),
        "fnb_service_port": int(get_setting("fnb_service_port") or 80),
        "web_url_template": get_setting("web_url_template") or "http://127.0.0.1:{local_port}",
        "tunnel_type": get_setting("tunnel_type") or "reverse"
    }

def set_global_tunnel_config(data: Dict[str, Any]):
    """Updates common/global reverse SSH tunnel settings."""
    if "tunnel_remote_port" in data:
        set_setting("tunnel_remote_port", str(data["tunnel_remote_port"]))
    if "fnb_service_port" in data:
        set_setting("fnb_service_port", str(data["fnb_service_port"]))
    if "web_url_template" in data:
        set_setting("web_url_template", data["web_url_template"].strip())
    if "tunnel_type" in data:
        set_setting("tunnel_type", data["tunnel_type"].strip())


# --- RUNS & RESULTS CRUD ---


def create_run(run: Run) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO runs (run_date, start_time, end_time, status, total_sites, completed_sites, action_points_count, no_action_points_count, failed_sites_count, log_path)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run.run_date, run.start_time, run.end_time, run.status,
        run.total_sites, run.completed_sites, run.action_points_count,
        run.no_action_points_count, run.failed_sites_count, run.log_path
    ))
    conn.commit()
    run_id = cursor.lastrowid
    conn.close()
    return run_id

def update_run(run: Run):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE runs SET end_time=?, status=?, completed_sites=?, action_points_count=?, no_action_points_count=?, failed_sites_count=?
    WHERE id=?
    """, (
        run.end_time, run.status, run.completed_sites, run.action_points_count,
        run.no_action_points_count, run.failed_sites_count, run.id
    ))
    conn.commit()
    conn.close()

def save_run_site_result(result: RunSiteResult) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    f_status = getattr(result, "fetch_menu_status", "UNKNOWN")
    p_status = getattr(result, "process_latest_menu_status", "UNKNOWN")
    d_status = getattr(result, "download_status", "UNKNOWN")
    f_code = getattr(result, "failure_code", "NONE")

    if result.id:
        cursor.execute("""
        UPDATE run_site_results SET status=?, action_point_status=?, csv_path=?, third_line_text=?, start_time=?, end_time=?, duration_seconds=?, retry_count=?, error_message=?, log_snippet=?, fetch_menu_status=?, process_latest_menu_status=?, download_status=?, failure_code=?
        WHERE id=?
        """, (
            result.status, result.action_point_status, result.csv_path, result.third_line_text,
            result.start_time, result.end_time, result.duration_seconds, result.retry_count,
            result.error_message, result.log_snippet, f_status, p_status, d_status, f_code, result.id
        ))
        res_id = result.id
    else:
        cursor.execute("""
        INSERT INTO run_site_results (run_id, site_id, site_name, status, action_point_status, csv_path, third_line_text, start_time, end_time, duration_seconds, retry_count, error_message, log_snippet, fetch_menu_status, process_latest_menu_status, download_status, failure_code)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.run_id, result.site_id, result.site_name, result.status,
            result.action_point_status, result.csv_path, result.third_line_text,
            result.start_time, result.end_time, result.duration_seconds,
            result.retry_count, result.error_message, result.log_snippet,
            f_status, p_status, d_status, f_code
        ))
        res_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return res_id

def get_runs_history(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()

    runs = []
    for r in rows:
        run_dict = dict(r)
        cursor.execute("SELECT * FROM run_site_results WHERE run_id = ? ORDER BY id ASC", (run_dict["id"],))
        site_rows = cursor.fetchall()
        run_dict["results"] = [dict(s) for s in site_rows]
        runs.append(run_dict)
    conn.close()
    return runs

def get_run_details(run_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
    run_row = cursor.fetchone()
    if not run_row:
        conn.close()
        return None

    cursor.execute("SELECT * FROM run_site_results WHERE run_id = ? ORDER BY id ASC", (run_id,))
    site_rows = cursor.fetchall()
    conn.close()

    return {
        "run": dict(run_row),
        "results": [dict(s) for s in site_rows]
    }

# --- SELECTORS CRUD ---

def get_selector(step_key: str) -> Optional[Selector]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM selectors WHERE step_key = ?", (step_key,))
    r = cursor.fetchone()
    conn.close()
    if not r:
        return None
    return Selector(
        step_key=r["step_key"],
        primary_selector=r["primary_selector"],
        fallback_selectors=r["fallback_selectors"],
        description=r["description"]
    )

def get_all_selectors() -> Dict[str, Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM selectors")
    rows = cursor.fetchall()
    conn.close()

    res = {}
    for r in rows:
        res[r["step_key"]] = {
            "primary": r["primary_selector"],
            "fallbacks": json.loads(r["fallback_selectors"]) if r["fallback_selectors"] else [],
            "description": r["description"]
        }
    return res

def save_selector(step_key: str, primary: str, fallbacks_json: str, description: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO selectors (step_key, primary_selector, fallback_selectors, description)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(step_key) DO UPDATE SET primary_selector=excluded.primary_selector, fallback_selectors=excluded.fallback_selectors, description=excluded.description
    """, (step_key, primary, fallbacks_json, description))
    conn.commit()
    conn.close()

def record_run_history(rec_dict: Dict[str, Any]) -> int:
    """Inserts a run history record into the run_history table."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO run_history (
        site_id, site_name, start_time, end_time, tunnel_status,
        login_status, sync_mymenu_status, fetch_menu_status,
        fetch_menu_attempts, service_recovery_count, final_status,
        error_code, error_message
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        rec_dict.get("site_id", 0),
        rec_dict.get("site_name", "FNB"),
        rec_dict.get("start_time", datetime.now().isoformat()),
        rec_dict.get("end_time", datetime.now().isoformat()),
        rec_dict.get("tunnel_status", "UNKNOWN"),
        rec_dict.get("login_status", "UNKNOWN"),
        rec_dict.get("sync_mymenu_status", "UNKNOWN"),
        rec_dict.get("fetch_menu_status", "UNKNOWN"),
        rec_dict.get("fetch_menu_attempts", 1),
        rec_dict.get("service_recovery_count", 0),
        rec_dict.get("final_status", "FAILED"),
        rec_dict.get("error_code", "NONE"),
        rec_dict.get("error_message", "")
    ))
    rec_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return rec_id


# --- DTH CHANNEL AUTOMATION CRUD ---

def create_dth_run(run_dict: Dict[str, Any]) -> int:
    """Creates a new DTH execution run record and returns run ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO dth_runs (
        run_date, start_time, end_time, mode, status, filename,
        total_channels, processed_channels, successful_channels,
        failed_channels, skipped_duplicates, invalid_channels,
        unknown_channels, site_id, site_name, error_message
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_dict.get("run_date", datetime.now().strftime("%Y-%m-%d")),
        run_dict.get("start_time", datetime.now().strftime("%H:%M:%S")),
        run_dict.get("end_time"),
        run_dict.get("mode", "DRY_RUN"),
        run_dict.get("status", "PENDING"),
        run_dict.get("filename", "channels.csv"),
        run_dict.get("total_channels", 0),
        run_dict.get("processed_channels", 0),
        run_dict.get("successful_channels", 0),
        run_dict.get("failed_channels", 0),
        run_dict.get("skipped_duplicates", 0),
        run_dict.get("invalid_channels", 0),
        run_dict.get("unknown_channels", 0),
        run_dict.get("site_id"),
        run_dict.get("site_name"),
        run_dict.get("error_message", "")
    ))
    run_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return run_id


def update_dth_run(run_id: int, updates: Dict[str, Any]):
    """Updates fields of a DTH run record."""
    if not updates:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    fields = []
    values = []
    for k, v in updates.items():
        fields.append(f"{k} = ?")
        values.append(v)
    values.append(run_id)
    sql = f"UPDATE dth_runs SET {', '.join(fields)} WHERE id = ?"
    cursor.execute(sql, tuple(values))
    conn.commit()
    conn.close()


def save_dth_channel_result(result_dict: Dict[str, Any]) -> int:
    """Inserts a per-channel execution result into dth_channel_results."""
    conn = get_db_connection()
    cursor = conn.cursor()
    categories = result_dict.get("categories", [])
    categories_str = json.dumps(categories) if isinstance(categories, list) else str(categories)

    cursor.execute("""
    INSERT INTO dth_channel_results (
        run_id, row_number, channel_number, name, osd, image,
        categories, status, attempt_count, duration_seconds,
        error_reason, verified_in_portal, started_at, completed_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result_dict.get("run_id", 0),
        result_dict.get("row_number", 0),
        str(result_dict.get("channel_number", "")),
        str(result_dict.get("name", "")),
        str(result_dict.get("osd", "")),
        str(result_dict.get("image", "")),
        categories_str,
        str(result_dict.get("status", "PENDING")),
        result_dict.get("attempt_count", 0),
        float(result_dict.get("duration_seconds", 0.0)),
        str(result_dict.get("error_reason", "")),
        1 if result_dict.get("verified_in_portal") else 0,
        result_dict.get("started_at"),
        result_dict.get("completed_at")
    ))
    res_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return res_id


def get_dth_runs_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Fetches past DTH execution runs in reverse chronological order."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM dth_runs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_dth_run_details(run_id: int) -> Optional[Dict[str, Any]]:
    """Fetches a specific DTH run summary and its per-channel results."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM dth_runs WHERE id = ?", (run_id,))
    run_row = cursor.fetchone()
    if not run_row:
        conn.close()
        return None

    cursor.execute("SELECT * FROM dth_channel_results WHERE run_id = ? ORDER BY row_number ASC", (run_id,))
    channel_rows = cursor.fetchall()
    conn.close()

    parsed_channels = []
    for c in channel_rows:
        cd = dict(c)
        try:
            cd["categories"] = json.loads(cd["categories"])
        except Exception:
            cd["categories"] = [cd["categories"]] if cd["categories"] else []
        parsed_channels.append(cd)

    return {
        "run": dict(run_row),
        "channels": parsed_channels
    }


# --- DTH SITES CRUD ---

def _row_to_dth_site(r: sqlite3.Row, include_passwords: bool = False) -> Dict[str, Any]:
    keys = r.keys()
    has_pwd = bool(r["idp_password_encrypted"]) if "idp_password_encrypted" in keys and r["idp_password_encrypted"] else False
    has_ssh_pwd = bool(r["ssh_password_encrypted"]) if "ssh_password_encrypted" in keys and r["ssh_password_encrypted"] else False

    dec_pass = decrypt_password(r["idp_password_encrypted"]) if has_pwd and include_passwords else ""
    dec_ssh_pass = decrypt_password(r["ssh_password_encrypted"]) if has_ssh_pwd and include_passwords else ""

    portal_url = r["portal_url"] if "portal_url" in keys and r["portal_url"] else ""
    local_port = r["local_port"] if "local_port" in keys and r["local_port"] is not None else 18001
    web_url = r["web_url"] if "web_url" in keys and r["web_url"] else (portal_url or f"http://localhost:{local_port}/zmp/main-menu.do")

    data = {
        "id": r["id"],
        "name": r["name"],
        "portal_url": portal_url,
        "local_port": local_port,
        "site_ip": r["site_ip"] if "site_ip" in keys and r["site_ip"] is not None else "",
        "site_port": r["site_port"] if "site_port" in keys and r["site_port"] is not None else 80,
        "remote_host": r["remote_host"] if "remote_host" in keys and r["remote_host"] is not None else "127.0.0.1",
        "remote_port": r["remote_port"] if "remote_port" in keys and r["remote_port"] is not None else 80,
        "ssh_host": r["ssh_host"] if "ssh_host" in keys and r["ssh_host"] is not None else "",
        "ssh_port": r["ssh_port"] if "ssh_port" in keys and r["ssh_port"] is not None else 22,
        "ssh_username": r["ssh_username"] if "ssh_username" in keys and r["ssh_username"] is not None else "",
        "auth_type": r["auth_type"] if "auth_type" in keys and r["auth_type"] is not None else "key",
        "putty_session": r["putty_session"] if "putty_session" in keys and r["putty_session"] is not None else "",
        "tunnel_type": r["tunnel_type"] if "tunnel_type" in keys and r["tunnel_type"] is not None else "reverse",
        "web_url": web_url,
        "idp_username": r["idp_username"] if "idp_username" in keys and r["idp_username"] is not None else "",
        "has_password": has_pwd,
        "has_credentials": bool(has_pwd or has_ssh_pwd),
        "idp_password_masked": "••••••••" if has_pwd else "",
        "has_ssh_password": has_ssh_pwd,
        "ssh_password_masked": "••••••••" if has_ssh_pwd else "",
        "enabled": bool(r["enabled"]),
        "sort_order": r["sort_order"] if "sort_order" in keys and r["sort_order"] is not None else 0,
        "notes": r["notes"] if "notes" in keys and r["notes"] is not None else "",
        "created_at": r["created_at"] if "created_at" in keys else None,
        "updated_at": r["updated_at"] if "updated_at" in keys else None
    }
    if include_passwords:
        data["idp_password"] = dec_pass
        data["ssh_password"] = dec_ssh_pass
    return data


def get_all_dth_sites(enabled_only: bool = False, include_passwords: bool = False) -> List[Dict[str, Any]]:
    """Fetches all DTH site configurations."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if enabled_only:
        cursor.execute("SELECT * FROM dth_sites WHERE enabled = 1 ORDER BY sort_order ASC, name ASC")
    else:
        cursor.execute("SELECT * FROM dth_sites ORDER BY sort_order ASC, name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [_row_to_dth_site(r, include_passwords=include_passwords) for r in rows]


def get_dth_site_by_id(site_id: int, include_passwords: bool = False) -> Optional[Dict[str, Any]]:
    """Fetches a single DTH site by its ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM dth_sites WHERE id = ?", (site_id,))
    r = cursor.fetchone()
    conn.close()
    if not r:
        return None
    return _row_to_dth_site(r, include_passwords=include_passwords)


def get_dth_site_by_name(name: str, include_passwords: bool = False) -> Optional[Dict[str, Any]]:
    """Fetches a DTH site by name (case-insensitive)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM dth_sites WHERE LOWER(name) = LOWER(?)", (name.strip(),))
    r = cursor.fetchone()
    conn.close()
    if not r:
        return None
    return _row_to_dth_site(r, include_passwords=include_passwords)


def add_dth_site(site_data: Dict[str, Any]) -> int:
    """Inserts a new DTH site into dth_sites table."""
    conn = get_db_connection()
    cursor = conn.cursor()
    raw_pwd = site_data.get("idp_password", "")
    enc_pwd = encrypt_password(raw_pwd) if raw_pwd else ""
    raw_ssh_pwd = site_data.get("ssh_password", "")
    enc_ssh_pwd = encrypt_password(raw_ssh_pwd) if raw_ssh_pwd else ""

    cursor.execute("SELECT MAX(sort_order) FROM dth_sites")
    max_order = cursor.fetchone()[0] or 0
    sort_order = site_data.get("sort_order") or (max_order + 1)
    now = datetime.now().isoformat()

    portal_url = str(site_data.get("portal_url", "")).strip()
    if portal_url == "None":
        portal_url = ""
    local_port = int(site_data.get("local_port") or 18001)
    web_url = str(site_data.get("web_url", "")).strip()
    if web_url == "None":
        web_url = ""
    if not web_url:
        web_url = portal_url or f"http://localhost:{local_port}/zmp/manage-stb-channels.do"

    raw_ip = str(site_data.get("site_ip", "")).strip()
    if not raw_ip or raw_ip == "None":
        raw_ip = str(site_data.get("remote_host", "")).strip()
    if raw_ip == "None":
        raw_ip = ""

    raw_port = site_data.get("site_port") or site_data.get("remote_port") or 80
    try:
        clean_port = int(raw_port)
    except Exception:
        clean_port = 80

    ssh_host = str(site_data.get("ssh_host", "")).strip()
    if ssh_host == "None":
        ssh_host = ""
    ssh_username = str(site_data.get("ssh_username", "")).strip()
    if ssh_username == "None":
        ssh_username = ""
    putty_session = str(site_data.get("putty_session", "")).strip()
    if putty_session == "None":
        putty_session = ""

    cursor.execute("""
    INSERT INTO dth_sites (
        name, portal_url, local_port, site_ip, site_port, remote_host, remote_port,
        ssh_host, ssh_port, ssh_username, ssh_password_encrypted, ssh_key_path,
        auth_type, putty_session, tunnel_type, web_url, idp_username, idp_password_encrypted,
        enabled, sort_order, notes, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(site_data.get("name", "")).strip(),
        portal_url,
        local_port,
        raw_ip,
        clean_port,
        raw_ip or "127.0.0.1",
        clean_port,
        ssh_host,
        int(site_data.get("ssh_port") or 22),
        ssh_username,
        enc_ssh_pwd,
        str(site_data.get("ssh_key_path", "")).strip(),
        str(site_data.get("auth_type", "key")).strip(),
        putty_session,
        str(site_data.get("tunnel_type", "reverse")).strip(),
        web_url,
        str(site_data.get("idp_username", "")).strip(),
        enc_pwd,
        1 if site_data.get("enabled", True) else 0,
        sort_order,
        str(site_data.get("notes", "")).strip(),
        now,
        now
    ))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_dth_site(site_id: int, site_data: Dict[str, Any]) -> bool:
    """Updates an existing DTH site record."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM dth_sites WHERE id = ?", (site_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    enc_idp = row["idp_password_encrypted"]
    if "idp_password" in site_data and site_data["idp_password"]:
        enc_idp = encrypt_password(site_data["idp_password"])

    enc_ssh = row["ssh_password_encrypted"]
    if "ssh_password" in site_data and site_data["ssh_password"]:
        enc_ssh = encrypt_password(site_data["ssh_password"])

    now = datetime.now().isoformat()
    site_name = str(site_data.get("name") or row["name"] or "").strip()
    portal_url = str(site_data.get("portal_url") or row["portal_url"] or "").strip()
    if portal_url == "None":
        portal_url = ""
    local_port = int(site_data.get("local_port") or row["local_port"] or 18001)
    web_url = str(site_data.get("web_url") or row["web_url"] or "").strip()
    if web_url == "None":
        web_url = ""
    if not web_url:
        web_url = portal_url or f"http://localhost:{local_port}/zmp/manage-stb-channels.do"

    raw_ip = str(site_data.get("site_ip") or site_data.get("remote_host") or row["site_ip"] or row["remote_host"] or "").strip()
    if raw_ip == "None":
        raw_ip = ""

    raw_port = site_data.get("site_port") or site_data.get("remote_port") or row["site_port"] or row["remote_port"] or 8080
    try:
        clean_port = int(raw_port)
    except Exception:
        clean_port = 8080

    ssh_host = str(site_data.get("ssh_host") or row["ssh_host"] or "").strip()
    if ssh_host == "None":
        ssh_host = ""
    ssh_username = str(site_data.get("ssh_username") or row["ssh_username"] or "").strip()
    if ssh_username == "None":
        ssh_username = ""
    putty_session = str(site_data.get("putty_session") or row["putty_session"] or "").strip()
    if putty_session == "None":
        putty_session = ""

    cursor.execute("""
    UPDATE dth_sites SET
        name = ?, portal_url = ?, local_port = ?, site_ip = ?, site_port = ?,
        remote_host = ?, remote_port = ?, ssh_host = ?, ssh_port = ?, ssh_username = ?,
        ssh_password_encrypted = ?, ssh_key_path = ?, auth_type = ?, putty_session = ?,
        tunnel_type = ?, web_url = ?, idp_username = ?, idp_password_encrypted = ?,
        enabled = ?, sort_order = ?, notes = ?, updated_at = ?
    WHERE id = ?
    """, (
        site_name,
        portal_url,
        local_port,
        raw_ip,
        clean_port,
        raw_ip or "127.0.0.1",
        clean_port,
        ssh_host,
        int(site_data.get("ssh_port") or row["ssh_port"] or 22),
        ssh_username,
        enc_ssh,
        str(site_data.get("ssh_key_path", row["ssh_key_path"] or "")).strip(),
        str(site_data.get("auth_type", row["auth_type"] or "key")).strip(),
        putty_session,
        str(site_data.get("tunnel_type", row["tunnel_type"] or "reverse")).strip(),
        web_url,
        str(site_data.get("idp_username", row["idp_username"] or "")).strip(),
        enc_idp,
        1 if site_data.get("enabled", row["enabled"] if row["enabled"] is not None else True) else 0,
        int(site_data.get("sort_order") if site_data.get("sort_order") is not None else (row["sort_order"] or 0)),
        str(site_data.get("notes", row["notes"] or "")).strip(),
        now,
        site_id
    ))
    conn.commit()
    conn.close()
    return True


def delete_dth_site(site_id: int) -> bool:
    """Deletes a DTH site from dth_sites table."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM dth_sites WHERE id = ?", (site_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def toggle_dth_site(site_id: int, enabled: bool) -> bool:
    """Enables or disables a DTH site."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE dth_sites SET enabled = ?, updated_at = ? WHERE id = ?", (1 if enabled else 0, datetime.now().isoformat(), site_id))
    ok = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return ok


# --- DTH SETTINGS CRUD ---

def get_dth_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM dth_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return default


def set_dth_setting(key: str, value: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO dth_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
    """, (key, str(value)))
    conn.commit()
    conn.close()


def get_all_dth_settings() -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM dth_settings")
    rows = cursor.fetchall()
    conn.close()
    result = dict(DEFAULT_DTH_SETTINGS)
    for r in rows:
        result[r[0]] = r[1]
    return result


def update_dth_settings(settings: Dict[str, Any]):
    conn = get_db_connection()
    cursor = conn.cursor()
    for k, v in settings.items():
        cursor.execute("""
        INSERT INTO dth_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
        """, (k, str(v)))
    conn.commit()
    conn.close()


def get_dth_dashboard_metrics() -> Dict[str, Any]:
    """Calculates DTH-specific metrics strictly from dth_sites and dth_runs."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM dth_sites")
    total_sites = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM dth_runs")
    total_runs = cursor.fetchone()[0] or 0

    cursor.execute("""
    SELECT 
        COALESCE(SUM(processed_channels), 0),
        COALESCE(SUM(successful_channels), 0),
        COALESCE(SUM(failed_channels), 0),
        COALESCE(SUM(skipped_duplicates), 0)
    FROM dth_runs
    """)
    sum_row = cursor.fetchone()
    total_processed = sum_row[0] if sum_row else 0
    successful_channels = sum_row[1] if sum_row else 0
    failed_channels = sum_row[2] if sum_row else 0
    skipped_duplicates = sum_row[3] if sum_row else 0

    cursor.execute("SELECT * FROM dth_runs ORDER BY id DESC LIMIT 5")
    recent_runs = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return {
        "total_sites": total_sites,
        "total_runs": total_runs,
        "total_channels_processed": total_processed,
        "successful_channels": successful_channels,
        "failed_channels": failed_channels,
        "skipped_duplicates": skipped_duplicates,
        "recent_runs": recent_runs
    }

