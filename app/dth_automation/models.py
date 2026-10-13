from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class DthItemState(str, Enum):
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    INVALID = "INVALID"
    SKIPPED_DUPLICATE = "SKIPPED_DUPLICATE"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    CANCELLED = "CANCELLED"


class DthRunState(str, Enum):
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class DthExecutionMode(str, Enum):
    DRY_RUN = "DRY_RUN"
    LIVE = "LIVE"


class ChannelItem(BaseModel):
    row_number: int
    channel_number: str
    name: str
    osd: str
    image: str
    categories: List[str] = Field(default_factory=list)
    raw_categories: str = ""
    resolved_image_path: Optional[str] = None

    class Config:
        from_attributes = True


class ChannelValidationResult(BaseModel):
    row_number: int
    channel_number: str
    name: str
    status: DthItemState = DthItemState.READY
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    resolved_categories: List[str] = Field(default_factory=list)
    resolved_image_path: Optional[str] = None


class DthBatchValidationResponse(BaseModel):
    success: bool
    filename: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    items: List[ChannelItem] = Field(default_factory=list)
    validation_results: List[ChannelValidationResult] = Field(default_factory=list)
    image_dir: Optional[str] = None
    portal_categories: List[str] = Field(default_factory=list)


class DthChannelExecutionResult(BaseModel):
    id: Optional[int] = None
    run_id: int
    row_number: int
    channel_number: str
    name: str
    osd: str
    image: str
    categories: List[str] = Field(default_factory=list)
    status: DthItemState = DthItemState.PENDING
    attempt_count: int = 0
    duration_seconds: float = 0.0
    error_reason: str = ""
    verified_in_portal: bool = False
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class DthRunSummary(BaseModel):
    id: Optional[int] = None
    run_date: str
    start_time: str
    end_time: Optional[str] = None
    mode: DthExecutionMode = DthExecutionMode.DRY_RUN
    status: DthRunState = DthRunState.PENDING
    filename: str
    total_channels: int = 0
    processed_channels: int = 0
    successful_channels: int = 0
    failed_channels: int = 0
    skipped_duplicates: int = 0
    invalid_channels: int = 0
    unknown_channels: int = 0
    current_channel: Optional[str] = None
    current_operation: str = "Idle"
    progress_percentage: float = 0.0
    site_id: Optional[int] = None
    site_name: Optional[str] = None
    error_message: Optional[str] = None


class StartDthRunRequest(BaseModel):
    filename: str
    image_dir: str
    mode: DthExecutionMode = DthExecutionMode.DRY_RUN
    site_id: int
    channel_delay_seconds: float = Field(default=1.0, ge=0.0, le=30.0)
    authorized: bool = Field(default=False, description="Explicit authorization required for LIVE mode")


class DthSite(BaseModel):
    id: Optional[int] = None
    name: str
    portal_url: str = ""
    local_port: int = 18001
    site_ip: str = ""
    site_port: int = 80
    remote_host: str = "127.0.0.1"
    remote_port: int = 80
    ssh_host: str = ""
    ssh_port: int = 22
    ssh_username: str = ""
    auth_type: str = "key"
    putty_session: str = ""
    tunnel_type: str = "reverse"
    web_url: str = ""
    idp_username: str = ""
    has_password: bool = False
    idp_password_masked: str = ""
    has_ssh_password: bool = False
    ssh_password_masked: str = ""
    enabled: bool = True
    sort_order: int = 0
    notes: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DthSiteCreateRequest(BaseModel):
    name: str
    portal_url: Optional[str] = ""
    local_port: Optional[int] = 18001
    site_ip: Optional[str] = ""
    site_port: Optional[int] = 80
    remote_host: Optional[str] = "127.0.0.1"
    remote_port: Optional[int] = 80
    ssh_host: Optional[str] = ""
    ssh_port: Optional[int] = 22
    ssh_username: Optional[str] = ""
    ssh_password: Optional[str] = ""
    ssh_key_path: Optional[str] = ""
    auth_type: Optional[str] = "key"
    putty_session: Optional[str] = ""
    tunnel_type: Optional[str] = "reverse"
    web_url: Optional[str] = ""
    idp_username: Optional[str] = ""
    idp_password: Optional[str] = ""
    enabled: Optional[bool] = True
    sort_order: Optional[int] = 0
    notes: Optional[str] = ""


class DthDashboardStats(BaseModel):
    total_sites: int = 0
    total_channels_processed: int = 0
    successful_channels: int = 0
    failed_channels: int = 0
    skipped_duplicates: int = 0
    total_runs: int = 0
    active_run_id: Optional[int] = None
    active_status: str = "IDLE"
    recent_runs: List[Dict[str, Any]] = Field(default_factory=list)


class DthSettingsModel(BaseModel):
    default_mode: str = "DRY_RUN"
    channel_delay_seconds: float = 1.0
    max_row_count: int = 5000
    max_file_size_mb: int = 10
    page_load_timeout: int = 60
    save_timeout: int = 30
    debug_screenshots: bool = True
    log_level: str = "INFO"
    image_allowed_extensions: str = ".png,.jpg,.jpeg,.bmp,.webp"
    max_image_size_kb: int = 2048
