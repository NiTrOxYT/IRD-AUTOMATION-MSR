import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
DATA_DIR = BASE_DIR / "data"
DOWNLOADS_DIR = BASE_DIR / "downloads"
REPORTS_DIR = BASE_DIR / "reports"
LOGS_DIR = BASE_DIR / "logs"
SCREENSHOTS_DIR = LOGS_DIR / "screenshots"

# Ensure required directories exist
for folder in [DATA_DIR, DOWNLOADS_DIR, REPORTS_DIR, LOGS_DIR, SCREENSHOTS_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

# Database Path
DB_PATH = DATA_DIR / "ird_automation.db"

# Application Metadata
APP_NAME = "IRD Sync Automation"
APP_VERSION = "1.0.0"

# Default Automation Settings
DEFAULT_SETTINGS = {
    "launcher_exe_path": r"C:\Program Files\MSR\MSR ZMP PORTAL LAUNCHER.exe",
    "launcher_window_title": "MSR ZMP PORTAL LAUNCHER",
    "browser_type": "chromium",  # chromium, msedge, chrome
    "headless": False,
    "page_load_timeout": 120,    # seconds
    "login_timeout": 60,         # seconds
    "fetch_menu_timeout": 600,   # seconds (10 minutes)
    "process_menu_timeout": 600, # seconds (10 minutes)
    "service_recovery_timeout": 600, # seconds (10 minutes)
    "download_timeout": 120,     # seconds
    "max_process_retries": 3,
    "retry_interval": 10,        # seconds
    "downloads_dir": str(DOWNLOADS_DIR),
    "reports_dir": str(REPORTS_DIR),
    "debug_mode": True,          # Capture screenshots on errors/steps
    "port": 18492,               # Internal API bridge port
    "putty_path": r"C:\Program Files\PuTTY\plink.exe",
    "default_local_port": 18001,
    "tunnel_start_timeout": 30,  # seconds
    "tunnel_retry_count": 3,
    "auto_stop_tunnel": True,
    "auto_restart_tunnel": True,
    "office_ssh_host": "111.93.205.187",
    "office_ssh_port": 22,
    "office_ssh_username": "sourik",
    "office_ssh_auth_type": "password",
    "office_ssh_key_path": "",
    "office_ssh_host_key": "",
}

