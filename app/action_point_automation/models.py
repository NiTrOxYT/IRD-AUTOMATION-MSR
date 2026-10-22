import enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class ActionPointStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    DRY_RUN = "DRY_RUN"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    SKIPPED_ALREADY_CONFIGURED = "SKIPPED_ALREADY_CONFIGURED"
    SKIPPED_UNSUPPORTED_STATUS = "SKIPPED_UNSUPPORTED_STATUS"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


class ActionClassification(str, enum.Enum):
    CATEGORY_UPDATE = "CATEGORY_UPDATE"
    UNSUPPORTED_STATUS = "UNSUPPORTED_STATUS"
    INVALID_DATA = "INVALID_DATA"


class ExecutionMode(str, enum.Enum):
    DRY_RUN = "DRY_RUN"
    LIVE = "LIVE"


class RunState(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class InspectionOutcome(str, enum.Enum):
    EXISTS = "EXISTS"
    MISSING_CONFIRMED = "MISSING_CONFIRMED"
    INSPECTION_FAILED = "INSPECTION_FAILED"


class CategoryInspectionResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    category_name: str
    outcome: InspectionOutcome
    matched_name: Optional[str] = None
    reason: str = ""
    pages_inspected: int = 0
    rows_inspected: int = 0
    restaurant: Optional[str] = None
    is_active: bool = True
    page_url: str = ""
    duration_seconds: float = 0.0


class SubcategoryInspectionResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    parent_category: str
    subcategory_name: str
    outcome: InspectionOutcome
    matched_name: Optional[str] = None
    reason: str = ""
    parent_expanded: bool = False
    children_found: List[str] = Field(default_factory=list)
    page_url: str = ""
    duration_seconds: float = 0.0


class ActionPointItem(BaseModel):
    """Represents a validated row from an action point CSV/XLSX file."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    row_number: int
    item_code: str                     # String preserved with leading zeros
    item_name: str
    item_price: str                    # Original string representation of price
    category: str
    subcategory: Optional[str] = ""
    original_status: str
    normalized_status: str
    classification: ActionClassification
    is_valid: bool = True
    validation_errors: List[str] = Field(default_factory=list)


class ItemExecutionResult(BaseModel):
    """Represents the execution outcome of a single action point item."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    row_number: int
    item_code: str
    item_name: str
    requested_category: str
    requested_subcategory: Optional[str] = ""
    original_status: str
    classification: ActionClassification
    status: ActionPointStatusEnum = ActionPointStatusEnum.PENDING
    failure_reason: str = ""
    category_created: bool = False
    subcategory_created: bool = False
    subcategory_verified: bool = False
    item_found: bool = False
    item_checkbox_selected: bool = False
    category_selected: bool = False
    subcategory_selected: bool = False
    subcategory_skipped: bool = False
    restaurant_selected: bool = False
    configure_submitted: bool = False
    persisted_verified: bool = False
    restaurant_verified: bool = False
    portal_verified: bool = False
    screenshot_path: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0
    failure_stage: Optional[str] = None
    search_duration_seconds: float = 0.0
    item_select_duration_seconds: float = 0.0
    category_select_duration_seconds: float = 0.0
    restaurant_select_duration_seconds: float = 0.0
    save_duration_seconds: float = 0.0
    post_save_duration_seconds: float = 0.0


class PerformanceMetrics(BaseModel):
    """Detailed runtime performance metrics."""
    total_run_duration_seconds: float = 0.0
    average_time_per_item_seconds: float = 0.0
    portal_navigation_duration_seconds: float = 0.0
    login_and_auth_duration_seconds: float = 0.0
    category_inspection_duration_seconds: float = 0.0
    category_creation_duration_seconds: float = 0.0
    subcategory_expansion_duration_seconds: float = 0.0
    subcategory_creation_duration_seconds: float = 0.0
    item_processing_duration_seconds: float = 0.0
    item_search_total_seconds: float = 0.0
    category_select_total_seconds: float = 0.0
    restaurant_select_total_seconds: float = 0.0
    configure_save_total_seconds: float = 0.0
    post_save_verification_total_seconds: float = 0.0
    screenshot_capture_total_seconds: float = 0.0
    report_generation_duration_seconds: float = 0.0
    total_navigations: int = 0
    total_searches: int = 0
    total_retries: int = 0
    total_screenshots: int = 0


class FileValidationSummary(BaseModel):
    """Summary of source file parsing and validation."""
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    action_point_rows: int = 0         # Rows classified as CATEGORY_UPDATE
    unsupported_status_rows: int = 0
    duplicate_item_codes: List[str] = Field(default_factory=list)
    unique_categories: List[str] = Field(default_factory=list)
    unique_subcategories: List[str] = Field(default_factory=list)


class ValidateFileResponse(BaseModel):
    """API response for file upload and preview."""
    success: bool
    filename: str
    summary: FileValidationSummary
    items: List[ActionPointItem] = Field(default_factory=list)
    structural_errors: List[str] = Field(default_factory=list)


class StartActionPointRunRequest(BaseModel):
    """Payload to trigger a Dry-Run or Live Execution."""
    site_id: int
    filename: str
    mode: ExecutionMode = ExecutionMode.DRY_RUN
    items: Optional[List[ActionPointItem]] = None
    capture_success_screenshots: bool = False


class BrowserSnapshot(BaseModel):
    """Represents an atomic screenshot and DOM inspection event."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    step_number: int
    timestamp: str
    action_name: str
    url: str
    page_title: str
    expected_state: Optional[str] = None
    detected_state: str = "UNKNOWN"
    verification_passed: bool = True
    screenshot_path: Optional[str] = None
    row_number: Optional[int] = None
    item_code: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
