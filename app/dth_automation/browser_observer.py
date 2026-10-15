import os
import re
import json
import time
import urllib.parse
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Callable
from playwright.async_api import Page, Frame

from app.config import LOGS_DIR
from app.dth_automation.models import BrowserSnapshot, DthWorkflowState

logger = logging.getLogger("DTH_BrowserObserver")

SENSITIVE_PARAM_KEYS = {
    "password", "pass", "pwd", "token", "secret", "auth",
    "key", "session", "sessionid", "jsessionid", "ticket"
}


def sanitize_url(raw_url: str) -> str:
    """Removes sensitive credentials or tokens from URL query parameters."""
    if not raw_url:
        return ""
    try:
        parsed = urllib.parse.urlsplit(raw_url)
        if not parsed.query:
            return raw_url
        query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        sanitized_pairs = []
        for k, v in query_pairs:
            if k.lower() in SENSITIVE_PARAM_KEYS or any(s in k.lower() for s in ["token", "secret", "pass"]):
                sanitized_pairs.append((k, "[REDACTED]"))
            else:
                sanitized_pairs.append((k, v))
        sanitized_query = urllib.parse.urlencode(sanitized_pairs)
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, sanitized_query, parsed.fragment))
    except Exception:
        return raw_url


def sanitize_text(text: str) -> str:
    """Masks obvious password or token values in text snippets."""
    if not text:
        return ""
    redacted = re.sub(r'(-pw\s+)(\S+)', r'\1[REDACTED]', text, flags=re.IGNORECASE)
    redacted = re.sub(r'(password=)([^&\s]+)', r'\1[REDACTED]', redacted, flags=re.IGNORECASE)
    redacted = re.sub(r'(token=)([^&\s]+)', r'\1[REDACTED]', redacted, flags=re.IGNORECASE)
    return redacted


class BrowserObserver:
    """
    Structured, contract-driven observer for browser automation.
    Enforces: OBSERVE -> DECIDE -> ACT -> WAIT -> SNAPSHOT -> VERIFY -> PROCEED.
    Captures sequentially numbered PNG screenshots and sanitized JSON DOM states.
    """

    def __init__(self, run_id: Any):
        self.run_id = str(run_id)
        self.step_counter = 0
        self.history: List[BrowserSnapshot] = []
        self.output_dir = Path(LOGS_DIR) / "dth" / f"run_{self.run_id}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[OBSERVER] Initialized for run #{self.run_id} at {self.output_dir}")

    async def capture_snapshot(
        self,
        page: Optional[Page],
        action_name: str,
        expected_state: Optional[str] = None,
        verification_fn: Optional[Callable[[Dict[str, Any]], Tuple[bool, str]]] = None,
        take_screenshot: bool = True
    ) -> BrowserSnapshot:
        """
        Captures a live DOM snapshot, accessibility elements, sanitized URL, and screenshot.
        Verifies against expected_state or verification_fn.
        Executes DOM extraction in-browser in <2ms to avoid hundreds of sequential CDP roundtrips.
        """
        self.step_counter += 1
        seq_str = f"{self.step_counter:03d}"
        clean_action = re.sub(r'[^a-zA-Z0-9_\-]', '_', action_name).strip('_').lower()
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        screenshot_filename = f"{seq_str}_{clean_action}.png"
        snapshot_filename = f"{seq_str}_{clean_action}.json"
        screenshot_path = self.output_dir / screenshot_filename
        snapshot_path = self.output_dir / snapshot_filename

        if not page or page.is_closed():
            snapshot = BrowserSnapshot(
                step_number=self.step_counter,
                action_name=action_name,
                url="about:blank",
                title="Page Closed",
                detected_state=DthWorkflowState.FAILED.value,
                verification_passed=False,
                verification_notes="Browser page is not open or was closed.",
                timestamp=timestamp
            )
            self._save_snapshot_json(snapshot, snapshot_path)
            self.history.append(snapshot)
            return snapshot

        # 1. Capture live page properties
        raw_url = page.url or ""
        clean_url = sanitize_url(raw_url)
        title = ""
        try:
            title = await page.title()
        except Exception:
            title = "Unknown"

        # 2. Capture Frame Hierarchy
        child_frames = []
        try:
            for f in page.frames[1:]:
                child_frames.append(sanitize_url(f.url))
        except Exception:
            pass

        # 3. High-Speed In-Browser DOM Extraction (<2ms)
        headings: List[str] = []
        inputs_summary: List[Dict[str, Any]] = []
        buttons_summary: List[str] = []
        text_summary: str = ""
        dom_extracted = False

        try:
            dom_data = await page.evaluate('''() => {
                // 1. Headings
                const headings = [];
                const hEls = document.querySelectorAll("h1, h2, h3, h4, .page-title, .title, legend");
                for (let i = 0; i < hEls.length && headings.length < 10; i++) {
                    const el = hEls[i];
                    if (el.offsetParent !== null) {
                        const txt = (el.innerText || el.textContent || "").trim();
                        if (txt) headings.push(txt.slice(0, 100));
                    }
                }

                // 2. Visible Inputs
                const inputs = [];
                const inpEls = document.querySelectorAll("input, select, textarea");
                for (let i = 0; i < inpEls.length && inputs.length < 30; i++) {
                    const inp = inpEls[i];
                    if (inp.offsetParent !== null) {
                        const tag = inp.tagName.toLowerCase();
                        const itype = (inp.getAttribute("type") || "text").toLowerCase();
                        const name = inp.getAttribute("name") || "";
                        const iid = inp.getAttribute("id") || "";
                        let val = "";
                        if (tag === "input" || tag === "textarea") {
                            if (itype !== "file") {
                                val = (inp.value || "").slice(0, 50);
                            }
                        }
                        inputs.push({ tag, type: itype, name, id: iid, value: val });
                    }
                }

                // 3. Visible Buttons and Clickables
                const buttons = [];
                const seen = new Set();
                const btnEls = document.querySelectorAll("button, input[type='submit'], input[type='button'], a.btn, a.button, a[href*='logout'], a.k-button, a.k-grid-add, a.k-grid-update, a.k-grid-cancel, a.k-grid-edit, a");
                for (let i = 0; i < btnEls.length && buttons.length < 25; i++) {
                    const b = btnEls[i];
                    if (b.offsetParent !== null) {
                        const txt = (b.innerText || b.textContent || b.value || "").trim().slice(0, 40);
                        if (txt && txt.length < 40 && !seen.has(txt)) {
                            const lower = txt.toLowerCase();
                            if (b.tagName.toLowerCase() === "button" || b.getAttribute("type") || lower.includes("save") || lower.includes("add") || lower.includes("edit") || lower.includes("logout") || lower.includes("login") || lower.includes("cancel") || lower.includes("submit") || b.classList.contains("btn") || b.classList.contains("button") || b.classList.contains("k-button") || b.classList.contains("k-grid-add") || b.classList.contains("k-grid-update") || b.classList.contains("k-grid-edit")) {
                                seen.add(txt);
                                buttons.push(txt);
                            }
                        }
                    }
                }

                // 4. Text Summary
                const bodyText = document.body ? (document.body.innerText || "") : "";
                const lines = bodyText.split('\\n').map(l => l.trim()).filter(Boolean).slice(0, 12);
                const textSummary = lines.join(" | ").slice(0, 300);

                return { headings, inputs, buttons, textSummary };
            }''')

            if isinstance(dom_data, dict):
                headings = [sanitize_text(h) for h in dom_data.get("headings", [])]
                for inp in dom_data.get("inputs", []):
                    itype = inp.get("type", "").lower()
                    name = inp.get("name", "")
                    val = inp.get("value", "")
                    if itype == "password" or "pass" in name.lower():
                        val = "[MASKED_PASSWORD]" if val else ""
                    else:
                        val = sanitize_text(val)
                    inputs_summary.append({
                        "tag": inp.get("tag", "input"),
                        "type": itype,
                        "name": name,
                        "id": inp.get("id", ""),
                        "value": val
                    })
                buttons_summary = [sanitize_text(b) for b in dom_data.get("buttons", [])]
                text_summary = sanitize_text(dom_data.get("textSummary", ""))
                dom_extracted = True
        except Exception as eval_ex:
            logger.debug(f"[OBSERVER] In-browser DOM extraction noticed: {eval_ex}")

        # Fallback if evaluate failed
        if not dom_extracted:
            try:
                body_text = await page.inner_text("body")
                lines = [l.strip() for l in body_text.splitlines() if l.strip()]
                text_summary = sanitize_text(" | ".join(lines[:12])[:300])
            except Exception:
                pass

        # 7. Classify Detected State
        detected_state, detected_auth = self._classify_page_state(clean_url, title, inputs_summary, buttons_summary, text_summary)

        # 8. Verification Contract
        verification_passed = True
        verification_notes = f"Observed state: {detected_state}"

        if expected_state:
            if detected_state != expected_state and expected_state not in detected_state:
                verification_passed = False
                verification_notes = f"Expected state '{expected_state}' but observed '{detected_state}' at {clean_url}"

        if verification_fn:
            obs_dict = {
                "url": clean_url,
                "title": title,
                "detected_state": detected_state,
                "inputs": inputs_summary,
                "buttons": buttons_summary,
                "headings": headings
            }
            try:
                fn_ok, fn_msg = verification_fn(obs_dict)
                if not fn_ok:
                    verification_passed = False
                    verification_notes = fn_msg
                else:
                    verification_notes = f"{verification_notes} (Custom verification: {fn_msg})"
            except Exception as ver_ex:
                verification_passed = False
                verification_notes = f"Verification function error: {ver_ex}"

        # 9. Smart Screenshot Capture (Fast on success, guaranteed on failure/error)
        screenshot_str = None
        if take_screenshot or not verification_passed:
            try:
                await page.screenshot(path=str(screenshot_path), full_page=False)
                screenshot_str = str(screenshot_path)
            except Exception as ss_ex:
                logger.debug(f"[OBSERVER] Screenshot capture error: {ss_ex}")

        snapshot = BrowserSnapshot(
            step_number=self.step_counter,
            action_name=action_name,
            url=clean_url,
            title=title,
            detected_state=detected_state,
            main_frame_url=clean_url,
            child_frame_urls=child_frames,
            visible_headings=headings,
            visible_text_summary=text_summary,
            visible_buttons=buttons_summary,
            visible_inputs=inputs_summary,
            detected_auth_state=detected_auth,
            verification_passed=verification_passed,
            verification_notes=verification_notes,
            screenshot_path=screenshot_str,
            snapshot_path=str(snapshot_path),
            timestamp=timestamp
        )

        self._save_snapshot_json(snapshot, snapshot_path)
        self.history.append(snapshot)
        logger.info(f"[SNAPSHOT {seq_str}] {action_name.upper()} | State: {detected_state} | Verify: {'PASS' if verification_passed else 'FAIL'} | URL: {clean_url}")
        return snapshot

    def _classify_page_state(
        self,
        url: str,
        title: str,
        inputs: List[Dict[str, Any]],
        buttons: List[str],
        text_summary: str
    ) -> Tuple[str, str]:
        """Classifies the actual live portal state based on observed controls and text."""
        url_lower = url.lower()
        title_lower = title.lower()
        summary_lower = text_summary.lower()

        has_username = any(i["name"].lower() in ["j_username", "username", "login", "userid"] for i in inputs)
        has_password = any(i["type"] == "password" or i["name"].lower() in ["j_password", "password"] for i in inputs)
        has_channel_num = any("channel" in i["name"].lower() or i["name"].lower() == "channelnumber" for i in inputs)
        has_logout = any("logout" in b.lower() for b in buttons) or "logout" in summary_lower or "j_spring_security_logout" in url_lower

        # Error page check
        if any(err in summary_lower or err in title_lower for err in ["500 internal server error", "whitelabel error page", "403 forbidden", "access denied", "404 not found"]):
            return DthWorkflowState.FAILED.value, "UNAUTHENTICATED"

        # Explicit login form
        if has_username and has_password:
            return DthWorkflowState.AUTHENTICATION_REQUIRED.value, "LOGIN_FORM_PRESENT"

        # Channel Form / Edit / Add controls check
        if has_channel_num and any(b.lower() in ["save", "submit"] for b in buttons):
            return DthWorkflowState.CHANNEL_FORM_VERIFIED.value, "AUTHENTICATED"

        # Channel Page / Listing check
        if "manage-stb-channels" in url_lower or (has_channel_num and not has_username):
            return DthWorkflowState.CHANNEL_PAGE_OPENED.value, "AUTHENTICATED"

        # Explicit login URL (only when not on channel page)
        if "login.do" in url_lower:
            return DthWorkflowState.AUTHENTICATION_REQUIRED.value, "LOGIN_PAGE"

        # Authenticated Dashboard / Main Menu
        if has_logout or "main-menu" in url_lower or ("smartler" in summary_lower and "dashboard" in summary_lower):
            return DthWorkflowState.AUTHENTICATED.value, "AUTHENTICATED"

        # Fallback login indicator
        if "login" in url_lower and not has_logout:
            return DthWorkflowState.AUTHENTICATION_REQUIRED.value, "LOGIN_PAGE"

        return DthWorkflowState.UNKNOWN.value, "UNKNOWN"

    def _save_snapshot_json(self, snapshot: BrowserSnapshot, filepath: Path):
        """Saves sanitized snapshot model to disk."""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(snapshot.model_dump(), f, indent=2)
        except Exception as ex:
            logger.debug(f"[OBSERVER] Error saving snapshot JSON: {ex}")

    def get_latest_snapshot(self) -> Optional[BrowserSnapshot]:
        return self.history[-1] if self.history else None
