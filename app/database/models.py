from dataclasses import dataclass, field
from typing import Optional, List, Any

from datetime import datetime

@dataclass
class Site:
    id: Optional[int] = None
    name: str = ""
    launcher_button: str = ""
    url: str = ""
    idp_username: str = ""
    idp_password: str = ""  # Plaintext in memory, stored encrypted in DB
    enabled: bool = True
    sort_order: int = 0
    notes: str = ""
    # Site IP, Site Port & Tunnel / SSH Configurations
    site_ip: str = ""
    site_port: int = 80
    local_port: int = 18001

    remote_host: str = "127.0.0.1"

    remote_port: int = 80
    ssh_host: str = ""
    ssh_port: int = 22
    ssh_username: str = ""
    ssh_password: str = ""  # Plaintext in memory, stored encrypted in DB
    ssh_key_path: str = ""
    auth_type: str = "key"  # key, session, password
    putty_session: str = ""
    tunnel_type: str = "reverse"
    web_url: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

def get_site_web_url(site: Any) -> str:
    """Returns canonical ZMP portal webpage URL: http://localhost:<local_port>/zmp/main-menu.do"""
    port = getattr(site, "local_port", 18001) if hasattr(site, "local_port") else 18001
    if not port:
        port = 18001
    return f"http://localhost:{port}/zmp/main-menu.do"


@dataclass
class Setting:
    key: str
    value: str
    updated_at: Optional[str] = None

@dataclass
class Run:
    id: Optional[int] = None
    run_date: str = ""
    start_time: str = ""
    end_time: Optional[str] = None
    status: str = "IN_PROGRESS" # IN_PROGRESS, COMPLETED, STOPPED, FAILED
    total_sites: int = 0
    completed_sites: int = 0
    action_points_count: int = 0
    no_action_points_count: int = 0
    failed_sites_count: int = 0
    log_path: str = ""

@dataclass
class RunSiteResult:
    id: Optional[int] = None
    run_id: int = 0
    site_id: int = 0
    site_name: str = ""
    status: str = "PENDING"
    action_point_status: str = "PENDING" # ACTION POINT FOUND, NO ACTION POINT, FAILED, SKIPPED
    csv_path: str = ""
    third_line_text: str = ""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_seconds: float = 0.0
    retry_count: int = 0
    error_message: str = ""
    log_snippet: str = ""

@dataclass
class Selector:
    step_key: str
    primary_selector: str
    fallback_selectors: str = "" # JSON list string
    description: str = ""

@dataclass
class RunHistoryRecord:
    id: Optional[int] = None
    site_id: int = 0
    site_name: str = ""
    start_time: str = ""
    end_time: str = ""
    tunnel_status: str = "UNKNOWN"
    login_status: str = "UNKNOWN"
    sync_mymenu_status: str = "UNKNOWN"
    fetch_menu_status: str = "UNKNOWN"
    fetch_menu_attempts: int = 1
    service_recovery_count: int = 0
    final_status: str = "FAILED"
    error_code: str = "NONE"
    error_message: str = ""

