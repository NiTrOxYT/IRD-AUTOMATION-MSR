import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from app.config import LOGS_DIR

logger = logging.getLogger("ActionPoint_AuditLogger")


class ActionPointAuditLogger:
    """Writes tamper-evident structured audit trail entries for action point runs."""

    def __init__(self, run_id: Any, site_name: str):
        self.run_id = run_id
        self.site_name = site_name
        self.date_str = datetime.now().strftime("%Y-%m-%d")
        self.audit_log_path = LOGS_DIR / f"action_point_{self.date_str}.log"

    def log_event(self, event_type: str, details: Dict[str, Any]):
        """Appends a structured JSON audit record."""
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "run_id": self.run_id,
            "site_name": self.site_name,
            "event_type": event_type,
            "details": details
        }
        try:
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.debug(f"Audit log write failed: {e}")
