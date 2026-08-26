import os
import logging
from pathlib import Path
from typing import Dict, List, Any

from app.config import DATA_DIR, DOWNLOADS_DIR, REPORTS_DIR, LOGS_DIR, DB_PATH
from app.tunneling.putty_paths import (
    get_application_root, get_bundled_plink_path,
    get_bundled_putty_path, get_relative_display_path
)

logger = logging.getLogger("IRD_PackageValidator")

class PackageValidator:
    """
    Validates complete package health, bundled executable availability, and directory permissions.
    """

    @classmethod
    def validate_package_health(cls) -> Dict[str, Any]:
        """
        Runs comprehensive checklist on portable application package.
        """
        root = get_application_root()
        checks: List[Dict[str, Any]] = []
        all_ok = True

        # 1. Bundled Plink Executable
        plink_p = get_bundled_plink_path()
        plink_ok = bool(plink_p and os.path.exists(plink_p))
        if not plink_ok:
            all_ok = False
        checks.append({
            "name": "Bundled Plink Executable",
            "status": "PASS" if plink_ok else "FAIL",
            "ok": plink_ok,
            "path": get_relative_display_path(plink_p or str(root / "tools" / "putty" / "plink.exe")),
            "description": "Required for reverse SSH tunnel management"
        })

        # 2. Bundled PuTTY Executable
        putty_p = get_bundled_putty_path()
        putty_ok = bool(putty_p and os.path.exists(putty_p))
        checks.append({
            "name": "Bundled PuTTY Executable",
            "status": "PASS" if putty_ok else "INFO",
            "ok": putty_ok,
            "path": get_relative_display_path(putty_p or str(root / "tools" / "putty" / "putty.exe")),
            "description": "Graphical PuTTY utility binary"
        })

        # 3. Core Application Code
        app_dir = root / "app"
        app_ok = app_dir.exists() and (app_dir / "main.py").exists()
        if not app_ok:
            all_ok = False
        checks.append({
            "name": "Core Application Files",
            "status": "PASS" if app_ok else "FAIL",
            "ok": app_ok,
            "path": "app/main.py",
            "description": "FastAPI & automation execution engine"
        })

        # 4. Database Directory
        db_dir_ok = DATA_DIR.exists()
        db_ok = DB_PATH.exists()
        checks.append({
            "name": "SQLite Database",
            "status": "PASS" if (db_dir_ok and db_ok) else "WARN",
            "ok": db_dir_ok,
            "path": get_relative_display_path(str(DB_PATH)),
            "description": "Persistent site configuration & run history database"
        })

        # 5. Writable Output Directories
        for name, p in [("Downloads Directory", DOWNLOADS_DIR), ("Reports Directory", REPORTS_DIR), ("Logs Directory", LOGS_DIR)]:
            ok = p.exists() and os.access(str(p), os.W_OK)
            if not ok:
                all_ok = False
            checks.append({
                "name": name,
                "status": "PASS" if ok else "FAIL",
                "ok": ok,
                "path": get_relative_display_path(str(p)),
                "description": f"Writable filesystem location for {name.lower()}"
            })

        # 6. UI Static Files
        index_html = app_dir / "ui" / "index.html"
        ui_ok = index_html.exists()
        if not ui_ok:
            all_ok = False
        checks.append({
            "name": "Frontend Web Console UI",
            "status": "PASS" if ui_ok else "FAIL",
            "ok": ui_ok,
            "path": "app/ui/index.html",
            "description": "Single-page desktop Web UI console"
        })

        overall_status = "READY" if all_ok else "INCOMPLETE"
        return {
            "overall_status": overall_status,
            "all_ok": all_ok,
            "application_root": str(root),
            "checks": checks
        }

package_validator = PackageValidator()
