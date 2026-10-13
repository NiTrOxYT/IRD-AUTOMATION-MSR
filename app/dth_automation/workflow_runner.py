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
    save_dth_channel_result
)
from app.dth_automation.models import (
    ChannelItem,
    ChannelValidationResult,
    DthItemState,
    DthRunState,
    DthExecutionMode,
    DthRunSummary,
    StartDthRunRequest
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
        image_dir: str,
        site_id: int,
        mode: DthExecutionMode = DthExecutionMode.DRY_RUN,
        channel_delay_seconds: float = 1.0,
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

        DthAuditLogger.log_event("RUN_STARTED", run_id, None, {
            "site": site.name,
            "filename": filename,
            "mode": mode.value,
            "image_dir": image_dir
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

            # Step 2: Establish Browser Session & Fetch Portal Duplicate Baseline
            self.portal_controller = DthPortalController()
            portal_nums: Set[str] = set()
            portal_names: Set[str] = set()
            available_categories = None

            try:
                self.current_operation = "Connecting to target portal"
                self._broadcast_status()
                # Use site URL
                target_url = getattr(site, "web_url", "") or f"http://localhost:{site.local_port}/zmp/main-menu.do"
                await self.portal_controller.initialize(headless=True)
                nav_ok = await self.portal_controller.navigate_to_url(target_url, timeout_seconds=45)
                if nav_ok:
                    # Authenticate if required
                    if site.idp_username and site.idp_password:
                        await self.portal_controller.login_if_required(site.idp_username, site.idp_password)
                    await self.portal_controller.open_dth_configuration()
                    available_categories = await self.portal_controller.read_available_categories()
                    portal_nums, portal_names = await self.portal_controller.get_existing_channels_from_portal()
            except Exception as ex:
                logger.warning(f"[DTH] Could not query live portal state: {ex}. Proceeding with offline validation.")

            # Step 3: Preflight Validation Pipeline
            self.current_operation = "Executing preflight validation"
            self._broadcast_status()
            items, validation_results = validate_channel_batch(
                raw_records,
                image_dir=image_dir,
                portal_categories=available_categories,
                portal_existing_channel_numbers=portal_nums,
                portal_existing_channel_names=portal_names
            )

            # Step 4: Process Channels
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

                # Handle portal duplicates (CREATE ONLY policy)
                if val_res.status == DthItemState.SKIPPED_DUPLICATE:
                    skipped_duplicates_count += 1
                    processed_count += 1
                    warn_msg = "; ".join(val_res.warnings) or "Duplicate channel already exists in portal"
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
                        "error_reason": warn_msg,
                        "verified_in_portal": True,
                        "started_at": ch_start,
                        "completed_at": time.strftime("%H:%M:%S")
                    }
                    save_dth_channel_result(rec)
                    channel_records.append(rec)
                    DthAuditLogger.log_event("CHANNEL_SKIPPED_DUPLICATE", run_id, channel_item.channel_number, {"warning": warn_msg})
                    continue

                # DRY RUN MODE: No browser mutations
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

                # LIVE MODE: Execute creation in portal
                self.current_operation = f"Creating channel {channel_item.channel_number}: '{channel_item.name}'"
                self._broadcast_status()

                item_state, reason, verified = await self.portal_controller.create_channel(channel_item)
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
