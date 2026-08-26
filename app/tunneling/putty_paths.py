import os
import sys
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("IRD_PuTTYPaths")

def get_application_root() -> Path:
    """
    Dynamically determines application root directory supporting:
    1. Normal Python execution (`python app/main.py`)
    2. Standalone scripts
    3. PyInstaller frozen application (`sys._MEIPASS` / `sys.executable`)
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller bundled environment
        exe_dir = Path(sys.executable).resolve().parent
        return exe_dir

    # Normal directory layout: app/tunneling/putty_paths.py -> root is 2 levels up
    file_path = Path(__file__).resolve()
    return file_path.parent.parent.parent

def get_bundled_plink_path() -> Optional[str]:
    """
    Returns absolute path to bundled plink.exe if present.
    Searches:
    1. <app_root>/tools/putty/plink.exe
    2. <app_root>/tools/plink.exe
    3. <app_root>/plink.exe
    """
    root = get_application_root()
    candidates = [
        root / "tools" / "putty" / "plink.exe",
        root / "tools" / "plink.exe",
        root / "plink.exe",
    ]

    for p in candidates:
        if p.exists() and p.is_file():
            return str(p)

    return None

def get_bundled_putty_path() -> Optional[str]:
    """
    Returns absolute path to bundled putty.exe if present.
    """
    root = get_application_root()
    candidates = [
        root / "tools" / "putty" / "putty.exe",
        root / "tools" / "putty.exe",
        root / "putty.exe",
    ]

    for p in candidates:
        if p.exists() and p.is_file():
            return str(p)

    return None

def get_active_plink_path() -> Tuple[Optional[str], bool, str]:
    """
    Determines active plink executable path.
    Returns (path, is_custom_override, source_description).
    """
    from app.database.db import get_setting

    use_custom = str(get_setting("use_custom_plink")).lower() in ("true", "1")
    custom_path = get_setting("custom_plink_path") or ""

    if use_custom and custom_path and os.path.exists(custom_path):
        return custom_path, True, "Custom Executable Override"

    bundled = get_bundled_plink_path()
    if bundled:
        return bundled, False, "Bundled Portable (tools/putty/plink.exe)"

    # Fallback search if setting path specified
    legacy_path = get_setting("putty_path")
    if legacy_path and os.path.exists(legacy_path):
        return legacy_path, False, "Configured Path"

    return None, False, "Not Found"

def get_relative_display_path(path_str: Optional[str]) -> str:
    """
    Converts absolute file path into clean relative display string (e.g. tools\\putty\\plink.exe).
    """
    if not path_str:
        return "NOT FOUND"

    try:
        root = get_application_root()
        abs_p = Path(path_str).resolve()
        if root in abs_p.parents or abs_p.parent == root:
            rel = abs_p.relative_to(root)
            return str(rel)
    except Exception:
        pass

    return path_str
