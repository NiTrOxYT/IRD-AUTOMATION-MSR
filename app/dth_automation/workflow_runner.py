import os
import time
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, Set

from app.config import REPORTS_DIR, DOWNLOADS_DIR
from app.database.db import (
    get_site_by_id,
    get_dth_site_by_id,
    create_dth_run,
    update_dth_run,
    save_dth_channel_result,
    get_all_dth_settings
)
from app.dth_automation.models import (
    ChannelItem,
    ChannelValidationResult,
    DthItemState,
    DthRunState,
    DthExecutionMode,
    DthRunSummary,
    StartDthRunRequest,
    BrowserSnapshot
)
from app.dth_automation.file_parser import parse_dth_file
from app.dth_automation.validator import validate_channel_batch
from app.dth_automation.selectors import DthSelectorRegistry
from app.dth_automation.portal_controller import DthPortalController
from app.dth_automation.audit_logger import DthAuditLogger
from app.dth_automation.report_generator import export_dth_reports

logger = logging.getLogger("DTH_WorkflowRunner")


class DthWorkflowRunner:
    def __init__(self):
        self.is_running: bool = False
        self.stop_requested: bool = False
        self.current_run_id: Optional[int] = None
        self.current_site_id: Optional[int] = None
        self.current_site_name: str = ""
        self.current_mode: DthExecutionMode = DthExecutionMode.DRY_RUN
        self.current_status: DthRunState = DthRunState.PENDING
        self.current_operation: str = "Idle"
        self.current_channel_identifier: Optional[str] = None
        self.progress_percentage: float = 0.0

        self.portal_controller: Optional[DthPortalController] = None
        self.status_listeners: List[Callable[[Dict[str, Any]], None]] = []

    def add_status_listener(self, listener: Callable[[Dict[str, Any]], None]):
        if listener not in self.status_listeners:
            self.status_listeners.append(listener)

    def _broadcast_status(self, extra: Optional[Dict[str, Any]] = None):
        payload = {
            "is_running": self.is_running,
            "run_id": self.current_run_id,
            "site_id": self.current_site_id,
            "site_name": self.current_site_name,
            "mode": self.current_mode.value,
            "status": self.current_status.value,
            "operation": self.current_operation,
            "current_channel": self.current_channel_identifier,
            "progress_percentage": self.progress_percentage
        }
        if extra:
            payload.update(extra)

        for listener in self.status_listeners:
            try:
                listener(payload)
            except Exception:
                pass

    def _on_browser_snapshot(self, snapshot: BrowserSnapshot):
        """Dispatches real-time browser diagnostic snapshots to listeners."""
        logger.info(f"[OBSERVER RUN #{self.current_run_id}] Step {snapshot.step_number:03d}: {snapshot.action_name} | State: {snapshot.detected_state} | Passed: {snapshot.verification_passed}")
        self._broadcast_status({
            "latest_snapshot": snapshot.model_dump(),
            "workflow_state": snapshot.detected_state,
            "operation": f"Step {snapshot.step_number}: {snapshot.action_name} ({snapshot.detected_state})"
        })

    def stop_automation(self):
        """Requests graceful cancellation of active DTH automation."""
        logger.warning("[DTH] Cancellation requested by user. Terminating execution...")
        self.stop_requested = True
        self.current_operation = "Cancellation requested"
        if self.portal_controller:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.portal_controller.emergency_stop())
            except Exception as e:
                logger.debug(f"[DTH] Controller stop notification notice: {e}")
        self._broadcast_status({"status": DthRunState.STOPPED.value})

    async def execute_batch(
        self,
        file_path: str,
        image_dir: Optional[str] = None,
        site_id: int = 1,
        mode: DthExecutionMode = DthExecutionMode.DRY_RUN,
        channel_delay_seconds: float = 0.2,
        authorized: bool = False
    ) -> Dict[str, Any]:
        """
        Main entrypoint for DTH bulk execution.
        Supports DRY_RUN (default, 0 mutations) and LIVE (requires authorized=True).
        """
        if self.is_running:
            raise RuntimeError("Another DTH automation batch is already running.")

        if mode == DthExecutionMode.LIVE and not authorized:
            raise ValueError("Live execution requires explicit authorization confirmation.")

        dth_site_dict = get_dth_site_by_id(site_id, include_passwords=True)
        if dth_site_dict:
            from types import SimpleNamespace
            site = SimpleNamespace(**dth_site_dict)
            if not getattr(site, "web_url", ""):
                site.web_url = getattr(site, "portal_url", "") or f"http://localhost:{site.local_port}/zmp/main-menu.do"
        else:
            site = get_site_by_id(site_id)

        if not site:
            raise ValueError(f"Target site #{site_id} not found in database.")

        self.is_running = True
        self.stop_requested = False
        self.current_site_id = site.id
        self.current_site_name = site.name
        self.current_mode = mode
        self.current_status = DthRunState.IN_PROGRESS
        self.current_operation = f"Starting {mode.value} execution"
        self.progress_percentage = 0.0

        filename = os.path.basename(file_path)
        date_str = datetime.now().strftime("%Y-%m-%d")
        start_time_str = datetime.now().strftime("%H:%M:%S")

        run_id = create_dth_run({
            "run_date": date_str,
            "start_time": start_time_str,
            "mode": mode.value,
            "status": DthRunState.IN_PROGRESS.value,
            "filename": filename,
            "site_id": site.id,
            "site_name": site.name
        })
        self.current_run_id = run_id
        self._broadcast_status()

        from app.config import CHANNEL_LOGOS_DIR
        effective_image_dir = image_dir or str(CHANNEL_LOGOS_DIR)

        DthAuditLogger.log_event("RUN_STARTED", run_id, None, {
            "site": site.name,
            "filename": filename,
            "mode": mode.value,
            "image_dir": effective_image_dir
        })

        # Counters
        processed_count = 0
        successful_count = 0
        failed_count = 0
        skipped_duplicates_count = 0
        invalid_count = 0
        unknown_count = 0

        channel_records: List[Dict[str, Any]] = []

        try:
            # Step 1: Parse Input File
            self.current_operation = "Parsing input file"
            self._broadcast_status()
            raw_records, parse_errors = parse_dth_file(file_path)
            if parse_errors:
                err_msg = f"File parsing failed: {'; '.join(parse_errors)}"
                self.current_status = DthRunState.FAILED
                self.current_operation = err_msg
                update_dth_run(run_id, {
                    "status": DthRunState.FAILED.value,
                    "end_time": datetime.now().strftime("%H:%M:%S"),
                    "error_message": err_msg
                })
                self._broadcast_status()
                return {"success": False, "run_id": run_id, "error": err_msg}

            total_channels = len(raw_records)
            update_dth_run(run_id, {"total_channels": total_channels})

            # Step 2: Establish Reverse Tunnel (Like IRD Automation)
            raw_ip = str(getattr(site, "site_ip", "") or getattr(site, "remote_host", "") or "").strip()
            needs_tunnel = bool(raw_ip and raw_ip != "127.0.0.1" and raw_ip.lower() != "localhost") or bool(getattr(site, "ssh_host", ""))

            if needs_tunnel:
                self.current_operation = f"Establishing reverse tunnel for {site.name} ({site.site_ip or site.remote_host})"
                self._broadcast_status()
                from app.tunneling.tunnel_manager import tunnel_manager
                t_ok, t_msg, t_logs = await tunnel_manager.start_and_verify_tunnel(site, timeout_seconds=30, keep_running=True)
                if not t_ok:
                    if mode == DthExecutionMode.LIVE:
                        err_msg = f"Reverse tunnel failed for {site.name}: {t_msg}"
                        logger.error(f"[DTH] {err_msg}")
                        self.current_status = DthRunState.FAILED
                        self.current_operation = err_msg
                        update_dth_run(run_id, {
                            "status": DthRunState.FAILED.value,
                            "end_time": datetime.now().strftime("%H:%M:%S"),
                            "error_message": err_msg
                        })
                        self._broadcast_status()
                        return {"success": False, "run_id": run_id, "error": err_msg}
                    else:
                        logger.warning(f"[DTH] Tunnel not established in DRY_RUN ({t_msg}). Proceeding with offline validation.")

            # Step 3: Open ZMP Portal and Navigate to /zmp/manage-stb-channels.do
            local_port = getattr(site, "local_port", 18001) or 18001
            base_url = f"http://localhost:{local_port}"
            entry_url = getattr(site, "portal_url", "") or getattr(site, "web_url", "") or f"{base_url}/zmp/main-menu.do"
            if "127.0.0.1" in entry_url:
                entry_url = entry_url.replace("127.0.0.1", "localhost")

            self.portal_controller = DthPortalController()
            self.portal_controller.on_snapshot = self._on_browser_snapshot
            portal_nums: Set[str] = set()
            portal_names: Set[str] = set()
            available_categories = None

            try:
                self.current_operation = "Connecting to target portal"
                self._broadcast_status()
                dth_settings = get_all_dth_settings()
                is_headless = str(dth_settings.get("headless", "false")).strip().lower() in ("true", "1", "yes")
                b_type = str(dth_settings.get("browser_type", "chromium")).strip().lower() or "chromium"
                logger.info(f"[DTH] Initializing Playwright browser (type: {b_type}, headless: {is_headless})...")
                if hasattr(self.portal_controller, "set_run_id"):
                    self.portal_controller.set_run_id(run_id)
                await self.portal_controller.initialize(headless=is_headless, browser_type_str=b_type)

                # Step 3A: IDP Authentication with Snapshot Verification
                idp_user = (getattr(site, "idp_username", "") or "").strip() or "admin"
                idp_pass = (getattr(site, "idp_password", "") or "").strip()

                self.current_operation = f"Connecting and authenticating IDP for {site.name}"
                self._broadcast_status()

                if hasattr(self.portal_controller, "observe_and_authenticate"):
                    auth_coro = self.portal_controller.observe_and_authenticate(
                        base_url=base_url,
                        username=idp_user,
                        password=idp_pass,
                        timeout_seconds=30
                    )
                    if asyncio.iscoroutine(auth_coro):
                        auth_ok, auth_msg = await auth_coro
                    else:
                        auth_ok, auth_msg = True, "Authenticated"
                else:
                    auth_ok, auth_msg = await self.portal_controller.login_if_required(idp_user, idp_pass)

                if not auth_ok:
                    err_msg = f"Portal IDP authentication failed: {auth_msg}"
                    logger.error(f"[DTH] {err_msg}")
                    if mode == DthExecutionMode.LIVE:
                        self.current_status = DthRunState.FAILED
                        self.current_operation = err_msg
                        update_dth_run(run_id, {
                            "status": DthRunState.FAILED.value,
                            "end_time": datetime.now().strftime("%H:%M:%S"),
                            "error_message": err_msg
                        })
                        self._broadcast_status()
                        return {"success": False, "run_id": run_id, "error": err_msg}

                # Step 3B: Open /zmp/manage-stb-channels.do with Snapshot Verification
                self.current_operation = "Opening DTH Channel Configuration"
                self._broadcast_status()
                cfg_ok, cfg_msg = await self.portal_controller.open_dth_configuration(base_url=base_url)
                if not cfg_ok and mode == DthExecutionMode.LIVE:
                    err_msg = f"Failed to open DTH Channel Configuration: {cfg_msg}"
                    logger.error(f"[DTH] {err_msg}")
                    self.current_status = DthRunState.FAILED
                    self.current_operation = err_msg
                    update_dth_run(run_id, {
                        "status": DthRunState.FAILED.value,
                        "end_time": datetime.now().strftime("%H:%M:%S"),
                        "error_message": err_msg
                    })
                    self._broadcast_status()
                    return {"success": False, "run_id": run_id, "error": err_msg}

                available_categories = await self.portal_controller.read_available_categories()
                portal_nums, portal_names = await self.portal_controller.get_existing_channels_from_portal()
            except Exception as ex:
                logger.warning(f"[DTH] Could not query live portal state: {ex}. Proceeding with offline validation.")

            portal_channels_map = getattr(self.portal_controller, "existing_channels_map", {}) if self.portal_controller else {}

            # Step 4: Preflight Validation Pipeline
            self.current_operation = "Executing preflight validation"
            self._broadcast_status()
            items, validation_results = validate_channel_batch(
                raw_records,
                image_dir=effective_image_dir,
                portal_categories=available_categories,
                portal_existing_channel_numbers=None,
                portal_existing_channel_names=None
            )

            # Step 5: Process Channels and Tally Against Portal
            for idx, (channel_item, val_res) in enumerate(zip(items, validation_results), start=1):
                if self.stop_requested:
                    logger.warning("[DTH] Stopping execution as requested by user.")
                    self.current_status = DthRunState.STOPPED
                    break

                self.current_channel_identifier = f"{channel_item.channel_number} - {channel_item.name}"
                self.progress_percentage = round((idx / total_channels) * 100, 1)
                ch_start = time.strftime("%H:%M:%S")
                start_ticks = time.time()

                # Handle preflight invalid items
                if val_res.status == DthItemState.INVALID:
                    invalid_count += 1
                    processed_count += 1
                    err_msg = "; ".join(val_res.errors)
                    rec = {
                        "run_id": run_id,
                        "row_number": channel_item.row_number,
                        "channel_number": channel_item.channel_number,
                        "name": channel_item.name,
                        "osd": channel_item.osd,
                        "image": channel_item.image,
                        "categories": channel_item.categories,
                        "status": DthItemState.INVALID.value,
                        "attempt_count": 0,
                        "duration_seconds": 0.0,
                        "error_reason": err_msg,
                        "verified_in_portal": False,
                        "started_at": ch_start,
                        "completed_at": time.strftime("%H:%M:%S")
                    }
                    save_dth_channel_result(rec)
                    channel_records.append(rec)
                    DthAuditLogger.log_event("CHANNEL_INVALID", run_id, channel_item.channel_number, {"errors": err_msg})
                    continue

                ch_key = str(channel_item.channel_number).strip().lower()
                is_num_in_portal = ch_key in portal_nums or ch_key in portal_channels_map
                portal_info = portal_channels_map.get(ch_key)
                portal_name = (portal_info.get("name") if portal_info else "").strip() if portal_info else ""
                file_name = channel_item.name.strip()

                # For every channel, first check with channel number in ZMP portal:
                if is_num_in_portal:
                    # Channel number ALREADY present in portal: check channel name
                    if portal_name and portal_name.lower() == file_name.lower():
                        # Portal name matches file name: tallied & duplicate
                        skipped_duplicates_count += 1
                        processed_count += 1
                        tally_msg = f"Channel #{channel_item.channel_number} already in portal with matching name '{portal_name}' (Tallied)"
                        rec = {
                            "run_id": run_id,
                            "row_number": channel_item.row_number,
                            "channel_number": channel_item.channel_number,
                            "name": channel_item.name,
                            "osd": channel_item.osd,
                            "image": channel_item.image,
                            "categories": channel_item.categories,
                            "status": DthItemState.SKIPPED_DUPLICATE.value,
                            "attempt_count": 0,
                            "duration_seconds": 0.0,
                            "error_reason": tally_msg,
                            "verified_in_portal": True,
                            "started_at": ch_start,
                            "completed_at": time.strftime("%H:%M:%S")
                        }
                        save_dth_channel_result(rec)
                        channel_records.append(rec)
                        DthAuditLogger.log_event("CHANNEL_TALLIED_DUPLICATE", run_id, channel_item.channel_number, {"message": tally_msg})
                        continue
                    else:
                        # Channel number is present, but name differs:
                        # File is always true: tally with portal and configure to match file!
                        if mode == DthExecutionMode.DRY_RUN:
                            successful_count += 1
                            processed_count += 1
                            tally_msg = f"Dry Run: Channel #{channel_item.channel_number} in portal as '{portal_name}', file has '{file_name}'. File is true - will configure in LIVE mode."
                            rec = {
                                "run_id": run_id,
                                "row_number": channel_item.row_number,
                                "channel_number": channel_item.channel_number,
                                "name": channel_item.name,
                                "osd": channel_item.osd,
                                "image": channel_item.image,
                                "categories": channel_item.categories,
                                "status": DthItemState.READY.value,
                                "attempt_count": 0,
                                "duration_seconds": 0.0,
                                "error_reason": tally_msg,
                                "verified_in_portal": False,
                                "started_at": ch_start,
                                "completed_at": time.strftime("%H:%M:%S")
                            }
                            save_dth_channel_result(rec)
                            channel_records.append(rec)
                            continue
                        else:
                            # LIVE MODE: Configure/update channel on portal to match file
                            self.current_operation = f"Updating Channel #{channel_item.channel_number}: '{portal_name}' -> '{file_name}'"
                            self._broadcast_status()

                            item_state, reason, verified = await self.portal_controller.update_channel(channel_item, portal_info)
                            duration = round(time.time() - start_ticks, 2)
                            processed_count += 1

                            if item_state == DthItemState.SUCCESS:
                                successful_count += 1
                            elif item_state == DthItemState.FAILED:
                                failed_count += 1
                            elif item_state == DthItemState.UNKNOWN:
                                unknown_count += 1

                            rec = {
                                "run_id": run_id,
                                "row_number": channel_item.row_number,
                                "channel_number": channel_item.channel_number,
                                "name": channel_item.name,
                                "osd": channel_item.osd,
                                "image": channel_item.image,
                                "categories": channel_item.categories,
                                "status": item_state.value,
                                "attempt_count": 1,
                                "duration_seconds": duration,
                                "error_reason": reason,
                                "verified_in_portal": verified,
                                "started_at": ch_start,
                                "completed_at": time.strftime("%H:%M:%S")
                            }
                            save_dth_channel_result(rec)
                            channel_records.append(rec)
                            DthAuditLogger.log_event("CHANNEL_UPDATED", run_id, channel_item.channel_number, {
                                "status": item_state.value,
                                "duration": duration,
                                "reason": reason
                            })

                            if channel_delay_seconds > 0 and not self.stop_requested:
                                await asyncio.sleep(channel_delay_seconds)
                            continue

                # Channel number NOT in portal:
                if mode == DthExecutionMode.DRY_RUN:
                    successful_count += 1
                    processed_count += 1
                    rec = {
                        "run_id": run_id,
                        "row_number": channel_item.row_number,
                        "channel_number": channel_item.channel_number,
                        "name": channel_item.name,
                        "osd": channel_item.osd,
                        "image": channel_item.image,
                        "categories": channel_item.categories,
                        "status": DthItemState.READY.value,
                        "attempt_count": 0,
                        "duration_seconds": 0.0,
                        "error_reason": "Dry run preview: Ready to create",
                        "verified_in_portal": False,
                        "started_at": ch_start,
                        "completed_at": time.strftime("%H:%M:%S")
                    }
                    save_dth_channel_result(rec)
                    channel_records.append(rec)
                    continue

                # LIVE MODE: Create channel on portal
                self.current_operation = f"Creating Channel #{channel_item.channel_number}: '{channel_item.name}'"
                self._broadcast_status()

                item_state, reason, verified = await self.portal_controller.create_channel(channel_item)
                duration = round(time.time() - start_ticks, 2)
                processed_count += 1

                if item_state == DthItemState.SUCCESS:
                    successful_count += 1
                    ch_key_lower = str(channel_item.channel_number).strip().lower()
                    portal_nums.add(ch_key_lower)
                    portal_names.add(channel_item.name.lower())
                    portal_channels_map[ch_key_lower] = {
                        "number": ch_key_lower,
                        "name": channel_item.name,
                        "row_id": f"row_{ch_key_lower}"
                    }
                elif item_state == DthItemState.FAILED:
                    failed_count += 1
                elif item_state == DthItemState.UNKNOWN:
                    unknown_count += 1

                rec = {
                    "run_id": run_id,
                    "row_number": channel_item.row_number,
                    "channel_number": channel_item.channel_number,
                    "name": channel_item.name,
                    "osd": channel_item.osd,
                    "image": channel_item.image,
                    "categories": channel_item.categories,
                    "status": item_state.value,
                    "attempt_count": 1,
                    "duration_seconds": duration,
                    "error_reason": reason,
                    "verified_in_portal": verified,
                    "started_at": ch_start,
                    "completed_at": time.strftime("%H:%M:%S")
                }
                save_dth_channel_result(rec)
                channel_records.append(rec)
                DthAuditLogger.log_event("CHANNEL_PROCESSED", run_id, channel_item.channel_number, {
                    "status": item_state.value,
                    "duration": duration,
                    "reason": reason
                })

                # Configurable delay between channel submissions
                if channel_delay_seconds > 0 and not self.stop_requested:
                    await asyncio.sleep(channel_delay_seconds)

            # Finalize run
            if self.stop_requested:
                self.current_status = DthRunState.STOPPED
            else:
                self.current_status = DthRunState.COMPLETED

            end_time_str = datetime.now().strftime("%H:%M:%S")
            self.current_operation = f"{mode.value} execution {self.current_status.value.lower()}"
            self.progress_percentage = 100.0

            run_summary_dict = {
                "id": run_id,
                "run_date": date_str,
                "start_time": start_time_str,
                "end_time": end_time_str,
                "mode": mode.value,
                "status": self.current_status.value,
                "filename": filename,
                "total_channels": total_channels,
                "processed_channels": processed_count,
                "successful_channels": successful_count,
                "failed_channels": failed_count,
                "skipped_duplicates": skipped_duplicates_count,
                "invalid_channels": invalid_count,
                "unknown_channels": unknown_count,
                "site_id": site.id,
                "site_name": site.name
            }
            update_dth_run(run_id, run_summary_dict)

            # Export CSV and JSON execution reports
            report_paths = export_dth_reports(run_summary_dict, channel_records)

            DthAuditLogger.log_event("RUN_COMPLETED", run_id, None, {
                "status": self.current_status.value,
                "total": total_channels,
                "successful": successful_count,
                "failed": failed_count,
                "skipped": skipped_duplicates_count
            })

            self._broadcast_status({"reports": report_paths})

            return {
                "success": True,
                "run_id": run_id,
                "summary": run_summary_dict,
                "reports": report_paths
            }

        except Exception as e:
            logger.error(f"[DTH] Workflow runner exception: {e}")
            self.current_status = DthRunState.FAILED
            self.current_operation = f"Execution failed: {str(e)}"
            update_dth_run(run_id, {
                "status": DthRunState.FAILED.value,
                "end_time": datetime.now().strftime("%H:%M:%S"),
                "error_message": str(e)
            })
            self._broadcast_status()
            return {"success": False, "run_id": run_id, "error": str(e)}

        finally:
            self.is_running = False
            if self.portal_controller:
                await self.portal_controller.close()
                self.portal_controller = None


dth_workflow_runner = DthWorkflowRunner()
