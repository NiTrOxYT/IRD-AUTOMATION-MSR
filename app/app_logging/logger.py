import os
import re
import sys
import logging
from datetime import datetime
from typing import List, Callable
from collections import deque
from pathlib import Path

from app.config import LOGS_DIR

# Password scrubber regex pattern
PASSWORD_SCRUB_REGEX = re.compile(
    r'(password|pass|pwd|secret|cred|credential)["\']?\s*[:=]\s*["\']?([^"\'\s&,]+)',
    re.IGNORECASE
)

class PasswordScrubbingFormatter(logging.Formatter):
    """Logging formatter that scrubs passwords from log messages."""
    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return PASSWORD_SCRUB_REGEX.sub(r'\1: [REDACTED]', formatted)

class MemoryLogBufferHandler(logging.Handler):
    """In-memory handler to stream logs to desktop UI terminal."""
    def __init__(self, maxlen: int = 1000):
        super().__init__()
        self.buffer = deque(maxlen=maxlen)
        self.listeners: List[Callable[[dict], None]] = []

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                "level": record.levelname,
                "logger": record.name,
                "message": msg
            }
            self.buffer.append(log_entry)
            for listener in self.listeners:
                try:
                    listener(log_entry)
                except Exception:
                    pass
        except Exception:
            self.handleError(record)

    def add_listener(self, callback: Callable[[dict], None]):
        if callback not in self.listeners:
            self.listeners.append(callback)

memory_log_handler = MemoryLogBufferHandler()

def setup_global_logging(log_filename: str = None) -> logging.Logger:
    """Configures root application logger."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = Path(LOGS_DIR) / (log_filename or f"{date_str}.log")

    formatter = PasswordScrubbingFormatter(
        fmt="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
        datefmt="%H:%M:%S"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    # File Handler
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)

    # Memory Handler for UI
    memory_log_handler.setFormatter(formatter)
    memory_log_handler.setLevel(logging.INFO)
    root_logger.addHandler(memory_log_handler)

    return root_logger

def get_recent_logs(limit: int = 200) -> List[dict]:
    """Returns recent log entries from memory buffer."""
    buf_list = list(memory_log_handler.buffer)
    return buf_list[-limit:]
