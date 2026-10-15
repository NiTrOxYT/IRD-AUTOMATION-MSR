from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class ControllerCloneRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    site_id: Optional[int] = None
    site_name: Optional[str] = ""
    site_ip: str = Field(..., description="Site server IP address")
    site_port: int = Field(default=2222, description="Site server SSH port")
    site_username: str = Field(default="support", description="Site server SSH username")
    site_password: str = Field(default="SuPp0rt@MVM@202602", description="Site server SSH password")

    jump_host: str = Field(default="111.93.205.187", description="Jump server IP")
    jump_port: int = Field(default=22, description="Jump server SSH port")
    jump_username: str = Field(default="sourik", description="Jump server username")
    jump_password: str = Field(default="s0urik@@", description="Jump server password")

    current_room_no: str = Field(..., description="Current room number, e.g. 101")
    current_room_ip: str = Field(..., description="Current controller IP address, e.g. 10.172.1.101")

    similar_room_no: str = Field(..., description="Similar room number to clone from, e.g. 102")
    similar_room_ip: str = Field(..., description="Similar controller IP to clone from, e.g. 10.172.1.102")

    is_new_controller: bool = Field(default=False, description="Whether this is a new controller with default IP 10.172.100.100")
    controller_passwords: List[str] = Field(default_factory=lambda: ["msr123", "msr@123"], description="Candidate passwords for controller root")
    restart_network_after_ip_change: bool = Field(default=False, description="Whether to restart network service after ifcfg changes")

    @property
    def target_ip(self) -> str:
        """Determines the target SSH IP based on whether the controller is new or already configured."""
        if self.is_new_controller:
            return "10.172.100.100"
        return self.current_room_ip.strip()


class TestConnectionRequest(BaseModel):
    __test__ = False
    model_config = ConfigDict(extra="ignore")

    site_id: Optional[int] = None
    site_ip: str
    site_port: int = 2222
    site_username: str = "support"
    site_password: str = "SuPp0rt@MVM@202602"

    jump_host: str = "111.93.205.187"
    jump_port: int = 22
    jump_username: str = "sourik"
    jump_password: str = "s0urik@@"

    current_room_ip: str
    similar_room_ip: str
    is_new_controller: bool = False
    controller_passwords: List[str] = Field(default_factory=lambda: ["msr123", "msr@123"])

    @property
    def target_ip(self) -> str:
        if self.is_new_controller:
            return "10.172.100.100"
        return self.current_room_ip.strip()


class ControllerStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    label: str
    status: str = "PENDING"  # PENDING, RUNNING, SUCCESS, FAILED, SKIPPED
    message: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0


class ControllerRunStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_uuid: str
    status: str = "PENDING"  # PENDING, RUNNING, SUCCESS, FAILED, STOPPED
    current_step: str = ""
    progress_pct: int = 0
    steps: List[ControllerStep] = Field(default_factory=list)
    logs: List[Dict[str, Any]] = Field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0
    error_message: Optional[str] = None

    site_name: str = ""
    site_ip: str = ""
    current_room_no: str = ""
    current_room_ip: str = ""
    target_ip: str = ""
    similar_room_no: str = ""
    similar_room_ip: str = ""
    is_new_controller: bool = False
    discovered_password: str = ""


class TestConnectionResult(BaseModel):
    __test__ = False
    model_config = ConfigDict(extra="ignore")

    success: bool
    jump_status: Dict[str, Any]
    site_status: Dict[str, Any]
    target_controller_status: Dict[str, Any]
    similar_controller_status: Dict[str, Any]
    message: str


class ControllerSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    jump_host: Optional[str] = None
    jump_port: Optional[int] = None
    jump_username: Optional[str] = None
    jump_password: Optional[str] = None
    site_username: Optional[str] = None
    site_password: Optional[str] = None
    site_default_port: Optional[int] = None
    candidate_passwords: Optional[str] = None
    default_new_controller_ip: Optional[str] = None
