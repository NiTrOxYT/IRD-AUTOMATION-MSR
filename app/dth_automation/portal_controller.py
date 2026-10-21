import os
import time
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Set, Tuple, Callable

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
from app.dth_automation.models import ChannelItem, DthItemState, BrowserSnapshot, DthWorkflowState
from app.dth_automation.browser_observer import BrowserObserver
from app.database.db import get_all_settings

logger = logging.getLogger("DTH_PortalController")


class DthPortalController:
    """
    Playwright controller for DTH Channel Configuration on the ZMP portal.
    Enforces contract: OBSERVE -> DECIDE -> ACT -> WAIT -> SNAPSHOT -> VERIFY -> PROCEED.
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
        self.observer: Optional[BrowserObserver] = None
        self.on_snapshot: Optional[Callable[[BrowserSnapshot], None]] = None
        self.existing_channels_map: Dict[str, Dict[str, Any]] = {}

    def set_run_id(self, run_id: Any):
        """Attaches diagnostic observer for specific execution run."""
        self.observer = BrowserObserver(run_id=run_id)

    async def initialize(self, headless: bool = True, browser_type_str: str = "chromium"):
        """Initializes Playwright browser instance and diagnostic observer."""
        if self.observer is None:
            self.observer = BrowserObserver(run_id=int(time.time()))
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

    async def snapshot(
        self,
        action_name: str,
        expected_state: Optional[str] = None,
        verification_fn: Optional[Callable[[Dict[str, Any]], Tuple[bool, str]]] = None,
        take_screenshot: bool = True
    ) -> BrowserSnapshot:
        """Captures structured diagnostic snapshot and notifies listeners."""
        if self.observer and self.page and not self.page.is_closed():
            snap = await self.observer.capture_snapshot(
                self.page,
                action_name=action_name,
                expected_state=expected_state,
                verification_fn=verification_fn,
                take_screenshot=take_screenshot
            )
            if self.on_snapshot:
                try:
                    self.on_snapshot(snap)
                except Exception:
                    pass
            return snap
        return BrowserSnapshot(
            step_number=0,
            action_name=action_name,
            url=self.page.url if self.page and not self.page.is_closed() else "",
            title="",
            detected_state=DthWorkflowState.UNKNOWN.value,
            verification_passed=True,
            verification_notes="No observer attached",
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
        )

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

    async def observe_and_authenticate(
        self,
        base_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout_seconds: int = 45
    ) -> Tuple[bool, str]:
        """
        Observes current page state, decides if authentication is required,
        fills credentials, submits login, and verifies authenticated state.
        Contract: OBSERVE -> DECIDE -> ACT -> WAIT -> SNAPSHOT -> VERIFY -> PROCEED.
        """
        if not self.page:
            return False, "Page not initialized"

        try:
            entry_url = f"{base_url.rstrip('/')}/zmp/main-menu.do"
            login_url = f"{base_url.rstrip('/')}/zmp/login.do"

            cur_url = (self.page.url or "").lower()
            if not cur_url or cur_url == "about:blank":
                logger.info(f"[DTH] Navigating to entry URL: {entry_url}...")
                nav_ok = await self.navigate_to_url(entry_url, timeout_seconds=timeout_seconds)
                if not nav_ok:
                    logger.info(f"[DTH] Entry URL failed; navigating to login URL: {login_url}...")
                    nav_ok = await self.navigate_to_url(login_url, timeout_seconds=timeout_seconds)
                    if not nav_ok:
                        return False, f"Could not navigate to portal at {base_url}"

            await asyncio.sleep(0.5)

            # Step 1: Observe & Snapshot initial entry state
            snap_entry = await self.snapshot("portal_entry_opened")
            logger.info(f"[DTH] Step 1 Observed: state={snap_entry.detected_state} at {snap_entry.url}")

            # Step 2: Check if session is already authenticated
            if snap_entry.detected_state in (DthWorkflowState.AUTHENTICATED.value, DthWorkflowState.CHANNEL_PAGE_OPENED.value, DthWorkflowState.CHANNEL_FORM_VERIFIED.value):
                logger.info("[DTH] Active session already authenticated on portal. Proceeding.")
                return True, "Session already authenticated"

            # Check if login form is present
            user_sels = DthSelectorRegistry.get_selectors("login_username")
            user_elem = await self.find_element(user_sels, timeout_ms=3000)

            pass_sels = DthSelectorRegistry.get_selectors("login_password")
            pass_elem = await self.find_element(pass_sels, timeout_ms=3000)

            if not user_elem and not pass_elem:
                # Re-check for logout indicator
                auth_sels = DthSelectorRegistry.get_selectors("indicator_authenticated")
                auth_elem = await self.find_element(auth_sels, timeout_ms=2000)
                if auth_elem:
                    logger.info("[DTH] Authentication indicator detected. Session authenticated.")
                    return True, "Session authenticated"

                # If on error or blank page, try direct login URL
                if "login" not in self.page.url.lower():
                    logger.info(f"[DTH] Navigating directly to login URL: {login_url}...")
                    await self.navigate_to_url(login_url, timeout_seconds=timeout_seconds)
                    await asyncio.sleep(0.5)
                    user_elem = await self.find_element(user_sels, timeout_ms=3000)
                    pass_elem = await self.find_element(pass_sels, timeout_ms=3000)

            if not user_elem or not pass_elem:
                await self.snapshot("login_form_not_found")
                return False, f"Login form not found on portal at {self.page.url}"

            # Step 3: Enter credentials
            eff_user = (username or "").strip() or "admin"
            eff_pass = (password or "").strip()

            if not eff_pass:
                err_msg = "IDP password is required but not configured for this site"
                logger.error(f"[DTH] {err_msg}")
                await self.snapshot("login_aborted_empty_password")
                return False, err_msg

            logger.info(f"[DTH] Entering IDP credentials for user '{eff_user}'...")
            await user_elem.fill(eff_user)
            await pass_elem.fill(eff_pass)
            await asyncio.sleep(0.2)

            # Step 4: Snapshot credentials entered (passwords masked)
            await self.snapshot("credentials_entered")

            # Step 5: Act - Submit form
            btn_sels = DthSelectorRegistry.get_selectors("login_submit")
            btn_elem = await self.find_element(btn_sels, timeout_ms=3000)

            logger.info("[DTH] Submitting IDP login form...")
            if btn_elem:
                await btn_elem.click()
            else:
                await pass_elem.press("Enter")

            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=timeout_seconds * 1000)
            except Exception:
                pass
            await asyncio.sleep(1.5)

            # Step 6: Snapshot post-submission state & Verify
            snap_post = await self.snapshot("login_submitted")
            logger.info(f"[DTH] Post-login observed state={snap_post.detected_state} at {snap_post.url}")

            # Check if login was rejected with bad credentials
            if snap_post.detected_state == DthWorkflowState.AUTHENTICATION_REQUIRED.value:
                err_sels = DthSelectorRegistry.get_selectors("msg_error")
                err_elem = await self.find_element(err_sels, timeout_ms=2000)
                err_text = (await err_elem.inner_text()).strip() if err_elem else "Portal rejected login credentials"
                logger.error(f"[DTH] IDP login failed: {err_text}")
                return False, f"IDP login failed: {err_text}"

            # Verify authenticated state
            if snap_post.detected_state in (DthWorkflowState.AUTHENTICATED.value, DthWorkflowState.CHANNEL_PAGE_OPENED.value, DthWorkflowState.CHANNEL_FORM_VERIFIED.value):
                return True, "IDP login successful and verified"

            # Check for authenticated indicator on page
            auth_sels = DthSelectorRegistry.get_selectors("indicator_authenticated")
            if await self.find_element(auth_sels, timeout_ms=3000):
                return True, "IDP login successful (indicator verified)"

            # If page title contains Smartler Management Portal
            if "smartler" in (await self.page.title()).lower() and "login.do" not in self.page.url.lower():
                return True, "IDP login successful"

            return False, f"Could not verify authenticated session (state: {snap_post.detected_state})"
        except Exception as e:
            logger.error(f"[DTH] Login exception: {e}")
            await self.snapshot("login_exception")
            return False, f"Login exception: {str(e)}"

    async def login_if_required(self, username: str, password: str, timeout_seconds: int = 45) -> Tuple[bool, str]:
        """Backward-compatible wrapper around observe_and_authenticate."""
        base_url = "http://localhost:18001"
        if self.page and self.page.url:
            import urllib.parse
            parsed = urllib.parse.urlsplit(self.page.url)
            if parsed.scheme and parsed.netloc:
                base_url = f"{parsed.scheme}://{parsed.netloc}"
        return await self.observe_and_authenticate(base_url, username, password, timeout_seconds)

    async def open_dth_configuration(self, base_url: Optional[str] = None) -> Tuple[bool, str]:
        """
        Navigates to the DTH Channel Configuration section in ZMP (/zmp/manage-stb-channels.do).
        Contract: OBSERVE -> DECIDE -> ACT -> WAIT -> SNAPSHOT -> VERIFY -> PROCEED.
        """
        if not self.page:
            return False, "Page not initialized"

        try:
            target_channels_url = f"{base_url.rstrip('/')}/zmp/manage-stb-channels.do" if base_url else ""
            cur_url = (self.page.url or "").lower()

            if "manage-stb-channels" in cur_url:
                await self.snapshot("channels_page_already_open")
                return True, "Already on DTH Channel Configuration page"

            if target_channels_url:
                logger.info(f"[DTH] Navigating directly to {target_channels_url}...")
                nav_ok = await self.navigate_to_url(target_channels_url, timeout_seconds=30)
                if nav_ok:
                    await asyncio.sleep(1.0)
                    snap = await self.snapshot("channels_page_opened")
                    if snap.detected_state == DthWorkflowState.AUTHENTICATION_REQUIRED.value:
                        return False, "Redirected to login: unauthenticated session"
                    return True, "Navigated to /zmp/manage-stb-channels.do"

            # Fallback navigation through menus
            logger.info("[DTH] Navigating to DTH Channel Configuration via menu...")
            service_sels = DthSelectorRegistry.get_selectors("nav_service_setup")
            service_btn = await self.find_element(service_sels, timeout_ms=3000)
            if service_btn:
                await service_btn.hover()
                await asyncio.sleep(0.3)
                await service_btn.click()
                await asyncio.sleep(0.5)

            dth_sels = DthSelectorRegistry.get_selectors("nav_dth_channel_config")
            dth_btn = await self.find_element(dth_sels, timeout_ms=4000)
            if dth_btn:
                await dth_btn.click()
                await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
                await asyncio.sleep(1.0)
                await self.snapshot("channels_page_opened_via_menu")
                return True, "Opened DTH Channel Configuration"

            await self.snapshot("channels_page_navigated")
            return True, "Navigated to main menu / service setup"
        except Exception as e:
            await self.snapshot("channels_page_open_error")
            return False, f"Error opening DTH configuration: {str(e)}"

    async def read_available_categories(self) -> List[str]:
        """
        Extracts available category names exposed by the portal.
        Falls back to standard defaults if not explicitly discovered.
        Executes via fast page evaluation to prevent blocking on thousands of checkboxes.
        """
        from app.dth_automation.validator import DEFAULT_PORTAL_CATEGORIES
        if not self.page or self.page.is_closed():
            return DEFAULT_PORTAL_CATEGORIES

        try:
            cats = await self.page.evaluate('''() => {
                const results = new Set();
                const labels = document.querySelectorAll('#row_newentry .multiselect label, .multiselect label');
                labels.forEach(lbl => {
                    const cb = lbl.querySelector('input[type="checkbox"]');
                    if (cb) {
                        const txt = (lbl.innerText || lbl.textContent || '').trim();
                        if (txt && txt.length < 40) {
                            results.add(txt);
                        }
                    }
                });
                return Array.from(results);
            }''')

            if cats and len(cats) > 0:
                cat_list = list(cats)
                if not any(c.lower() == "all" for c in cat_list):
                    cat_list.insert(0, "all")
                return cat_list
        except Exception as e:
            logger.debug(f"[DTH] Could not extract live categories: {e}")

        return DEFAULT_PORTAL_CATEGORIES

    async def get_existing_channels_from_portal(self, take_snapshot: bool = True) -> Tuple[Set[str], Set[str]]:
        """
        Extracts existing (channel_numbers, channel_names) from portal listing table (#datatable).
        Populates self.existing_channels_map with row references and edit metadata.
        Captures diagnostic snapshot of discovered channels if take_snapshot is True.
        """
        existing_numbers: Set[str] = set()
        existing_names: Set[str] = set()
        self.existing_channels_map: Dict[str, Dict[str, Any]] = {}

        if not self.page or self.page.is_closed():
            return existing_numbers, existing_names

        try:
            raw_items = await self.page.evaluate('''() => {
                const result = [];
                const table = document.getElementById("datatable") || document.querySelector("table.tablesorter") || document.querySelector("table");
                if (!table) return result;

                const rows = table.querySelectorAll('tbody tr[id^="row_"], tbody tr');
                rows.forEach((r, rowIdx) => {
                    if (r.id === "row_newentry") return;
                    const numInput = r.querySelector('input[name="channelNumber"]');
                    const nameInput = r.querySelector('input[name="name"]');
                    const numDisplay = r.querySelector('td:nth-child(1) .value-display') || r.querySelector('td:nth-child(1)');
                    const nameDisplay = r.querySelector('td:nth-child(2) .value-display') || r.querySelector('td:nth-child(2)');

                    const no = (numInput ? numInput.value : (numDisplay ? numDisplay.innerText : '')).trim().toLowerCase();
                    const nm = (nameInput ? nameInput.value : (nameDisplay ? nameDisplay.innerText : '')).trim();
                    if (no && !['channel no', 'channel number', 'number', '#', 's.no', 'sl no'].includes(no)) {
                        result.push({ number: no, name: nm, rowIndex: rowIdx, rowId: r.id });
                    }
                });
                return result;
            }''')

            for item in (raw_items or []):
                ch_no = str(item.get("number", "")).strip().lower()
                ch_name = str(item.get("name", "")).strip()
                if ch_no:
                    existing_numbers.add(ch_no)
                    existing_names.add(ch_name.lower())
                    self.existing_channels_map[ch_no] = {
                        "number": ch_no,
                        "name": ch_name,
                        "row_index": item.get("rowIndex", 0),
                        "row_id": item.get("rowId", "")
                    }

            if take_snapshot:
                await self.snapshot("channels_table_scraped")
        except Exception as e:
            logger.debug(f"[DTH] Could not scrape existing channel table: {e}")

        return existing_numbers, existing_names

    async def update_channel(self, channel: ChannelItem, existing_info: Optional[Dict[str, Any]] = None) -> Tuple[DthItemState, str, bool]:
        """
        Updates an existing channel on the portal when the uploaded file (source of truth)
        specifies different properties than the current portal record.
        Contract: OBSERVE -> DECIDE -> ACT -> WAIT -> SNAPSHOT -> VERIFY -> PROCEED.
        """
        if self.stop_requested:
            return DthItemState.CANCELLED, "Operation cancelled by user", False

        if not self.page or self.page.is_closed():
            return DthItemState.FAILED, "Browser page not available", False

        try:
            logger.info(f"[DTH] Updating Channel {channel.channel_number}: updating name to '{channel.name}'...")
            opened_edit = False
            row_id = existing_info.get("row_id") if existing_info else None
            row_sel = f"tr#{row_id}" if row_id else f"table#datatable tr:has-text('{channel.channel_number}')"

            if row_id:
                edit_btn = self.page.locator(f"tr#{row_id} a.k-grid-edit, tr#{row_id} a:has-text('Edit')").first
                if await edit_btn.count() > 0:
                    await edit_btn.click()
                    await asyncio.sleep(0.5)
                    opened_edit = True

            if not opened_edit:
                row_loc = self.page.locator(f"table#datatable tr:has-text('{channel.channel_number}')").first
                if await row_loc.count() > 0:
                    edit_in_row = row_loc.locator("a.k-grid-edit, a:has-text('EDIT'), a:has-text('Edit')").first
                    if await edit_in_row.count() > 0:
                        await edit_in_row.click()
                        await asyncio.sleep(0.5)
                        opened_edit = True

            if not opened_edit:
                edit_sels = DthSelectorRegistry.get_selectors("btn_edit_channel")
                edit_btn = await self.find_element(edit_sels, timeout_ms=2000)
                if edit_btn:
                    await edit_btn.click()
                    await asyncio.sleep(0.5)
                    opened_edit = True

            # Snapshot: Edit opened
            await self.snapshot(f"ch_{channel.channel_number}_edit_opened")

            # Update Channel Name in that row
            name_loc = self.page.locator(f"{row_sel} input[name='name']").first
            if await name_loc.count() > 0:
                await name_loc.fill(channel.name)
            else:
                name_sels = DthSelectorRegistry.get_selectors("input_channel_name")
                name_elem = await self.find_element(name_sels, timeout_ms=3000)
                if name_elem:
                    await name_elem.fill(channel.name)
                else:
                    await self.snapshot(f"ch_{channel.channel_number}_edit_name_missing")
                    return DthItemState.FAILED, "Channel name input field not found on portal edit form", False

            # Update OSD Text in that row
            osd_loc = self.page.locator(f"{row_sel} input[name='osd']").first
            if await osd_loc.count() > 0:
                await osd_loc.fill(channel.osd or channel.name)

            # Upload Channel Logo Image if resolved
            if channel.resolved_image_path and os.path.exists(channel.resolved_image_path):
                img_loc = self.page.locator(f"{row_sel} input[type='file']").first
                if await img_loc.count() > 0:
                    logger.info(f"[DTH] Uploading channel logo: {channel.resolved_image_path}")
                    await img_loc.set_input_files(channel.resolved_image_path)
                else:
                    img_sels = DthSelectorRegistry.get_selectors("input_channel_image")
                    img_elem = await self.find_element(img_sels, timeout_ms=2000)
                    if img_elem:
                        logger.info(f"[DTH] Uploading channel logo: {channel.resolved_image_path}")
                        await img_elem.set_input_files(channel.resolved_image_path)

            # Assign Categories within this specific row: 'all' + exactly one relevant category
            await self._assign_categories_on_form(channel.categories, row_selector=row_sel, channel_name=channel.name)

            # Snapshot: Edit form filled (fast DOM snapshot)
            await self.snapshot(f"ch_{channel.channel_number}_edit_filled", take_screenshot=False)

            # Submit Channel Form (Update button in row)
            save_loc = self.page.locator(f"{row_sel} a.k-grid-update, {row_sel} a:has-text('Update')").first
            if await save_loc.count() > 0:
                await save_loc.click()
            else:
                save_sels = DthSelectorRegistry.get_selectors("btn_save_channel")
                save_btn = await self.find_element(save_sels, timeout_ms=2000)
                if not save_btn:
                    await self.snapshot(f"ch_{channel.channel_number}_edit_save_missing")
                    return DthItemState.FAILED, "Save button not found on portal edit form", False
                await save_btn.click()

            # Snapshot: Edit submitted
            await self.snapshot(f"ch_{channel.channel_number}_edit_submitted", take_screenshot=True)

            return await self._verify_or_reconcile_save(channel)

        except PlaywrightTimeoutError:
            logger.warning(f"[DTH] Timeout while updating channel {channel.channel_number}. Entering reconciliation...")
            await self.snapshot(f"ch_{channel.channel_number}_edit_timeout")
            return await self.reconcile_save(channel)
        except Exception as e:
            logger.error(f"[DTH] Channel update exception for {channel.channel_number}: {e}")
            await self.snapshot(f"ch_{channel.channel_number}_edit_exception")
            return DthItemState.FAILED, f"Exception during update submission: {str(e)}", False

    async def create_channel(self, channel: ChannelItem) -> Tuple[DthItemState, str, bool]:
        """
        Executes sequential channel creation through the portal:
        1. Click 'Add new Channel' (.k-grid-add) to make add row (#row_newentry) visible.
        2. Snapshot form opened and verify fields are visible.
        3. Fill channel number, name, OSD in #row_newentry.
        4. Upload logo image if found.
        5. Assign categories (enforcing mandatory 'all').
        6. Snapshot filled form.
        7. Submit form via #row_newentry Save button (.k-grid-update).
        8. Snapshot submitted outcome.
        9. Verify saved outcome in table or reconcile.
        """
        if self.stop_requested:
            return DthItemState.CANCELLED, "Operation cancelled by user", False

        if not self.page or self.page.is_closed():
            return DthItemState.FAILED, "Browser page not available", False

        try:
            logger.info(f"[DTH] Starting creation for Channel {channel.channel_number}: '{channel.name}'...")

            # 1. Click 'ADD NEW CHANNEL' button if row not already open
            is_open = False
            try:
                is_open = await self.page.evaluate('''() => {
                    const r = document.getElementById("row_newentry");
                    return !!(r && r.style.display !== "none" && r.offsetParent !== null);
                }''')
            except Exception:
                is_open = False

            if not is_open:
                # Fast direct locator click
                add_btn = self.page.locator("a.k-grid-add, .k-grid-add, a:has-text('Add new Channel'), a:has-text('Add New Channel')").first
                if await add_btn.count() > 0:
                    await add_btn.click()
                else:
                    add_btn_sels = DthSelectorRegistry.get_selectors("btn_add_new_channel")
                    add_elem = await self.find_element(add_btn_sels, timeout_ms=1500)
                    if add_elem:
                        await add_elem.click()
                    else:
                        await self.page.evaluate('''() => {
                            const btn = document.querySelector(".k-grid-add, a:has-text('Add new Channel')");
                            if (btn) btn.click();
                            else {
                                const r = document.getElementById("row_newentry");
                                if (r) r.style.display = "table-row";
                            }
                        }''')

                # Fast wait for #row_newentry to become visible
                try:
                    await self.page.locator("#row_newentry").wait_for(state="visible", timeout=1500)
                except Exception:
                    # Fallback via jQuery trigger
                    try:
                        await self.page.evaluate('''() => {
                            if (window.jQuery) {
                                window.jQuery(".k-grid-add").trigger("click");
                                window.jQuery("#row_newentry").css("display", "table-row");
                            }
                        }''')
                    except Exception:
                        pass

            # Snapshot: Add Channel form opened (fast DOM snapshot)
            await self.snapshot("add_channel_form_opened", take_screenshot=False)

            # 2. Fill Channel Number directly targeting #row_newentry
            num_loc = self.page.locator("#row_newentry input#channelNumber, #row_newentry input[name='channelNumber'], #channelNumber").first
            if await num_loc.count() > 0:
                await num_loc.fill(str(channel.channel_number))
            else:
                num_sels = DthSelectorRegistry.get_selectors("input_channel_number")
                num_elem = await self.find_element(num_sels, timeout_ms=1500)
                if not num_elem or await num_elem.count() == 0:
                    await self.snapshot(f"ch_{channel.channel_number}_number_field_missing")
                    return DthItemState.FAILED, "Channel number input field not found on portal", False
                await num_elem.fill(str(channel.channel_number))

            # 3. Fill Channel Name directly targeting #row_newentry
            name_loc = self.page.locator("#row_newentry input#name, #row_newentry input[name='name'], #name").first
            if await name_loc.count() > 0:
                await name_loc.fill(channel.name)
            else:
                name_sels = DthSelectorRegistry.get_selectors("input_channel_name")
                name_elem = await self.find_element(name_sels, timeout_ms=1500)
                if not name_elem or await name_elem.count() == 0:
                    await self.snapshot(f"ch_{channel.channel_number}_name_field_missing")
                    return DthItemState.FAILED, "Channel name input field not found on portal", False
                await name_elem.fill(channel.name)

            # 4. Fill OSD Text directly targeting #row_newentry
            osd_loc = self.page.locator("#row_newentry input#osd, #row_newentry input[name='osd'], #osd").first
            if await osd_loc.count() > 0:
                await osd_loc.fill(channel.osd or channel.name)
            else:
                osd_sels = DthSelectorRegistry.get_selectors("input_channel_osd")
                osd_elem = await self.find_element(osd_sels, timeout_ms=1000)
                if osd_elem and await osd_elem.count() > 0:
                    await osd_elem.fill(channel.osd or channel.name)

            # 5. Upload Channel Logo Image if resolved
            if channel.resolved_image_path and os.path.exists(channel.resolved_image_path):
                img_loc = self.page.locator("#row_newentry #addnewcmsimage, #row_newentry input[type='file'], #addnewcmsimage").first
                if await img_loc.count() > 0:
                    logger.info(f"[DTH] Uploading channel logo: {channel.resolved_image_path}")
                    await img_loc.set_input_files(channel.resolved_image_path)
                else:
                    img_sels = DthSelectorRegistry.get_selectors("input_channel_image")
                    img_elem = await self.find_element(img_sels, timeout_ms=1000)
                    if img_elem and await img_elem.count() > 0:
                        logger.info(f"[DTH] Uploading channel logo: {channel.resolved_image_path}")
                        await img_elem.set_input_files(channel.resolved_image_path)
                    else:
                        logger.warning("[DTH] File upload input field not found on portal form.")

            # 6. Assign Categories: strictly 'all' and only one other relevant category
            await self._assign_categories_on_form(channel.categories, row_selector="#row_newentry", channel_name=channel.name)

            # Snapshot: Form populated (fast DOM snapshot)
            await self.snapshot(f"ch_{channel.channel_number}_form_filled", take_screenshot=False)

            # 7. Submit Channel Form (Click Save on #row_newentry)
            save_loc = self.page.locator("#row_newentry a.k-grid-update, #row_newentry a:has-text('Save'), a.k-grid-update").first
            if not save_loc or await save_loc.count() == 0:
                save_sels = DthSelectorRegistry.get_selectors("btn_save_channel")
                save_loc = await self.find_element(save_sels, timeout_ms=1500)

            if not save_loc or await save_loc.count() == 0:
                await self.snapshot(f"ch_{channel.channel_number}_save_button_missing")
                return DthItemState.FAILED, "Save button not found on portal", False

            logger.info(f"[DTH] Submitting channel form for Channel {channel.channel_number}...")
            await save_loc.click()

            # Snapshot: Post-submission
            await self.snapshot(f"ch_{channel.channel_number}_submitted", take_screenshot=True)

            # 8. Fast DOM Verification & Reconciliation
            return await self._verify_or_reconcile_save(channel)

        except PlaywrightTimeoutError:
            logger.warning(f"[DTH] Timeout while saving channel {channel.channel_number}. Entering reconciliation...")
            await self.snapshot(f"ch_{channel.channel_number}_timeout")
            return await self.reconcile_save(channel)
        except Exception as e:
            logger.error(f"[DTH] Channel creation exception for {channel.channel_number}: {e}")
            await self.snapshot(f"ch_{channel.channel_number}_exception")
            return DthItemState.FAILED, f"Exception during submission: {str(e)}", False

    async def _assign_categories_on_form(
        self,
        target_categories: List[str],
        row_selector: str = "#row_newentry",
        channel_name: Optional[str] = None
    ):
        """
        Locates category checkboxes within target row/form and marks them.
        STRICT REQUIREMENT: The automation must only select 'all' and only ONE other relevant category!
        All other checkboxes are strictly unchecked.
        Executes via fast evaluate inside the specific row multiselect.
        """
        if not self.page or self.page.is_closed():
            return

        # 1. Identify non-'all' category candidates
        non_all = [c.strip() for c in target_categories if c and c.strip().lower() != "all"]
        relevant_category = non_all[0] if non_all else None

        # 2. If no non-all category provided, infer from channel name or portal options
        if not relevant_category and channel_name:
            from app.dth_automation.validator import infer_category_from_name
            relevant_category = infer_category_from_name(channel_name)

        if not relevant_category:
            relevant_category = "most-viewed"

        try:
            res = await self.page.evaluate('''({ rowSel, otherCat }) => {
                const row = document.querySelector(rowSel) || document;
                const labels = row.querySelectorAll('.multiselect label, label');
                const targetOther = (otherCat || '').trim().toLowerCase();

                let allChecked = false;
                let otherChecked = false;

                // First pass: identify matching checkboxes
                labels.forEach(lbl => {
                    const cb = lbl.querySelector('input[type="checkbox"]');
                    if (!cb) return;
                    const txt = (lbl.innerText || lbl.textContent || '').trim().toLowerCase();
                    const val = (cb.value || '').trim().toLowerCase();

                    const isAll = (txt === "all" || val === "all");
                    const isOther = targetOther && (txt === targetOther || val === targetOther || (targetOther.length > 3 && (txt.includes(targetOther) || targetOther.includes(txt))));

                    if (isAll && !allChecked) {
                        allChecked = true;
                        if (!cb.checked) {
                            cb.checked = true;
                            if (window.jQuery) {
                                window.jQuery(cb).parent().addClass("multiselect-on");
                                window.jQuery(cb).trigger("change");
                            }
                        }
                    } else if (isOther && !otherChecked) {
                        otherChecked = true;
                        if (!cb.checked) {
                            cb.checked = true;
                            if (window.jQuery) {
                                window.jQuery(cb).parent().addClass("multiselect-on");
                                window.jQuery(cb).trigger("change");
                            }
                        }
                    } else {
                        // Crucial: ensure ALL OTHER checkboxes are strictly unchecked
                        if (cb.checked) {
                            cb.checked = false;
                            if (window.jQuery) {
                                window.jQuery(cb).parent().removeClass("multiselect-on");
                                window.jQuery(cb).trigger("change");
                            }
                        }
                    }
                });

                // If targetOther wasn't found in labels, prioritize default portal categories: most-viewed or infotainment
                if (!otherChecked && labels.length > 1) {
                    for (let i = 0; i < labels.length; i++) {
                        const lbl = labels[i];
                        const cb = lbl.querySelector('input[type="checkbox"]');
                        if (!cb) continue;
                        const txt = (lbl.innerText || lbl.textContent || '').trim().toLowerCase();
                        const val = (cb.value || '').trim().toLowerCase();
                        if (txt.includes("most-viewed") || val.includes("most-viewed") || txt.includes("infotainment") || val.includes("infotainment")) {
                            cb.checked = true;
                            otherChecked = true;
                            if (window.jQuery) {
                                window.jQuery(cb).parent().addClass("multiselect-on");
                                window.jQuery(cb).trigger("change");
                            }
                            break;
                        }
                    }
                    if (!otherChecked) {
                        for (let i = 0; i < labels.length; i++) {
                            const lbl = labels[i];
                            const cb = lbl.querySelector('input[type="checkbox"]');
                            if (!cb) continue;
                            const txt = (lbl.innerText || lbl.textContent || '').trim().toLowerCase();
                            const val = (cb.value || '').trim().toLowerCase();
                            if (txt !== "all" && val !== "all") {
                                cb.checked = true;
                                otherChecked = true;
                                if (window.jQuery) {
                                    window.jQuery(cb).parent().addClass("multiselect-on");
                                    window.jQuery(cb).trigger("change");
                                }
                                break;
                            }
                        }
                    }
                }

                return { allChecked, otherChecked, targetOther };
            }''', {"rowSel": row_selector, "otherCat": relevant_category})

            logger.info(f"[DTH] Categories assigned: ['all', '{relevant_category}'] (all others unchecked, status: {res})")
        except Exception as e:
            logger.debug(f"[DTH] Error ticking category checkboxes: {e}")

    async def _verify_or_reconcile_save(self, channel: ChannelItem) -> Tuple[DthItemState, str, bool]:
        """
        Fast, non-blocking DOM verification of channel save:
        1. Repeatedly polls DOM every 100ms:
           - Checks if error banner/toast/dialog appears -> immediate failure.
           - Checks if channel number appears in #datatable tbody -> immediate success.
           - Checks if success toast appears -> immediate success.
        2. If not resolved within poll window, falls back to full table reconciliation.
        Never blindly claims success without confirmation.
        """
        if not self.page:
            return DthItemState.UNKNOWN, "Page closed before verification", False

        ch_num_clean = str(channel.channel_number).strip().lower()
        ch_name_clean = (channel.name or "").strip().lower()

        try:
            # High-speed poll loop (every 100ms for up to 3.5s)
            poll_interval = 0.1
            max_polls = 35

            for _ in range(max_polls):
                eval_res = None
                try:
                    eval_res = await self.page.evaluate('''({ targetNum, targetName }) => {
                        // 1. Check for error alerts
                        const err = document.querySelector(".alert-danger, .toast-error, .error-message, .k-window .k-content, .field-validation-error");
                        if (err && err.offsetParent !== null) {
                            const errTxt = (err.innerText || err.textContent || "").trim();
                            if (errTxt && errTxt.length > 2) {
                                return { status: "error", message: errTxt };
                            }
                        }

                        // 2. Check for success alert
                        const succ = document.querySelector(".alert-success, .toast-success");
                        if (succ && succ.offsetParent !== null) {
                            const succTxt = (succ.innerText || succ.textContent || "").trim();
                            return { status: "success", message: succTxt || "Channel saved successfully" };
                        }

                        // 3. Check table rows for targetNum or targetName
                        const table = document.getElementById("datatable") || document.querySelector("table.tablesorter") || document.querySelector("table");
                        if (table) {
                            const rows = table.querySelectorAll('tbody tr');
                            for (let i = 0; i < rows.length; i++) {
                                const r = rows[i];
                                if (r.id === "row_newentry") continue;
                                const numInput = r.querySelector('input[name="channelNumber"]');
                                const nameInput = r.querySelector('input[name="name"]');
                                const numDisplay = r.querySelector('td:nth-child(1) .value-display') || r.querySelector('td:nth-child(1)');
                                const nameDisplay = r.querySelector('td:nth-child(2) .value-display') || r.querySelector('td:nth-child(2)');

                                const no = (numInput ? numInput.value : (numDisplay ? numDisplay.innerText : '')).trim().toLowerCase();
                                const nm = (nameInput ? nameInput.value : (nameDisplay ? nameDisplay.innerText : '')).trim().toLowerCase();

                                if (no === targetNum || (targetName && nm === targetName)) {
                                    return { status: "success", message: "Verified present in portal channel table after submission" };
                                }
                            }
                        }

                        return { status: "pending" };
                    }''', {"targetNum": ch_num_clean, "targetName": ch_name_clean})
                except Exception:
                    pass

                if isinstance(eval_res, dict):
                    st = eval_res.get("status")
                    if st == "success":
                        msg = eval_res.get("message", "Channel saved and verified")
                        # Update in-memory tracking
                        if hasattr(self, "existing_channels_map") and self.existing_channels_map is not None:
                            self.existing_channels_map[ch_num_clean] = {
                                "number": ch_num_clean,
                                "name": channel.name,
                                "row_id": f"row_{ch_num_clean}"
                            }
                        return DthItemState.SUCCESS, msg, True
                    elif st == "error":
                        err_msg = eval_res.get("message", "Portal rejected channel submission")
                        return DthItemState.FAILED, f"Portal rejected save: {err_msg}", False

                await asyncio.sleep(poll_interval)

            # Fallback check for toast / error selectors (useful for mock tests / unexpected layouts)
            succ_sels = DthSelectorRegistry.get_selectors("msg_success")
            succ_elem = await self.find_element(succ_sels, timeout_ms=500)
            if succ_elem:
                return DthItemState.SUCCESS, "Channel saved and verified by portal success toast", True

            err_sels = DthSelectorRegistry.get_selectors("msg_error")
            err_elem = await self.find_element(err_sels, timeout_ms=500)
            if err_elem:
                err_text = await err_elem.inner_text()
                return DthItemState.FAILED, f"Portal rejected save: {err_text.strip()}", False

            # Fallback to full reconciliation
            return await self.reconcile_save(channel)

        except Exception as e:
            logger.debug(f"[DTH] Verification check error: {e}")
            return await self.reconcile_save(channel)

    async def reconcile_save(self, channel: ChannelItem) -> Tuple[DthItemState, str, bool]:
        """
        Inspects portal listing after submission to verify if channel exists.
        Avoids duplicate creations when timeouts occur.
        """
        existing_nums, existing_names = await self.get_existing_channels_from_portal(take_snapshot=False)
        ch_num_lower = str(channel.channel_number).strip().lower()
        ch_name_lower = (channel.name or "").strip().lower()

        if ch_num_lower in existing_nums or (ch_name_lower and ch_name_lower in existing_names):
            logger.info(f"[DTH] Reconciliation confirmed channel {channel.channel_number} was created successfully.")
            return DthItemState.SUCCESS, "Verified present in portal channel table after submission", True

        logger.warning(f"[DTH] Reconciliation could not confirm save for channel {channel.channel_number}.")
        return DthItemState.UNKNOWN, "Submission status ambiguous (not found in table, timed out)", False
