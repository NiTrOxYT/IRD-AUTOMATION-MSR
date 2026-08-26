from dataclasses import dataclass, field
from typing import Optional, List
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
    # Tunnel / SSH Configurations
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
