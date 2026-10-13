import os
import time
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Set, Tuple

from playwright.async_api import (
    async_playwright,
    Playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError
)

from app.config import SCREENSHOTS_DIR
from app.dth_automation.selectors import DthSelectorRegistry
from app.dth_automation.models import ChannelItem, DthItemState
from app.database.db import get_all_settings

logger = logging.getLogger("DTH_PortalController")


class DthPortalController:
    """
    Playwright controller for DTH Channel Configuration on the ZMP portal.
    Handles navigation, category inspection, duplicate extraction,
    safe sequential form filling, file uploads, and state reconciliation.
    """

    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.stop_requested: bool = False
        self.is_connected: bool = False

    async def initialize(self, headless: bool = True, browser_type_str: str = "chromium"):
        """Initializes Playwright browser instance."""
        logger.info(f"[DTH] Initializing Playwright Browser (type: {browser_type_str}, headless: {headless})...")
        self.playwright = await async_playwright().start()

        launch_kwargs: Dict[str, Any] = {
            "headless": headless,
            "args": ["--start-maximized", "--disable-blink-features=AutomationControlled"]
        }
        if browser_type_str.lower() in ("msedge", "edge"):
            launch_kwargs["channel"] = "msedge"
        elif browser_type_str.lower() == "chrome":
            launch_kwargs["channel"] = "chrome"

        try:
            self.browser = await self.playwright.chromium.launch(**launch_kwargs)
        except Exception as e:
            logger.warning(f"[DTH] Could not launch with {launch_kwargs}, falling back to standard chromium: {e}")
            self.browser = await self.playwright.chromium.launch(headless=headless)

        self.context = await self.browser.new_context(
            accept_downloads=True,
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True
        )
        self.page = await self.context.new_page()
        self.is_connected = True
        logger.info("[DTH] Browser initialized successfully.")

    async def close(self):
        """Safely releases Playwright browser resources."""
        self.is_connected = False
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
        try:
            if self.browser:
                await self.browser.close()
        except Exception:
            pass
        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None
            logger.info("[DTH] Browser closed.")

    async def emergency_stop(self):
        """Immediately requests stop and aborts active operations."""
        self.stop_requested = True
        logger.warning("[DTH] Emergency stop triggered. Aborting browser session...")
        await self.close()

    async def capture_screenshot(self, site_name: str, step_name: str) -> Optional[str]:
        """Captures sanitized debug screenshot for diagnostics."""
        if not self.page or self.page.is_closed():
            return None
        try:
            date_str = time.strftime("%Y-%m-%d")
            clean_site = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in site_name)
            clean_step = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in step_name)

            site_folder = SCREENSHOTS_DIR / date_str / "dth" / clean_site
            site_folder.mkdir(parents=True, exist_ok=True)

            filename = f"{clean_step}_{int(time.time())}.png"
            path = site_folder / filename
            await self.page.screenshot(path=str(path), full_page=False)
            logger.info(f"[DTH] Captured screenshot: {path}")
            return str(path)
        except Exception as e:
            logger.debug(f"[DTH] Screenshot failed: {e}")
            return None

    async def find_element(self, selectors: List[str], timeout_ms: int = 5000):
        """Locates first matching element across fallback selector list."""
        if not self.page or self.page.is_closed():
            raise RuntimeError("Browser page not available")

        for sel in selectors:
            try:
                locator = self.page.locator(sel).first
                if await locator.count() > 0 and await locator.is_visible(timeout=timeout_ms / len(selectors)):
                    return locator
            except Exception:
                continue
        return None

    async def navigate_to_url(self, url: str, timeout_seconds: int = 60) -> bool:
        """Navigates to URL and waits for DOM content loaded."""
        if not self.page:
            return False
        try:
            logger.info(f"[DTH] Navigating to URL: {url}")
            await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
            return True
        except Exception as e:
            logger.error(f"[DTH] Navigation failed: {e}")
            return False

    async def login_if_required(self, username: str, password: str, timeout_seconds: int = 45) -> Tuple[bool, str]:
        """Performs IDP login if login form is detected on current page."""
        if not self.page:
            return False, "Page not initialized"

        try:
            # Check if login username field is present
            from app.browser.selectors import SelectorRegistry
            user_selectors = SelectorRegistry.get_selectors_for_step("login_username")
            user_elem = await self.find_element(user_selectors, timeout_ms=3000)
            if not user_elem:
                logger.info("[DTH] No login form detected. Session already active or not required.")
                return True, "No login form detected"

            logger.info("[DTH] Login form detected. Entering credentials...")
            await user_elem.fill(username)

            pass_selectors = SelectorRegistry.get_selectors_for_step("login_password")
            pass_elem = await self.find_element(pass_selectors, timeout_ms=3000)
            if pass_elem:
                await pass_elem.fill(password)

            btn_selectors = SelectorRegistry.get_selectors_for_step("login_submit")
            btn_elem = await self.find_element(btn_selectors, timeout_ms=3000)
            if btn_elem:
                await btn_elem.click()

            await self.page.wait_for_load_state("domcontentloaded", timeout=timeout_seconds * 1000)
            await asyncio.sleep(1.0)
            return True, "Login successful"
        except Exception as e:
            logger.error(f"[DTH] Login error: {e}")
            return False, f"Login failed: {str(e)}"

    async def open_dth_configuration(self) -> Tuple[bool, str]:
        """
        Navigates to the DTH Channel Configuration section in ZMP.
        Attempts Service Setup -> DTH Channel Configuration.
        """
        if not self.page:
            return False, "Page not initialized"

        try:
            logger.info("[DTH] Navigating to DTH Channel Configuration...")
            # Step 1: Click 'Service Setup' if present
            service_sels = DthSelectorRegistry.get_selectors("nav_service_setup")
            service_btn = await self.find_element(service_sels, timeout_ms=3000)
            if service_btn:
                await service_btn.click()
                await asyncio.sleep(0.5)

            # Step 2: Click 'DTH Channel Configuration'
            dth_sels = DthSelectorRegistry.get_selectors("nav_dth_channel_config")
            dth_btn = await self.find_element(dth_sels, timeout_ms=4000)
            if dth_btn:
                await dth_btn.click()
                await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
                return True, "Opened DTH Channel Configuration"

            # If sub-nav button not found directly, check if current URL already contains channel / dth
            cur_url = self.page.url.lower()
            if "channel" in cur_url or "stb" in cur_url or "dth" in cur_url:
                return True, "Already on DTH Channel Configuration page"

            return True, "Navigated to main menu / service setup"
        except Exception as e:
            return False, f"Error opening DTH configuration: {str(e)}"

    async def read_available_categories(self) -> List[str]:
        """
        Extracts available category names exposed by the portal.
        Falls back to standard defaults if not explicitly discovered.
        """
        from app.dth_automation.validator import DEFAULT_PORTAL_CATEGORIES
        if not self.page:
            return DEFAULT_PORTAL_CATEGORIES

        found_categories: Set[str] = set()
        try:
            checkbox_sels = DthSelectorRegistry.get_selectors("category_checkboxes")
            for sel in checkbox_sels:
                elements = await self.page.locator(sel).all()
                for el in elements:
                    val = await el.get_attribute("value")
                    label_text = await el.evaluate("e => e.parentElement ? e.parentElement.innerText : ''")
                    name = (label_text or val or "").strip()
                    if name and len(name) < 40:
                        found_categories.add(name)

            if found_categories:
                # Ensure 'all' is in list
                cats = list(found_categories)
                if not any(c.lower() == "all" for c in cats):
                    cats.insert(0, "all")
                return cats
        except Exception as e:
            logger.debug(f"[DTH] Could not extract live categories: {e}")

        return DEFAULT_PORTAL_CATEGORIES

    async def get_existing_channels_from_portal(self) -> Tuple[Set[str], Set[str]]:
        """
        Extracts existing (channel_numbers, channel_names) from portal listing table.
        Used to enforce CREATE ONLY policy and prevent duplicates.
        """
        existing_numbers: Set[str] = set()
        existing_names: Set[str] = set()

        if not self.page:
            return existing_numbers, existing_names

        try:
            table_sels = DthSelectorRegistry.get_selectors("channel_table")
            tbl = await self.find_element(table_sels, timeout_ms=3000)
            if tbl:
                rows = await tbl.locator("tbody tr").all()
                for r in rows:
                    cells = await r.locator("td").all_inner_texts()
                    if len(cells) >= 2:
                        ch_no = cells[0].strip().lower()
                        ch_name = cells[1].strip().lower()
                        if ch_no:
                            existing_numbers.add(ch_no)
                        if ch_name:
                            existing_names.add(ch_name)
        except Exception as e:
            logger.debug(f"[DTH] Could not scrape existing channel table: {e}")

        return existing_numbers, existing_names

    async def create_channel(self, channel: ChannelItem) -> Tuple[DthItemState, str, bool]:
        """
        Executes sequential channel creation through the portal:
        1. Click 'Add New Channel'
        2. Fill channel number, name, OSD
        3. Upload logo image
        4. Assign categories (enforcing mandatory 'all')
        5. Submit form
        6. Verify saved outcome or reconcile on timeout
        Returns: (DthItemState, reason_or_message, verified_in_portal)
        """
        if self.stop_requested:
            return DthItemState.CANCELLED, "Operation cancelled by user", False

        if not self.page:
            return DthItemState.FAILED, "Browser page not available", False

        try:
            logger.info(f"[DTH] Starting creation for Channel {channel.channel_number}: '{channel.name}'...")

            # 1. Click 'Add New Channel' button if present
            add_btn_sels = DthSelectorRegistry.get_selectors("btn_add_new_channel")
            add_btn = await self.find_element(add_btn_sels, timeout_ms=3000)
            if add_btn:
                await add_btn.click()
                await asyncio.sleep(0.5)

            # 2. Fill Channel Number
            num_sels = DthSelectorRegistry.get_selectors("input_channel_number")
            num_elem = await self.find_element(num_sels, timeout_ms=3000)
            if num_elem:
                await num_elem.fill(channel.channel_number)
            else:
                return DthItemState.FAILED, "Channel number input field not found on portal", False

            # 3. Fill Channel Name
            name_sels = DthSelectorRegistry.get_selectors("input_channel_name")
            name_elem = await self.find_element(name_sels, timeout_ms=2000)
            if name_elem:
                await name_elem.fill(channel.name)
            else:
                return DthItemState.FAILED, "Channel name input field not found on portal", False

            # 4. Fill OSD Text
            osd_sels = DthSelectorRegistry.get_selectors("input_channel_osd")
            osd_elem = await self.find_element(osd_sels, timeout_ms=2000)
            if osd_elem:
                await osd_elem.fill(channel.osd)

            # 5. Upload Channel Logo Image if resolved
            if channel.resolved_image_path and os.path.exists(channel.resolved_image_path):
                img_sels = DthSelectorRegistry.get_selectors("input_channel_image")
                img_elem = await self.find_element(img_sels, timeout_ms=2000)
                if img_elem:
                    logger.info(f"[DTH] Uploading channel logo: {channel.resolved_image_path}")
                    await img_elem.set_input_files(channel.resolved_image_path)
                else:
                    logger.warning("[DTH] File upload input field not found on portal form.")

            # 6. Assign Categories (Enforcing mandatory 'all')
            await self._assign_categories_on_form(channel.categories)

            # 7. Submit Channel Form
            save_sels = DthSelectorRegistry.get_selectors("btn_save_channel")
            save_btn = await self.find_element(save_sels, timeout_ms=3000)
            if not save_btn:
                return DthItemState.FAILED, "Save button not found on portal", False

            await save_btn.click()

            # 8. Verify Submission Outcome
            return await self._verify_or_reconcile_save(channel)

        except PlaywrightTimeoutError:
            logger.warning(f"[DTH] Timeout while saving channel {channel.channel_number}. Entering reconciliation...")
            return await self.reconcile_save(channel)
        except Exception as e:
            logger.error(f"[DTH] Channel creation exception for {channel.channel_number}: {e}")
            return DthItemState.FAILED, f"Exception during submission: {str(e)}", False

    async def _assign_categories_on_form(self, target_categories: List[str]):
        """
        Locates category checkboxes or multiselect options on form and marks them.
        Always ensures 'all' is checked.
        """
        if not self.page:
            return

        normalized_targets = {c.strip().lower() for c in target_categories if c.strip()}
        normalized_targets.add("all")  # Mandatory rule enforcement

        try:
            checkbox_sels = DthSelectorRegistry.get_selectors("category_checkboxes")
            for sel in checkbox_sels:
                elements = await self.page.locator(sel).all()
                for el in elements:
                    val = (await el.get_attribute("value") or "").strip().lower()
                    label = (await el.evaluate("e => e.parentElement ? e.parentElement.innerText : ''") or "").strip().lower()
                    if val in normalized_targets or label in normalized_targets:
                        if not await el.is_checked():
                            await el.check()
        except Exception as e:
            logger.debug(f"[DTH] Error ticking category checkboxes: {e}")

    async def _verify_or_reconcile_save(self, channel: ChannelItem) -> Tuple[DthItemState, str, bool]:
        """
        Verifies portal feedback after submitting.
        Never blindly claims success without confirmation.
        """
        if not self.page:
            return DthItemState.UNKNOWN, "Page closed before verification", False

        try:
            # Check for success alert/toast
            succ_sels = DthSelectorRegistry.get_selectors("msg_success")
            succ_elem = await self.find_element(succ_sels, timeout_ms=3000)
            if succ_elem:
                return DthItemState.SUCCESS, "Channel saved and verified by portal success toast", True

            # Check for error alert/toast
            err_sels = DthSelectorRegistry.get_selectors("msg_error")
            err_elem = await self.find_element(err_sels, timeout_ms=2000)
            if err_elem:
                err_text = await err_elem.inner_text()
                return DthItemState.FAILED, f"Portal rejected save: {err_text.strip()}", False

            # If no toast, check listing table
            await asyncio.sleep(1.0)
            return await self.reconcile_save(channel)

        except Exception as e:
            logger.debug(f"[DTH] Verification check error: {e}")
            return await self.reconcile_save(channel)

    async def reconcile_save(self, channel: ChannelItem) -> Tuple[DthItemState, str, bool]:
        """
        Inspects portal listing after submission to verify if channel exists.
        Avoids duplicate creations when timeouts occur.
        """
        existing_nums, existing_names = await self.get_existing_channels_from_portal()
        if channel.channel_number.lower() in existing_nums or channel.name.lower() in existing_names:
            logger.info(f"[DTH] Reconciliation confirmed channel {channel.channel_number} was created successfully.")
            return DthItemState.SUCCESS, "Verified present in portal channel table after submission", True

        logger.warning(f"[DTH] Reconciliation could not confirm save for channel {channel.channel_number}.")
        return DthItemState.UNKNOWN, "Submission status ambiguous (not found in table, timed out)", False
