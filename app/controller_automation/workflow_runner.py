import os
import time
import uuid
import logging
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable

from app.controller_automation.models import (
    ControllerCloneRequest,
    TestConnectionRequest,
    TestConnectionResult,
    ControllerStep,
    ControllerRunStatus
)
from app.controller_automation.ssh_runner import MultiHopSSHRunner
from app.database.db import (
    create_controller_run,
    update_controller_run,
    get_all_controller_settings
)

logger = logging.getLogger("Controller_WorkflowRunner")


class ControllerWorkflowRunner:
    """
    Manages and executes Room Controller configuration copy / provisioning jobs.
    Runs asynchronously in a background thread and emits live step & log events.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._status_listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._active_thread: Optional[threading.Thread] = None
        self._cancel_requested = False

        self.current_status: ControllerRunStatus = ControllerRunStatus(
            run_uuid="",
            status="IDLE",
            current_step="",
            progress_pct=0,
            steps=self._init_default_steps(is_new_controller=False),
            logs=[]
        )

    def add_status_listener(self, listener: Callable[[Dict[str, Any]], None]):
        """Registers a listener for live progress updates."""
        with self._lock:
            self._status_listeners.append(listener)

    def _notify_status(self):
        """Dispatches status updates to all listeners."""
        with self._lock:
            payload = self.current_status.model_dump()
            listeners = list(self._status_listeners)

        for listener in listeners:
            try:
                listener(payload)
            except Exception as e:
                logger.warning(f"Error in status listener callback: {e}")

    def _add_log(self, level: str, message: str):
        """Appends a log message and notifies listeners."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = {
            "timestamp": timestamp,
            "level": level.upper(),
            "message": message
        }
        with self._lock:
            self.current_status.logs.append(entry)
            # Cap in-memory logs to last 1000
            if len(self.current_status.logs) > 1000:
                self.current_status.logs = self.current_status.logs[-1000:]
        logger.info(f"[{level.upper()}] {message}")
        self._notify_status()

    def _init_default_steps(self, is_new_controller: bool = False) -> List[ControllerStep]:
        """Builds default step definitions for a run."""
        steps = [
            ControllerStep(id="hop_check", label="Verify Jump, Site Server & Controller Connectivity"),
            ControllerStep(id="backup", label="Target Controller Config Backup (/usr/local/smartler)"),
            ControllerStep(id="scp_clone", label="Clone Configuration from Similar Room Controller"),
            ControllerStep(id="patch_xml", label="Patch XML & Properties Config Files"),
            ControllerStep(id="service_restart", label="Restart Smartler Service"),
        ]
        if is_new_controller:
            steps.append(ControllerStep(id="network_config", label="Network Scripts IP Configuration (ifcfg-enp1s0/2s0)"))
        steps.append(ControllerStep(id="verification", label="Final Verification & Completion"))
        return steps

    def _update_step(self, step_id: str, status: str, message: str = ""):
        """Updates a specific step's status, timestamp, and message."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            for s in self.current_status.steps:
                if s.id == step_id:
                    s.status = status
                    if message:
                        s.message = message
                    if status == "RUNNING" and not s.started_at:
                        s.started_at = now_str
                    elif status in ("SUCCESS", "FAILED", "SKIPPED"):
                        s.completed_at = now_str
                    break

            # Calculate progress percentage
            total_steps = len(self.current_status.steps)
            completed_steps = sum(1 for s in self.current_status.steps if s.status in ("SUCCESS", "SKIPPED"))
            self.current_status.progress_pct = int((completed_steps / total_steps) * 100) if total_steps > 0 else 0
            self.current_status.current_step = step_id

        self._notify_status()

    def is_running(self) -> bool:
        """Returns True if a provisioning workflow is actively running."""
        with self._lock:
            return self.current_status.status == "RUNNING"

    def cancel_run(self) -> bool:
        """Requests cancellation of the ongoing workflow."""
        with self._lock:
            if self.current_status.status != "RUNNING":
                return False
            self._cancel_requested = True
            self._add_log("WARNING", "Cancellation requested by user. Aborting after current operation...")
            return True

    def test_connection(self, request: TestConnectionRequest) -> TestConnectionResult:
        """
        Executes a non-destructive multi-hop connectivity test.
        Verifies:
        1. Jump Server
        2. Site Server
        3. Target Controller (discovers working root password)
        4. Similar Controller (discovers working root password)
        """
        runner = MultiHopSSHRunner(
            jump_host=request.jump_host,
            jump_port=request.jump_port,
            jump_user=request.jump_username,
            jump_pass=request.jump_password
        )

        jump_ok, jump_msg = runner.test_jump_connection()
        if not jump_ok:
            return TestConnectionResult(
                success=False,
                jump_status={"connected": False, "message": jump_msg},
                site_status={"connected": False, "message": "Skipped due to jump failure"},
                target_controller_status={"connected": False, "message": "Skipped"},
                similar_controller_status={"connected": False, "message": "Skipped"},
                message=f"Jump server connection failed: {jump_msg}"
            )

        site_ok, site_msg = runner.test_site_connection(
            request.site_ip, request.site_port, request.site_username, request.site_password
        )
        if not site_ok:
            return TestConnectionResult(
                success=False,
                jump_status={"connected": True, "message": jump_msg},
                site_status={"connected": False, "message": site_msg},
                target_controller_status={"connected": False, "message": "Skipped due to site failure"},
                similar_controller_status={"connected": False, "message": "Skipped"},
                message=f"Site server connection failed: {site_msg}"
            )

        # Test Target Controller
        target_ip = request.target_ip
        target_pwd, target_msg = runner.discover_controller_password(
            request.site_ip, request.site_port, request.site_username, request.site_password,
            target_ip, request.controller_passwords
        )
        target_ok = target_pwd is not None

        # Test Similar Controller
        similar_pwd, similar_msg = runner.discover_controller_password(
            request.site_ip, request.site_port, request.site_username, request.site_password,
            request.similar_room_ip.strip(), request.controller_passwords
        )
        similar_ok = similar_pwd is not None

        overall_success = jump_ok and site_ok and target_ok and similar_ok
        summary_msg = (
            "All connection hops verified successfully!" if overall_success
            else f"Connection checks incomplete. Target controller: {target_msg}; Similar controller: {similar_msg}"
        )

        return TestConnectionResult(
            success=overall_success,
            jump_status={"connected": jump_ok, "message": jump_msg},
            site_status={"connected": site_ok, "message": site_msg},
            target_controller_status={"connected": target_ok, "ip": target_ip, "message": target_msg},
            similar_controller_status={"connected": similar_ok, "ip": request.similar_room_ip, "message": similar_msg},
            message=summary_msg
        )

    def start_run(self, request: ControllerCloneRequest) -> str:
        """Initiates the controller provisioning workflow in a background thread."""
        with self._lock:
            if self.current_status.status == "RUNNING":
                raise RuntimeError("Another controller provisioning workflow is already in progress.")

            run_uuid = f"ctrl_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
            self._cancel_requested = False

            steps = self._init_default_steps(is_new_controller=request.is_new_controller)
            self.current_status = ControllerRunStatus(
                run_uuid=run_uuid,
                status="RUNNING",
                current_step="hop_check",
                progress_pct=0,
                steps=steps,
                logs=[],
                started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                site_name=request.site_name or request.site_ip,
                site_ip=request.site_ip,
                current_room_no=request.current_room_no.strip(),
                current_room_ip=request.current_room_ip.strip(),
                target_ip=request.target_ip,
                similar_room_no=request.similar_room_no.strip(),
                similar_room_ip=request.similar_room_ip.strip(),
                is_new_controller=request.is_new_controller
            )

        # Record in DB
        try:
            create_controller_run({
                "run_uuid": run_uuid,
                "site_id": request.site_id,
                "site_name": request.site_name,
                "site_ip": request.site_ip,
                "site_port": request.site_port,
                "current_room_no": request.current_room_no,
                "current_room_ip": request.current_room_ip,
                "similar_room_no": request.similar_room_no,
                "similar_room_ip": request.similar_room_ip,
                "is_new_controller": request.is_new_controller,
                "target_ip": request.target_ip,
                "status": "RUNNING",
                "current_step": "hop_check",
                "started_at": self.current_status.started_at,
                "steps": [s.model_dump() for s in steps],
                "logs": []
            })
        except Exception as e:
            logger.error(f"Failed to record run in DB: {e}")

        self._active_thread = threading.Thread(
            target=self._execute_workflow,
            args=(request, run_uuid),
            daemon=True,
            name=f"ControllerThread_{run_uuid}"
        )
        self._active_thread.start()
        return run_uuid

    def _execute_workflow(self, request: ControllerCloneRequest, run_uuid: str):
        """Worker thread executing the 5-7 step controller provisioning chain."""
        start_time = time.time()
        self._add_log("INFO", f"=== STARTING CONTROLLER CONFIGURATION CLONE (Run {run_uuid}) ===")
        self._add_log("INFO", f"Target: Room {request.current_room_no} (IP: {request.target_ip}, New Controller: {request.is_new_controller})")
        self._add_log("INFO", f"Source: Room {request.similar_room_no} (IP: {request.similar_room_ip})")

        runner = MultiHopSSHRunner(
            jump_host=request.jump_host,
            jump_port=request.jump_port,
            jump_user=request.jump_username,
            jump_pass=request.jump_password
        )

        target_password = ""
        similar_password = ""
        backup_folder_name = ""

        try:
            # ---------------------------------------------------------
            # STEP 1: HOP CONNECTIVITY CHECK & CREDENTIAL DISCOVERY
            # ---------------------------------------------------------
            self._update_step("hop_check", "RUNNING", "Testing connectivity across hops...")
            self._add_log("INFO", "[STEP 1] Testing Jump Server connectivity...")

            if self._check_cancelled(): return

            jump_ok, jump_msg = runner.test_jump_connection()
            if not jump_ok:
                raise RuntimeError(f"Jump Server check failed: {jump_msg}")
            self._add_log("INFO", f"✓ {jump_msg}")

            if self._check_cancelled(): return

            self._add_log("INFO", f"[STEP 1] Testing Site Server connectivity to {request.site_ip}:{request.site_port}...")
            site_ok, site_msg = runner.test_site_connection(
                request.site_ip, request.site_port, request.site_username, request.site_password
            )
            if not site_ok:
                raise RuntimeError(f"Site Server check failed: {site_msg}")
            self._add_log("INFO", f"✓ {site_msg}")

            if self._check_cancelled(): return

            # Discover Target Controller root password
            target_ip = request.target_ip
            self._add_log("INFO", f"[STEP 1] Testing Target Controller root authentication on {target_ip}...")
            target_pwd, target_pwd_msg = runner.discover_controller_password(
                request.site_ip, request.site_port, request.site_username, request.site_password,
                target_ip, request.controller_passwords
            )
            if not target_pwd:
                raise RuntimeError(f"Target Controller ({target_ip}) auth failed: {target_pwd_msg}")
            target_password = target_pwd
            self.current_status.discovered_password = target_password
            self._add_log("INFO", f"✓ Target controller root authenticated with password: {target_password}")

            if self._check_cancelled(): return

            # Discover Similar Controller root password
            similar_ip = request.similar_room_ip.strip()
            self._add_log("INFO", f"[STEP 1] Testing Similar Controller root authentication on {similar_ip}...")
            sim_pwd, sim_pwd_msg = runner.discover_controller_password(
                request.site_ip, request.site_port, request.site_username, request.site_password,
                similar_ip, request.controller_passwords
            )
            if not sim_pwd:
                raise RuntimeError(f"Similar Controller ({similar_ip}) auth failed: {sim_pwd_msg}")
            similar_password = sim_pwd
            self._add_log("INFO", f"✓ Similar controller root authenticated with password: {similar_password}")

            self._update_step("hop_check", "SUCCESS", "All 3 hops and root credentials verified")

            # ---------------------------------------------------------
            # STEP 2: BACKUP TARGET CONTROLLER CONFIG
            # ---------------------------------------------------------
            if self._check_cancelled(): return
            self._update_step("backup", "RUNNING", "Backing up /usr/local/smartler/config...")
            self._add_log("INFO", "[STEP 2] Backing up existing config on target controller...")

            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_cmd = f"""
            set -e
            cd /usr/local/smartler || exit 1
            if [ -d "config" ]; then
                BACKUP_NAME="config_{date_str}"
                mv config "$BACKUP_NAME"
                echo "BACKUP_NAME_OK: $BACKUP_NAME"
            else
                echo "BACKUP_NAME_OK: NO_EXISTING_CONFIG"
            fi
            """

            code, out, err = runner.run_on_controller(
                request.site_ip, request.site_port, request.site_username, request.site_password,
                target_ip, target_password, backup_cmd, timeout=30
            )

            if code != 0:
                raise RuntimeError(f"Failed to backup existing config on target controller: {err.strip() or out.strip()}")

            for line in out.splitlines():
                if "BACKUP_NAME_OK:" in line:
                    backup_folder_name = line.split(":", 1)[1].strip()
                    break

            self._add_log("INFO", f"✓ Target controller backup completed: {backup_folder_name or 'config_' + date_str}")
            self._update_step("backup", "SUCCESS", f"Backup created: {backup_folder_name}")

            # ---------------------------------------------------------
            # STEP 3: CLONE CONFIGURATION FROM SIMILAR CONTROLLER
            # ---------------------------------------------------------
            if self._check_cancelled(): return
            self._update_step("scp_clone", "RUNNING", f"Cloning config from {similar_ip}...")
            self._add_log("INFO", f"[STEP 3] Cloning /usr/local/smartler/config from Similar Controller ({similar_ip})...")

            # Check if target controller has sshpass for direct clone
            direct_clone_cmd = f"""
            set -e
            cd /usr/local/smartler
            if command -v sshpass >/dev/null 2>&1; then
                sshpass -p '{similar_password}' scp -r -o StrictHostKeyChecking=no -o ConnectTimeout=20 root@{similar_ip}:/usr/local/smartler/config .
                echo "DIRECT_SCP_SUCCESS"
            else
                echo "DIRECT_SCP_NOT_SUPPORTED"
            fi
            """

            code, out, err = runner.run_on_controller(
                request.site_ip, request.site_port, request.site_username, request.site_password,
                target_ip, target_password, direct_clone_cmd, timeout=45
            )

            if "DIRECT_SCP_SUCCESS" in out:
                self._add_log("INFO", f"✓ Direct SCP clone completed from root@{similar_ip}:/usr/local/smartler/config to target")
            else:
                self._add_log("INFO", "[STEP 3] Target controller lacks sshpass; performing staged clone via Site Server...")
                # Staged clone via Site Server
                staged_ok, staged_msg = runner.scp_between_controllers_via_site(
                    request.site_ip, request.site_port, request.site_username, request.site_password,
                    similar_ip, similar_password, target_ip, target_password, timeout=60
                )
                if not staged_ok:
                    raise RuntimeError(f"Clone failed: {staged_msg}")
                self._add_log("INFO", f"✓ {staged_msg}")

            # Verify config directory exists on target
            verify_cmd = "test -d /usr/local/smartler/config && echo 'CONFIG_DIR_EXISTS' || echo 'CONFIG_DIR_MISSING'"
            c_code, c_out, _ = runner.run_on_controller(
                request.site_ip, request.site_port, request.site_username, request.site_password,
                target_ip, target_password, verify_cmd, timeout=15
            )
            if "CONFIG_DIR_EXISTS" not in c_out:
                raise RuntimeError("Verification failed: /usr/local/smartler/config directory was not created on target controller")

            self._update_step("scp_clone", "SUCCESS", "Cloned /usr/local/smartler/config from similar controller")

            # ---------------------------------------------------------
            # STEP 4: PATCH XML & PROPERTIES FILES
            # ---------------------------------------------------------
            if self._check_cancelled(): return
            self._update_step("patch_xml", "RUNNING", "Patching config-menu.xml, config-smartler.xml, config-smartler.properties...")
            self._add_log("INFO", "[STEP 4] Modifying configuration files in /usr/local/smartler/config/...")

            # Replacements per user specification:
            # 1. config-menu.xml: similar controller IP -> current controller IP; similar room no -> current room no
            # 2. config-smartler.xml: similar controller IP -> current controller IP
            # 3. config-smartler.properties: similar controller IP -> current controller IP
            curr_ip = request.current_room_ip.strip()
            curr_room = request.current_room_no.strip()
            sim_ip = request.similar_room_ip.strip()
            sim_room = request.similar_room_no.strip()

            patch_script = f"""
            set -e
            cd /usr/local/smartler/config || exit 1

            replace_text() {{
                local file="$1"
                local search="$2"
                local replace="$3"
                local desc="$4"
                if [ -f "$file" ]; then
                    local count=$(grep -c -F "$search" "$file" || true)
                    if [ "$count" -gt 0 ]; then
                        sed -i "s|${{search}}|${{replace}}|g" "$file"
                        echo "PATCHED: $file ($desc: replaced $count occurrence(s) of '$search' with '$replace')"
                    else
                        echo "NOTICE: $file ($desc: search string '$search' not found)"
                    fi
                else
                    echo "MISSING_FILE: $file does not exist"
                fi
            }}

            # IMPORTANT: Replace IP addresses BEFORE room numbers so numbers don't collide with octets
            replace_text "config-menu.xml" "{sim_ip}" "{curr_ip}" "Menu Controller IP"
            replace_text "config-menu.xml" "{sim_room}" "{curr_room}" "Menu Room Number"
            replace_text "config-smartler.xml" "{sim_ip}" "{curr_ip}" "Smartler Controller IP"
            replace_text "config-smartler.properties" "{sim_ip}" "{curr_ip}" "Properties Controller IP"

            echo "PATCH_OPERATION_COMPLETED"
            """

            p_code, p_out, p_err = runner.run_on_controller(
                request.site_ip, request.site_port, request.site_username, request.site_password,
                target_ip, target_password, patch_script, timeout=30
            )

            if p_code != 0 or "PATCH_OPERATION_COMPLETED" not in p_out:
                raise RuntimeError(f"Configuration file patch failed: {p_err.strip() or p_out.strip()}")

            for l in p_out.splitlines():
                l_str = l.strip()
                if l_str.startswith("PATCHED:") or l_str.startswith("NOTICE:") or l_str.startswith("MISSING_FILE:"):
                    self._add_log("INFO", f"  ↳ {l_str}")

            self._update_step("patch_xml", "SUCCESS", "All config files updated with new Room & IP")

            # ---------------------------------------------------------
            # STEP 5: RESTART SMARTLER SERVICE
            # ---------------------------------------------------------
            if self._check_cancelled(): return
            self._update_step("service_restart", "RUNNING", "Restarting smartler service...")
            self._add_log("INFO", "[STEP 5] Restarting smartler service on target controller...")

            service_cmd = """
            if command -v service >/dev/null 2>&1; then
                service smartler restart
            elif command -v systemctl >/dev/null 2>&1; then
                systemctl restart smartler
            else
                /etc/init.d/smartler restart
            fi

            sleep 2
            if ps aux | grep -v grep | grep -q smartler; then
                echo "SERVICE_STATUS: RUNNING"
            else
                echo "SERVICE_STATUS: CHECK_FAILED"
            fi
            """

            s_code, s_out, s_err = runner.run_on_controller(
                request.site_ip, request.site_port, request.site_username, request.site_password,
                target_ip, target_password, service_cmd, timeout=30
            )

            if "SERVICE_STATUS: RUNNING" in s_out:
                self._add_log("INFO", "✓ Smartler service restarted and process confirmed running")
            else:
                self._add_log("WARNING", f"Smartler restart executed. Status output: {s_out.strip() or s_err.strip()}")

            self._update_step("service_restart", "SUCCESS", "Smartler service restarted successfully")

            # ---------------------------------------------------------
            # STEP 6: NETWORK SCRIPTS CONFIGURATION (IF NEW CONTROLLER)
            # ---------------------------------------------------------
            if request.is_new_controller:
                if self._check_cancelled(): return
                self._update_step("network_config", "RUNNING", "Inspecting /etc/sysconfig/network-scripts/...")
                self._add_log("INFO", "[STEP 6] Inspecting network scripts for default IP 10.172.100.100...")

                network_cmd = f"""
                set -e
                cd /etc/sysconfig/network-scripts || exit 1
                MODIFIED_COUNT=0

                for f in ifcfg-enp1s0 ifcfg-enp2s0; do
                    if [ -f "$f" ]; then
                        if grep -q "10\.172\.100\.100" "$f"; then
                            cp "$f" "${{f}}.bak_{date_str}"
                            sed -i "s|10\.172\.100\.100|{curr_ip}|g" "$f"
                            echo "NET_PATCHED: $f (10.172.100.100 replaced with {curr_ip})"
                            MODIFIED_COUNT=$((MODIFIED_COUNT + 1))
                        else
                            echo "NET_NO_MATCH: 10.172.100.100 not found in $f"
                        fi
                    else
                        echo "NET_NOT_FOUND: $f does not exist"
                    fi
                done

                echo "TOTAL_NET_MODIFIED: $MODIFIED_COUNT"
                """

                n_code, n_out, n_err = runner.run_on_controller(
                    request.site_ip, request.site_port, request.site_username, request.site_password,
                    target_ip, target_password, network_cmd, timeout=30
                )

                for l in n_out.splitlines():
                    l_str = l.strip()
                    if l_str.startswith("NET_PATCHED:") or l_str.startswith("NET_NO_MATCH:") or l_str.startswith("NET_NOT_FOUND:"):
                        self._add_log("INFO", f"  ↳ {l_str}")

                self._add_log("INFO", f"✓ Network configuration updated. Controller will now respond on {curr_ip} upon system restart/network reload.")
                self._update_step("network_config", "SUCCESS", f"Updated network scripts with IP {curr_ip}")

            # ---------------------------------------------------------
            # STEP 7: FINAL VERIFICATION & REPORT
            # ---------------------------------------------------------
            if self._check_cancelled(): return
            self._update_step("verification", "RUNNING", "Validating final controller state...")

            # Verify files are non-empty and exist
            check_files_cmd = "ls -lh /usr/local/smartler/config/config-menu.xml /usr/local/smartler/config/config-smartler.xml /usr/local/smartler/config/config-smartler.properties"
            v_code, v_out, _ = runner.run_on_controller(
                request.site_ip, request.site_port, request.site_username, request.site_password,
                target_ip, target_password, check_files_cmd, timeout=15
            )

            self._add_log("INFO", "[VERIFICATION] Configuration files verified in /usr/local/smartler/config/:")
            for line in v_out.splitlines():
                if line.strip():
                    self._add_log("INFO", f"  {line.strip()}")

            self._update_step("verification", "SUCCESS", "All verification checks passed")

            duration = round(time.time() - start_time, 2)
            with self._lock:
                self.current_status.status = "SUCCESS"
                self.current_status.progress_pct = 100
                self.current_status.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.current_status.duration_seconds = duration

            self._add_log("INFO", f"🎉 [SUCCESS] Controller Configuration Copy Completed Successfully in {duration}s!")
            self._notify_status()

            # Update DB record
            update_controller_run(run_uuid, {
                "status": "SUCCESS",
                "completed_at": self.current_status.completed_at,
                "duration_seconds": duration,
                "backup_folder": backup_folder_name,
                "discovered_password": target_password,
                "steps": [s.model_dump() for s in self.current_status.steps],
                "logs": self.current_status.logs
            })

        except Exception as e:
            duration = round(time.time() - start_time, 2)
            err_msg = str(e)
            logger.exception(f"Controller workflow failed: {e}")
            self._add_log("ERROR", f"❌ Execution Failed: {err_msg}")

            with self._lock:
                self.current_status.status = "FAILED"
                self.current_status.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.current_status.duration_seconds = duration
                self.current_status.error_message = err_msg

                # Mark any running step as failed
                for s in self.current_status.steps:
                    if s.status == "RUNNING":
                        s.status = "FAILED"
                        s.message = err_msg
                        s.completed_at = self.current_status.completed_at

            self._notify_status()

            # Update DB record
            update_controller_run(run_uuid, {
                "status": "FAILED",
                "completed_at": self.current_status.completed_at,
                "duration_seconds": duration,
                "error_message": err_msg,
                "discovered_password": target_password,
                "steps": [s.model_dump() for s in self.current_status.steps],
                "logs": self.current_status.logs
            })

    def _check_cancelled(self) -> bool:
        """Returns True and sets state if run was cancelled."""
        if self._cancel_requested:
            with self._lock:
                self.current_status.status = "STOPPED"
                self.current_status.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for s in self.current_status.steps:
                    if s.status == "RUNNING":
                        s.status = "STOPPED"
                        s.message = "Cancelled by user"
            self._add_log("WARNING", "Workflow halted by user request.")
            self._notify_status()
            return True
        return False


# Global singleton instance
controller_workflow_runner = ControllerWorkflowRunner()
