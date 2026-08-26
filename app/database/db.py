import sqlite3
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from app.config import DB_PATH, DEFAULT_SETTINGS
from app.database.models import Site, Setting, Run, RunSiteResult, Selector
from app.security.credentials import encrypt_password, decrypt_password

logger = logging.getLogger("IRD_Database")

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

    # Non-destructive Migration for Sites Table Tunnel Fields
    cursor.execute("PRAGMA table_info(sites)")
    existing_cols = {col[1] for col in cursor.fetchall()}

    tunnel_columns = [
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

    conn.commit()
    conn.close()

    # Ensure default settings exist
    for key, val in DEFAULT_SETTINGS.items():
        if get_setting(key) is None:
            set_setting(key, str(val))

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
        web_url=r["web_url"] if "web_url" in keys and r["web_url"] is not None else "",
        created_at=r["created_at"],
        updated_at=r["updated_at"]
    )

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
        local_port, remote_host, remote_port, ssh_host, ssh_port, ssh_username, ssh_password_encrypted,
        ssh_key_path, auth_type, putty_session, tunnel_type, web_url, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        site.name.strip(), site.launcher_button.strip(), site.url.strip(), site.idp_username.strip(), enc_pass,
        1 if site.enabled else 0, sort_order, site.notes,
        site.local_port, site.remote_host.strip(), site.remote_port, site.ssh_host.strip(), site.ssh_port,
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
        local_port=?, remote_host=?, remote_port=?, ssh_host=?, ssh_port=?, ssh_username=?, ssh_password_encrypted=?,
        ssh_key_path=?, auth_type=?, putty_session=?, tunnel_type=?, web_url=?, updated_at=?
    WHERE id=?
    """, (
        site.name.strip(), site.launcher_button.strip(), site.url.strip(), site.idp_username.strip(), enc_idp,
        1 if site.enabled else 0, site.sort_order, site.notes,
        site.local_port, site.remote_host.strip(), site.remote_port, site.ssh_host.strip(), site.ssh_port,
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
    if result.id:
        cursor.execute("""
        UPDATE run_site_results SET status=?, action_point_status=?, csv_path=?, third_line_text=?, start_time=?, end_time=?, duration_seconds=?, retry_count=?, error_message=?, log_snippet=?
        WHERE id=?
        """, (
            result.status, result.action_point_status, result.csv_path, result.third_line_text,
            result.start_time, result.end_time, result.duration_seconds, result.retry_count,
            result.error_message, result.log_snippet, result.id
        ))
        res_id = result.id
    else:
        cursor.execute("""
        INSERT INTO run_site_results (run_id, site_id, site_name, status, action_point_status, csv_path, third_line_text, start_time, end_time, duration_seconds, retry_count, error_message, log_snippet)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.run_id, result.site_id, result.site_name, result.status,
            result.action_point_status, result.csv_path, result.third_line_text,
            result.start_time, result.end_time, result.duration_seconds,
            result.retry_count, result.error_message, result.log_snippet
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
    conn.close()

    runs = []
    for r in rows:
        runs.append(dict(r))
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
