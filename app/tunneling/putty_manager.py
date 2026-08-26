import os
import re
import subprocess
import logging
from typing import Dict, List, Optional, Any, Tuple

from app.database.db import get_setting
from app.tunneling.putty_paths import (
    get_bundled_plink_path, get_bundled_putty_path,
    get_active_plink_path, get_relative_display_path
)

logger = logging.getLogger("IRD_PuTTYManager")

class PuTTYManager:
    """
    Manages portable execution, command generation, version testing, and log scrubbing for PuTTY and Plink.
    """

    @classmethod
    def detect_executables(cls) -> Dict[str, Any]:
        """
        Detects bundled and active paths for plink.exe and putty.exe.
        """
        plink_path, is_custom, source_desc = get_active_plink_path()
        putty_path = get_bundled_putty_path()
        rel_plink = get_relative_display_path(plink_path)

        version_info = "Unknown"
        if plink_path and os.path.exists(plink_path):
            v_res = cls.test_plink_executable(plink_path)
            if v_res["success"]:
                version_info = v_res.get("version", "Release")

        return {
            "plink": plink_path,
            "putty": putty_path,
            "relative_plink": rel_plink,
            "is_custom": is_custom,
            "source": source_desc,
            "version": version_info,
            "found": bool(plink_path and os.path.exists(plink_path))
        }

    @classmethod
    def test_plink_executable(cls, plink_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Runs 'plink.exe -V' without establishing SSH connections.
        """
        if not plink_path:
            plink_path, _, _ = get_active_plink_path()

        if not plink_path or not os.path.exists(plink_path):
            return {
                "success": False,
                "message": "Bundled Plink executable was not found.",
                "path": "tools/putty/plink.exe",
                "version": "Not Available",
                "details": "Expected path: tools/putty/plink.exe. Please ensure full application package is extracted."
            }

        rel_path = get_relative_display_path(plink_path)
        try:
            output = subprocess.check_output([plink_path, "-V"], stderr=subprocess.STDOUT, text=True, timeout=5)
            first_line = output.strip().splitlines()[0] if output else "plink"
            return {
                "success": True,
                "message": f"Plink version test passed: {first_line}",
                "path": rel_path,
                "version": first_line,
                "details": output.strip()
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Execution of plink at '{rel_path}' failed: {str(e)}",
                "path": rel_path,
                "version": "Error",
                "details": str(e)
            }

    @classmethod
    def scrub_sensitive_info(cls, text: str) -> str:
        """
        Removes SSH passwords, IDP passwords, and secret parameters from text.
        """
        if not text:
            return ""

        # Replace -pw <password>
        scrubbed = re.sub(r'(-pw\s+)(\S+)', r'\1********', text, flags=re.IGNORECASE)
        # Replace password=...
        scrubbed = re.sub(r'(password=)([^&\s]+)', r'\1********', scrubbed, flags=re.IGNORECASE)
        return scrubbed

    @classmethod
    def build_plink_command(cls, site: Any, plink_path: Optional[str] = None) -> List[str]:
        """
        Constructs safe subprocess argument list for plink.exe (-R reverse tunnel).
        """
        if not plink_path:
            plink_path, _, _ = get_active_plink_path()

        if not plink_path:
            raise FileNotFoundError("Bundled Plink executable tools/putty/plink.exe was not found.")

        cmd = [plink_path, "-batch", "-N"]

        auth_type = getattr(site, "auth_type", "key") or "key"
        session_name = getattr(site, "putty_session", "") or ""

        # 1. PuTTY Saved Session
        if auth_type == "session" and session_name:
            cmd.extend(["-load", session_name])
        else:
            cmd.append("-ssh")

            ssh_port = getattr(site, "ssh_port", 22) or 22
            cmd.extend(["-P", str(ssh_port)])

            ssh_user = getattr(site, "ssh_username", "") or ""
            if ssh_user:
                cmd.extend(["-l", ssh_user])

            # Private Key
            ssh_key = getattr(site, "ssh_key_path", "") or ""
            if auth_type == "key" and ssh_key:
                cmd.extend(["-i", ssh_key])

            # Password Auth
            ssh_pass = getattr(site, "ssh_password", "") or ""
            if auth_type == "password" and ssh_pass:
                cmd.extend(["-pw", ssh_pass])

        # Reverse Tunnel Specification: -R <REMOTE_PORT>:<REMOTE_HOST>:<LOCAL_PORT>
        local_port = getattr(site, "local_port", 18001) or 18001
        remote_host = getattr(site, "remote_host", "127.0.0.1") or "127.0.0.1"
        remote_port = getattr(site, "remote_port", 80) or 80

        tunnel_arg = f"{remote_port}:{remote_host}:{local_port}"
        cmd.extend(["-R", tunnel_arg])

        # Target SSH Host
        ssh_host = getattr(site, "ssh_host", "") or "127.0.0.1"
        if not (auth_type == "session" and session_name):
            cmd.append(ssh_host)

        return cmd

putty_manager = PuTTYManager()
