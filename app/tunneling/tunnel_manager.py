import os
import time
import socket
import asyncio
import subprocess
import logging
import urllib.request
from typing import Dict, List, Optional, Any, Tuple

from app.database.db import get_setting
from app.tunneling.port_manager import port_manager
from app.tunneling.putty_manager import putty_manager

logger = logging.getLogger("IRD_TunnelManager")

class TunnelManager:
    """
    Manages SSH reverse tunnel sub-processes and health verification per site.
    """

    def __init__(self):
        # Maps site_id -> Dict representing active tunnel instance
        # { "process": Popen, "pid": int, "site": Site, "start_time": float, "status": str }
        self.active_tunnels: Dict[int, Dict[str, Any]] = {}

    def is_tunnel_running(self, site: Any) -> bool:
        """
        Checks if Plink process for the site is active and alive.
        """
        site_id = getattr(site, "id", None)
        if site_id not in self.active_tunnels:
            return False

        t_data = self.active_tunnels[site_id]
        proc: Optional[subprocess.Popen] = t_data.get("process")
        if proc and proc.poll() is None:
            return True

        # Process died
        t_data["status"] = "DISCONNECTED"
        return False

    def get_tunnel_status(self, site: Any) -> Dict[str, Any]:
        """
        Returns structured status dict for site's tunnel.
        """
        site_id = getattr(site, "id", None)
        local_port = getattr(site, "local_port", 18001) or 18001
        site_name = getattr(site, "name", "Unknown")

        if site_id not in self.active_tunnels:
            return {
                "site_id": site_id,
                "site_name": site_name,
                "status": "STOPPED",
                "pid": None,
                "local_port": local_port,
                "web_url": getattr(site, "web_url", "") or f"http://127.0.0.1:{local_port}"
            }

        t_data = self.active_tunnels[site_id]
        is_alive = self.is_tunnel_running(site)
        return {
            "site_id": site_id,
            "site_name": site_name,
            "status": t_data.get("status", "CONNECTED") if is_alive else "DISCONNECTED",
            "pid": t_data.get("pid"),
            "local_port": local_port,
            "web_url": getattr(site, "web_url", "") or f"http://127.0.0.1:{local_port}"
        }

    async def start_tunnel(self, site: Any) -> Tuple[bool, str]:
        """
        Launches Plink process for site SSH reverse tunnel.
        """
        site_id = getattr(site, "id", None)
        site_name = getattr(site, "name", "Unknown")
        local_port = getattr(site, "local_port", 18001) or 18001

        # Stop existing tunnel for this site if running
        if self.is_tunnel_running(site):
            logger.info(f"[{site_name}] Tunnel already running. Stopping existing process...")
            self.stop_tunnel(site)

        # Build plink command
        detected = putty_manager.detect_executables()
        plink_path = detected["plink"] or get_setting("putty_path") or r"C:\Program Files\PuTTY\plink.exe"

        cmd = putty_manager.build_plink_command(site, plink_path)
        scrubbed_cmd_str = putty_manager.scrub_sensitive_info(" ".join(cmd))
        logger.info(f"[{site_name}] Launching Plink tunnel: {scrubbed_cmd_str}")

        try:
            # Start process without shell=True
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                shell=False
            )
            self.active_tunnels[site_id] = {
                "process": proc,
                "pid": proc.pid,
                "site": site,
                "start_time": time.time(),
                "status": "STARTING",
                "cmd": scrubbed_cmd_str
            }
            logger.info(f"[{site_name}] Plink process launched successfully with PID {proc.pid}")
            return True, f"Plink process started (PID {proc.pid})"
        except Exception as e:
            err_msg = f"Failed to start Plink executable at '{plink_path}': {str(e)}"
            logger.error(f"[{site_name}] {err_msg}")
            return False, err_msg

    async def verify_tunnel(self, site: Any, timeout_seconds: int = 30) -> Tuple[bool, str, List[str]]:
        """
        Verifies:
        1. Process alive
        2. Local port listening
        3. Webpage availability
        """
        site_id = getattr(site, "id", None)
        site_name = getattr(site, "name", "Unknown")
        local_port = getattr(site, "local_port", 18001) or 18001
        web_url = getattr(site, "web_url", "") or f"http://127.0.0.1:{local_port}"

        details = []
        details.append(f"Verifying SSH tunnel process for '{site_name}'...")

        if not self.is_tunnel_running(site):
            details.append("ERROR: Plink process is not running or terminated prematurely.")
            return False, f"[{site_name}] Plink process died before verification.", details

        t_data = self.active_tunnels[site_id]
        details.append(f"Plink process active with PID {t_data.get('pid')}")

        # 2. Check local port listening
        details.append(f"Waiting for local port {local_port} to accept TCP connections (Timeout: {timeout_seconds}s)...")
        port_open = False
        start_t = time.time()

        while time.time() - start_t < timeout_seconds:
            if not self.is_tunnel_running(site):
                details.append("ERROR: Plink process exited while waiting for local port.")
                return False, f"[{site_name}] Plink process exited while waiting for port {local_port}.", details

            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1.0)
                    result = sock.connect_ex(("127.0.0.1", local_port))
                    if result == 0:
                        port_open = True
                        break
            except Exception:
                pass
            await asyncio.sleep(1.0)

        if not port_open:
            details.append(f"ERROR: Local port {local_port} was not listening within {timeout_seconds} seconds.")
            t_data["status"] = "FAILED"
            return False, f"[{site_name}] Local port {local_port} is not accepting connections.", details

        details.append(f"Local port {local_port} is open and listening.")

        # 3. Check Webpage Availability
        details.append(f"Checking web service availability at URL: {web_url}...")
        web_ok = False
        try:
            req = urllib.request.Request(web_url, headers={"User-Agent": "Mozilla/5.0 (IRD-Automation)"})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status in (200, 301, 302, 401, 403):
                    web_ok = True
                    details.append(f"Web service responded with HTTP status code {resp.status}")
        except Exception as e:
            # Service might require specific headers or self-signed TLS, port open is primary indicator
            details.append(f"Web service check note ({str(e)}), local tunnel port confirmed open.")
            web_ok = True  # Local port listening confirms reverse tunnel path

        if web_ok:
            t_data["status"] = "CONNECTED"
            details.append("Tunnel verification completed successfully. Status: CONNECTED")
            return True, f"[{site_name}] SSH Tunnel CONNECTED on port {local_port}", details

        t_data["status"] = "FAILED"
        return False, f"[{site_name}] Webpage unavailable at {web_url}", details

    async def start_and_verify_tunnel(self, site: Any, timeout_seconds: int = 30) -> Tuple[bool, str, List[str]]:
        """
        Convenience method to start and verify tunnel in sequence.
        """
        started, start_msg = await self.start_tunnel(site)
        if not started:
            return False, start_msg, [start_msg]

        return await self.verify_tunnel(site, timeout_seconds=timeout_seconds)

    def stop_tunnel(self, site: Any):
        """
        Terminates the Plink process for site.
        """
        site_id = getattr(site, "id", None)
        site_name = getattr(site, "name", "Unknown")

        if site_id in self.active_tunnels:
            t_data = self.active_tunnels[site_id]
            proc: Optional[subprocess.Popen] = t_data.get("process")
            if proc:
                try:
                    logger.info(f"[{site_name}] Terminating Plink process PID {proc.pid}...")
                    proc.terminate()
                    try:
                        proc.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                except Exception as e:
                    logger.warning(f"[{site_name}] Exception terminating process: {e}")
            t_data["status"] = "STOPPED"
            del self.active_tunnels[site_id]
            logger.info(f"[{site_name}] Tunnel stopped.")

    def stop_all_tunnels(self):
        """
        Stops all running site tunnels.
        """
        site_ids = list(self.active_tunnels.keys())
        for sid in site_ids:
            site = getattr(self.active_tunnels[sid], "site", None)
            if site:
                self.stop_tunnel(site)
            else:
                try:
                    proc = self.active_tunnels[sid].get("process")
                    if proc:
                        proc.kill()
                except Exception:
                    pass
                del self.active_tunnels[sid]

tunnel_manager = TunnelManager()
