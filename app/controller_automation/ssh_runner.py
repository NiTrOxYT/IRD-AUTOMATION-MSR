import os
import sys
import base64
import logging
import subprocess
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any

from app.config import BASE_DIR

logger = logging.getLogger("Controller_SSHRunner")

# Prefer bundled plink.exe in tools/putty/plink.exe, fallback to system PATH
BUNDLED_PLINK = BASE_DIR / "tools" / "putty" / "plink.exe"


def get_plink_path() -> str:
    """Returns absolute path to plink.exe."""
    if BUNDLED_PLINK.exists():
        return str(BUNDLED_PLINK)
    # Check standard install path
    std_path = Path(r"C:\Program Files\PuTTY\plink.exe")
    if std_path.exists():
        return str(std_path)
    return "plink.exe"


class MultiHopSSHRunner:
    """
    Executes commands across a 3-hop SSH topology:
    Host (Windows) -> Jump Server (Plink) -> Site Server (sshpass) -> Room Controller (sshpass)
    """

    def __init__(
        self,
        jump_host: str = "111.93.205.187",
        jump_port: int = 22,
        jump_user: str = "sourik",
        jump_pass: str = "s0urik@@",
        timeout: int = 25
    ):
        self.jump_host = jump_host.strip()
        self.jump_port = int(jump_port)
        self.jump_user = jump_user.strip()
        self.jump_pass = jump_pass.strip()
        self.timeout = timeout
        self.plink_path = get_plink_path()

    def run_on_jump(self, command: str, timeout: Optional[int] = None) -> Tuple[int, str, str]:
        """
        Executes a command directly on the Jump Server using plink.exe.
        Uses base64 script wrapper to prevent quoting/escaping issues.
        """
        t = timeout or self.timeout
        # Base64 encode the command to avoid any cmd/powershell/bash character mangling
        b64_cmd = base64.b64encode(command.encode("utf-8")).decode("ascii")
        remote_exec = f"echo {b64_cmd} | base64 -d | bash"

        cmd_args = [
            self.plink_path,
            "-batch",
            "-ssh",
            "-P", str(self.jump_port),
            "-l", self.jump_user,
            "-pw", self.jump_pass,
            self.jump_host,
            remote_exec
        ]

        logger.debug(f"[PLINK -> JUMP] Executing: {command[:100]}...")
        try:
            proc = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                timeout=t,
                encoding="utf-8",
                errors="replace"
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            logger.error(f"[PLINK -> JUMP] Command timed out after {t}s")
            return -1, "", f"Execution timed out after {t} seconds"
        except Exception as e:
            logger.error(f"[PLINK -> JUMP] Execution exception: {e}")
            return -1, "", str(e)

    def run_on_site(
        self,
        site_ip: str,
        site_port: int,
        site_user: str,
        site_pass: str,
        command: str,
        timeout: Optional[int] = None
    ) -> Tuple[int, str, str]:
        """
        Executes a command on the Site Server via the Jump Server.
        """
        t = timeout or (self.timeout + 10)
        # Base64 encode the inner command to run on Site Server
        b64_inner = base64.b64encode(command.encode("utf-8")).decode("ascii")
        inner_exec = f"echo {b64_inner} | base64 -d | bash"

        # Construct jump server command using sshpass to Site Server
        jump_command = (
            f"sshpass -p '{site_pass}' ssh -o StrictHostKeyChecking=no "
            f"-o ConnectTimeout=12 -p {site_port} {site_user}@{site_ip} '{inner_exec}'"
        )

        return self.run_on_jump(jump_command, timeout=t)

    def run_on_controller(
        self,
        site_ip: str,
        site_port: int,
        site_user: str,
        site_pass: str,
        controller_ip: str,
        controller_pass: str,
        command: str,
        timeout: Optional[int] = None
    ) -> Tuple[int, str, str]:
        """
        Executes a command on the Room Controller via Site Server via Jump Server.
        """
        t = timeout or (self.timeout + 15)
        # Base64 encode the target controller script
        b64_target = base64.b64encode(command.encode("utf-8")).decode("ascii")
        target_exec = f"echo {b64_target} | base64 -d | bash"

        # Construct site server command to target controller
        site_command = (
            f"sshpass -p '{controller_pass}' ssh -o StrictHostKeyChecking=no "
            f"-o ConnectTimeout=12 root@{controller_ip} '{target_exec}'"
        )

        return self.run_on_site(site_ip, site_port, site_user, site_pass, site_command, timeout=t)

    def test_jump_connection(self) -> Tuple[bool, str]:
        """Tests connectivity to the Jump Server."""
        code, out, err = self.run_on_jump("echo JUMP_OK; which sshpass; which ssh", timeout=12)
        if code == 0 and "JUMP_OK" in out:
            return True, f"Jump server connected ({self.jump_host}:{self.jump_port})"
        return False, f"Failed to connect to jump server {self.jump_host}:{self.jump_port}. Error: {err.strip() or out.strip()}"

    def test_site_connection(
        self,
        site_ip: str,
        site_port: int,
        site_user: str,
        site_pass: str
    ) -> Tuple[bool, str]:
        """Tests connectivity from Jump Server to Site Server."""
        code, out, err = self.run_on_site(
            site_ip, site_port, site_user, site_pass,
            "echo SITE_OK; hostname",
            timeout=15
        )
        if code == 0 and "SITE_OK" in out:
            lines = [l.strip() for l in out.splitlines() if l.strip()]
            hostname = lines[-1] if len(lines) > 1 else site_ip
            return True, f"Site server reachable ({site_user}@{site_ip}:{site_port}, host: {hostname})"
        return False, f"Cannot reach site server {site_user}@{site_ip}:{site_port}. Error: {err.strip() or out.strip()}"

    def discover_controller_password(
        self,
        site_ip: str,
        site_port: int,
        site_user: str,
        site_pass: str,
        controller_ip: str,
        candidate_passwords: List[str]
    ) -> Tuple[Optional[str], str]:
        """
        Tests each candidate password against root@controller_ip.
        Returns (working_password, log_message).
        """
        for pwd in candidate_passwords:
            logger.info(f"Testing root password on controller {controller_ip}...")
            code, out, err = self.run_on_controller(
                site_ip, site_port, site_user, site_pass,
                controller_ip, pwd,
                "echo CONTROLLER_AUTH_SUCCESS",
                timeout=15
            )
            if code == 0 and "CONTROLLER_AUTH_SUCCESS" in out:
                logger.info(f"Verified working root password for {controller_ip}")
                return pwd, f"Authenticated successfully with root on {controller_ip}"

        return None, f"Failed to authenticate on root@{controller_ip}. Neither candidate password succeeded."

    def scp_between_controllers_via_site(
        self,
        site_ip: str,
        site_port: int,
        site_user: str,
        site_pass: str,
        source_ip: str,
        source_pass: str,
        target_ip: str,
        target_pass: str,
        source_path: str = "/usr/local/smartler/config",
        target_dest: str = "/usr/local/smartler",
        timeout: int = 60
    ) -> Tuple[bool, str]:
        """
        Fallback staging copy through Site Server when direct SCP on controller is unavailable:
        1. Site Server pulls config from source controller into staging directory /tmp/cfg_stage_<ts>
        2. Site Server pushes staging directory to target controller
        3. Site Server cleans up staging directory
        """
        staging_dir = f"/tmp/staging_config_{os.getpid()}"
        cmd = f"""
        set -e
        echo "Staging config from {source_ip} to Site Server..."
        rm -rf {staging_dir}
        sshpass -p '{source_pass}' scp -r -o StrictHostKeyChecking=no -o ConnectTimeout=15 root@{source_ip}:{source_path} {staging_dir}
        echo "Pushing staged config to target controller {target_ip}..."
        sshpass -p '{target_pass}' scp -r -o StrictHostKeyChecking=no -o ConnectTimeout=15 {staging_dir} root@{target_ip}:{target_dest}/config
        rm -rf {staging_dir}
        echo "STAGED_SCP_COMPLETED"
        """
        code, out, err = self.run_on_site(
            site_ip, site_port, site_user, site_pass,
            cmd,
            timeout=timeout
        )
        if code == 0 and "STAGED_SCP_COMPLETED" in out:
            return True, "Config successfully transferred via site server staging"
        return False, f"Staged SCP transfer failed: {err.strip() or out.strip()}"
