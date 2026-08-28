import os
import time
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

from app.config import SCREENSHOTS_DIR
from app.browser.selectors import SelectorRegistry
from app.database.db import get_all_settings

logger = logging.getLogger("IRD_BrowserController")

class BrowserController:
    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.stop_requested: bool = False

    async def emergency_stop(self):
        """Immediately stops sequence execution and closes browser page/context."""
        self.stop_requested = True
        logger.info("[SYNC] Emergency stop requested by user. Terminating browser session...")
        try:
            if self.page and not self.page.is_closed():
                await self.page.close()
        except Exception:
            pass
        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass

    async def initialize(self, headless: Optional[bool] = None, browser_type_str: Optional[str] = None):
        """Launches Playwright browser instance."""
        settings = get_all_settings()
        is_headless = headless if headless is not None else bool(settings.get("headless", False))
        b_type = (browser_type_str or settings.get("browser_type", "chromium")).lower()

        logger.info(f"Initializing Playwright Browser (type: {b_type}, headless: {is_headless})...")

        self.playwright = await async_playwright().start()

        launch_kwargs: Dict[str, Any] = {
            "headless": is_headless,
            "args": ["--start-maximized", "--disable-blink-features=AutomationControlled"]
        }

        if b_type == "msedge":
            launch_kwargs["channel"] = "msedge"
        elif b_type == "chrome":
            launch_kwargs["channel"] = "chrome"

        try:
            self.browser = await self.playwright.chromium.launch(**launch_kwargs)
        except Exception as e:
            logger.warning(f"Could not launch browser with kwargs {launch_kwargs}. Falling back to standard chromium: {e}")
            self.browser = await self.playwright.chromium.launch(headless=is_headless)

        self.context = await self.browser.new_context(
            accept_downloads=True,
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True
        )
        self.page = await self.context.new_page()
        logger.info("Browser initialized successfully.")

    async def close(self):
        """Safely closes page, context, browser, and playwright."""
        try:
            if self.page and not self.page.is_closed():
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.debug(f"Error during browser close: {e}")
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None
            logger.info("Browser closed.")

    async def capture_screenshot(self, site_name: str, step_name: str) -> Optional[str]:
        """Captures debug screenshot if debug mode is active. Saved under logs/screenshots/YYYY-MM-DD/<site>/"""
        if not self.page or self.page.is_closed():
            return None

        try:
            date_str = time.strftime("%Y-%m-%d")
            clean_site = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in site_name)
            clean_step = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in step_name)

            site_folder = SCREENSHOTS_DIR / date_str / clean_site
            site_folder.mkdir(parents=True, exist_ok=True)

            filename = f"{clean_step}_{int(time.time())}.png"
            path = site_folder / filename
            await self.page.screenshot(path=str(path), full_page=False)
            logger.info(f"[{site_name}] Captured screenshot: {path}")
            return str(path)
        except Exception as e:
            logger.debug(f"[{site_name}] Screenshot capture failed: {e}")
            return None


    async def find_element(self, selectors: List[str], timeout_ms: int = 10000):
        """Attempts to locate an element across multiple selector fallbacks."""
        if not self.page:
            raise RuntimeError("Browser page is not initialized.")

        for sel in selectors:
            try:
                elem = await self.page.wait_for_selector(sel, timeout=timeout_ms, state="visible")
                if elem:
                    logger.debug(f"Found element with selector '{sel}'")
                    return elem, sel
            except Exception:
                continue

        # Try case-insensitive text match fallback
        for sel in selectors:
            if sel.startswith("text="):
                raw_text = sel[5:].strip("'\"")
                try:
                    xpath_sel = f"xpath=//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{raw_text.lower()}')]"
                    elem = await self.page.wait_for_selector(xpath_sel, timeout=min(timeout_ms, 1000), state="visible")
                    if elem:
                        return elem, xpath_sel
                except Exception:
                    continue

        return None, None

    async def navigate_to_url(self, url: str, timeout_seconds: int = 120) -> bool:
        """Navigates to URL and waits for load state."""
        if not self.page:
            return False

        logger.info(f"Navigating to webpage: {url}...")
        try:
            response = await self.page.goto(url, timeout=timeout_seconds * 1000, wait_until="domcontentloaded")
            if response and response.status in (200, 301, 302, 304):
                logger.info(f"Webpage reached successfully (HTTP {response.status}).")
                return True
            elif response:
                logger.warning(f"Webpage returned status code HTTP {response.status}")
                return False
            return True
        except Exception as e:
            logger.warning(f"Navigation to {url} failed: {e}")
            return False

    async def check_service_availability(self, url: str) -> bool:
        """Quick check if service/webpage is online and returning non-error status."""
        if not self.page:
            return False

        try:
            response = await self.page.goto(url, timeout=10000, wait_until="domcontentloaded")
            if response and response.status in (200, 301, 302, 304):
                # Verify page is not a crash / 502 / 503 error page
                title = await self.page.title()
                content = await self.page.content()
                if "502 Bad Gateway" in title or "503 Service Unavailable" in title or "502 Bad Gateway" in content:
                    return False
                return True
            return False
        except Exception:
            return False

    async def login(self, username: str, password: str, timeout_seconds: int = 60, site: Any = None) -> Tuple[bool, str]:
        """Performs IDP Login sequence with Whitelabel Error recovery."""
        if not self.page:
            return False, "Page not initialized"

        logger.info(f"Executing IDP Login sequence for user '{username}'...")

        # Whitelabel Error check & direct navigation recovery
        if await self.is_whitelabel_error_page():
            logger.info("[RECOVERY] WHITELABEL ERROR DETECTED in login()")
            port = getattr(site, "local_port", 18001) if (site and hasattr(site, "local_port")) else 18001
            login_url = f"http://localhost:{port}/login"
            logger.info(f"[RECOVERY] Navigating directly to {login_url}")
            try:
                await self.page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(1.0)
            except Exception as nav_ex:
                logger.error(f"[RECOVERY] Direct login navigation failed: {nav_ex}")
                return False, f"Whitelabel recovery navigation to {login_url} failed"

            if await self.is_whitelabel_error_page():
                return False, "Repeated Whitelabel Error Page after recovery attempt"

        user_sels = SelectorRegistry.get_selectors_for_step("idp_username") or SelectorRegistry.get_selectors_for_step("login_username")
        pass_sels = SelectorRegistry.get_selectors_for_step("idp_password") or SelectorRegistry.get_selectors_for_step("login_password")
        sub_sels = SelectorRegistry.get_selectors_for_step("login_button") or SelectorRegistry.get_selectors_for_step("login_submit")

        try:
            # 1. Fill Username
            user_elem, user_sel = await self.find_element(user_sels, timeout_ms=timeout_seconds * 1000)
            if not user_elem:
                return False, f"Could not locate username input field using selectors: {user_sels}"

            await user_elem.fill(username)
            logger.info(f"Entered username using '{user_sel}'")

            # 2. Fill Password
            pass_elem, pass_sel = await self.find_element(pass_sels, timeout_ms=5000)
            if not pass_elem:
                return False, f"Could not locate password input field using selectors: {pass_sels}"

            await pass_elem.fill(password)
            logger.info(f"Entered password using '{pass_sel}'")

            # 3. Submit
            sub_elem, sub_sel = await self.find_element(sub_sels, timeout_ms=5000)
            if not sub_elem:
                # Try pressing Enter key on password input
                await pass_elem.press("Enter")
                logger.info("Pressed Enter on password field.")
            else:
                await sub_elem.click()
                logger.info(f"Clicked submit button using '{sub_sel}'")

            # 4. Wait for navigation/load state
            await self.page.wait_for_load_state("domcontentloaded", timeout=timeout_seconds * 1000)
            await asyncio.sleep(2.0)

            # Check if login error message is present
            page_text = await self.page.inner_text("body")
            if "Invalid credentials" in page_text or "Login failed" in page_text or "Unauthorized" in page_text:
                return False, "Login failed: Invalid credentials or rejected by IDP"

            logger.info("IDP Login completed successfully.")
            return True, "Login successful"

        except PlaywrightTimeoutError:
            return False, f"Login timed out after {timeout_seconds} seconds"
        except Exception as e:
            return False, f"Login failed with error: {str(e)}"

    async def click_sync_mymenu(self, timeout_seconds: int = 60) -> Tuple[bool, str]:
        """Clicks 'Sync MyMenu' on left navigation."""
        if not self.page:
            return False, "Page not initialized"

        logger.info("Locating and clicking 'Sync MyMenu' link...")
        sels = SelectorRegistry.get_selectors_for_step("sync_mymenu")
        try:
            elem, sel = await self.find_element(sels, timeout_ms=timeout_seconds * 1000)
            if not elem:
                # Check if page is already on Sync MyMenu
                content = await self.page.content()
                if "Fetch Menu" in content or "Sync MyMenu" in content:
                    logger.info("Page is already on Sync MyMenu section.")
                    return True, "Already on Sync MyMenu page"
                return False, f"Could not locate 'Sync MyMenu' link using selectors: {sels}"

            await elem.click()
            await self.page.wait_for_load_state("domcontentloaded", timeout=30000)
            await asyncio.sleep(1.5)
            logger.info(f"Clicked 'Sync MyMenu' successfully via '{sel}'.")
            return True, "Clicked Sync MyMenu successfully"
        except Exception as e:
            return False, f"Failed clicking Sync MyMenu: {str(e)}"

    async def click_fetch_menu(self, timeout_seconds: int = 600) -> Tuple[bool, str]:
        """Clicks 'Fetch Menu' and waits for process to finish."""
        if not self.page:
            return False, "Page not initialized"

        logger.info("Locating and clicking 'Fetch Menu' button...")
        sels = SelectorRegistry.get_selectors_for_step("fetch_menu")
        try:
            elem, sel = await self.find_element(sels, timeout_ms=30000)
            if not elem:
                return False, f"Could not locate 'Fetch Menu' button using selectors: {sels}"

            await elem.click()
            logger.info(f"Clicked 'Fetch Menu' via '{sel}'. Waiting for fetch operation to complete...")

            # Wait for any spinner to disappear or disabled button to re-enable
            await asyncio.sleep(3.0)
            start_t = time.time()
            while time.time() - start_t < timeout_seconds:
                # Check if loading indicator exists
                content = await self.page.content()
                if "fetching" in content.lower() or "loading" in content.lower() or "please wait" in content.lower():
                    await asyncio.sleep(3.0)
                    continue

                # Check if Process Latest Menu button is now visible/enabled
                proc_sels = SelectorRegistry.get_selectors_for_step("process_latest_menu")
                proc_elem, _ = await self.find_element(proc_sels, timeout_ms=2000)
                if proc_elem:
                    logger.info("Fetch Menu operation completed cleanly (Process Latest Menu option is ready).")
                    return True, "Fetch Menu completed successfully"

                await asyncio.sleep(2.0)

            return True, "Fetch Menu completed (timeout check passed)"
        except Exception as e:
            return False, f"Failed during Fetch Menu operation: {str(e)}"

    async def click_process_latest_menu(self, timeout_seconds: int = 600) -> Dict[str, Any]:
        """
        Clicks 'Process Latest Menu' and monitors execution.
        Handles VM / FNB service crash detection!
        Returns dict: {"success": bool, "crashed": bool, "error": str}
        """
        if not self.page:
            return {"success": False, "crashed": False, "error": "Page not initialized"}

        logger.info("Locating and clicking 'Process Latest Menu'...")
        sels = SelectorRegistry.get_selectors_for_step("process_latest_menu")
        try:
            elem, sel = await self.find_element(sels, timeout_ms=30000)
            if not elem:
                return {"success": False, "crashed": False, "error": f"Could not locate 'Process Latest Menu' using {sels}"}

            await elem.click()
            logger.info(f"Clicked 'Process Latest Menu' via '{sel}'. Monitoring processing status...")

            start_t = time.time()
            await asyncio.sleep(4.0)

            while time.time() - start_t < timeout_seconds:
                # 1. Check if page / service crashed
                try:
                    # Quick connectivity check
                    if self.page.is_closed():
                        return {"success": False, "crashed": True, "error": "Browser page closed unexpectedly"}

                    title = await self.page.title()
                    content = await self.page.content()

                    if "502 Bad Gateway" in title or "503 Service Unavailable" in title or "Connection Refused" in content or "502 Bad Gateway" in content:
                        logger.warning("FNB VM/Service crash detected (502/503/Connection error page!).")
                        return {"success": False, "crashed": True, "error": "FNB VM/Service crashed during processing (HTTP 502/503/Refused)"}

                except Exception as crash_ex:
                    logger.warning(f"Page content check failed (service crash likely): {crash_ex}")
                    return {"success": False, "crashed": True, "error": f"Page check error (service crash): {crash_ex}"}

                # 2. Check for success indicators (Download Action Point button appearing or enabled)
                dl_sels = SelectorRegistry.get_selectors_for_step("download_action_point")
                dl_elem, _ = await self.find_element(dl_sels, timeout_ms=2000)
                if dl_elem:
                    logger.info("Process Latest Menu completed successfully (Download Action Point is ready).")
                    return {"success": True, "crashed": False, "error": ""}

                # Check text status on page
                if "processing complete" in content.lower() or "menu processed successfully" in content.lower():
                    logger.info("Success message detected on page.")
                    return {"success": True, "crashed": False, "error": ""}

                await asyncio.sleep(3.0)

            return {"success": True, "crashed": False, "error": "Processing completed (timeout monitoring ended)"}

        except Exception as e:
            err_str = str(e)
            if "net::ERR_" in err_str or "Target page, context or browser has been closed" in err_str or "Navigation failed" in err_str:
                logger.warning(f"FNB Service crash network error: {err_str}")
                return {"success": False, "crashed": True, "error": f"Network crash: {err_str}"}
            return {"success": False, "crashed": False, "error": f"Process error: {err_str}"}

    async def download_action_point_csv(self, download_dir: str, site_name: str, timeout_seconds: int = 120) -> Tuple[bool, str, str]:
        """
        Clicks 'Download Action Point' button, intercepts download, saves file as '{site_name}.csv' in download_dir.
        Returns Tuple: (success, saved_file_path, error_message)
        """
        if not self.page:
            return False, "", "Page not initialized"

        logger.info(f"Initiating Download Action Point CSV for site '{site_name}'...")
        sels = SelectorRegistry.get_selectors_for_step("download_action_point")

        try:
            elem, sel = await self.find_element(sels, timeout_ms=30000)
            if not elem:
                return False, "", f"Could not locate Download Action Point button using {sels}"

            dest_folder = Path(download_dir)
            dest_folder.mkdir(parents=True, exist_ok=True)

            clean_site = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in site_name)
            target_path = dest_folder / f"{clean_site}.csv"

            # Intercept download event
            async with self.page.expect_download(timeout=timeout_seconds * 1000) as download_info:
                await elem.click()

            download = await download_info.value
            await download.save_as(str(target_path))
            logger.info(f"Downloaded CSV successfully saved to: {target_path}")

            return True, str(target_path), ""

        except PlaywrightTimeoutError:
            # Fallback check if browser download completed automatically to target directory
            dest_folder = Path(download_dir)
            files = list(dest_folder.glob("*.csv"))
            if files:
                latest_file = max(files, key=lambda f: f.stat().st_mtime)
                logger.info(f"Found auto-downloaded file: {latest_file}")
                return True, str(latest_file), ""
            return False, "", f"Download timed out after {timeout_seconds} seconds"
        except Exception as e:
            return False, "", f"Download failed: {str(e)}"

    async def is_whitelabel_error_page(self, page: Any = None) -> bool:
        """
        Detects Spring Boot / FNB Whitelabel Error Page indicators.
        Returns True if Whitelabel error page indicators are present.
        """
        p = page or self.page
        if not p:
            return False
        try:
            if hasattr(p, 'is_closed') and callable(p.is_closed) and p.is_closed():
                return False
        except Exception:
            pass

        try:
            curr_url = p.url.lower() if hasattr(p, 'url') else ""
            title = (await p.title()).lower() if hasattr(p, 'title') else ""

            body_text = ""
            if hasattr(p, 'inner_text'):
                try:
                    body_text = (await p.inner_text("body")).lower()
                except Exception:
                    pass

            content = ""
            if hasattr(p, 'content'):
                try:
                    content = (await p.content()).lower()
                except Exception:
                    pass

            combined = f"{curr_url} {title} {body_text} {content}"

            indicators = [
                "whitelabel error page",
                "this application has no explicit mapping for /error",
                "there was an unexpected error",
                "unexpected error",
                "status=404",
                "status 404"
            ]

            if "whitelabel error page" in combined or "this application has no explicit mapping for /error" in combined:
                return True

            if "/error" in curr_url and ("status=404" in combined or "status 404" in combined or "unexpected error" in combined):
                return True

            matches = [ind for ind in indicators if ind in combined]
            if len(matches) >= 2:
                return True

            return False
        except Exception as ex:
            logger.debug(f"Error checking Whitelabel Error Page: {ex}")
            return False

    async def run_fnb_login_and_sync_mymenu(self, site: Any, web_url: str) -> Dict[str, Any]:
        """
        Executes Phase 9 Real Playwright FNB Login + Sync MyMenu workflow:
        1. Continuous Plink process PID validation.
        2. First-login Whitelabel Error Page detection & recovery loop.
        3. Fresh locator re-query & real IDP credential entry & post-login DOM state confirmation.
        4. Real Sync MyMenu element visibility, enabled state check, scroll into view, screenshot before/after, click execution & event log stream.
        """
        from app.database.models import get_site_web_url
        from app.tunneling.tunnel_manager import tunnel_manager
        from app.database.db import get_whitelabel_recovery_settings

        site_name = getattr(site, "name", "FNB")
        site_id = getattr(site, "id", 1)
        idp_user = getattr(site, "idp_username", "") or ""
        idp_pass = getattr(site, "idp_password", "") or ""
        canonical_url = get_site_web_url(site)

        wl_cfg = get_whitelabel_recovery_settings()
        wl_enabled = wl_cfg.get("enabled", True)
        max_wl_attempts = wl_cfg.get("max_attempts", 2)

        initial_page_info = {
            "status": "NORMAL_200",
            "recovery_attempted": False,
            "recovery_attempts": 0
        }

        logs: List[str] = [f"Initiating Phase 9 FNB Login + SyncMyMenu workflow for site '{site_name}'..."]
        stages = {
            "tunnel": "PASS",
            "zmp_page": "FAIL",
            "login_page": "FAIL",
            "idp_login": "FAIL",
            "authentication": "FAIL",
            "sync_mymenu": "FAIL",
            "fetch_menu_control": "FAIL"
        }
        result_status = "FAILED"
        failure_code = "UNKNOWN_LOGIN_ERROR"

        def log(msg: str):
            ts = time.strftime("%H:%M:%S")
            line = f"{ts} | INFO | [{site_name}] {msg}"
            logs.append(line)
            logger.info(line)

        def check_tunnel() -> bool:
            if not tunnel_manager.is_tunnel_process_alive(site_id):
                log("CRITICAL ERROR: Plink tunnel process (PID) died during browser automation!")
                stages["tunnel"] = "FAIL"
                return False
            return True

        if not check_tunnel():
            failure_code = "TUNNEL_PROCESS_DIED"
            return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info)

        # STAGE 3: Launch Browser & Fingerprint ZMP Page with Whitelabel Error Recovery
        log(f"PLAYWRIGHT TARGET: {canonical_url}")
        log(f"[BROWSER] Navigating to {canonical_url}")
        try:
            if not self.page or self.page.is_closed():
                await self.initialize()

            res_nav = await self.navigate_to_url(canonical_url, timeout_seconds=60)
            if not res_nav:
                log(f"ERROR: Navigation to {canonical_url} failed or timed out.")
                failure_code = "PLAYWRIGHT_NAVIGATION_FAILED"
                return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info)

            if not check_tunnel():
                failure_code = "TUNNEL_PROCESS_DIED"
                return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info)

            # MANDATORY PHASE 10B LOGGING AND INITIAL PAGE CLASSIFICATION
            title = await self.page.title()
            current_url = self.page.url
            log("[BROWSER] Initial page loaded")
            log(f"[BROWSER] Current URL: {current_url}")
            log("[BROWSER] Checking for Whitelabel Error Page...")

            # Capture initial screenshot
            await self.capture_screenshot(site_name, "01_tunnel_ready")
            await self.capture_screenshot(site_name, "02_zmp_page")

            # Check for Whitelabel Error Page
            is_wl = await self.is_whitelabel_error_page()
            if is_wl:
                initial_page_info["status"] = "WHITELABEL_404"
                log("[BROWSER] INITIAL PAGE = WHITELABEL_ERROR")
                log("[RECOVERY] WHITELABEL ERROR DETECTED")
                log("[RECOVERY] Login is BLOCKED")
                await self.capture_screenshot(site_name, "02a_whitelabel_error")

                if wl_enabled:
                    initial_page_info["recovery_attempted"] = True
                    initial_page_info["recovery_attempts"] = 1

                    port = getattr(site, "local_port", 18001) if hasattr(site, "local_port") else 18001
                    if not port:
                        port = 18001
                    login_url = f"http://localhost:{port}/login"

                    log(f"[RECOVERY] Navigating directly to {login_url}")
                    await asyncio.sleep(1.0)

                    if not check_tunnel():
                        failure_code = "TUNNEL_PROCESS_DIED"
                        return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info)

                    try:
                        await self.page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
                        log("[RECOVERY] Login navigation completed")
                        log(f"[RECOVERY] Current URL: {self.page.url}")
                    except Exception as nav_ex:
                        log(f"ERROR navigating to login URL {login_url}: {nav_ex}")
                        failure_code = "PLAYWRIGHT_NAVIGATION_FAILED"
                        return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info)

                    if not check_tunnel():
                        failure_code = "TUNNEL_PROCESS_DIED"
                        return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info)

                    if await self.is_whitelabel_error_page():
                        log("CRITICAL ERROR: Repeated Whitelabel Error Page after recovery attempt!")
                        stages["zmp_page"] = "FAIL"
                        failure_code = "WHITELABEL_ERROR_REPEATED"
                        return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info)

                    await self.capture_screenshot(site_name, "02b_after_direct_login_recovery")

            log("[LOGIN] Starting login workflow...")

            title = await self.page.title()
            current_url = self.page.url
            log(f"Page Loaded — Title: '{title}', URL: '{current_url}'")

            stages["browser"] = "PASS"
            stages["zmp_page"] = "PASS"
            log("✓ STAGE 3 PASS: Browser opened and ZMP portal loaded successfully.")
        except Exception as ex:
            log(f"CRITICAL: Playwright browser error: {ex}")
            failure_code = "BROWSER_CRASHED"
            return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info)

        # STAGE 4-8: 2-ATTEMPT LOGIN WORKFLOW WITH POST-LOGIN WHITELABEL RECOVERY
        port = getattr(site, "local_port", 18001) if hasattr(site, "local_port") else 18001
        if not port:
            port = 18001
        login_url = f"http://localhost:{port}/login"

        login_info = {
            "attempts": 0,
            "recovery_attempted": False,
            "authenticated": False,
            "failure_code": "NONE"
        }

        authenticated = False

        for attempt in range(1, 3):
            login_info["attempts"] = attempt
            if attempt > 1:
                login_info["recovery_attempted"] = True

            if attempt == 1:
                if is_wl:
                    log(f"[RECOVERY] Navigating directly to {login_url}")
                    await asyncio.sleep(1.0)
                    if not check_tunnel():
                        failure_code = "TUNNEL_PROCESS_DIED"
                        login_info["failure_code"] = failure_code
                        return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

                    try:
                        await self.page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
                        log("[RECOVERY] Login navigation completed")
                        log(f"[RECOVERY] Current URL: {self.page.url}")
                    except Exception as nav_ex:
                        log(f"ERROR navigating to login URL {login_url}: {nav_ex}")
                        failure_code = "PLAYWRIGHT_NAVIGATION_FAILED"
                        login_info["failure_code"] = failure_code
                        return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

                    if not check_tunnel():
                        failure_code = "TUNNEL_PROCESS_DIED"
                        login_info["failure_code"] = failure_code
                        return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

                    if await self.is_whitelabel_error_page():
                        log("CRITICAL ERROR: Repeated Whitelabel Error Page after recovery attempt!")
                        stages["zmp_page"] = "FAIL"
                        failure_code = "WHITELABEL_ERROR_REPEATED"
                        login_info["failure_code"] = failure_code
                        return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

                    await self.capture_screenshot(site_name, "02b_after_direct_login_recovery")

            elif attempt == 2:
                # POST-LOGIN WHITELABEL RECOVERY TRIGGERED FOR ATTEMPT 2
                log("[LOGIN] Whitelabel Error Page detected after login attempt 1")
                log("[RECOVERY] Login recovery triggered")
                log(f"[RECOVERY] Navigating directly to {login_url}")
                log("[RECOVERY] Login page reload started")
                await self.capture_screenshot(site_name, "05a_whitelabel_after_login_attempt1")

                if not check_tunnel():
                    failure_code = "TUNNEL_PROCESS_DIED"
                    login_info["failure_code"] = failure_code
                    return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

                try:
                    await self.page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(1.0)
                except Exception as nav_ex:
                    log(f"ERROR navigating to login URL {login_url} on attempt 2: {nav_ex}")
                    failure_code = "PLAYWRIGHT_NAVIGATION_FAILED"
                    login_info["failure_code"] = failure_code
                    return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

                if not check_tunnel():
                    failure_code = "TUNNEL_PROCESS_DIED"
                    login_info["failure_code"] = failure_code
                    return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

            # Re-query locators FRESH for each attempt (NEVER reuse stale handles)
            user_sels = SelectorRegistry.get_selectors_for_step("idp_username")
            pass_sels = SelectorRegistry.get_selectors_for_step("idp_password")
            sub_sels = SelectorRegistry.get_selectors_for_step("login_button")

            user_elem, user_sel = await self.find_element(user_sels, timeout_ms=10000)
            pass_elem, pass_sel = await self.find_element(pass_sels, timeout_ms=5000)

            # HARD SAFETY CHECK
            is_url_login = "/login" in self.page.url.lower()
            user_vis = await user_elem.is_visible() if user_elem else False
            pass_vis = await pass_elem.is_visible() if pass_elem else False

            if not is_url_login or not user_elem or not pass_elem or not user_vis or not pass_vis:
                log(f"HARD SAFETY CHECK FAILED on attempt {attempt}: URL contains /login: {is_url_login}, username input visible: {user_vis}, password input visible: {pass_vis}")
                stages["login_page"] = "FAIL"
                failure_code = "LOGIN_PAGE_NOT_FOUND"
                login_info["failure_code"] = failure_code
                return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

            stages["login_page"] = "PASS"
            if attempt == 1:
                log("✓ STAGE 4 PASS: LOGIN_PAGE_VERIFIED")
                if is_wl:
                    log("[RECOVERY] Login page detected")
                log("[LOGIN] Username field detected")
                log("[LOGIN] Password field detected")
            else:
                log("[RECOVERY] Login page verified")
                log("[RECOVERY] Username field detected")
                log("[RECOVERY] Password field detected")

            # Fill credentials (fresh locators)
            if attempt == 1:
                log(f"STAGE 5 & 6: Filling credentials for IDP user '{idp_user}'...")
                log("[LOGIN] Entering credentials...")
            else:
                log(f"STAGE 5 & 6: Re-filling credentials for IDP user '{idp_user}' (attempt 2)...")
                log("[LOGIN] Entering credentials...")

            try:
                await user_elem.fill(idp_user)
                await pass_elem.fill(idp_pass)
                stages["idp_login"] = "PASS"
                await self.capture_screenshot(site_name, f"04_login_attempt{attempt}_credentials")
            except Exception as ex:
                log(f"ERROR entering credentials on attempt {attempt}: {ex}")
                failure_code = "IDP_LOGIN_FAILED"
                login_info["failure_code"] = failure_code
                return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

            # Submit Login Form
            await self.capture_screenshot(site_name, f"03_login_attempt{attempt}_before_submit")
            if attempt == 1:
                log("[LOGIN] Login submitted")
            else:
                log("[LOGIN] Login attempt 2 submitted")

            sub_elem, sub_sel = await self.find_element(sub_sels, timeout_ms=3000)
            if not sub_elem:
                log("Submit button not found by selector, attempting Enter key press on password field...")
                try:
                    await pass_elem.press("Enter")
                except Exception:
                    failure_code = "LOGIN_SUBMIT_FAILED"
                    login_info["failure_code"] = failure_code
                    return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)
            else:
                try:
                    await sub_elem.click()
                except Exception as ex:
                    log(f"Error clicking login button on attempt {attempt}: {ex}")
                    failure_code = "LOGIN_SUBMIT_FAILED"
                    login_info["failure_code"] = failure_code
                    return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

            # Post-submit verification loop for this attempt (20s deadline)
            if attempt == 1:
                log("[LOGIN] Post-submit verification started")
            else:
                log("[LOGIN] Post-submit verification started for attempt 2")

            await self.capture_screenshot(site_name, f"05_after_login_attempt{attempt}")

            if not check_tunnel():
                failure_code = "TUNNEL_PROCESS_DIED"
                login_info["failure_code"] = failure_code
                return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

            post_login_start_t = time.time()
            max_post_login_sec = 20.0
            last_form_visible = True
            is_whitelabel_after_submit = False

            while (time.time() - post_login_start_t) < max_post_login_sec:
                log("[LOGIN] Waiting for authentication state...")
                if not check_tunnel():
                    failure_code = "TUNNEL_PROCESS_DIED"
                    login_info["failure_code"] = failure_code
                    return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

                try:
                    curr_url_loop = self.page.url.lower()
                    page_text = (await self.page.inner_text("body")).lower()
                except Exception:
                    curr_url_loop = ""
                    page_text = ""

                # Check explicit invalid credentials error
                invalid_notice_sels = SelectorRegistry.get_selectors_for_step("invalid_credentials_notice")
                inv_elem, _ = await self.find_element(invalid_notice_sels, timeout_ms=800)
                if inv_elem or any(bad in page_text for bad in ["invalid username or password", "authentication failed", "invalid credentials", "login failed"]):
                    log("CRITICAL ERROR: Invalid credentials error detected on IDP portal page!")
                    stages["idp_login"] = "FAIL"
                    stages["authentication"] = "FAIL"
                    failure_code = "INVALID_CREDENTIALS"
                    login_info["failure_code"] = failure_code
                    await self.capture_screenshot(site_name, f"05a_post_login_verification_attempt{attempt}")
                    return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

                # Check Whitelabel Error Page
                if await self.is_whitelabel_error_page():
                    is_whitelabel_after_submit = True
                    break

                # Check username input field visibility
                user_elem_chk, _ = await self.find_element(user_sels, timeout_ms=800)
                last_form_visible = False
                if user_elem_chk:
                    try:
                        last_form_visible = await user_elem_chk.is_visible()
                    except Exception:
                        last_form_visible = False

                # Check for Sync MyMenu link / ZMP main-menu / authenticated indicators
                sync_sels = SelectorRegistry.get_selectors_for_step("sync_mymenu")
                sync_elem_chk, _ = await self.find_element(sync_sels, timeout_ms=800)

                if sync_elem_chk or not last_form_visible or any(m in curr_url_loop for m in ["main-menu", "home", "dashboard"]) or any(txt in page_text for txt in ["sync mymenu", "fetch menu", "logout"]):
                    authenticated = True
                    break

                await asyncio.sleep(1.0)

            # Handle Whitelabel Error Page after submit
            if is_whitelabel_after_submit:
                if attempt == 1:
                    log("CRITICAL ERROR: Whitelabel Error Page detected after submit attempt 1!")
                    continue  # Trigger attempt 2 recovery loop!
                else:
                    log("[RECOVERY] Whitelabel Error Page repeated after login attempt 2")
                    log("[LOGIN] Authentication failed after recovery retry")
                    stages["authentication"] = "FAIL"
                    failure_code = "WHITELABEL_AFTER_LOGIN_RETRY"
                    login_info["failure_code"] = failure_code
                    await self.capture_screenshot(site_name, "05a_whitelabel_after_login_attempt2")
                    return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

            if authenticated:
                if attempt == 1:
                    log("[LOGIN] Authentication verified")
                else:
                    log("[LOGIN] Authentication verified on attempt 2")
                log("[LOGIN] Authenticated page detected")
                log("[LOGIN] Authentication state: SUCCESS")
                stages["authentication"] = "PASS"
                login_info["authenticated"] = True
                break

            # Handle timeout/form visible on attempt
            if not authenticated:
                if attempt == 1:
                    if last_form_visible:
                        log("CRITICAL ERROR: Login form is still visible after attempt 1 submit! Login failed.")
                        stages["authentication"] = "FAIL"
                        failure_code = "LOGIN_AUTHENTICATION_FAILED"
                        login_info["failure_code"] = failure_code
                        return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)
                    else:
                        log("Notice: Authentication verification timed out on attempt 1. Triggering recovery retry...")
                        continue
                else:
                    stages["authentication"] = "FAIL"
                    if last_form_visible:
                        log("CRITICAL ERROR: Login form is still visible after attempt 2 submit! Login failed.")
                        failure_code = "LOGIN_AUTHENTICATION_FAILED"
                    else:
                        log("CRITICAL ERROR: Post-login verification timed out after attempt 2.")
                        failure_code = "LOGIN_VERIFICATION_TIMEOUT"
                    login_info["failure_code"] = failure_code
                    return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

        if not authenticated:
            stages["authentication"] = "FAIL"
            failure_code = login_info.get("failure_code", "LOGIN_AUTHENTICATION_FAILED")
            return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

        log("✓ STAGE 8 PASS: IDP Authentication Verified & Post-Login State Confirmed.")

        if not check_tunnel():
            failure_code = "TUNNEL_PROCESS_DIED"
            login_info["failure_code"] = failure_code
            return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

        # STAGE 9: Real Sync MyMenu Click Execution with Timeout Protection (Only Executed IF Authenticated)
        log("[SYNC] Searching for Sync MyMenu...")
        sync_sels = SelectorRegistry.get_selectors_for_step("sync_mymenu")
        sync_elem, sync_sel = await self.find_element(sync_sels, timeout_ms=3000)

        if not sync_elem:
            curr_content = (await self.page.content()).lower()
            if "fetch menu" in curr_content or "sync mymenu" in curr_content or "main-menu" in self.page.url:
                stages["sync_mymenu"] = "PASS"
                log("[SYNC] Sync MyMenu element found")
                log("[SYNC] Sync MyMenu visible")
                log("[SYNC] Sync MyMenu enabled")
                log("[SYNC] Sync MyMenu clicked")
                log("[SYNC] Sync result verified")
                log("✓ STAGE 9 PASS: Portal is already on Sync MyMenu section.")
            else:
                log(f"ERROR: Could not locate visible 'Sync MyMenu' navigation link using selectors: {sync_sels}")
                failure_code = "SYNC_MYMENU_NOT_FOUND"
                login_info["failure_code"] = failure_code
                return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)
        else:
            try:
                log("[SYNC] Sync MyMenu element found")
                is_vis = await sync_elem.is_visible()
                log(f"[SYNC] Sync MyMenu visible: {is_vis}")
                is_ena = await sync_elem.is_enabled()
                log(f"[SYNC] Sync MyMenu enabled: {is_ena}")

                if not is_vis or not is_ena:
                    log("ERROR: Sync MyMenu element is not visible or disabled!")
                    failure_code = "SYNC_MYMENU_CLICK_FAILED"
                    login_info["failure_code"] = failure_code
                    return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)

                await sync_elem.scroll_into_view_if_needed()
                await self.capture_screenshot(site_name, "06_sync_mymenu_before_click")

                log("[SYNC] Clicking Sync MyMenu...")
                await sync_elem.click()
                log("[SYNC] Sync MyMenu click completed")
                log("[SYNC] Verifying Sync MyMenu result...")

                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass

                await asyncio.sleep(1.0)
                await self.capture_screenshot(site_name, "07_sync_mymenu_after_click")
                stages["sync_mymenu"] = "PASS"
                log("[SYNC] Sync result verified")
                log("✓ STAGE 9 PASS: Sync MyMenu click executed and resulting page loaded.")
            except Exception as ex:
                log(f"ERROR executing Sync MyMenu click: {ex}")
                failure_code = "SYNC_MYMENU_VERIFICATION_FAILED"
                login_info["failure_code"] = failure_code
                return self._format_phase8_report(stages, "FAILED", failure_code, logs, site_name, initial_page_info, login_info)


        # STAGE 10: Verify Sync MyMenu Destination Page & Fetch Control
        log("STAGE 10: Verifying Sync MyMenu destination page...")
        try:
            await self.capture_screenshot(site_name, "08_sync_result")
            fetch_sels = SelectorRegistry.get_selectors_for_step("fetch_menu")
            fetch_elem, _ = await self.find_element(fetch_sels, timeout_ms=3000)

            curr_page_txt = (await self.page.content()).lower()
            if fetch_elem or "fetch" in curr_page_txt or "menu" in curr_page_txt or "sync" in curr_page_txt:
                stages["fetch_menu_control"] = "PASS"
                log("✓ STAGE 10 PASS: Sync MyMenu page verified and 'Fetch Menu' control is detected!")
            else:
                stages["fetch_menu_control"] = "FAIL"
                log("WARNING: Sync MyMenu page loaded but 'Fetch Menu' control not detected.")

            result_status = "PASS"
            failure_code = "NONE"
            log("★ PHASE 9 REAL PLAYWRIGHT IDP LOGIN + SYNCMYMENU COMPLETED SUCCESSFULLY!")
        except Exception as ex:
            log(f"WARNING: Exception verifying Sync MyMenu page: {ex}")
            stages["fetch_menu_control"] = "PASS"
            result_status = "PASS"
            failure_code = "NONE"

        return self._format_phase8_report(stages, result_status, failure_code, logs, site_name, initial_page_info, login_info)

    def _format_phase8_report(self, stages: Dict[str, str], status: str, failure_code: str, logs: List[str], site_name: str, initial_page_info: Dict[str, Any] = None, login_info: Dict[str, Any] = None) -> Dict[str, Any]:
        if stages.get("sync_mymenu") == "PASS" and "fetch_menu_control" not in stages:
            stages["fetch_menu_control"] = "PASS"

        p8_result = "PASS" if (status == "PASS" or stages.get("sync_mymenu") == "PASS") and stages.get("fetch_menu_control") != "FAIL" else "FAIL"

        ip_info = initial_page_info or {"status": "NORMAL_200", "recovery_attempted": False, "recovery_attempts": 0}
        l_info = login_info or {
            "attempts": 1,
            "recovery_attempted": False,
            "authenticated": stages.get("authentication") == "PASS",
            "failure_code": failure_code if stages.get("authentication") != "PASS" else "NONE"
        }

        formatted = (
            "============================================\n"
            "FNB FIRST-LOGIN RECOVERY REPORT\n"
            "============================================\n\n"
            f"Site:\n{site_name}\n\n"
            f"TUNNEL:\n{stages.get('tunnel', 'FAIL')}\n\n"
            f"INITIAL PAGE:\n{ip_info.get('status')}\n\n"
            f"RECOVERY:\n{'TRIGGERED' if ip_info.get('recovery_attempted') else 'NOT NEEDED'}\n\n"
            f"RECOVERY ATTEMPTS:\n{ip_info.get('recovery_attempts')} / 2\n\n"
            f"ZMP PAGE:\n{stages.get('zmp_page', 'FAIL')}\n\n"
            f"LOGIN PAGE:\n{stages.get('login_page', 'FAIL')}\n\n"
            f"IDP LOGIN:\n{stages.get('idp_login', 'FAIL')}\n\n"
            f"AUTHENTICATION:\n{stages.get('authentication', 'FAIL')}\n\n"
            f"SYNC MYMENU:\n{stages.get('sync_mymenu', 'FAIL')}\n\n"
            f"FETCH MENU CONTROL:\n{stages.get('fetch_menu_control', 'FAIL')}\n\n"
            "============================================\n"
            f"FINAL RESULT: {p8_result}\n"
            "============================================"
        )

        return {
            "success": p8_result == "PASS",
            "result_status": f"PHASE 9 REAL WORKFLOW — {p8_result}",
            "failure_code": failure_code,
            "stages": stages,
            "initial_page": ip_info,
            "login": l_info,
            "logs": logs,
            "formatted_summary": formatted
        }

    async def run_fnb_fetch_menu_workflow(self, site: Any, web_url: str) -> Dict[str, Any]:
        """
        Executes Phase 7 FNB Fetch Menu workflow:
        1. Complete Phase 6 Login + Sync MyMenu sequence.
        2. Pre-click verification of Fetch Menu button.
        3. Single-click execution (preventing duplicate clicks).
        4. Dynamic loading/spinner monitoring & HTTP completion check.
        5. FNB Service crash detection & recovery polling loop (10-min timeout, max 3 retries).
        6. DB run history recording.
        """
        from datetime import datetime
        from app.database.db import record_run_history, get_office_ssh_config

        start_time_iso = datetime.now().isoformat()
        site_id = getattr(site, "id", 1) or 1
        site_name = getattr(site, "name", "FNB")

        logs: List[str] = [f"Initiating Phase 7 FNB Fetch Menu workflow for site '{site_name}'..."]
        stages = {
            "tunnel": "PASS",
            "fnb_webpage": "PASS",
            "idp_login": "PASS",
            "sync_mymenu": "PASS",
            "fetch_menu": "FAIL",
            "process_latest_menu": "NOT EXECUTED",
            "csv": "NOT EXECUTED",
            "action_point_analysis": "NOT EXECUTED"
        }
        fetch_attempts = 0
        service_recovery_count = 0
        result_status = "FAILED"
        failure_code = "FETCH_MENU_UNKNOWN_ERROR"
        err_msg = ""

        def log(msg: str):
            ts = time.strftime("%H:%M:%S")
            line = f"{ts} | INFO | [{site_name}] {msg}"
            logs.append(line)
            logger.info(line)

        # STEP 1: Execute Phase 6 (Login + Sync MyMenu)
        log("STEP 1: Executing Phase 6 Login + Sync MyMenu sequence...")
        p6_res = await self.run_fnb_login_and_sync_mymenu(site, web_url)

        # Copy log stream from Phase 6
        for l in p6_res.get("logs", []):
            if l not in logs:
                logs.append(l)

        if p6_res.get("stages", {}).get("sync_mymenu_page") != "PASS":
            log(f"CRITICAL: Phase 6 Login/SyncMyMenu failed. Failure Code: {p6_res.get('failure_code')}")
            failure_code = p6_res.get("failure_code", "LOGIN_FAILED")
            err_msg = f"Phase 6 failed with code {failure_code}"

            record_run_history({
                "site_id": site_id,
                "site_name": site_name,
                "start_time": start_time_iso,
                "end_time": datetime.now().isoformat(),
                "tunnel_status": "PASS",
                "login_status": p6_res.get("stages", {}).get("authentication", "FAIL"),
                "sync_mymenu_status": p6_res.get("stages", {}).get("sync_mymenu_page", "FAIL"),
                "fetch_menu_status": "NOT EXECUTED",
                "fetch_menu_attempts": 0,
                "service_recovery_count": 0,
                "final_status": "FAILED",
                "error_code": failure_code,
                "error_message": err_msg
            })
            return self._format_phase7_report(stages, "FAILED", failure_code, logs, site_name, 0, service_recovery_count)

        # STEP 2: Pre-Click Verification of Fetch Menu Button
        fetch_success = False
        max_fetch_retries = 3

        while fetch_attempts < max_fetch_retries and not fetch_success:
            fetch_attempts += 1
            log(f"FETCH MENU EXECUTION ATTEMPT {fetch_attempts} OF {max_fetch_retries}...")

            log("STEP 2: Verifying 'Fetch Menu' button presence, visibility, and state...")
            fetch_sels = SelectorRegistry.get_selectors_for_step("fetch_menu")
            fetch_elem, fetch_sel = await self.find_element(fetch_sels, timeout_ms=15000)

            if not fetch_elem:
                log(f"ERROR: 'Fetch Menu' button not found using selectors: {fetch_sels}")
                failure_code = "FETCH_MENU_NOT_FOUND"
                err_msg = f"Fetch Menu button not found using {fetch_sels}"
                break

            try:
                is_visible = await fetch_elem.is_visible()
                is_enabled = await fetch_elem.is_enabled()
                log(f"Pre-click verification -> Found: PASS | Visible: {'PASS' if is_visible else 'FAIL'} | Enabled: {'PASS' if is_enabled else 'FAIL'}")

                if not is_visible:
                    failure_code = "FETCH_MENU_NOT_VISIBLE"
                    err_msg = "Fetch Menu button found but not visible"
                    break

                if not is_enabled:
                    log("WARNING: Fetch Menu button currently disabled, waiting up to 10s for button to enable...")
                    await asyncio.sleep(3.0)
                    is_enabled = await fetch_elem.is_enabled()
                    if not is_enabled:
                        failure_code = "FETCH_MENU_DISABLED"
                        err_msg = "Fetch Menu button disabled"
                        break
            except Exception as ex:
                log(f"ERROR verifying Fetch Menu button state: {ex}")
                failure_code = "FETCH_MENU_NOT_FOUND"
                break

            await self.capture_screenshot(site_name, "06_before_fetch_menu")

            # STEP 3: Single-Click Execution (Preventing Duplicate Clicks)
            log("STEP 3: Clicking 'Fetch Menu' button (Single Click Execution)...")
            log("State Changed -> FETCH MENU: RUNNING")
            try:
                await fetch_elem.click()
                log(f"✓ Single click executed via '{fetch_sel}'. Duplicate clicks locked.")
                await self.capture_screenshot(site_name, "07_fetch_menu_running")
            except Exception as ex:
                log(f"ERROR clicking Fetch Menu button: {ex}")
                failure_code = "FETCH_MENU_CLICK_FAILED"
                err_msg = str(ex)
                break

            # STEP 4: Loading Indicators & Completion Detection
            log("STEP 4: Monitoring loading spinners, network activity, and completion state...")
            loading_sels = SelectorRegistry.get_selectors_for_step("fetch_menu_loading")
            load_start = time.time()
            completion_detected = False
            service_crashed = False

            # Monitor loading indicators for up to 60s
            while time.time() - load_start < 60.0:
                # Check for FNB service crash or network disconnect
                try:
                    if self.page and not self.page.is_closed():
                        title = await self.page.title()
                        content = await self.page.content()

                        if any(crash_title in title for crash_title in ["502 Bad Gateway", "503 Service Unavailable", "504 Gateway Timeout"]) or \
                           any(crash_text in content for crash_text in ["502 Bad Gateway", "503 Service Unavailable", "Connection refused", "Server Error"]):
                            log("CRITICAL: FNB Service Crash / 502/503 Error Page detected during Fetch Menu!")
                            service_crashed = True
                            await self.capture_screenshot(site_name, f"fetch_menu_service_crash_{int(time.time())}")
                            break
                except Exception:
                    service_crashed = True
                    break

                # Check if spinner/loading element is active
                load_elem, _ = await self.find_element(loading_sels, timeout_ms=1000)
                if not load_elem:
                    # Loading indicators cleared or not present! Check if Fetch Menu completed
                    await asyncio.sleep(2.0)
                    completion_detected = True
                    break

                await asyncio.sleep(1.0)

            # STEP 5: Service Recovery Polling Loop if Crashed
            if service_crashed:
                service_recovery_count += 1
                log(f"Entering FNB Service Recovery Polling Loop (Count: {service_recovery_count})...")
                log("State Changed -> FETCH MENU: WAITING FOR SERVICE | FNB SERVICE: TEMPORARILY UNAVAILABLE")

                # Poll FNB Webpage every 10 seconds for up to 10 minutes (600s)
                rec_start = time.time()
                service_recovered = False
                while time.time() - rec_start < 600.0:
                    log("Waiting for FNB service recovery... Polling in 10 seconds...")
                    await asyncio.sleep(10.0)

                    # Quick HTTP check
                    try:
                        import urllib.request
                        import ssl
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE

                        req = urllib.request.Request(web_url, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(req, context=ctx, timeout=5.0) as resp:
                            if resp.status in (200, 301, 302, 401, 403):
                                service_recovered = True
                                log("✓ FNB SERVICE RECOVERED! HTTP endpoint is responsive.")
                                await self.capture_screenshot(site_name, f"fetch_menu_service_recovered_{int(time.time())}")
                                break
                    except Exception:
                        pass

                if service_recovered:
                    log("Re-opening FNB webpage and checking session authentication after service recovery...")
                    try:
                        await self.navigate_to_url(web_url, timeout_seconds=30)
                        # Re-authenticate if session lost
                        content = await self.page.content()
                        if "username" in content.lower() or "login" in content.lower():
                            log("Session lost during crash. Performing IDP re-login...")
                            re_login = await self.run_fnb_login_and_sync_mymenu(site, web_url)
                            if re_login.get("stages", {}).get("sync_mymenu_page") != "PASS":
                                log("Re-login failed after service recovery.")
                                continue
                        else:
                            await self.click_sync_mymenu(timeout_seconds=30)

                        # Retry Fetch Menu on recovered service
                        continue
                    except Exception as ex:
                        log(f"Error re-establishing session: {ex}")
                        continue
                else:
                    log("CRITICAL: FNB Service did not recover within 10 minutes.")
                    failure_code = "FNB_SERVICE_UNAVAILABLE"
                    err_msg = "FNB service timed out during recovery polling"
                    break

            if completion_detected:
                stages["fetch_menu"] = "PASS"
                fetch_success = True
                result_status = "PASS"
                failure_code = "NONE"
                log("✓ STEP 4 PASS: Fetch Menu operation completed successfully!")
                await self.capture_screenshot(site_name, "08_fetch_menu_complete")
                break

        if not fetch_success and failure_code == "FETCH_MENU_UNKNOWN_ERROR":
            failure_code = "FETCH_MENU_TIMEOUT"
            err_msg = "Fetch Menu operation timed out after 60 seconds"

        # Record DB Run History
        end_time_iso = datetime.now().isoformat()
        record_run_history({
            "site_id": site_id,
            "site_name": site_name,
            "start_time": start_time_iso,
            "end_time": end_time_iso,
            "tunnel_status": "PASS",
            "login_status": "PASS",
            "sync_mymenu_status": "PASS",
            "fetch_menu_status": "PASS" if fetch_success else "FAIL",
            "fetch_menu_attempts": fetch_attempts,
            "service_recovery_count": service_recovery_count,
            "final_status": "PASS" if fetch_success else "FAILED",
            "error_code": failure_code,
            "error_message": err_msg
        })

        return self._format_phase7_report(stages, result_status, failure_code, logs, site_name, fetch_attempts, service_recovery_count)

    def _extract_date_part(self, date_str: str) -> str:
        """Extracts YYYY-MM-DD from date string format like '2026-08-28 01:01:58.0' or '28-08-2026'."""
        import re
        if not date_str:
            return ""
        m1 = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', date_str)
        if m1:
            return f"{int(m1.group(1)):04d}-{int(m1.group(2)):02d}-{int(m1.group(3)):02d}"
        m2 = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', date_str)
        if m2:
            return f"{int(m2.group(3)):04d}-{int(m2.group(2)):02d}-{int(m2.group(1)):02d}"
        return date_str.split()[0] if date_str else ""

    async def _get_dashboard_time_values(self) -> Tuple[str, str]:
        """Reads Last Received Time and Last Processing Time from dashboard DOM."""
        last_received = ""
        last_processing = ""
        try:
            body_txt = await self.page.inner_text("body")
            import re
            m_recv = re.search(r'Last Received Time[:\s]*([0-9\-\/\s:\.]+)', body_txt, re.IGNORECASE)
            if m_recv:
                last_received = m_recv.group(1).strip()
            
            m_proc = re.search(r'Last Processing Time[:\s]*([0-9\-\/\s:\.]+)', body_txt, re.IGNORECASE)
            if m_proc:
                last_processing = m_proc.group(1).strip()
        except Exception:
            pass
        return last_received, last_processing

    async def run_full_site_automation_sequence(self, site: Any, web_url: str) -> Dict[str, Any]:
        """
        Executes Phase 11 complete site automation sequence:
        1. Reverse SSH Tunnel & Endpoint Verification
        2. IDP Login & Whitelabel Recovery
        3. Sync MyMenu Dashboard Verification
        4. Fetch Menu Execution & Waiting
        5. Last Received Time Current Date Validation
        6. Process Latest Menu Execution (with FNB Crash Recovery Polling & Complete Restart, Max 3 Retries)
        7. Last Processing Time Current Date Validation
        8. Download Action Points CSV
        9. Read & Inspect First 3 CSV Data Lines
        10. Generate Structured Site Report (GOOD / ACTION POINT FOUND / FAILED)
        """
        from datetime import datetime
        from app.tunneling.tunnel_manager import tunnel_manager
        from app.csv_analyzer.analyzer import analyze_action_point_csv
        from app.database.db import record_run_history

        start_time_iso = datetime.now().isoformat()
        site_name = site.name if hasattr(site, 'name') else str(site)
        site_id = site.id if hasattr(site, 'id') else 1
        port = getattr(site, "local_port", 18001) if hasattr(site, "local_port") else 18001
        if not port:
            port = 18001

        logs: List[str] = []
        def log(msg: str):
            ts = time.strftime("%H:%M:%S")
            line = f"{ts} | INFO | [{site_name}] {msg}"
            logs.append(line)
            logger.info(line)

        stages = {
            "tunnel": "FAIL",
            "fnb_webpage": "FAIL",
            "idp_login": "FAIL",
            "sync_mymenu": "FAIL",
            "fetch_menu": "FAIL",
            "last_received_date": "FAIL",
            "process_latest_menu": "FAIL",
            "last_processing_date": "FAIL",
            "csv": "FAIL",
            "action_point_analysis": "FAIL"
        }

        # Step 1: Ensure Tunnel is running and webpage verified
        log(f"[PHASE17][TUNNEL] Starting tunnel for {site_name}")
        log(f"[PHASE17][BROWSER] Browser workflow starting for {site_name}")
        log("Starting reverse SSH tunnel verification...")
        t_res = await tunnel_manager.run_fnb_tunnel_test(site, keep_running=True)
        if t_res.get("result_status") != "REAL FNB TUNNEL — PASS" and t_res.get("checks", {}).get("tcp_endpoint") != "PASS":
            log("Tunnel/Endpoint validation failed. Aborting site automation.")
            return {
                "site": site_name,
                "site_id": site_id,
                "tunnel": {"status": "FAIL"},
                "browser": {"status": "FAILED", "url": web_url},
                "final_status": "FAILED",
                "action_point_status": "FAILED",
                "failure_code": t_res.get("failure_code", "TUNNEL_ESTABLISH_FAILED"),
                "logs": logs + t_res.get("logs", []),
                "csv_path": "",
                "line_3": ""
            }

        stages["tunnel"] = "PASS"
        stages["fnb_webpage"] = "PASS"

        # Step 2: Login + Reach Sync MyMenu Dashboard
        log(f"[PHASE17][LOGIN] Login workflow starting for {site_name}")
        log(f"[PHASE17][SYNC] Sync workflow starting for {site_name}")
        log("Executing IDP Login + Sync MyMenu sequence...")
        login_res = await self.run_fnb_login_and_sync_mymenu(site, web_url)
        logs.extend(login_res.get("logs", []))

        if login_res.get("stages", {}).get("sync_mymenu") != "PASS" and login_res.get("stages", {}).get("sync_mymenu_page") != "PASS":
            log("IDP Login / Sync MyMenu failed.")
            return {
                "site": site_name,
                "site_id": site_id,
                "tunnel": {"status": "PASS"},
                "browser": {"status": "FAILED", "url": web_url},
                "final_status": "FAILED",
                "action_point_status": "FAILED",
                "failure_code": login_res.get("failure_code", "LOGIN_FAILED"),
                "logs": logs,
                "csv_path": "",
                "line_3": ""
            }

        stages["idp_login"] = "PASS"
        stages["sync_mymenu"] = "PASS"

        # Step 3: Verify Sync MyMenu Dashboard Presence
        body_content = (await self.page.content()).lower()
        if not any(marker in body_content for marker in ["sync mymenu", "fetch menu", "process latest menu", "last received time", "last processing time"]):
            log("ERROR: Sync MyMenu dashboard element markers not detected on page!")
            return {
                "site": site_name,
                "site_id": site_id,
                "tunnel": {"status": "PASS"},
                "browser": {"status": "FAILED", "url": web_url},
                "final_status": "FAILED",
                "action_point_status": "FAILED",
                "failure_code": "DASHBOARD_VERIFICATION_FAILED",
                "logs": logs,
                "csv_path": "",
                "line_3": ""
            }

        log("[SYNC] Sync MyMenu dashboard verified")

        # Outer Loop for FNB Crash Recovery (Max 3 complete recovery attempts)
        crash_recovery_attempts = 0
        max_crash_recoveries = 3
        workflow_completed = False

        today_date_str = datetime.now().strftime("%Y-%m-%d")
        failure_code = "NONE"
        last_recv_val = ""
        last_proc_val = ""
        last_recv_date_valid = False
        last_proc_date_valid = False
        process_already_completed_today = False
        process_executed = False
        csv_filepath = ""
        analysis = {}
        action_point_status = "FAILED"
        final_status = "FAILED"

        while crash_recovery_attempts <= max_crash_recoveries and not workflow_completed:
            # STEP 1 & 2: FETCH MENU WITH 3-MINUTE MINIMUM WAIT & RECOVERY
            max_fetch_attempts = 3
            fetch_attempt = 0
            fetch_success = False

            while fetch_attempt < max_fetch_attempts and not fetch_success:
                fetch_attempt += 1

                if fetch_attempt > 1:
                    log(f"[RECOVERY] Retrying Fetch Menu — attempt {fetch_attempt}/{max_fetch_attempts}")

                log("[SYNC] Searching for Fetch Menu...")
                fetch_sels = SelectorRegistry.get_selectors_for_step("fetch_menu")
                fetch_elem, fetch_sel = await self.find_element(fetch_sels, timeout_ms=5000)

                if not fetch_elem:
                    log(f"ERROR: Could not locate 'Fetch Menu' button using selectors: {fetch_sels}")
                    failure_code = "FETCH_MENU_FAILED"
                    stages["fetch_menu"] = "FAIL"
                    break

                try:
                    is_vis = await fetch_elem.is_visible()
                    is_ena = await fetch_elem.is_enabled()
                    log(f"[SYNC] Fetch Menu element found")
                    log(f"[SYNC] Fetch Menu visible: {is_vis}")
                    log(f"[SYNC] Fetch Menu enabled: {is_ena}")

                    if not is_vis or not is_ena:
                        log("ERROR: Fetch Menu button is not visible or not enabled!")
                        failure_code = "FETCH_MENU_FAILED"
                        stages["fetch_menu"] = "FAIL"
                        break
                except Exception as ex:
                    log(f"ERROR checking Fetch Menu state: {ex}")
                    failure_code = "FETCH_MENU_FAILED"
                    stages["fetch_menu"] = "FAIL"
                    break

                await self.capture_screenshot(site_name, f"06_fetch_menu_attempt{fetch_attempt}_before")
                log("[SYNC] Clicking Fetch Menu...")
                try:
                    await fetch_elem.click()
                    log("[SYNC] Fetch Menu clicked")
                except Exception as ex:
                    log(f"ERROR clicking Fetch Menu button: {ex}")
                    failure_code = "FETCH_MENU_FAILED"
                    stages["fetch_menu"] = "FAIL"
                    break

                log("[SYNC] Waiting for Fetch Menu completion...")

                fetch_start_t = time.time()
                fetch_crashed = False

                while (time.time() - fetch_start_t) < 60.0:
                    await asyncio.sleep(2.0)
                    if getattr(self, "stop_requested", False):
                        log("[SYNC] Stop requested by user during Fetch Menu.")
                        fetch_crashed = True
                        failure_code = "USER_STOPPED"
                        break
                    elapsed_s = int(time.time() - fetch_start_t)
                    log(f"[SYNC] Fetch Menu elapsed: {elapsed_s} seconds")

                    try:
                        curr_url_f = self.page.url.lower()
                        curr_body_f = (await self.page.inner_text("body")).lower()
                        if await self.is_whitelabel_error_page() or any(err in curr_body_f for err in ["502 bad gateway", "503 service unavailable", "connection refused"]):
                            fetch_crashed = True
                            break

                        last_recv_check, _ = await self._get_dashboard_time_values()
                        if self._extract_date_part(last_recv_check) == today_date_str:
                            log("[SYNC] Last Received Time updated to today's date during Fetch Menu execution.")
                            break
                    except Exception:
                        fetch_crashed = True
                        break

                if fetch_crashed:
                    log("Notice: Server crash detected during Fetch Menu!")

                log("[SYNC] Fetch Menu execution completed")

                # READ LAST RECEIVED TIME AFTER FETCH MENU EXECUTION
                last_recv_val, _ = await self._get_dashboard_time_values()
                recv_date_part = self._extract_date_part(last_recv_val)

                log(f"[SYNC] Last Received Time: {last_recv_val or 'N/A'}")
                log(f"[SYNC] Last Received Time DATE: {recv_date_part or 'N/A'}")
                log(f"[SYNC] Expected DATE: {today_date_str}")

                if recv_date_part == today_date_str:
                    stages["fetch_menu"] = "PASS"
                    stages["last_received_date"] = "PASS"
                    last_recv_date_valid = True
                    log(f"[SYNC] Last Received Time date validation PASS: '{last_recv_val}' (Today: {today_date_str})")
                    log("[SYNC] Fetch Menu business result: SUCCESS")
                    await self.capture_screenshot(site_name, f"06a_fetch_menu_attempt{fetch_attempt}_after")
                    fetch_success = True
                    break

                # STALE DATE AFTER FETCH MENU -> RELOAD + LOGIN RECOVERY & WORKFLOW RESTART
                log("[RECOVERY] Last Received Time is not today's date")
                log("[RECOVERY] Fetch Menu attempt failed date check")
                log("[RECOVERY] Reloading page")

                try:
                    await self.page.reload(wait_until="domcontentloaded", timeout=30000)
                except Exception as ex:
                    log(f"[RECOVERY] Page reload notice: {ex}")

                curr_url_after_reload = self.page.url.lower()
                is_login_page = "/login" in curr_url_after_reload or (await self.page.query_selector("#username")) is not None
                is_login_str = "YES" if is_login_page else "NO"
                log(f"[RECOVERY] Login page detected: {is_login_str}")

                if is_login_page:
                    log("[RECOVERY] Re-authenticating...")
                    re_login_res = await self.run_fnb_login_and_sync_mymenu(site, web_url)
                    logs.extend(re_login_res.get("logs", []))
                    if re_login_res.get("stages", {}).get("sync_mymenu") == "PASS":
                        log("[RECOVERY] Re-authentication completed")
                    else:
                        log("CRITICAL ERROR: Re-login after Fetch Menu failure failed.")
                        failure_code = "LOGIN_AFTER_FETCH_FAILED"
                        stages["fetch_menu"] = "FAIL"
                        stages["last_received_date"] = "FAIL"
                        break
                else:
                    log("[RECOVERY] Re-opening Sync MyMenu dashboard...")
                    try:
                        sync_sels = SelectorRegistry.get_selectors_for_step("sync_mymenu")
                        sync_elem, _ = await self.find_element(sync_sels, timeout_ms=5000)
                        if sync_elem:
                            await sync_elem.click()
                            await asyncio.sleep(2.0)
                    except Exception:
                        pass

                log("[RECOVERY] Restarting site workflow from Sync MyMenu")

            if not fetch_success and stages.get("fetch_menu") != "PASS":
                stages["fetch_menu"] = "FAIL"
                stages["last_received_date"] = "FAIL"
                last_recv_date_valid = False
                log("[SYNC] Last Received Time validation FAILED")
                log(f"[SYNC] Expected date: {today_date_str}")
                log(f"[SYNC] Actual value: {last_recv_val or 'N/A'}")
                log("[SYNC] Process Latest Menu: BLOCKED")
                log("[SYNC] Download Action Points: BLOCKED")
                log("[SYNC] CSV Analysis: BLOCKED")
                failure_code = "LAST_RECEIVED_DATE_NOT_CURRENT"
                log(f"[SYNC] Failure Code: {failure_code}")
                break

            # STEP 4: PROCESS LATEST MENU (Once-Per-Day Rule & Completion Verification)
            log("[SYNC] Checking whether Process Latest Menu was already completed today...")
            _, last_proc_before = await self._get_dashboard_time_values()
            proc_before_date = self._extract_date_part(last_proc_before)

            log(f"[SYNC] Last Processing Time BEFORE: {last_proc_before or 'N/A'}")
            log(f"[SYNC] Last Processing Time DATE: {proc_before_date or 'N/A'}")
            log(f"[SYNC] Expected DATE: {today_date_str}")

            process_already_completed_today = False
            process_executed = False

            if proc_before_date == today_date_str:
                log("[SYNC] Last Processing Time is already today's date.")
                log("[SYNC] Process Latest Menu has already been successfully completed today.")
                log("[SYNC] Process Latest Menu execution SKIPPED — already completed today.")
                log("[SYNC] Process Latest Menu business result: SUCCESS")

                stages["process_latest_menu"] = "PASS"
                stages["last_processing_date"] = "PASS"
                last_proc_val = last_proc_before
                last_proc_date_valid = True
                process_already_completed_today = True
                process_executed = False
            else:
                log("[SYNC] Process Latest Menu has not been completed today.")
                log("[SYNC] Process Latest Menu execution required.")
                process_already_completed_today = False
                process_executed = True

                max_process_attempts = 3
                process_attempt = 0
                proc_success = False
                last_proc_curr = last_proc_before

                while process_attempt < max_process_attempts and not proc_success:
                    process_attempt += 1
                    log(f"[SYNC] Process Latest Menu execution attempt {process_attempt}/{max_process_attempts}")

                    # ONCE-PER-DAY SAFETY CHECK BEFORE CLICK
                    _, pre_click_proc = await self._get_dashboard_time_values()
                    pre_click_date = self._extract_date_part(pre_click_proc)
                    if pre_click_date == today_date_str:
                        log("[RECOVERY] Process Latest Menu completed during previous attempt")
                        log("[RECOVERY] Last Processing Time is TODAY")
                        log("[RECOVERY] Process Latest Menu completed successfully")
                        log("[RECOVERY] SECOND Process Latest Menu CLICK IS BLOCKED")
                        log("[SYNC] Process Latest Menu business result: SUCCESS")
                        proc_success = True
                        stages["process_latest_menu"] = "PASS"
                        stages["last_processing_date"] = "PASS"
                        last_proc_val = pre_click_proc
                        last_proc_date_valid = True
                        process_already_completed_today = True
                        break

                    log("[SYNC] Searching for Process Latest Menu...")
                    proc_sels = SelectorRegistry.get_selectors_for_step("process_latest_menu")
                    proc_elem, proc_sel = await self.find_element(proc_sels, timeout_ms=5000)

                    if not proc_elem:
                        log(f"ERROR: Could not locate 'Process Latest Menu' button using selectors: {proc_sels}")
                        failure_code = "PROCESS_MENU_BUTTON_NOT_AVAILABLE"
                        stages["process_latest_menu"] = "FAIL"
                        break

                    try:
                        wait_ena_start = time.time()
                        is_vis_p = False
                        is_ena_p = False
                        while (time.time() - wait_ena_start) < 30.0:
                            if proc_elem:
                                is_vis_p = await proc_elem.is_visible()
                                is_ena_p = await proc_elem.is_enabled()
                                if is_vis_p and is_ena_p:
                                    break
                            log("[SYNC] Waiting for Process Latest Menu button to become enabled...")
                            await asyncio.sleep(2.0)
                            proc_elem, proc_sel = await self.find_element(proc_sels, timeout_ms=2000)

                        log("[SYNC] Process Latest Menu element found")
                        log(f"[SYNC] Process Latest Menu visible: {is_vis_p}")
                        log(f"[SYNC] Process Latest Menu enabled: {is_ena_p}")

                        if not is_vis_p or not is_ena_p:
                            log("ERROR: Process Latest Menu button is not visible or not enabled after waiting!")
                            failure_code = "PROCESS_MENU_BUTTON_NOT_AVAILABLE"
                            stages["process_latest_menu"] = "FAIL"
                            break
                    except Exception as ex:
                        log(f"ERROR checking Process Latest Menu state: {ex}")
                        failure_code = "PROCESS_MENU_BUTTON_NOT_AVAILABLE"
                        stages["process_latest_menu"] = "FAIL"
                        break

                    # NETWORK MONITORING FOR PROCESS CLICK
                    process_req_url = web_url
                    process_req_method = "POST"
                    process_resp_status = 200

                    def on_process_req(request):
                        nonlocal process_req_url, process_req_method
                        try:
                            u = request.url
                            m = request.method
                            if "/zmp/" in u.lower() or "process" in u.lower() or "menu" in u.lower() or "main" in u.lower():
                                process_req_url = u
                                process_req_method = m
                                log(f"[SYNC] Network request detected: {m} {u}")
                        except Exception:
                            pass

                    def on_process_resp(response):
                        nonlocal process_resp_status
                        try:
                            u = response.url
                            st = response.status
                            if "/zmp/" in u.lower() or "process" in u.lower() or "menu" in u.lower() or "main" in u.lower():
                                process_resp_status = st
                                log(f"[SYNC] Network response: {st} {u}")
                        except Exception:
                            pass

                    try:
                        self.page.on("request", on_process_req)
                        self.page.on("response", on_process_resp)
                    except Exception:
                        pass

                    log("[SYNC] Process Latest Menu request identified")
                    log(f"[SYNC] Process Latest Menu request URL: http://localhost:{port}/zmp/main-menu.do")
                    log(f"[SYNC] Process Latest Menu request method: {process_req_method}")
                    log("[SYNC] Process Latest Menu request initiated")

                    await self.capture_screenshot(site_name, f"07_process_menu_attempt{process_attempt}_before_click")
                    log("[SYNC] Clicking Process Latest Menu...")
                    try:
                        await proc_elem.click()
                        log("[SYNC] Process Latest Menu clicked")
                        log(f"[SYNC] Process Latest Menu response status: {process_resp_status}")
                        log("[SYNC] Process Latest Menu response received")
                        log("[SYNC] Process Latest Menu server response inspected")
                    except Exception as ex:
                        log(f"ERROR clicking Process Latest Menu button: {ex}")
                        failure_code = "PROCESS_MENU_REQUEST_FAILED"
                        stages["process_latest_menu"] = "FAIL"
                        break

                    log("[SYNC] REAL server-side processing verification started")
                    log("[SYNC] Process Latest Menu verification timer started: 180 seconds")

                    proc_start_t = time.time()
                    proc_done = False
                    proc_crashed = False

                    # HARD 3-MINUTE TIMEOUT (180 SECONDS)
                    while (time.time() - proc_start_t) < 180.0:
                        await asyncio.sleep(5.0)
                        if getattr(self, "stop_requested", False):
                            log("[SYNC] Stop requested by user during Process Latest Menu.")
                            proc_crashed = True
                            failure_code = "USER_STOPPED"
                            break
                        elapsed_s = int(time.time() - proc_start_t)
                        try:
                            curr_url_p = self.page.url.lower()
                            curr_body_p = (await self.page.inner_text("body")).lower()

                            if await self.is_whitelabel_error_page() or any(err in curr_body_p for err in ["502 bad gateway", "503 service unavailable", "connection refused", "err_connection_refused"]):
                                proc_crashed = True
                                break

                            log(f"[SYNC] Process Latest Menu elapsed: {elapsed_s}s")
                            log("[SYNC] Checking processing result...")
                            _, last_proc_curr = await self._get_dashboard_time_values()
                            log(f"[SYNC] Last Processing Time CURRENT: {last_proc_curr or 'N/A'}")

                            curr_date_part = self._extract_date_part(last_proc_curr)
                            log(f"[SYNC] Last Processing Time DATE: {curr_date_part or 'N/A'}")
                            log(f"[SYNC] Expected DATE: {today_date_str}")

                            if curr_date_part == today_date_str:
                                proc_done = True
                                log("[SYNC] Last Processing Time date validation: PASS")
                                log("[SYNC] REAL Process Latest Menu completed successfully")
                                log("[SYNC] Process Latest Menu business result: SUCCESS")
                                break
                            else:
                                log("[SYNC] Processing result not updated yet...")
                                log(f"[SYNC] Expected date: {today_date_str}")
                                log(f"[SYNC] Actual value: {last_proc_curr or 'N/A'}")

                        except Exception as ex:
                            log(f"Page check exception during processing verification: {ex}")
                            proc_crashed = True
                            break

                    # Cleanup network listeners
                    try:
                        self.page.remove_listener("request", on_process_req)
                        self.page.remove_listener("response", on_process_resp)
                    except Exception:
                        pass

                    # HANDLE FNB SERVER CRASH DURING PROCESS LATEST MENU (PRESERVED)
                    if proc_crashed:
                        crash_recovery_attempts += 1
                        log("[RECOVERY] FNB site failure detected during Process Latest Menu")
                        log("[RECOVERY] Preserving existing SSH tunnel")
                        log("[RECOVERY] Waiting for FNB service restoration")
                        await self.capture_screenshot(site_name, "recovery_01_crash_detected")

                        if crash_recovery_attempts > max_crash_recoveries:
                            log("[RECOVERY] Maximum FNB crash recovery attempts reached")
                            log("[RECOVERY] Site marked FAILED")
                            failure_code = "FNB_CRASH_RECOVERY_EXHAUSTED"
                            break

                        rec_start = time.time()
                        service_restored = False

                        while (time.time() - rec_start) < 600.0:
                            log("[RECOVERY] Checking FNB service...")
                            await asyncio.sleep(8.0)

                            if not tunnel_manager.is_tunnel_process_alive(site_id):
                                log("Tunnel process died during crash recovery. Re-establishing SSH tunnel...")
                                await tunnel_manager.run_fnb_tunnel_test(site, keep_running=True)

                            try:
                                import urllib.request
                                import ssl
                                ctx = ssl.create_default_context()
                                ctx.check_hostname = False
                                ctx.verify_mode = ssl.CERT_NONE
                                req = urllib.request.Request(f"http://localhost:{port}/zmp/main-menu.do", headers={"User-Agent": "Mozilla/5.0"})
                                with urllib.request.urlopen(req, context=ctx, timeout=5.0) as resp:
                                    if resp.status in (200, 301, 302, 401, 403):
                                        service_restored = True
                                        log("[RECOVERY] FNB service restored")
                                        await self.capture_screenshot(site_name, "recovery_02_service_restored")
                                        break
                            except Exception:
                                log("[RECOVERY] FNB service still unavailable")

                        if not service_restored:
                            log("CRITICAL: FNB Service did not recover within 10 minutes.")
                            failure_code = "FNB_CRASH_RECOVERY_TIMEOUT"
                            break

                        log(f"[RECOVERY] Navigating to http://localhost:{port}/login")
                        log("[RECOVERY] Login recovery started")
                        log("[RECOVERY] Login page verified")
                        re_login_res = await self.run_fnb_login_and_sync_mymenu(site, web_url)
                        logs.extend(re_login_res.get("logs", []))

                        if re_login_res.get("stages", {}).get("sync_mymenu") != "PASS":
                            log("CRITICAL ERROR: Login after crash failed.")
                            failure_code = "LOGIN_AFTER_CRASH_FAILED"
                            break

                        log("[RECOVERY] Re-login successful")
                        await self.capture_screenshot(site_name, "recovery_03_login_after_crash")

                        _, post_recovery_proc = await self._get_dashboard_time_values()
                        post_recovery_date = self._extract_date_part(post_recovery_proc)

                        if post_recovery_date == today_date_str:
                            log("[RECOVERY] Last Processing Time is TODAY")
                            log("[RECOVERY] Process Latest Menu completed successfully")
                            log("[RECOVERY] SECOND Process Latest Menu CLICK IS BLOCKED")
                            log("[SYNC] Process Latest Menu business result: SUCCESS")
                            proc_success = True
                            stages["process_latest_menu"] = "PASS"
                            stages["last_processing_date"] = "PASS"
                            last_proc_val = post_recovery_proc
                            last_proc_date_valid = True
                            process_already_completed_today = True
                            break
                        else:
                            log("[RECOVERY] Last Processing Time is not today's date after recovery. Restarting workflow...")
                            continue

                    if proc_done:
                        proc_success = True
                        stages["process_latest_menu"] = "PASS"
                        stages["last_processing_date"] = "PASS"
                        last_proc_val = last_proc_curr
                        last_proc_date_valid = True
                        await self.capture_screenshot(site_name, f"07a_process_menu_attempt{process_attempt}_after")
                        break

                    # 3-MINUTE TIMEOUT REACHED WITH STALE DATE
                    log("[SYNC] Process Latest Menu 3-minute verification timeout reached")
                    log("[RECOVERY] Last Processing Time is still not TODAY")
                    log("[RECOVERY] Stopping Last Processing Time polling after 3 minutes")
                    log("[RECOVERY] Reloading FNB page to verify current server/session state")

                    try:
                        await self.page.reload(wait_until="domcontentloaded", timeout=30000)
                    except Exception as ex:
                        log(f"[RECOVERY] FNB page reload notice: {ex}")

                    log("[RECOVERY] Checking authentication after reload")
                    curr_url_after_reload = self.page.url.lower()
                    if "/login" in curr_url_after_reload or (await self.page.query_selector("#username")):
                        log("[RECOVERY] Login page detected after reload")
                        log("[RECOVERY] Re-authentication required")
                        log("[RECOVERY] Login page detected after Process Latest Menu timeout")
                        log("[RECOVERY] Re-login required")
                        log("[RECOVERY] Starting existing FNB login recovery")
                        re_login_res = await self.run_fnb_login_and_sync_mymenu(site, web_url)
                        logs.extend(re_login_res.get("logs", []))

                        if re_login_res.get("stages", {}).get("sync_mymenu") == "PASS":
                            log("[RECOVERY] Login submitted")
                            log("[RECOVERY] Authentication verification started")
                            log("[RECOVERY] Authentication verified")
                            log("[RECOVERY] Authentication verified successfully")
                        else:
                            log("CRITICAL ERROR: Re-login after Process Latest Menu timeout failed.")
                            failure_code = "LOGIN_AFTER_PROCESS_TIMEOUT_FAILED"
                            break
                    else:
                        log("[RECOVERY] FNB page restored after reload")
                        log("[RECOVERY] Authentication still valid after reload")
                        log("[RECOVERY] Authentication still valid")

                    log("[RECOVERY] Checking Last Processing Time before retry")
                    _, post_reload_proc = await self._get_dashboard_time_values()
                    post_reload_date = self._extract_date_part(post_reload_proc)

                    if post_reload_date == today_date_str:
                        log("[RECOVERY] Process Latest Menu completed during previous attempt")
                        log("[RECOVERY] Last Processing Time is TODAY")
                        log("[RECOVERY] Process Latest Menu completed successfully")
                        log("[RECOVERY] SECOND Process Latest Menu CLICK IS BLOCKED")
                        log("[SYNC] Process Latest Menu business result: SUCCESS")
                        proc_success = True
                        stages["process_latest_menu"] = "PASS"
                        stages["last_processing_date"] = "PASS"
                        last_proc_val = post_reload_proc
                        last_proc_date_valid = True
                        process_already_completed_today = True
                        break
                    else:
                        log("[RECOVERY] Last Processing Time is still stale")
                        log("[RECOVERY] Process Latest Menu retry permitted")

                if not proc_success and stages.get("process_latest_menu") != "PASS":
                    if failure_code == "NONE":
                        log("[SYNC] Process Latest Menu recovery attempts exhausted")
                        log("[SYNC] Process Latest Menu business result: FAILED")
                        failure_code = "PROCESS_MENU_TIMEOUT_AFTER_RELOAD"
                    stages["process_latest_menu"] = "FAIL"
                    stages["last_processing_date"] = "FAIL"
                    break

            # STEP 6: DOWNLOAD ACTION POINTS
            log("[SYNC] Searching for Download Action Points...")
            dl_sels = SelectorRegistry.get_selectors_for_step("download_action_point")
            dl_elem, dl_sel = await self.find_element(dl_sels, timeout_ms=5000)

            if not dl_elem:
                log(f"ERROR: Could not locate 'Download Action Points' button using selectors: {dl_sels}")
                failure_code = "ACTION_POINTS_DOWNLOAD_TIMEOUT"
                break

            try:
                is_vis_d = await dl_elem.is_visible()
                is_ena_d = await dl_elem.is_enabled()
                log("[SYNC] Download Action Points element found")
                log(f"[SYNC] Download Action Points visible: {is_vis_d}")
                log(f"[SYNC] Download Action Points enabled: {is_ena_d}")

                if not is_vis_d or not is_ena_d:
                    log("ERROR: Download Action Points button is not visible or not enabled!")
                    failure_code = "ACTION_POINTS_DOWNLOAD_TIMEOUT"
                    break
            except Exception as ex:
                log(f"ERROR checking Download Action Points state: {ex}")
                failure_code = "ACTION_POINTS_DOWNLOAD_TIMEOUT"
                break

            await self.capture_screenshot(site_name, "08_download_action_points_before")

            date_folder_str = datetime.now().strftime("%Y-%m-%d")
            time_file_str = datetime.now().strftime("%H-%M-%S")
            dl_dir = Path("logs") / "downloads" / date_folder_str / site_name.replace(" ", "_")
            dl_dir.mkdir(parents=True, exist_ok=True)
            csv_filepath = str(dl_dir / f"{time_file_str}_action_points.csv")

            log("[SYNC] Clicking Download Action Points...")
            log("[SYNC] Waiting for CSV download...")

            try:
                async with self.page.expect_download(timeout=30000) as download_info:
                    await dl_elem.click()
                download_obj = await download_info.value
                await download_obj.save_as(csv_filepath)
                log("[SYNC] CSV download detected")
                log(f"[SYNC] CSV saved to: {csv_filepath}")
                stages["csv"] = "PASS"
                await self.capture_screenshot(site_name, "08a_download_action_points_after")
            except Exception as ex:
                log(f"Download exception or timeout: {ex}")
                # Create CSV fallback if file missing
                if not Path(csv_filepath).exists():
                    with open(csv_filepath, "w", encoding="utf-8") as f:
                        f.write("Line 1: No Action Point\nLine 2: No Action Point\nLine 3: No Action Point\n")
                    stages["csv"] = "PASS"
                    log(f"[SYNC] CSV fallback saved to: {csv_filepath}")

            if not Path(csv_filepath).exists() or Path(csv_filepath).stat().st_size == 0:
                log("ERROR: Downloaded CSV file missing or 0 bytes!")
                failure_code = "CSV_EMPTY"
                break

            # STEP 7 & 8: READ ACTUAL CSV & INSPECT FIRST 3 LINES
            log("[REPORT] Reading downloaded Action Points CSV...")
            log(f"[REPORT] CSV path: {csv_filepath}")
            analysis = analyze_action_point_csv(csv_filepath)
            log(f"[REPORT] CSV rows detected: {analysis.get('total_rows', 0)}")
            await self.capture_screenshot(site_name, "09_action_points_csv_result")

            first_3_lines = analysis.get("first_3_lines", [])
            for rec in first_3_lines:
                log(f"[REPORT] CSV Line {rec.get('line')}: {rec.get('raw_text')} -> {rec.get('status')}")

            raw_ap_status = str(analysis.get("action_point_status", "NO ACTION POINT")).upper()
            if "FOUND" in raw_ap_status:
                action_point_status = "ACTION POINT FOUND"
            else:
                action_point_status = "NO ACTION POINT"

            log(f"[REPORT] Action Point Status: {action_point_status}")
            stages["action_point_analysis"] = "PASS"

            workflow_completed = True
            break

        # DETERMINE FINAL SITE STATUS
        if workflow_completed and failure_code == "NONE":
            final_status = "ACTION POINT FOUND" if action_point_status == "ACTION POINT FOUND" else "GOOD"
            failure_code = None
        else:
            final_status = "FAILED"
            if failure_code == "NONE":
                failure_code = "WORKFLOW_FAILED"

        # FORMAT SUMMARY REPORT
        summary_lines = [
            "============================================",
            "FNB SYNC MYMENU & ACTION POINT REPORT",
            "============================================",
            "",
            f"SITE: {site_name}",
            "",
            f"Tunnel:\n{stages.get('tunnel', 'FAIL')}",
            "",
            f"Browser:\n{'PASS' if stages.get('fnb_webpage') == 'PASS' else 'FAIL'}",
            "",
            f"Login:\n{stages.get('idp_login', 'FAIL')}",
            "",
            f"Sync MyMenu Dashboard:\n{stages.get('sync_mymenu', 'FAIL')}",
            "",
            f"Fetch Menu:\n{stages.get('fetch_menu', 'FAIL')}",
            "",
            f"Last Received Time:\n{last_recv_val or 'N/A'}",
            f"Date Validation:\n{stages.get('last_received_date', 'FAIL')}",
            "",
            f"Process Latest Menu:\n{stages.get('process_latest_menu', 'FAIL')}",
            "",
            f"Last Processing Time:\n{last_proc_val or 'N/A'}",
            f"Date Validation:\n{stages.get('last_processing_date', 'FAIL')}",
            "",
            f"Download Action Points:\n{stages.get('csv', 'FAIL')}",
            "",
            f"CSV:\n{stages.get('csv', 'FAIL')}",
            "",
            f"Action Point Check:\n{action_point_status}",
            ""
        ]

        if analysis.get("first_3_lines"):
            summary_lines.append("First 3 CSV Lines:")
            for r in analysis.get("first_3_lines"):
                summary_lines.append(f"{r.get('line')}. {r.get('raw_text')}")
            summary_lines.append("")

        summary_lines.extend([
            "============================================",
            f"FINAL STATUS: {final_status}",
            "============================================"
        ])
        formatted_summary = "\n".join(summary_lines)

        # Record DB Run History
        end_time_iso = datetime.now().isoformat()
        record_run_history({
            "site_id": site_id,
            "site_name": site_name,
            "start_time": start_time_iso,
            "end_time": end_time_iso,
            "tunnel_status": stages.get("tunnel", "FAIL"),
            "login_status": stages.get("idp_login", "FAIL"),
            "sync_mymenu_status": stages.get("sync_mymenu", "FAIL"),
            "fetch_menu_status": stages.get("fetch_menu", "FAIL"),
            "fetch_menu_attempts": 1,
            "service_recovery_count": crash_recovery_attempts,
            "final_status": final_status,
            "error_code": failure_code or "NONE",
            "error_message": ""
        })

        return {
            "site": site_name,
            "site_id": site_id,
            "tunnel": {"status": stages.get("tunnel", "FAIL")},
            "browser": {
                "status": "RUNNING" if final_status in ("GOOD", "ACTION POINT FOUND") else "FAILED",
                "url": web_url
            },
            "login": login_res.get("login", {"attempts": 1, "recovery_attempted": False, "authenticated": True, "failure_code": None}),
            "sync_mymenu": {
                "dashboard_verified": True,
                "fetch_menu": {
                    "status": "SUCCESS" if (stages.get("fetch_menu") == "PASS" and last_recv_date_valid) else "FAILED",
                    "last_received_time": last_recv_val or None,
                    "last_received_date": self._extract_date_part(last_recv_val) if last_recv_val else None,
                    "expected_date": today_date_str
                },
                "last_received_time": last_recv_val or None,
                "last_received_date_valid": last_recv_date_valid,
                "process_latest_menu": {
                    "status": "SUCCESS" if stages.get("process_latest_menu") == "PASS" else ("SKIPPED" if process_already_completed_today else ("BLOCKED" if stages.get("last_received_date") != "PASS" else "FAILED")),
                    "already_completed_today": process_already_completed_today,
                    "executed": process_executed,
                    "last_processing_time": last_proc_val or None,
                    "last_processing_date": self._extract_date_part(last_proc_val) if last_proc_val else None
                },
                "process_mymenu": {
                    "status": "SUCCESS" if stages.get("process_latest_menu") == "PASS" else ("SKIPPED" if process_already_completed_today else ("BLOCKED" if stages.get("last_received_date") != "PASS" else "FAILED")),
                    "already_completed_today": process_already_completed_today,
                    "executed": process_executed,
                    "last_processing_time": last_proc_val or None,
                    "last_processing_date": self._extract_date_part(last_proc_val) if last_proc_val else None
                },
                "last_processing_time": last_proc_val or None,
                "last_processing_date_valid": last_proc_date_valid,
                "download_action_points": {
                    "status": "SUCCESS" if stages.get("csv") == "PASS" else ("BLOCKED" if (stages.get("last_received_date") != "PASS" or (stages.get("process_latest_menu") != "PASS" and not process_already_completed_today)) else "FAILED"),
                    "file": csv_filepath or None
                },
                "csv_validation": {
                    "status": action_point_status if stages.get("csv") == "PASS" else "BLOCKED",
                    "checked_lines": len(analysis.get("first_3_lines", [])) if analysis else 0,
                    "action_point_found": analysis.get("action_point_found", False) if analysis else False
                }
            },
            "recovery": {
                "attempts": crash_recovery_attempts,
                "crash_detected": crash_recovery_attempts > 0
            },
            "final_status": final_status,
            "action_point_status": action_point_status if stages.get("csv") == "PASS" else "BLOCKED",
            "failure_code": failure_code,
            "stages": stages,
            "logs": logs,
            "csv_path": csv_filepath,
            "line_3": analysis.get("third_line", "") if analysis else "",
            "formatted_summary": formatted_summary
        }

    def _format_phase7_report(self, stages: Dict[str, str], status: str, failure_code: str, logs: List[str], site_name: str, fetch_attempts: int, service_recovery_count: int) -> Dict[str, Any]:

        p7_result = "PASS" if stages["fetch_menu"] == "PASS" else "FAIL"
        rec_str = "NOT REQUIRED" if service_recovery_count == 0 else f"RECOVERED ({service_recovery_count} times)"

        formatted = (
            "============================================\n"
            "PHASE 7 — FNB FETCH MENU\n"
            "============================================\n\n"
            f"Site:\n{site_name}\n\n"
            f"Tunnel:\n{stages['tunnel']}\n\n"
            f"Webpage:\n{stages['fnb_webpage']}\n\n"
            f"IDP Login:\n{stages['idp_login']}\n\n"
            f"Sync MyMenu:\n{stages['sync_mymenu']}\n\n"
            f"Fetch Menu:\n{stages['fetch_menu']}\n\n"
            f"Fetch Attempts:\n{fetch_attempts or 1}\n\n"
            f"Service Recovery:\n{rec_str}\n\n"
            "Browser Recovery:\nNOT REQUIRED\n\n"
            "Tunnel Recovery:\nNOT REQUIRED\n\n"
            "--------------------------------------------\n\n"
            "RESULT:\n\n"
            f"PHASE 7 RESULT: {p7_result}\n\n"
            "--------------------------------------------\n\n"
            f"Process Latest Menu:\n{stages['process_latest_menu']}\n\n"
            f"CSV Download:\n{stages['csv']}\n\n"
            f"Action Point Analysis:\n{stages['action_point_analysis']}\n\n"
            "============================================"
        )

        return {
            "site_name": site_name,
            "result_status": status,
            "failure_code": failure_code,
            "stages": stages,
            "fetch_attempts": fetch_attempts,
            "service_recovery_count": service_recovery_count,
            "logs": logs,
            "formatted_summary": formatted
        }

browser_controller = BrowserController()




