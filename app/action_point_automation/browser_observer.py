import os
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, Callable

from app.config import SCREENSHOTS_DIR
from app.action_point_automation.models import BrowserSnapshot

logger = logging.getLogger("ActionPoint_Observer")


class ActionPointBrowserObserver:
    """
    Enforces screenshot-first interaction paradigm:
    OBSERVE -> SNAPSHOT -> DECIDE -> ACT -> WAIT -> SNAPSHOT -> VERIFY.
    Captures sequentially numbered PNG screenshots, page title, URL,
    and structured verification results for auditing and diagnostics.
    """

    def __init__(self, run_id: Any, site_name: str = "UnknownSite"):
        self.run_id = run_id
        self.site_name = site_name
        self.step_counter = 0

        date_str = datetime.now().strftime("%Y-%m-%d")
        clean_site = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in str(site_name))
        self.output_dir = SCREENSHOTS_DIR / date_str / clean_site / "action_point" / f"run_{run_id}"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def capture_snapshot(
        self,
        page: Any,
        action_name: str,
        expected_state: Optional[str] = None,
        verification_fn: Optional[Callable[[Dict[str, Any]], Tuple[bool, str]]] = None,
        take_screenshot: bool = True,
        row_number: Optional[int] = None,
        item_code: Optional[str] = None,
        extra_details: Optional[Dict[str, Any]] = None
    ) -> BrowserSnapshot:
        """
        Captures live DOM state, sanitized URL, and screenshot before/after interaction.
        """
        self.step_counter += 1
        seq_str = f"{self.step_counter:03d}"
        clean_action = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in action_name)
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        url = "about:blank"
        title = "Unknown"
        detected_state = "UNKNOWN"
        verification_passed = True
        screenshot_path_str: Optional[str] = None

        if page is not None and not getattr(page, "is_closed", lambda: False)():
            try:
                url = page.url or ""
            except Exception:
                pass
            try:
                title = await page.title() if hasattr(page, "title") else ""
            except Exception:
                pass

        # Verification check
        details = extra_details or {}
        if verification_fn:
            try:
                v_passed, v_state = verification_fn({"url": url, "title": title, "page": page})
                verification_passed = v_passed
                detected_state = v_state
            except Exception as ex:
                verification_passed = False
                detected_state = f"VERIFICATION_ERROR: {ex}"
        elif expected_state:
            detected_state = expected_state

        # Screenshot capture
        if take_screenshot and page is not None and not getattr(page, "is_closed", lambda: False)():
            screenshot_filename = f"{seq_str}_{clean_action}.png"
            screenshot_path = self.output_dir / screenshot_filename
            try:
                if hasattr(page, "screenshot"):
                    await page.screenshot(path=str(screenshot_path), full_page=False)
                    screenshot_path_str = str(screenshot_path)
                    logger.debug(f"[OBSERVER] Saved screenshot: {screenshot_path}")
            except Exception as ss_ex:
                logger.debug(f"[OBSERVER] Screenshot capture error: {ss_ex}")

        snapshot = BrowserSnapshot(
            step_number=self.step_counter,
            timestamp=now_ts,
            action_name=action_name,
            url=url,
            page_title=title,
            expected_state=expected_state,
            detected_state=detected_state,
            verification_passed=verification_passed,
            screenshot_path=screenshot_path_str,
            row_number=row_number,
            item_code=item_code,
            details=details
        )
        return snapshot
