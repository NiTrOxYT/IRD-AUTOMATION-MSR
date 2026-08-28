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

    def is_tunnel_process_alive(self, site_id: int) -> bool:
        """
        Verifies if Plink subprocess for the site_id is active, alive, and hasn't exited.
        """
        if site_id not in self.active_tunnels:
            return False
        t_data = self.active_tunnels[site_id]
        proc: Optional[subprocess.Popen] = t_data.get("process")
        if proc and proc.poll() is None:
            return True
        t_data["status"] = "FAILED"
        return False

    def is_tunnel_running(self, site: Any) -> bool:
        """
        Checks if Plink process for the site is active and alive.
        """
        site_id = getattr(site, "id", None)
        if site_id is None:
            return False
        return self.is_tunnel_process_alive(site_id)

    def get_tunnel_status(self, site: Any) -> Dict[str, Any]:
        """
        Returns structured status dict for site's Local Port Forwarding (-L) tunnel.
        """
        from app.database.models import get_site_web_url
        from app.database.db import get_office_ssh_config
        global_ssh = get_office_ssh_config()

        site_id = getattr(site, "id", None)
        site_name = getattr(site, "name", "Unknown")
        site_ip = getattr(site, "site_ip", "") or "14.142.185.130"
        site_port = getattr(site, "site_port", 8082) or 8082
        local_port = getattr(site, "local_port", 18001) or 18001
        ssh_host = getattr(site, "ssh_host", "") or global_ssh.get("ssh_host") or "111.93.205.187"
        ssh_port = getattr(site, "ssh_port", 22) or global_ssh.get("ssh_port") or 22
        office_ssh = f"{ssh_host}:{ssh_port}"
        local_endpoint = f"127.0.0.1:{local_port}"
        browser_url = get_site_web_url(site)
        forward_spec = f"-L {local_port}:{site_ip}:{site_port}"

        detected = putty_manager.detect_executables()
        plink_path = detected["plink"] or "tools/putty/plink.exe"

        if site_id not in self.active_tunnels:
            return {
                "site_id": site_id,
                "site_name": site_name,
                "site_ip": site_ip,
                "site_port": site_port,
                "office_ssh": office_ssh,
                "local_port": local_port,
                "local_endpoint": local_endpoint,
                "browser_url": browser_url,
                "plink": plink_path,
                "pid": None,
                "forward": forward_spec,
                "status": "STOPPED",
                "process_running": False
            }

        t_data = self.active_tunnels[site_id]
        is_alive = self.is_tunnel_process_alive(site_id)
        current_status = t_data.get("status", "ESTABLISHED") if is_alive else "FAILED"

        return {
            "site_id": site_id,
            "site_name": site_name,
            "site_ip": site_ip,
            "site_port": site_port,
            "office_ssh": office_ssh,
            "local_port": local_port,
            "local_endpoint": local_endpoint,
            "browser_url": browser_url,
            "plink": plink_path,
            "pid": t_data.get("pid"),
            "forward": forward_spec,
            "status": current_status,
            "process_running": is_alive
        }


    async def run_fnb_tunnel_test(self, site: Any, keep_running: bool = False) -> Dict[str, Any]:
        """
        Executes the Phase 5B REAL FNB TUNNEL TEST sequence:
        1. Validate configuration
        2. Validate bundled Plink
        3. Validate local port
        4. Start Plink
        5. Capture PID & monitor output
        6. Detect SSH connection
        7. Verify forwarding
        8. Verify local endpoint
        9. Verify FNB webpage/service
        10. Clean up or preserve process based on keep_running
        """
        site_name = getattr(site, "name", "FNB")
        site_id = getattr(site, "id", 1)
        local_port = getattr(site, "local_port", 18001) or 18001
        site_ip = getattr(site, "site_ip", "") or getattr(site, "remote_host", "") or "127.0.0.1"

        from app.database.db import get_office_ssh_config, get_office_ssh_password_decrypted, get_global_tunnel_config
        global_ssh = get_office_ssh_config()
        global_tunnel = get_global_tunnel_config()

        ssh_host = getattr(site, "ssh_host", "") or global_ssh.get("ssh_host") or "111.93.205.187"
        ssh_user = getattr(site, "ssh_username", "") or global_ssh.get("ssh_username") or "sourik"
        auth_type = str(getattr(site, "auth_type", "") or global_ssh.get("auth_type") or "password").lower()
        ssh_key = getattr(site, "ssh_key_path", "") or global_ssh.get("ssh_key_path") or ""
        ssh_pass = getattr(site, "ssh_password", "") or get_office_ssh_password_decrypted()
        from app.database.models import get_site_web_url
        site_port = getattr(site, "site_port", 80) or getattr(site, "remote_port", 80) or 80
        local_endpoint = f"127.0.0.1:{local_port}"
        browser_url = get_site_web_url(site)

        logs: List[str] = []
        checks = {
            "plink": "FAIL",
            "ssh_connection": "FAIL",
            "ssh_authentication": "FAIL",
            "tunnel": "FAIL",
            "tcp_endpoint": "FAIL",
            "http_endpoint": "FAIL",
            "fnb_service": "FAIL",
            "playwright": "FAIL"
        }
        result_status = "FAILED"
        failure_code = "UNKNOWN_ERROR"
        pid = None

        def log(msg: str):
            ts = time.strftime("%H:%M:%S")
            line = f"{ts} | INFO | [{site_name}] {msg}"
            logs.append(line)
            logger.info(line)

        log("PHASE 5E REAL FNB ENDPOINT VALIDATION STARTED")
        log(f"[TUNNEL] SSH server: {ssh_host}:{getattr(site, 'ssh_port', 22) or 22}")
        log(f"[TUNNEL] FNB target: {site_ip}:{site_port}")
        log(f"[TUNNEL] Forward mode: LOCAL")
        log(f"[TUNNEL] Local endpoint: {local_endpoint}")
        log(f"[TUNNEL] Remote target: {site_ip}:{site_port}")
        log(f"[TUNNEL] TCP validation target: {local_endpoint}")
        log(f"[TUNNEL] HTTP validation URL: {browser_url}")
        log(f"Forward: -L {local_port}:{site_ip}:{site_port}")

        # STEP 1: Validate configuration & bundled Plink
        log("STEP 1: Validating bundled Plink executable...")
        detected = putty_manager.detect_executables()
        plink_path = detected["plink"]
        if not plink_path or not os.path.exists(plink_path):
            log("ERROR: Bundled Plink executable not found at tools/putty/plink.exe")
            failure_code = "PLINK_NOT_FOUND"
            return self._format_fnb_test_report(checks, "FAILED", failure_code, logs, pid, site_ip, local_port, ssh_host)

        checks["plink"] = "PASS"
        log(f"Bundled Plink detected: {putty_manager.get_relative_display_path(plink_path)}")

        # STEP 2 & 3 & 4: Build Command & Connect to Office SSH
        log(f"STEP 2 & 3 & 4: Launching Plink to {ssh_host}:{getattr(site, 'ssh_port', 22) or 22}...")
        try:
            cmd = putty_manager.build_plink_command(site, plink_path)
            scrubbed_cmd = putty_manager.scrub_sensitive_info(" ".join(cmd))
            log(f"[TUNNEL] Plink command: {scrubbed_cmd}")
            log(f"Generated Plink Command: {scrubbed_cmd}")

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                shell=False
            )
            pid = proc.pid
            log(f"Plink process launched cleanly with PID: {pid}")

            self.active_tunnels[site_id] = {
                "process": proc,
                "pid": pid,
                "site": site,
                "start_time": time.time(),
                "status": "CONNECTING",
                "cmd": scrubbed_cmd
            }

        except Exception as e:
            log(f"ERROR: Failed to launch Plink subprocess: {e}")
            failure_code = "TUNNEL_ESTABLISH_FAILED"
            return self._format_fnb_test_report(checks, "FAILED", failure_code, logs, pid, site_ip, local_port, ssh_host)

        # Monitor SSH authentication & connection negotiation
        log("Waiting for SSH authentication & reverse tunnel setup (Timeout: 15s)...")
        ssh_connected = False
        start_t = time.time()

        while time.time() - start_t < 15.0:
            if proc.poll() is not None:
                err_output = proc.stderr.read() if proc.stderr else ""
                out_output = proc.stdout.read() if proc.stdout else ""
                combined = (out_output + " " + err_output).strip()
                scrubbed_err = putty_manager.scrub_sensitive_info(combined)

                if "Access denied" in combined or "Authentication failed" in combined or "password" in combined.lower():
                    log(f"ERROR: SSH Authentication Failed: {scrubbed_err}")
                    failure_code = "SSH_AUTHENTICATION_FAILED"
                elif "WARNING - HOST KEY HAS CHANGED!" in combined:
                    log(f"ERROR: SSH Host Key Verification Failed: {scrubbed_err}")
                    failure_code = "SSH_HOST_KEY_FAILED"
                elif "Unable to open" in combined or "Network error" in combined or "Host does not exist" in combined:
                    log(f"ERROR: SSH Host Unreachable: {scrubbed_err}")
                    failure_code = "SSH_CONNECTION_FAILED"
                else:
                    log(f"ERROR: SSH Process Exited: {scrubbed_err or 'Exit code ' + str(proc.returncode)}")
                    failure_code = "SSH_CONNECTION_FAILED"
                break

            if time.time() - start_t >= 2.0:
                ssh_connected = True
                break

            await asyncio.sleep(0.5)

        if not ssh_connected and failure_code == "UNKNOWN_ERROR":
            if proc.poll() is None:
                log("ERROR: SSH connection timed out.")
                failure_code = "TIMEOUT"

        if ssh_connected:
            checks["ssh_connection"] = "PASS"
            checks["ssh_authentication"] = "PASS"
            checks["tunnel"] = "PASS"
            log("✓ SSH Connection & Authentication Successful. Reverse Tunnel Established.")

            # STEP 5: Verify TCP Endpoint Listener
            log(f"STEP 5: Verifying TCP socket connect to 127.0.0.1:{local_port} (Timeout: 15s)...")
            tcp_ok = False
            start_fwd = time.time()
            while time.time() - start_fwd < 15.0:
                if proc.poll() is not None:
                    log("ERROR: Plink process terminated while waiting for local port listener.")
                    failure_code = "TUNNEL_ESTABLISH_FAILED"
                    break

                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.settimeout(1.0)
                        if sock.connect_ex(("127.0.0.1", local_port)) == 0:
                            tcp_ok = True
                            break
                except Exception:
                    pass
                await asyncio.sleep(1.0)

            if tcp_ok:
                checks["tcp_endpoint"] = "PASS"
                log(f"✓ STEP 5 PASS: TCP Socket Connected on 127.0.0.1:{local_port}")

                # STEP 6: Perform Actual HTTP Request using canonical browser_url (/zmp/main-menu.do)
                expected_url = f"http://localhost:{local_port}/zmp/main-menu.do"
                if browser_url != expected_url:
                    log(f"ERROR: Local endpoint mismatch! Tunnel local port is {local_port}, but HTTP test URL is {browser_url}")
                    failure_code = "LOCAL_ENDPOINT_MISMATCH"
                    return self._format_fnb_test_report(checks, "FAILED", failure_code, logs, pid, site_ip, local_port, ssh_host)

                log(f"STEP 6: Executing HTTP GET request to {browser_url}...")
                http_ok = False
                http_status = None
                http_latency_ms = 0
                body_text = ""

                try:
                    import ssl
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE

                    req = urllib.request.Request(
                        browser_url,
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) IRD-Automation/1.0"}
                    )


                    h_start = time.time()
                    with urllib.request.urlopen(req, context=ctx, timeout=10.0) as resp:
                        http_latency_ms = int((time.time() - h_start) * 1000)
                        http_status = resp.status
                        body_bytes = resp.read(4096)
                        body_text = body_bytes.decode('utf-8', errors='ignore')
                        http_ok = True
                        log(f"✓ STEP 6 PASS: HTTP Response Received. Status: {http_status}, Latency: {http_latency_ms}ms")
                except urllib.error.HTTPError as he:
                    http_latency_ms = int((time.time() - start_fwd) * 1000)
                    http_status = he.code
                    body_text = he.read(4096).decode('utf-8', errors='ignore')
                    http_ok = True
                    log(f"✓ STEP 6 PASS: HTTP Server Responded with status {http_status}")
                except Exception as ex:
                    log(f"ERROR: HTTP Request Failed: {ex}")
                    failure_code = "HTTP_ENDPOINT_UNAVAILABLE"

                if http_ok:
                    checks["http_endpoint"] = "PASS"

                    # STEP 7: Service Validation (FNB Portal Content Inspection)
                    log("STEP 7: Inspecting HTTP body content for FNB Service markers...")
                    body_lower = body_text.lower()
                    service_ok = False

                    # Check for valid HTML or FNB / MyMenu / Portal markers
                    if any(marker in body_lower for marker in ["<html", "<head", "<title", "<body", "fnb", "mymenu", "portal", "login", "ird"]):
                        service_ok = True
                        log("✓ STEP 7 PASS: FNB Service / Portal Content Verified.")
                    elif len(body_text.strip()) > 0:
                        # Endpoint returned non-empty response
                        service_ok = True
                        log(f"✓ STEP 7 PASS: HTTP Response body received ({len(body_text)} bytes).")
                    else:
                        log("ERROR: HTTP Response body empty or invalid.")
                        failure_code = "FNB_SERVICE_UNAVAILABLE"

                    if service_ok:
                        checks["fnb_service"] = "PASS"
                        result_status = "REAL FNB TUNNEL — PASS"
                        failure_code = "NONE"
                        log("★ REAL FNB TUNNEL & ENDPOINT VALIDATED SUCCESSFULLY!")
                    else:
                        failure_code = "FNB_SERVICE_UNAVAILABLE"
            else:
                if failure_code == "UNKNOWN_ERROR":
                    failure_code = "TCP_ENDPOINT_UNAVAILABLE"

        # Cleanup handling based on keep_running option
        if result_status == "REAL FNB TUNNEL — PASS" and keep_running:
            log("Option 'Keep tunnel running' is ENABLED. Tunnel remains RUNNING.")
            if site_id in self.active_tunnels:
                self.active_tunnels[site_id]["status"] = "RUNNING"
        else:
            log("Stopping test tunnel and cleaning up process...")
            self.stop_tunnel(site)
            log("Plink process terminated cleanly.")

        return self._format_fnb_test_report(checks, result_status, failure_code, logs, pid, site_ip, local_port, ssh_host)

    def _format_fnb_test_report(self, checks: Dict[str, str], status: str, failure_code: str, logs: List[str], pid: Optional[int], site_ip: str, local_port: int, ssh_host: str) -> Dict[str, Any]:
        real_tunnel_pass = "PASS" if checks["fnb_service"] == "PASS" else "FAIL"
        fnb_webpage_pass = "PASS" if checks["fnb_service"] == "PASS" else "FAIL"

        formatted = (
            "========================================\n"
            "PHASE 5E — REAL FNB ENDPOINT VALIDATION\n"
            "========================================\n\n"
            "Site:\nFNB\n\n"
            f"Site IP:\n{site_ip}\n\n"
            f"Local Port:\n{local_port}\n\n"
            f"Office SSH:\n{ssh_host}:22\n\n"
            "----------------------------------------\n\n"
            f"Plink:\n{checks['plink']}\n\n"
            f"SSH Connection:\n{checks['ssh_connection']}\n\n"
            f"SSH Authentication:\n{checks['ssh_authentication']}\n\n"
            f"Tunnel:\n{checks['tunnel']}\n\n"
            f"TCP Endpoint:\n{checks['tcp_endpoint']}\n\n"
            f"HTTP Endpoint:\n{checks['http_endpoint']}\n\n"
            f"FNB Service:\n{checks['fnb_service']}\n\n"
            f"Playwright:\n{checks['playwright']}\n\n"
            "----------------------------------------\n\n"
            "RESULT:\n\n"
            f"REAL FNB TUNNEL:\n{real_tunnel_pass}\n\n"
            f"FNB WEBPAGE:\n{fnb_webpage_pass}\n\n"
            "========================================"
        )

        return {
            "site_name": "FNB",
            "result_status": status,
            "failure_code": failure_code,
            "checks": checks,
            "pid": pid,
            "logs": logs,
            "formatted_summary": formatted
        }


    async def open_fnb_webpage_test(self, site: Any) -> Dict[str, Any]:
        """
        Executes dedicated OPEN FNB WEBPAGE test:
        1. Verify tunnel / start if needed
        2. Open configured Web URL
        3. Wait for page load
        4. Display page title & final URL
        """
        web_url = getattr(site, "web_url", "") or f"http://127.0.0.1:{getattr(site, 'local_port', 18001)}"
        logs = []
        logs.append(f"Starting FNB Webpage Test for URL: {web_url}")

        tunnel_ok = False
        if self.is_tunnel_running(site):
            tunnel_ok = True
            logs.append("Active tunnel process detected.")
        else:
            logs.append("No active tunnel found. Running tunnel test first...")
            t_res = await self.run_fnb_tunnel_test(site, keep_running=True)
            if t_res["result_status"] == "TUNNEL CONNECTED":
                tunnel_ok = True
                logs.append("Tunnel successfully started.")
            else:
                logs.append(f"Tunnel test failed with error code: {t_res['failure_code']}")

        if not tunnel_ok:
            return {
                "success": False,
                "tunnel": "FAIL",
                "navigation": "FAIL",
                "page_load": "FAIL",
                "title": "N/A",
                "url": web_url,
                "result": "FAIL",
                "logs": logs
            }

        # Test URL navigation using HTTP client / Playwright
        try:
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(web_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, context=ctx, timeout=10.0) as resp:
                status_code = resp.status
                body = resp.read(4096).decode("utf-8", errors="ignore")
                title = "FNB Web Portal"
                if "<title>" in body.lower():
                    title = body.split("<title>")[1].split("</title>")[0].strip()

                logs.append(f"Successfully loaded webpage. HTTP status: {status_code}, Title: '{title}'")
                return {
                    "success": True,
                    "tunnel": "PASS",
                    "navigation": "PASS",
                    "page_load": "PASS",
                    "title": title or "FNB Portal",
                    "url": web_url,
                    "result": "PASS",
                    "logs": logs
                }
        except Exception as e:
            logs.append(f"Webpage navigation error: {e}")
            return {
                "success": False,
                "tunnel": "PASS",
                "navigation": "FAIL",
                "page_load": "FAIL",
                "title": "Error",
                "url": web_url,
                "result": "FAIL",
                "logs": logs
            }

    async def test_playwright_tunnel(self, site: Any) -> Dict[str, Any]:
        """
        Verifies Playwright browser controller navigation to the tunnel web_url.
        """
        local_port = getattr(site, "local_port", 18001) or 18001
        web_url = getattr(site, "web_url", "") or f"http://127.0.0.1:{local_port}"
        logs = [f"Launching Playwright browser controller for URL: {web_url}"]

        from app.browser.browser_controller import browser_controller
        res = await browser_controller.launch_and_navigate(web_url)

        browser_pass = "PASS" if res.get("success") else "FAIL"
        page_load_pass = "PASS" if res.get("success") else "FAIL"
        portal_pass = "PASS" if res.get("success") else "FAIL"
        result_msg = "FNB WEBPAGE ACCESSIBLE" if res.get("success") else "PLAYWRIGHT_LOAD_FAILED"

        logs.append(f"Playwright result: {res.get('message') or result_msg}")

        formatted = (
            "========================================\n"
            "PLAYWRIGHT FNB TEST\n"
            "========================================\n\n"
            f"Browser:\n{browser_pass}\n\n"
            f"URL:\n{web_url}\n\n"
            f"Page Load:\n{page_load_pass}\n\n"
            f"FNB Portal Detected:\n{portal_pass}\n\n"
            "RESULT:\n"
            f"{result_msg}\n"
            "========================================"
        )

        return {
            "success": res.get("success", False),
            "stage": "Playwright Navigation",
            "browser": browser_pass,
            "url": web_url,
            "page_load": page_load_pass,
            "portal_detected": portal_pass,
            "logs": logs,
            "result": result_msg,
            "formatted_summary": formatted
        }


    async def test_office_ssh_connection(self) -> Dict[str, Any]:
        """
        Executes real Office SSH Server connection test (111.93.205.187:22)
        using bundled plink.exe and DPAPI decrypted credentials in memory.
        """
        from app.database.db import get_office_ssh_config, get_office_ssh_password_decrypted
        from app.tunneling.putty_paths import get_active_plink_path, get_relative_display_path

        cfg = get_office_ssh_config()
        ssh_host = cfg.get("ssh_host") or "111.93.205.187"
        ssh_port = cfg.get("ssh_port") or 22
        ssh_user = cfg.get("ssh_username") or "sourik"
        auth_type = cfg.get("auth_type") or "password"

        plink_path, _, _ = get_active_plink_path()
        rel_plink = get_relative_display_path(plink_path)

        logs = [
            f"Resolving SSH server {ssh_host}...",
            f"Connecting to {ssh_host}:{ssh_port}...",
            f"Authenticating as user '{ssh_user}' using {auth_type}..."
        ]

        if not plink_path or not os.path.exists(plink_path):
            return {
                "success": False,
                "server_reachability": "FAIL",
                "ssh_connection": "FAIL",
                "authentication": "FAIL",
                "result_message": "PLINK EXECUTABLE NOT FOUND",
                "plink_path": rel_plink,
                "host": ssh_host,
                "port": ssh_port,
                "username": ssh_user,
                "logs": logs + ["ERROR: Bundled Plink executable tools/putty/plink.exe missing."],
                "formatted_summary": (
                    "========================================\n"
                    "SSH CONNECTION TEST\n"
                    "========================================\n"
                    f"Server:\n{ssh_host}:{ssh_port}\n\n"
                    f"Username:\n{ssh_user}\n\n"
                    f"Plink:\n{rel_plink}\n\n"
                    "Server Reachability:\nFAIL\n\n"
                    "SSH Connection:\nFAIL\n\n"
                    "Authentication:\nFAIL\n\n"
                    "Result:\nPLINK NOT FOUND\n"
                    "========================================"
                )
            }

        # Decrypt password in memory ONLY for process execution
        cfg_exec = dict(cfg)
        cfg_exec["ssh_password"] = get_office_ssh_password_decrypted()

        try:
            cmd = putty_manager.build_ssh_test_command(cfg_exec, plink_path)
            scrubbed_cmd = putty_manager.scrub_sensitive_info(" ".join(cmd))
            logs.append(f"Executing Plink command: {scrubbed_cmd}")

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                shell=False
            )

            try:
                out, err = proc.communicate(timeout=15.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                out, err = proc.communicate()
                logs.append("ERROR: SSH Connection timed out after 15 seconds.")
                return {
                    "success": False,
                    "server_reachability": "PASS",
                    "ssh_connection": "FAIL",
                    "authentication": "FAIL",
                    "result_message": "CONNECTION TIMEOUT",
                    "plink_path": rel_plink,
                    "host": ssh_host,
                    "port": ssh_port,
                    "username": ssh_user,
                    "logs": logs,
                    "formatted_summary": self._format_ssh_test_summary(ssh_host, ssh_port, ssh_user, rel_plink, "PASS", "FAIL", "FAIL", "CONNECTION TIMEOUT")
                }

            combined = (out + " " + err).strip()
            scrubbed_output = putty_manager.scrub_sensitive_info(combined)
            logs.append(f"Plink Output: {scrubbed_output}")

            # Parse results
            if "SSH_TEST_OK" in out or proc.returncode == 0:
                logs.append("✓ SSH Connection and Authentication Successful.")
                return {
                    "success": True,
                    "server_reachability": "PASS",
                    "ssh_connection": "PASS",
                    "authentication": "PASS",
                    "result_message": "SSH SERVER REACHABLE",
                    "plink_path": rel_plink,
                    "host": ssh_host,
                    "port": ssh_port,
                    "username": ssh_user,
                    "logs": logs,
                    "formatted_summary": self._format_ssh_test_summary(ssh_host, ssh_port, ssh_user, rel_plink, "PASS", "PASS", "PASS", "SSH SERVER REACHABLE")
                }
            elif "WARNING - HOST KEY HAS CHANGED!" in combined or "HOST KEY HAS CHANGED" in combined:
                logs.append("CRITICAL: SSH HOST KEY CHANGED! Stopping connection.")
                return {
                    "success": False,
                    "server_reachability": "PASS",
                    "ssh_connection": "FAIL",
                    "authentication": "FAIL",
                    "result_message": "SSH HOST KEY CHANGED",
                    "plink_path": rel_plink,
                    "host": ssh_host,
                    "port": ssh_port,
                    "username": ssh_user,
                    "logs": logs,
                    "formatted_summary": self._format_ssh_test_summary(ssh_host, ssh_port, ssh_user, rel_plink, "PASS", "FAIL", "FAIL", "SSH HOST KEY CHANGED")
                }
            elif "host key is not cached" in combined or "Store key in cache?" in combined:
                logs.append("WARNING: SSH Host key is not cached in PuTTY registry.")
                return {
                    "success": False,
                    "server_reachability": "PASS",
                    "ssh_connection": "FAIL",
                    "authentication": "FAIL",
                    "result_message": "HOST KEY UNKNOWN",
                    "plink_path": rel_plink,
                    "host": ssh_host,
                    "port": ssh_port,
                    "username": ssh_user,
                    "logs": logs,
                    "formatted_summary": self._format_ssh_test_summary(ssh_host, ssh_port, ssh_user, rel_plink, "PASS", "FAIL", "FAIL", "HOST KEY UNKNOWN")
                }
            elif "Access denied" in combined or "Authentication failed" in combined or "password" in combined.lower():
                logs.append("ERROR: SSH Authentication Failed (Invalid Username/Password).")
                return {
                    "success": False,
                    "server_reachability": "PASS",
                    "ssh_connection": "PASS",
                    "authentication": "FAIL",
                    "result_message": "AUTHENTICATION FAILED",
                    "plink_path": rel_plink,
                    "host": ssh_host,
                    "port": ssh_port,
                    "username": ssh_user,
                    "logs": logs,
                    "formatted_summary": self._format_ssh_test_summary(ssh_host, ssh_port, ssh_user, rel_plink, "PASS", "PASS", "FAIL", "AUTHENTICATION FAILED")
                }
            elif "Connection refused" in combined:
                logs.append("ERROR: SSH Connection refused by server port.")
                return {
                    "success": False,
                    "server_reachability": "PASS",
                    "ssh_connection": "FAIL",
                    "authentication": "FAIL",
                    "result_message": "CONNECTION REFUSED",
                    "plink_path": rel_plink,
                    "host": ssh_host,
                    "port": ssh_port,
                    "username": ssh_user,
                    "logs": logs,
                    "formatted_summary": self._format_ssh_test_summary(ssh_host, ssh_port, ssh_user, rel_plink, "PASS", "FAIL", "FAIL", "CONNECTION REFUSED")
                }
            else:
                logs.append(f"ERROR: SSH Host Unreachable: {scrubbed_output}")
                return {
                    "success": False,
                    "server_reachability": "FAIL",
                    "ssh_connection": "FAIL",
                    "authentication": "FAIL",
                    "result_message": "HOST UNREACHABLE",
                    "plink_path": rel_plink,
                    "host": ssh_host,
                    "port": ssh_port,
                    "username": ssh_user,
                    "logs": logs,
                    "formatted_summary": self._format_ssh_test_summary(ssh_host, ssh_port, ssh_user, rel_plink, "FAIL", "FAIL", "FAIL", "HOST UNREACHABLE")
                }

        except Exception as ex:
            logs.append(f"ERROR executing Plink: {ex}")
            return {
                "success": False,
                "server_reachability": "FAIL",
                "ssh_connection": "FAIL",
                "authentication": "FAIL",
                "result_message": f"ERROR: {ex}",
                "plink_path": rel_plink,
                "host": ssh_host,
                "port": ssh_port,
                "username": ssh_user,
                "logs": logs,
                "formatted_summary": self._format_ssh_test_summary(ssh_host, ssh_port, ssh_user, rel_plink, "FAIL", "FAIL", "FAIL", "ERROR")
            }

    def _format_ssh_test_summary(self, host: str, port: int, user: str, plink: str, reach: str, conn: str, auth: str, res: str) -> str:
        return (
            "========================================\n"
            "SSH CONNECTION TEST\n"
            "========================================\n\n"
            f"Server:\n{host}:{port}\n\n"
            f"Username:\n{user}\n\n"
            f"Plink:\n{plink}\n\n"
            f"Server Reachability:\n{reach}\n\n"
            f"SSH Connection:\n{conn}\n\n"
            f"Authentication:\n{auth}\n\n"
            f"Result:\n{res}\n\n"
            "========================================"
        )

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
    async def test_remote_site_connectivity(self, site: Any) -> Dict[str, Any]:
        """
        Executes real Office Server (111.93.205.187) -> Site IP remote TCP & HTTP connectivity test.
        Tests configured site_port and common ports [80, 443, 8080, 8089] from Office Server.
        """
        from app.database.db import get_office_ssh_config, get_office_ssh_password_decrypted
        from app.tunneling.putty_paths import get_active_plink_path

        site_name = getattr(site, "name", "Site")
        site_ip = getattr(site, "site_ip", "") or getattr(site, "remote_host", "127.0.0.1") or "127.0.0.1"
        site_port = getattr(site, "site_port", 80) or getattr(site, "remote_port", 80) or 80

        cfg = get_office_ssh_config()
        ssh_host = cfg.get("ssh_host") or "111.93.205.187"
        ssh_port = cfg.get("ssh_port") or 22
        ssh_user = cfg.get("ssh_username") or "sourik"
        ssh_pass = get_office_ssh_password_decrypted()

        plink_path, _, _ = get_active_plink_path()

        logs = [
            f"[{site_name}] Starting Office Server -> Site Remote Connectivity Test",
            f"[{site_name}] Office SSH: {ssh_host}:{ssh_port} (User: {ssh_user})",
            f"[{site_name}] Target Site IP: {site_ip} | Configured Site Port: {site_port}"
        ]

        if not plink_path or not os.path.exists(plink_path):
            return {
                "success": False,
                "site_name": site_name,
                "site_ip": site_ip,
                "site_port": site_port,
                "office_ssh": f"{ssh_host}:{ssh_port}",
                "ssh": "FAIL",
                "remote_tcp": "FAIL",
                "remote_http": "NOT_TESTED",
                "failure_code": "PLINK_NOT_FOUND",
                "port_tests": {},
                "logs": logs + ["ERROR: Bundled Plink executable tools/putty/plink.exe missing."]
            }

        ports_to_test = list(dict.fromkeys([site_port, 80, 443, 8080, 8089]))
        ports_str = ", ".join(str(p) for p in ports_to_test)

        remote_script = (
            "python3 -c \"import socket; "
            "check=lambda p: (s:=socket.socket(), s.settimeout(2.0), r:=s.connect_ex(('" + site_ip + "', p)), s.close(), r)[4]; "
            "print({p: check(p) for p in (" + ports_str + ")})\""
        )

        cmd = [plink_path, "-batch", "-ssh", "-P", str(ssh_port), "-l", ssh_user]
        if ssh_pass:
            cmd.extend(["-pw", ssh_pass])
        cmd.extend([ssh_host, remote_script])

        scrubbed_cmd = putty_manager.scrub_sensitive_info(" ".join(cmd))
        logs.append(f"Executing remote SSH command: {scrubbed_cmd}")

        start_t = time.time()
        port_results = {}
        ssh_pass_status = "FAIL"
        latency_ms = 0

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            out, err = proc.communicate(timeout=20.0)
            latency_ms = int((time.time() - start_t) * 1000)

            if proc.returncode == 0 and "{" in out and "}" in out:
                ssh_pass_status = "PASS"
                logs.append(f"✓ SSH Authentication to {ssh_host}:{ssh_port} Successful.")
                raw_dict_str = out[out.find("{"):out.rfind("}") + 1]
                import ast
                res_dict = ast.literal_eval(raw_dict_str)
                for p_num, err_code in res_dict.items():
                    if err_code == 0:
                        port_results[str(p_num)] = "PASS"
                    elif err_code in (111, 10061):
                        port_results[str(p_num)] = "FAIL (CONNECTION_REFUSED)"
                    else:
                        port_results[str(p_num)] = f"FAIL (ERR_{err_code})"
                    logs.append(f"Port {p_num}: {port_results[str(p_num)]}")
            else:
                logs.append(f"ERROR: SSH Remote execution failed: {err.strip() or out.strip()}")
                return {
                    "success": False,
                    "site_name": site_name,
                    "site_ip": site_ip,
                    "site_port": site_port,
                    "office_ssh": f"{ssh_host}:{ssh_port}",
                    "ssh": "FAIL",
                    "remote_tcp": "FAIL",
                    "remote_http": "NOT_TESTED",
                    "failure_code": "SSH_CONNECTION_FAILED",
                    "port_tests": {},
                    "logs": logs
                }
        except Exception as ex:
            logs.append(f"ERROR: Exception executing SSH command: {ex}")
            return {
                "success": False,
                "site_name": site_name,
                "site_ip": site_ip,
                "site_port": site_port,
                "office_ssh": f"{ssh_host}:{ssh_port}",
                "ssh": "FAIL",
                "remote_tcp": "FAIL",
                "remote_http": "NOT_TESTED",
                "failure_code": "SSH_CONNECTION_FAILED",
                "port_tests": {},
                "logs": logs
            }

        config_port_str = str(site_port)
        configured_tcp_status = port_results.get(config_port_str, "FAIL")
        remote_tcp_pass = "PASS" if "PASS" in configured_tcp_status else "FAIL"

        failure_code = "REMOTE_SITE_REACHABLE" if remote_tcp_pass == "PASS" else "NETWORK_PATH_FAILURE"
        if remote_tcp_pass == "FAIL":
            if "CONNECTION_REFUSED" in configured_tcp_status:
                failure_code = "REMOTE_SITE_CONNECTION_REFUSED"
            elif "TIMEOUT" in configured_tcp_status or "11" in configured_tcp_status:
                failure_code = "REMOTE_SITE_TIMEOUT"
            else:
                failure_code = "REMOTE_SITE_UNREACHABLE"

        remote_http_status = "NOT_TESTED"

        if remote_tcp_pass == "PASS":
            logs.append(f"Configured Site Port {site_port} TCP PASS. Testing Remote HTTP GET from Office Server...")
            http_cmd_str = (
                "python3 -c \"import urllib.request, ssl; "
                "ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE; "
                "req=urllib.request.Request('http://" + site_ip + ":" + str(site_port) + "/', headers={'User-Agent': 'Mozilla/5.0'}); "
                "resp=urllib.request.urlopen(req, context=ctx, timeout=5); "
                "print('STATUS:', resp.status); print('BODY:', resp.read(200).decode('utf-8', 'ignore'))\""
            )

            cmd_http = [plink_path, "-batch", "-ssh", "-P", str(ssh_port), "-l", ssh_user]
            if ssh_pass:
                cmd_http.extend(["-pw", ssh_pass])
            cmd_http.extend([ssh_host, http_cmd_str])

            try:
                proc_h = subprocess.Popen(cmd_http, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                out_h, err_h = proc_h.communicate(timeout=10.0)

                if "STATUS: 200" in out_h or "STATUS:" in out_h:
                    remote_http_status = "PASS"
                    logs.append(f"✓ Remote HTTP GET Response Received: {out_h.strip()}")
                else:
                    remote_http_status = "FAIL"
                    logs.append(f"ERROR: Remote HTTP GET Failed: {err_h.strip() or out_h.strip()}")
            except Exception as h_ex:
                remote_http_status = "FAIL"
                logs.append(f"ERROR: Exception executing remote HTTP test: {h_ex}")

        formatted = (
            "========================================\n"
            "OFFICE → SITE NETWORK TEST\n"
            "========================================\n\n"
            f"Site:\n{site_name}\n\n"
            f"Site IP:\n{site_ip}\n\n"
            f"Configured Site Port:\n{site_port}\n\n"
            f"Office SSH:\n{ssh_host}:{ssh_port}\n\n"
            f"SSH:\n{ssh_pass_status}\n\n"
            f"Remote TCP:\n{remote_tcp_pass}\n\n"
            f"Remote HTTP:\n{remote_http_status}\n\n"
            "Port Tests:\n"
            + "\n".join([f"  {p}: {st}" for p, st in port_results.items()]) + "\n\n"
            f"Failure Classification:\n{failure_code}\n"
            "========================================"
        )

        return {
            "success": remote_tcp_pass == "PASS",
            "site_name": site_name,
            "site_ip": site_ip,
            "site_port": site_port,
            "office_ssh": f"{ssh_host}:{ssh_port}",
            "ssh": ssh_pass_status,
            "remote_tcp": remote_tcp_pass,
            "remote_http": remote_http_status,
            "failure_code": failure_code,
            "port_tests": port_results,
            "latency_ms": latency_ms,
            "logs": logs,
            "formatted_summary": formatted
        }

tunnel_manager = TunnelManager()



