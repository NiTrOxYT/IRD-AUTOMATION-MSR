import os
import time
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable

from app.config import DOWNLOADS_DIR, REPORTS_DIR, SCREENSHOTS_DIR
from app.database.models import Site, Run, RunSiteResult
from app.database.db import (
    get_all_sites, get_site_by_id, create_run, update_run,
    save_run_site_result, get_all_settings, get_run_details
)
from app.automation.state_machine import SiteStatus
from app.launcher.launcher_manager import LauncherManager
from app.browser.browser_controller import BrowserController
from app.csv_analyzer.analyzer import analyze_action_point_csv
from app.reports.report_generator import export_reports
from app.tunneling import port_manager, putty_manager, tunnel_manager

logger = logging.getLogger("IRD_WorkflowRunner")

class WorkflowRunner:
    def __init__(self):
        self.is_running = False
        self.stop_requested = False
        self.current_run_id: Optional[int] = None
        self.current_site_id: Optional[int] = None
        self.current_site_name: str = ""
        self.current_status: str = SiteStatus.READY
        self.current_operation: str = "Idle"
        self.current_status_details: str = "Ready to start"
        self.progress_percentage: float = 0.0

        self.launcher_mgr = LauncherManager()  # Deprecated in Phase 4
        self.tunnel_mgr = tunnel_manager
        self.browser_ctrl: Optional[BrowserController] = None

        # Event callbacks for UI broadcast
        self.status_listeners: List[Callable[[Dict[str, Any]], None]] = []

    def add_status_listener(self, listener: Callable[[Dict[str, Any]], None]):
        if listener not in self.status_listeners:
            self.status_listeners.append(listener)

    def _broadcast_status(self, extra: Dict[str, Any] = None):
        payload = {
            "is_running": self.is_running,
            "run_id": self.current_run_id,
            "current_site_id": self.current_site_id,
            "current_site_name": self.current_site_name,
            "status": str(self.current_status),
            "operation": self.current_operation,
            "details": self.current_status_details,
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
        """Requests graceful stop of automation execution."""
        logger.info("Stop requested by user. Terminating automation after current task...")
        self.stop_requested = True
        self.current_operation = "Stopping..."
        self.current_status_details = "Automation stopped by user."
        self._broadcast_status()

    async def run_single_site_test(self, site_id: int) -> Dict[str, Any]:
        """
        Executes connection test for a single site:
        Launch launcher -> open webpage -> check availability -> login -> confirm Sync MyMenu -> finish.
        Does NOT execute Fetch, Process, or Download.
        """
        return await self.run_integration_test_stage(site_id, "dry_run")

    async def run_integration_test_stage(self, site_id: int, stage_name: str) -> Dict[str, Any]:
        """
        Executes atomic Integration Test stage for a single site (Requirement 2):
        Stages: 'backend_test', 'launcher', 'tunnel_webpage', 'login', 'sync_mymenu', 'fetch_menu', 'process_menu', 'download_csv', 'full_workflow'
        """
        site = get_site_by_id(site_id)
        if not site:
            return {"success": False, "stage": stage_name, "message": f"Site ID {site_id} not found."}

        clean_stage = stage_name.lower().strip()
        self.stop_requested = False
        logger.info(f"\n==========================================")
        logger.info(f"[{site.name}] RUNNING INTEGRATION TEST STAGE: {clean_stage.upper()}")
        logger.info(f"==========================================")

        # STAGE 0: DIAGNOSTIC BACKEND TEST
        if clean_stage in ("backend_test", "test_backend"):
            logger.info(f"[{site.name}] Step 1/3: Received request at backend endpoint.")
            await asyncio.sleep(0.5)
            logger.info(f"[{site.name}] Step 2/3: Validated site configuration and database record.")
            await asyncio.sleep(0.5)
            logger.info(f"[{site.name}] Step 3/3: Backend infrastructure diagnostic check completed.")
            return {
                "success": True,
                "stage": "backend_test",
                "site": site.name,
                "message": f"[{site.name}] Integration Test infrastructure working. Backend test stage passed.",
                "details": [
                    "Received request at backend endpoint /api/integration-test/run",
                    f"Validated site configuration for '{site.name}' (Launcher Button: '{site.launcher_button}')",
                    "Executed async 1-second diagnostic mock test",
                    "Status: PASS"
                ]
            }

        settings = get_all_settings()
        url = site.web_url or site.url or f"http://127.0.0.1:{site.local_port}"
        date_str = datetime.now().strftime("%Y-%m-%d")
        daily_downloads_dir = os.path.join(settings.get("downloads_dir", str(DOWNLOADS_DIR)), date_str)

        try:
            # STAGE: PACKAGE HEALTH CHECK
            if clean_stage in ("package_check", "package_health"):
                from app.diagnostics.package_validator import package_validator
                health = package_validator.validate_package_health()
                details = [f"{c['name']}: {c['status']} ({c['path']})" for c in health["checks"]]
                return {
                    "success": health["all_ok"],
                    "stage": "package_check",
                    "site": site.name,
                    "message": f"Package Health Status: {health['overall_status']}",
                    "details": details
                }

            # STAGE: PLINK EXECUTABLE CHECK
            if clean_stage in ("plink_check", "test_plink"):
                p_res = putty_manager.test_plink_executable()
                return {
                    "success": p_res["success"],
                    "stage": "plink_check",
                    "site": site.name,
                    "message": p_res["message"],
                    "details": [
                        f"Path: {p_res['path']}",
                        f"Version: {p_res['version']}",
                        f"Output: {p_res.get('details', '')}"
                    ]
                }

            # STAGE: PORT CHECK
            if clean_stage == "port_check":
                is_free = port_manager.verify_port_available(site.local_port)
                return {
                    "success": is_free,
                    "stage": "port_check",
                    "site": site.name,
                    "message": f"[{site.name}] Local port {site.local_port} is {'AVAILABLE' if is_free else 'OCCUPIED'}",
                    "details": [
                        f"Target Local Port: {site.local_port}",
                        f"Port Status: {'FREE' if is_free else 'IN USE / OCCUPIED'}"
                    ]
                }

            # STAGE: START PUTTY TUNNEL
            if clean_stage in ("start_tunnel", "putty_tunnel"):
                t_ok, t_msg, t_details = await self.tunnel_mgr.start_and_verify_tunnel(site, timeout_seconds=int(settings.get("tunnel_start_timeout", 30)))
                return {
                    "success": t_ok,
                    "stage": "start_tunnel",
                    "site": site.name,
                    "message": t_msg,
                    "details": t_details
                }

            # STAGE 1: LAUNCHER (DEPRECATED FALLBACK)
            if clean_stage == "launcher":
                logger.info(f"[{site.name}] Step 1/2: Looking for MSR ZMP PORTAL LAUNCHER window (DEPRECATED)...")
                logger.info(f"[{site.name}] Step 2/2: Checking '{site.launcher_button}' button in Launcher...")
                res = self.launcher_mgr.test_launcher_stage(site.launcher_button)
                logger.info(f"[{site.name}] Launcher stage result: {res['overall_status']}")
                return {
                    "success": res["overall_status"] == "PASS" or "PASS" in res["overall_status"],
                    "stage": "launcher",
                    "site": site.name,
                    "message": f"Launcher button test '{site.launcher_button}': {res['overall_status']}",
                    "details": res["details"]
                }

            # BROWSER BASED STAGES
            browser = BrowserController()
            # Stage: TUNNEL WEBPAGE
            if clean_stage in ("tunnel_webpage", "login", "sync_mymenu", "fetch_menu", "process_menu", "download_csv", "full_workflow", "dry_run"):
                if self.stop_requested:
                    return {"success": False, "stage": clean_stage, "site": site.name, "message": "Test stopped by user."}

                # Establish PuTTY / Plink Reverse Tunnel
                logger.info(f"[{site.name}] Step 1: Starting and verifying PuTTY SSH reverse tunnel on local port {site.local_port}...")
                t_ok, t_msg, t_details = await self.tunnel_mgr.start_and_verify_tunnel(site, timeout_seconds=int(settings.get("tunnel_start_timeout", 30)))
                if not t_ok:
                    return {"success": False, "stage": clean_stage, "site": site.name, "message": f"[{site.name}] Tunnel start failed: {t_msg}", "details": t_details}

                logger.info(f"[{site.name}] Step 2: Initializing Playwright browser controller...")
                await browser.initialize(headless=bool(settings.get("headless", False)))

                logger.info(f"[{site.name}] Step 3: Navigating to URL: {url} (Timeout: {settings.get('page_load_timeout', 120)}s)...")
                nav_ok = await browser.navigate_to_url(url, timeout_seconds=int(settings.get("page_load_timeout", 120)))

                if not nav_ok:
                    await browser.close()
                    return {"success": False, "stage": clean_stage, "site": site.name, "message": f"[{site.name}] Webpage unreachable at {url} within timeout."}

                if clean_stage == "tunnel_webpage":
                    await browser.capture_screenshot(site.name, "tunnel_webpage_test")
                    await browser.close()
                    return {"success": True, "stage": "tunnel_webpage", "site": site.name, "message": f"[{site.name}] Webpage reachable at {url}"}

            # Stage: LOGIN
            if clean_stage in ("login", "sync_mymenu", "fetch_menu", "process_menu", "download_csv", "full_workflow", "dry_run"):
                if self.stop_requested:
                    await browser.close()
                    return {"success": False, "stage": clean_stage, "site": site.name, "message": "Test stopped by user."}

                if site.idp_username and site.idp_password:
                    logger.info(f"[{site.name}] Step 4: Authenticating IDP user '{site.idp_username}'...")
                    login_ok, login_msg = await browser.login(site.idp_username, site.idp_password, timeout_seconds=int(settings.get("login_timeout", 60)))
                    if not login_ok:
                        await browser.capture_screenshot(site.name, "login_test_failed")
                        await browser.close()
                        return {"success": False, "stage": clean_stage, "site": site.name, "message": f"[{site.name}] Login failed: {login_msg}"}

                if clean_stage == "login":
                    await browser.capture_screenshot(site.name, "login_test_success")
                    await browser.close()
                    return {"success": True, "stage": "login", "site": site.name, "message": f"[{site.name}] IDP Login successful"}

            # Stage: SYNC MYMENU
            if clean_stage in ("sync_mymenu", "fetch_menu", "process_menu", "download_csv", "full_workflow", "dry_run"):
                if self.stop_requested:
                    await browser.close()
                    return {"success": False, "stage": clean_stage, "site": site.name, "message": "Test stopped by user."}

                logger.info(f"[{site.name}] Step 5: Navigating to Sync MyMenu page...")
                sync_ok, sync_msg = await browser.click_sync_mymenu(timeout_seconds=60)
                if not sync_ok:
                    await browser.capture_screenshot(site.name, "sync_mymenu_failed")
                    await browser.close()
                    return {"success": False, "stage": clean_stage, "site": site.name, "message": f"[{site.name}] Sync MyMenu failed: {sync_msg}"}

                if clean_stage in ("sync_mymenu", "dry_run"):
                    await browser.capture_screenshot(site.name, "sync_mymenu_success")
                    await browser.close()
                    return {"success": True, "stage": clean_stage, "site": site.name, "message": f"[{site.name}] Sync MyMenu page ready"}

            # Stage: FETCH MENU
            if clean_stage in ("fetch_menu", "process_menu", "download_csv", "full_workflow"):
                if self.stop_requested:
                    await browser.close()
                    return {"success": False, "stage": clean_stage, "site": site.name, "message": "Test stopped by user."}

                logger.info(f"[{site.name}] Step 6: Executing Fetch Menu operation...")
                fetch_ok, fetch_msg = await browser.click_fetch_menu(timeout_seconds=int(settings.get("fetch_menu_timeout", 600)))
                if not fetch_ok:
                    await browser.capture_screenshot(site.name, "fetch_menu_failed")
                    await browser.close()
                    return {"success": False, "stage": clean_stage, "site": site.name, "message": f"[{site.name}] Fetch Menu failed: {fetch_msg}"}

                if clean_stage == "fetch_menu":
                    await browser.capture_screenshot(site.name, "fetch_menu_success")
                    await browser.close()
                    return {"success": True, "stage": "fetch_menu", "site": site.name, "message": f"[{site.name}] Fetch Menu operation completed"}

            # Stage: PROCESS MENU
            if clean_stage in ("process_menu", "download_csv", "full_workflow"):
                if self.stop_requested:
                    await browser.close()
                    return {"success": False, "stage": clean_stage, "site": site.name, "message": "Test stopped by user."}

                logger.info(f"[{site.name}] Step 7: Processing latest menu...")
                proc_res = await browser.click_process_latest_menu(timeout_seconds=int(settings.get("process_menu_timeout", 600)))
                if not proc_res["success"]:
                    await browser.capture_screenshot(site.name, "process_menu_failed")
                    await browser.close()
                    return {"success": False, "stage": clean_stage, "site": site.name, "message": f"[{site.name}] Process Menu failed: {proc_res['error']}"}

                if clean_stage == "process_menu":
                    await browser.capture_screenshot(site.name, "process_menu_success")
                    await browser.close()
                    return {"success": True, "stage": "process_menu", "site": site.name, "message": f"[{site.name}] Process Latest Menu completed"}

            # Stage: DOWNLOAD CSV
            if clean_stage in ("download_csv", "full_workflow"):
                if self.stop_requested:
                    await browser.close()
                    return {"success": False, "stage": clean_stage, "site": site.name, "message": "Test stopped by user."}

                logger.info(f"[{site.name}] Step 8: Downloading Action Point CSV...")
                dl_ok, csv_path, dl_err = await browser.download_action_point_csv(daily_downloads_dir, site.name, timeout_seconds=int(settings.get("download_timeout", 120)))
                await browser.close()

                if not dl_ok or not csv_path:
                    return {"success": False, "stage": clean_stage, "site": site.name, "message": f"[{site.name}] CSV download failed: {dl_err}"}

                csv_res = analyze_action_point_csv(csv_path)
                return {
                    "success": True,
                    "stage": clean_stage,
                    "site": site.name,
                    "csv_path": csv_path,
                    "action_point_status": csv_res["action_point_status"],
                    "third_line": csv_res["third_line"],
                    "message": f"[{site.name}] Stage {clean_stage} completed: {csv_res['action_point_status']} (Line 3: '{csv_res['third_line']}')"
                }

            await browser.close()
            return {"success": True, "stage": clean_stage, "site": site.name, "message": f"[{site.name}] Stage test finished"}

        except Exception as e:
            try:
                if 'browser' in locals() and browser:
                    await browser.close()
            except Exception:
                pass
            import traceback
            tb = traceback.format_exc()
            logger.error(f"[{site.name}] Integration test stage '{clean_stage}' failed with exception: {e}\n{tb}")
            return {
                "success": False,
                "stage": clean_stage,
                "site": site.name,
                "message": f"[{site.name}] Integration test stage exception: {str(e)}",
                "traceback": tb,
                "details": [f"Exception: {str(e)}"]
            }


    async def start_batch_sync(self, selected_site_ids: List[int] = None, dry_run: bool = False, resume_run_id: int = None) -> int:
        """
        Executes daily multi-site sequential synchronization workflow.
        Returns run_id.
        """
        if self.is_running:
            raise RuntimeError("Automation is already running.")

        self.is_running = True
        self.stop_requested = False

        settings = get_all_settings()
        date_str = datetime.now().strftime("%Y-%m-%d")
        daily_downloads_dir = os.path.join(settings.get("downloads_dir", str(DOWNLOADS_DIR)), date_str)
        os.makedirs(daily_downloads_dir, exist_ok=True)

        # Determine target sites
        all_sites = get_all_sites()
        if selected_site_ids:
            target_sites = [s for s in all_sites if s.id in selected_site_ids and s.enabled]
        else:
            target_sites = [s for s in all_sites if s.enabled]

        if not target_sites:
            self.is_running = False
            raise ValueError("No enabled sites selected to process.")

        # Create or resume run record
        if resume_run_id:
            run_details = get_run_details(resume_run_id)
            if run_details and run_details["run"]:
                self.current_run_id = resume_run_id
                completed_site_ids = {r["site_id"] for r in run_details["results"] if r["status"] == "COMPLETED"}
                target_sites = [s for s in target_sites if s.id not in completed_site_ids]
                logger.info(f"Resuming run #{self.current_run_id}. Remaining sites to process: {len(target_sites)}")
            else:
                resume_run_id = None

        if not resume_run_id:
            run_obj = Run(
                run_date=date_str,
                start_time=datetime.now().strftime("%H:%M:%S"),
                status="IN_PROGRESS",
                total_sites=len(target_sites),
                completed_sites=0,
                action_points_count=0,
                no_action_points_count=0,
                failed_sites_count=0,
                log_path=os.path.join(settings.get("reports_dir", str(REPORTS_DIR)), f"{date_str}.log")
            )
            self.current_run_id = create_run(run_obj)
            logger.info(f"Created new batch run #{self.current_run_id} for {len(target_sites)} sites.")

        # Initialize counters
        completed_count = 0
        action_point_count = 0
        no_action_count = 0
        failed_count = 0

        total_target = len(target_sites)

        # Iterate sites sequentially
        for idx, site in enumerate(target_sites, start=1):
            if self.stop_requested:
                logger.info("Batch run stopped by user request.")
                break

            self.current_site_id = site.id
            self.current_site_name = site.name
            self.progress_percentage = round(((idx - 1) / total_target) * 100, 1)

            logger.info(f"\n==========================================")
            logger.info(f"[{idx}/{total_target}] STARTING SITE: {site.name}")
            logger.info(f"==========================================")

            result_record = RunSiteResult(
                run_id=self.current_run_id,
                site_id=site.id,
                site_name=site.name,
                status="IN_PROGRESS",
                start_time=datetime.now().strftime("%H:%M:%S")
            )
            result_id = save_run_site_result(result_record)
            result_record.id = result_id

            site_start_t = time.time()

            # Execute single site workflow
            site_result = await self._process_single_site_workflow(site, result_record, dry_run, settings, daily_downloads_dir)

            site_end_t = time.time()
            site_duration = site_end_t - site_start_t

            site_result.end_time = datetime.now().strftime("%H:%M:%S")
            site_result.duration_seconds = site_duration
            save_run_site_result(site_result)

            if site_result.status == SiteStatus.FAILED:
                failed_count += 1
            else:
                completed_count += 1
                if site_result.action_point_status == "ACTION POINT FOUND":
                    action_point_count += 1
                elif site_result.action_point_status == "NO ACTION POINT":
                    no_action_count += 1

            # Update overall run progress
            run_obj = Run(
                id=self.current_run_id,
                end_time=datetime.now().strftime("%H:%M:%S") if (idx == total_target or self.stop_requested) else None,
                status="STOPPED" if self.stop_requested else ("COMPLETED" if idx == total_target else "IN_PROGRESS"),
                total_sites=total_target,
                completed_sites=completed_count,
                action_points_count=action_point_count,
                no_action_points_count=no_action_count,
                failed_sites_count=failed_count
            )
            update_run(run_obj)

            self.progress_percentage = round((idx / total_target) * 100, 1)
            self._broadcast_status()

        # Batch Run Finished
        self.is_running = False
        self.current_site_id = None
        self.current_site_name = ""
        self.current_status = SiteStatus.COMPLETED if not self.stop_requested else SiteStatus.STOPPED
        self.current_operation = "Batch Completed" if not self.stop_requested else "Stopped"
        self.current_status_details = f"Processed {completed_count}/{total_target} sites. ({action_point_count} Action Points, {no_action_count} No Action Point, {failed_count} Failed)"

        # Generate Reports
        run_data = get_run_details(self.current_run_id)
        if run_data:
            export_reports(run_data, settings.get("reports_dir", str(REPORTS_DIR)))

        self._broadcast_status({"reports_ready": True})
        logger.info(f"\nDAILY IRD SYNC FINISHED. Status: {self.current_status_details}\n")
        return self.current_run_id

    async def _process_single_site_workflow(self, site: Site, result_rec: RunSiteResult, dry_run: bool, settings: Dict[str, Any], download_dir: str) -> RunSiteResult:
        """Executes full single-site workflow with VM crash recovery and retries."""
        browser = BrowserController()
        max_retries = int(settings.get("max_process_retries", 3))
        rec_timeout = int(settings.get("service_recovery_timeout", 600))
        retry_interval = int(settings.get("retry_interval", 10))

        try:
            # 1. Launch MSR ZMP PORTAL LAUNCHER button
            self.current_status = SiteStatus.TUNNELING
            self.current_operation = f"Launching tunnel for {site.name}"
            self.current_status_details = f"Clicking launcher button '{site.launcher_button}'"
            self._broadcast_status()

            self.launcher_mgr.click_site_button(site.launcher_button)
            await asyncio.sleep(3.0)

            # 2. Initialize Browser
            self.current_status = SiteStatus.WAITING_FOR_WEBPAGE
            self.current_operation = "Opening browser"
            self.current_status_details = "Initializing Playwright instance"
            self._broadcast_status()

            await browser.initialize(headless=bool(settings.get("headless", False)))

            # 3. Wait for webpage availability
            url = site.url or f"https://{site.name.lower().replace(' ', '')}.mymenu.internal"
            self.current_status_details = f"Navigating to {url}"
            self._broadcast_status()

            nav_ok = await browser.navigate_to_url(url, timeout_seconds=int(settings.get("page_load_timeout", 120)))
            if not nav_ok:
                result_rec.status = SiteStatus.FAILED
                result_rec.action_point_status = "FAILED"
                result_rec.error_message = f"Webpage unreachable at {url}"
                await browser.close()
                return result_rec

            # 4. Login
            if site.idp_username and site.idp_password:
                self.current_status = SiteStatus.LOGIN
                self.current_operation = "Logging into IDP"
                self.current_status_details = f"User: {site.idp_username}"
                self._broadcast_status()

                login_ok, login_msg = await browser.login(site.idp_username, site.idp_password, timeout_seconds=int(settings.get("login_timeout", 60)))
                if not login_ok:
                    result_rec.status = SiteStatus.FAILED
                    result_rec.action_point_status = "FAILED"
                    result_rec.error_message = login_msg
                    await browser.capture_screenshot(site.name, "login_failed")
                    await browser.close()
                    return result_rec

            # 5. Click Sync MyMenu
            self.current_status = SiteStatus.SYNC_MYMENU
            self.current_operation = "Navigating to Sync MyMenu"
            self.current_status_details = "Clicking Sync MyMenu navigation link"
            self._broadcast_status()

            sync_ok, sync_msg = await browser.click_sync_mymenu(timeout_seconds=60)
            if not sync_ok:
                result_rec.status = SiteStatus.FAILED
                result_rec.action_point_status = "FAILED"
                result_rec.error_message = sync_msg
                await browser.capture_screenshot(site.name, "sync_mymenu_failed")
                await browser.close()
                return result_rec

            # If Dry Run, stop here safely!
            if dry_run:
                logger.info(f"DRY RUN completed successfully for site '{site.name}'.")
                result_rec.status = SiteStatus.COMPLETED
                result_rec.action_point_status = "NO ACTION POINT"
                result_rec.third_line_text = "[DRY RUN PASSED]"
                await browser.close()
                return result_rec

            # 6. Click Fetch Menu
            self.current_status = SiteStatus.FETCHING_MENU
            self.current_operation = "Fetching Menu"
            self.current_status_details = "Clicking Fetch Menu and awaiting completion"
            self._broadcast_status()

            fetch_ok, fetch_msg = await browser.click_fetch_menu(timeout_seconds=int(settings.get("fetch_menu_timeout", 600)))
            if not fetch_ok:
                result_rec.status = SiteStatus.FAILED
                result_rec.action_point_status = "FAILED"
                result_rec.error_message = fetch_msg
                await browser.capture_screenshot(site.name, "fetch_menu_failed")
                await browser.close()
                return result_rec

            # 7. Click Process Latest Menu with VM / FNB Service Crash Handling!
            process_success = False
            process_attempts = 0

            while process_attempts < max_retries:
                process_attempts += 1
                result_rec.retry_count = process_attempts - 1

                self.current_status = SiteStatus.PROCESSING_MENU if process_attempts == 1 else SiteStatus.RETRYING
                self.current_operation = f"Processing Latest Menu (Attempt {process_attempts}/{max_retries})"
                self.current_status_details = "Executing Process Latest Menu"
                self._broadcast_status()

                proc_res = await browser.click_process_latest_menu(timeout_seconds=int(settings.get("process_menu_timeout", 600)))

                if proc_res["success"]:
                    process_success = True
                    logger.info(f"Process Latest Menu succeeded on attempt #{process_attempts}")
                    break

                # Check if FNB service/VM crashed!
                if proc_res["crashed"]:
                    logger.warning(f"FNB Service/VM crashed on attempt #{process_attempts}. Entering VM Recovery wait loop...")

                    self.current_status = SiteStatus.WAITING_FOR_SERVICE
                    self.current_operation = f"FNB Service Crashed (Attempt {process_attempts}/{max_retries})"
                    self.current_status_details = f"Waiting up to {rec_timeout // 60} minutes for VM service to recover..."
                    self._broadcast_status()

                    # Recovery Loop: poll service health every retry_interval seconds
                    rec_start = time.time()
                    service_recovered = False

                    while time.time() - rec_start < rec_timeout:
                        if self.stop_requested:
                            break

                        await asyncio.sleep(retry_interval)
                        elapsed_secs = int(time.time() - rec_start)
                        self.current_status_details = f"VM Recovery check ({elapsed_secs}s / {rec_timeout}s). Checking service availability..."
                        self._broadcast_status()

                        # Check service availability
                        avail = await browser.check_service_availability(url)
                        if avail:
                            logger.info(f"FNB VM/Service recovered after {elapsed_secs} seconds!")
                            service_recovered = True
                            self.current_status_details = f"Service recovered after {elapsed_secs}s! Re-navigating to Sync MyMenu..."
                            self._broadcast_status()

                            # Re-navigate and prepare to retry Process Latest Menu
                            await browser.navigate_to_url(url)
                            if site.idp_username and site.idp_password:
                                await browser.login(site.idp_username, site.idp_password)
                            await browser.click_sync_mymenu()
                            break

                    if not service_recovered:
                        logger.error(f"FNB Service failed to recover within {rec_timeout} seconds.")
                        result_rec.error_message = f"FNB Service VM crash recovery timed out ({rec_timeout}s)"
                        break

            if not process_success:
                result_rec.status = SiteStatus.FAILED
                result_rec.action_point_status = "FAILED"
                if not result_rec.error_message:
                    result_rec.error_message = f"Process Latest Menu failed after {max_retries} attempts."
                await browser.capture_screenshot(site.name, "process_menu_failed")
                await browser.close()
                return result_rec

            # 8. Download Action Point CSV
            self.current_status = SiteStatus.DOWNLOADING_CSV
            self.current_operation = "Downloading Action Point CSV"
            self.current_status_details = "Clicking Download Action Point"
            self._broadcast_status()

            dl_ok, csv_path, dl_err = await browser.download_action_point_csv(
                download_dir=download_dir,
                site_name=site.name,
                timeout_seconds=int(settings.get("download_timeout", 120))
            )

            await browser.close()

            if not dl_ok or not csv_path:
                result_rec.status = SiteStatus.FAILED
                result_rec.action_point_status = "FAILED"
                result_rec.error_message = f"CSV Download failed: {dl_err}"
                return result_rec

            # 9. CSV Analysis (Line 3 check)
            self.current_status = SiteStatus.CHECKING_CSV
            self.current_operation = "Inspecting downloaded CSV"
            self.current_status_details = f"Analyzing first 3 lines of {os.path.basename(csv_path)}"
            self._broadcast_status()

            csv_res = analyze_action_point_csv(csv_path)

            result_rec.status = SiteStatus.COMPLETED
            result_rec.action_point_status = csv_res["action_point_status"]
            result_rec.csv_path = csv_path
            result_rec.third_line_text = csv_res["third_line"]

            if csv_res["action_point_status"] == "ACTION POINT FOUND":
                self.current_status = SiteStatus.ACTION_POINT_FOUND
            else:
                self.current_status = SiteStatus.NO_ACTION_POINT

            self.current_status_details = f"Site completed: {csv_res['action_point_status']} (Line 3: '{csv_res['third_line']}')"
            self._broadcast_status()

            logger.info(f"SITE FINISHED: {site.name} -> {result_rec.action_point_status} | CSV: {csv_path}")
            return result_rec

        except Exception as e:
            logger.error(f"Unhandled exception during workflow for site '{site.name}': {e}", exc_info=True)
            result_rec.status = SiteStatus.FAILED
            result_rec.action_point_status = "FAILED"
            result_rec.error_message = f"Unhandled exception: {str(e)}"
            if browser:
                await browser.close()
            return result_rec

# Global Workflow Runner Singleton
workflow_runner = WorkflowRunner()
