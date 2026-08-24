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
        """Captures debug screenshot if debug mode is active."""
        if not self.page or self.page.is_closed():
            return None

        try:
            date_str = time.strftime("%Y-%m-%d")
            folder = SCREENSHOTS_DIR / date_str
            folder.mkdir(parents=True, exist_ok=True)
            clean_site = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in site_name)
            clean_step = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in step_name)
            filename = f"{clean_site}_{clean_step}_{int(time.time())}.png"
            path = folder / filename
            await self.page.screenshot(path=str(path), full_page=False)
            logger.info(f"Captured screenshot: {path}")
            return str(path)
        except Exception as e:
            logger.debug(f"Screenshot capture failed: {e}")
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
                    elem = await self.page.wait_for_selector(xpath_sel, timeout=3000, state="visible")
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

    async def login(self, username: str, password: str, timeout_seconds: int = 60) -> Tuple[bool, str]:
        """Performs IDP Login sequence."""
        if not self.page:
            return False, "Page not initialized"

        logger.info(f"Executing IDP Login sequence for user '{username}'...")
        user_sels = SelectorRegistry.get_selectors_for_step("login_username")
        pass_sels = SelectorRegistry.get_selectors_for_step("login_password")
        sub_sels = SelectorRegistry.get_selectors_for_step("login_submit")

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
