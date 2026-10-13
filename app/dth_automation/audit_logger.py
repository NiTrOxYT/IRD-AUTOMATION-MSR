import logging
import re
import json
import time
from typing import Dict, Any, Optional

logger = logging.getLogger("DTH_Audit")

# Patterns for sensitive tokens that must NEVER appear in audit logs
SENSITIVE_PATTERNS = [
    r"password[\"']?\s*[:=]\s*[\"']?([^\"'\s,]+)",
    r"bearer\s+([a-zA-Z0-9\._\-]+)",
    r"session[_\-]?id[\"']?\s*[:=]\s*[\"']?([^\"'\s,]+)",
    r"token[\"']?\s*[:=]\s*[\"']?([^\"'\s,]+)"
]


def sanitize_message(msg: str) -> str:
    """Sanitizes text to prevent leakage of credentials or session tokens."""
    if not msg:
        return ""
    sanitized = str(msg)
    for pat in SENSITIVE_PATTERNS:
        sanitized = re.sub(pat, r"***REDACTED***", sanitized, flags=re.IGNORECASE)
    return sanitized


class DthAuditLogger:
    @staticmethod
    def log_event(event_type: str, run_id: Optional[int], channel_number: Optional[str], details: Dict[str, Any]):
        """Records a sanitized structured audit event."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        sanitized_details = {}
        for k, v in details.items():
            if isinstance(v, str):
                sanitized_details[k] = sanitize_message(v)
            else:
                sanitized_details[k] = v

        log_payload = {
            "timestamp": timestamp,
            "event": event_type,
            "run_id": run_id,
            "channel_number": channel_number,
            "details": sanitized_details
        }
        logger.info(f"[AUDIT] {event_type} | Run #{run_id or 'NONE'} | Ch: {channel_number or 'N/A'} | {json.dumps(sanitized_details)}")
        return log_payload
