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
    def get_relative_display_path(cls, path_str: Optional[str]) -> str:
        return get_relative_display_path(path_str)

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
        # Replace secret tokens / keys in strings
        scrubbed = re.sub(r'(token=)([^&\s]+)', r'\1********', scrubbed, flags=re.IGNORECASE)
        return scrubbed

    @classmethod
    def build_plink_command(cls, site: Any, plink_path: Optional[str] = None) -> List[str]:
        """
        Constructs safe subprocess argument list for plink.exe from:
        Global Office SSH Server Config + Site IP + Site Local Port.
        """
        from app.database.db import get_office_ssh_config, get_office_ssh_password_decrypted, get_global_tunnel_config

        if not plink_path:
            plink_path, _, _ = get_active_plink_path()

        if not plink_path:
            raise FileNotFoundError("Bundled Plink executable tools/putty/plink.exe was not found.")

        cmd = [plink_path, "-batch", "-N"]

        ssh_cfg = get_office_ssh_config()
        global_tunnel_cfg = get_global_tunnel_config()

        # SSH Server Host, Port, Username
        ssh_host = getattr(site, "ssh_host", "") or ssh_cfg.get("ssh_host") or "111.93.205.187"
        ssh_port = getattr(site, "ssh_port", 0) or ssh_cfg.get("ssh_port") or 22
        ssh_user = getattr(site, "ssh_username", "") or ssh_cfg.get("ssh_username") or "sourik"
        auth_type = str(getattr(site, "auth_type", "") or ssh_cfg.get("auth_type") or "password").lower()
        session_name = getattr(site, "putty_session", "") or ""

        # 1. PuTTY Saved Session
        if auth_type == "session" and session_name:
            cmd.extend(["-load", session_name])
        else:
            cmd.append("-ssh")
            cmd.extend(["-P", str(ssh_port)])

            if ssh_user:
                cmd.extend(["-l", ssh_user])

            # Host Key if configured
            ssh_host_key = (getattr(site, "ssh_host_key", "") or "").strip() or ssh_cfg.get("ssh_host_key", "")
            if ssh_host_key:
                cmd.extend(["-hostkey", ssh_host_key])

            # Private Key
            ssh_key = (getattr(site, "ssh_key_path", "") or "").strip() or ssh_cfg.get("ssh_key_path", "")
            if auth_type == "key" and ssh_key and os.path.exists(ssh_key):
                cmd.extend(["-i", ssh_key])
            else:
                # Password Auth (DPAPI Decrypted in memory)
                ssh_pass = (getattr(site, "ssh_password", "") or "").strip() or get_office_ssh_password_decrypted()
                if ssh_pass:
                    cmd.extend(["-pw", ssh_pass])

        # Forwarding Specification: Local Port, Site IP, Site Port
        local_port = getattr(site, "local_port", 18001) or 18001
        site_ip = getattr(site, "site_ip", "") or getattr(site, "remote_host", "127.0.0.1") or "127.0.0.1"
        site_port = getattr(site, "site_port", 0) or getattr(site, "remote_port", 0) or global_tunnel_cfg.get("tunnel_remote_port") or 8082
        
        # Architecture is LOCAL PORT FORWARDING (-L) for desktop browser access (127.0.0.1:<local_port> -> <site_ip>:<site_port>)
        cmd.extend(["-L", f"{local_port}:{site_ip}:{site_port}"])

        # Target SSH Host
        if not (auth_type == "session" and session_name):
            cmd.append(ssh_host)

        return cmd




    @classmethod
    def build_ssh_test_command(cls, ssh_cfg: Dict[str, Any], plink_path: Optional[str] = None) -> List[str]:
        """
        Constructs safe subprocess argument list for testing direct SSH connectivity.
        """
        if not plink_path:
            plink_path, _, _ = get_active_plink_path()

        if not plink_path:
            raise FileNotFoundError("Bundled Plink executable tools/putty/plink.exe was not found.")

        cmd = [plink_path, "-batch", "-ssh"]

        ssh_port = ssh_cfg.get("ssh_port") or ssh_cfg.get("port") or 22
        cmd.extend(["-P", str(ssh_port)])

        ssh_user = ssh_cfg.get("ssh_username") or ssh_cfg.get("username") or ""
        if ssh_user:
            cmd.extend(["-l", ssh_user])

        auth_type = str(ssh_cfg.get("auth_type", "password")).lower()
        if auth_type == "key" and ssh_cfg.get("ssh_key_path"):
            cmd.extend(["-i", ssh_cfg["ssh_key_path"]])

        ssh_pass = ssh_cfg.get("ssh_password") or ""
        if auth_type == "password" and ssh_pass:
            cmd.extend(["-pw", ssh_pass])

        host_key = ssh_cfg.get("ssh_host_key") or ""
        if host_key:
            cmd.extend(["-hostkey", host_key])

        ssh_host = ssh_cfg.get("ssh_host") or ssh_cfg.get("host") or "111.93.205.187"
        cmd.append(ssh_host)
        cmd.append("echo SSH_TEST_OK")

        return cmd

putty_manager = PuTTYManager()


