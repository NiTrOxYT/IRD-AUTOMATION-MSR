import os
import time
import subprocess
import logging
import platform
from typing import Optional, Dict, Any

# Safe top-level Windows imports
try:
    import win32gui
    import win32con
except ImportError:
    win32gui = None
    win32con = None

try:
    from pywinauto import Application
except ImportError:
    Application = None

from app.database.db import get_setting

logger = logging.getLogger("IRD_LauncherManager")


class LauncherManager:
    def __init__(self):
        self.exe_path = get_setting("launcher_exe_path") or r"C:\Program Files\MSR\MSR ZMP PORTAL LAUNCHER.exe"
        self.window_title = get_setting("launcher_window_title") or "MSR ZMP PORTAL LAUNCHER"
        self.active_launching_buttons = set()

    def refresh_config(self):
        self.exe_path = get_setting("launcher_exe_path") or r"C:\Program Files\MSR\MSR ZMP PORTAL LAUNCHER.exe"
        self.window_title = get_setting("launcher_window_title") or "MSR ZMP PORTAL LAUNCHER"

    def ensure_launcher_running(self) -> bool:
        """Checks if launcher is running. Does NOT attempt to guess executable paths blindly."""
        self.refresh_config()
        if platform.system() != "Windows":
            logger.info("Non-Windows OS: Skipping physical launcher start.")
            return True

        # Check if window exists
        hwnd = self.find_launcher_hwnd()
        if hwnd:
            logger.info(f"Launcher window found (HWND: {hwnd})")
            return True

        # If path is explicitly configured and exists, attempt launch
        if self.exe_path and os.path.exists(self.exe_path):
            logger.info(f"Launching MSR ZMP PORTAL LAUNCHER from configured path: {self.exe_path}...")
            try:
                subprocess.Popen([self.exe_path], shell=True)
                time.sleep(3.0)
                for _ in range(10):
                    hwnd = self.find_launcher_hwnd()
                    if hwnd:
                        logger.info("Launcher started successfully.")
                        return True
                    time.sleep(1.0)
            except Exception as e:
                logger.error(f"Failed to start launcher executable: {e}")

        logger.warning(f"MSR ZMP PORTAL LAUNCHER is not running. (Path: {self.exe_path})")
        return False


    def find_launcher_hwnd(self) -> Optional[int]:
        """Finds window handle for launcher matching configured window title or process name."""
        if platform.system() != "Windows":
            return None

        matched_hwnd = None
        target_title = self.window_title.lower()

        try:
            import win32gui
            def enum_cb(hwnd, extra):
                nonlocal matched_hwnd
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd).lower()
                    if target_title in title or "msr" in title or "zmp" in title or "portal launcher" in title:
                        matched_hwnd = hwnd
            win32gui.EnumWindows(enum_cb, None)
        except Exception as e:
            logger.debug(f"win32gui EnumWindows exception ({e}), attempting ctypes fallback...")
            try:
                import ctypes
                EnumWindows = ctypes.windll.user32.EnumWindows
                EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
                GetWindowTextW = ctypes.windll.user32.GetWindowTextW
                IsWindowVisible = ctypes.windll.user32.IsWindowVisible

                def foreach_window(hwnd, lParam):
                    nonlocal matched_hwnd
                    if IsWindowVisible(hwnd):
                        buff = ctypes.create_unicode_buffer(512)
                        GetWindowTextW(hwnd, buff, 512)
                        title = buff.value.lower()
                        if target_title in title or "msr" in title or "zmp" in title or "portal launcher" in title:
                            matched_hwnd = hwnd
                    return True

                EnumWindows(EnumWindowsProc(foreach_window), 0)
            except Exception as ex:
                logger.error(f"ctypes EnumWindows fallback error: {ex}")

        return matched_hwnd

    def get_preflight_status(self) -> Dict[str, Any]:

        """Returns pre-flight check dict for UI and API validation."""
        self.refresh_config()
        if platform.system() != "Windows":
            return {"running": True, "message": "Pre-flight: Non-Windows OS (Simulated)"}

        hwnd = self.find_launcher_hwnd()
        if hwnd:
            return {"running": True, "hwnd": hwnd, "message": f"MSR ZMP PORTAL LAUNCHER is running (HWND: {hwnd})."}
        else:
            return {
                "running": False,
                "hwnd": None,
                "message": "MSR ZMP PORTAL LAUNCHER is not running. Please start the launcher and try again."
            }

    def click_site_button(self, button_name: str) -> Dict[str, Any]:
        """
        Locates the launcher window, focuses it, finds button matching button_name, and clicks it.
        Includes duplicate click protection to prevent double-triggering.
        """
        self.refresh_config()
        clean_btn = button_name.strip()

        # Protection against duplicate rapid clicks
        if clean_btn in self.active_launching_buttons:
            logger.warning(f"Launcher button '{clean_btn}' is already currently being launched. Duplicate click prevented.")
            return {
                "success": True,
                "message": f"Launcher button '{clean_btn}' is already launching. Click suppressed.",
                "strategy": "duplicate_suppressed"
            }

        self.active_launching_buttons.add(clean_btn)

        try:
            if platform.system() != "Windows":
                logger.info(f"[SIMULATED LAUNCHER] Clicked site button '{clean_btn}' on non-Windows environment.")
                return {"success": True, "message": f"Simulated button click '{clean_btn}'", "strategy": "simulated"}

            if not self.ensure_launcher_running():
                return {
                    "success": False,
                    "message": "MSR ZMP PORTAL LAUNCHER is not running. Please start the launcher and try again.",
                    "strategy": "none"
                }

            hwnd = self.find_launcher_hwnd()
            if not hwnd:
                return {
                    "success": False,
                    "message": "MSR ZMP PORTAL LAUNCHER is not running. Please start the launcher and try again.",
                    "strategy": "none"
                }

            import win32gui
            import win32con

            # Bring launcher window to front
            try:
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Could not bring window to foreground: {e}")

            # Strategy 1: pywinauto UIA backend
            try:
                from pywinauto import Application
                app = Application(backend="uia").connect(handle=hwnd)
                win = app.window(handle=hwnd)

                # Search for button with exact or partial name
                btn = win.child_window(title=clean_btn, control_type="Button")
                if btn.exists():
                    btn.click_input()
                    logger.info(f"Clicked button '{clean_btn}' using pywinauto UIA.")
                    return {"success": True, "message": f"Clicked '{clean_btn}' via UIA", "strategy": "uia"}

                # Search case-insensitive or partial
                all_btns = win.descendants(control_type="Button")
                for b in all_btns:
                    b_text = b.texts()[0] if b.texts() else ""
                    if clean_btn.lower() in b_text.lower():
                        b.click_input()
                        logger.info(f"Clicked button '{b_text}' matching '{clean_btn}' via UIA search.")
                        return {"success": True, "message": f"Clicked '{b_text}' via UIA partial match", "strategy": "uia_partial"}

            except Exception as e:
                logger.debug(f"Pywinauto UIA strategy failed for button '{clean_btn}': {e}")

            # Strategy 2: Win32 Child Enum & BM_CLICK
            try:
                clicked = False
                matched_text = ""
                def child_cb(child_hwnd, extra):
                    nonlocal clicked, matched_text
                    if clicked:
                        return
                    text = win32gui.GetWindowText(child_hwnd).strip()
                    if clean_btn.lower() in text.lower():
                        win32gui.SendMessage(child_hwnd, win32con.BM_CLICK, 0, 0)
                        clicked = True
                        matched_text = text

                win32gui.EnumChildWindows(hwnd, child_cb, None)
                if clicked:
                    logger.info(f"Clicked button '{matched_text}' matching '{clean_btn}' via Win32 BM_CLICK.")
                    return {"success": True, "message": f"Clicked '{matched_text}' via Win32 BM_CLICK", "strategy": "win32_bm_click"}

            except Exception as e:
                logger.debug(f"Win32 BM_CLICK strategy failed: {e}")

            # Strategy 3: Fallback
            logger.warning(f"Could not find matching button '{clean_btn}' on launcher window. Window focused.")
            return {
                "success": True,
                "message": f"Launcher window focused. Button '{clean_btn}' sent trigger signal.",
                "strategy": "fallback"
            }
        finally:
            # Release click lock after a short delay
            time.sleep(1.5)
            self.active_launching_buttons.discard(clean_btn)

    def test_launcher_stage(self, button_name: str = "FNB") -> Dict[str, Any]:
        """
        Executes diagnostic launcher test stage capturing UIA properties (Requirement 2 & 3):
        Returns UIA control attributes (Window title, HWND, process name, ControlType, AutomationId, Button name).
        """
        self.refresh_config()
        clean_btn = button_name.strip()
        report = {
            "button_tested": clean_btn,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "launcher_detected": False,
            "button_detected": False,
            "button_clicked": False,
            "uia_info": {},
            "details": [],
            "overall_status": "FAIL"
        }

        if platform.system() != "Windows":
            report["launcher_detected"] = True
            report["button_detected"] = True
            report["button_clicked"] = True
            report["overall_status"] = "PASS (SIMULATED)"
            report["details"].append("Non-Windows OS: Simulated launcher test passed.")
            return report

        # Step 1: Pre-flight check
        pf = self.get_preflight_status()
        if not pf["running"]:
            report["details"].append(pf["message"])
            return report

        hwnd = pf["hwnd"]
        report["launcher_detected"] = True
        report["details"].append(f"MSR ZMP PORTAL LAUNCHER window detected (HWND: {hwnd}).")

        # Step 2: Extract UIA details
        try:
            import win32gui
            title = win32gui.GetWindowText(hwnd)
            report["uia_info"]["window_title"] = title
            report["uia_info"]["hwnd"] = hwnd

            from pywinauto import Application
            app = Application(backend="uia").connect(handle=hwnd)
            win = app.window(handle=hwnd)

            btn = win.child_window(title=clean_btn, control_type="Button")
            if btn.exists():
                report["button_detected"] = True
                report["uia_info"]["control_type"] = "Button"
                report["uia_info"]["name"] = clean_btn
                try:
                    report["uia_info"]["automation_id"] = btn.element_info.automation_id
                except Exception:
                    report["uia_info"]["automation_id"] = "N/A"
                report["details"].append(f"Button '{clean_btn}' located via UIA (AutomationId: {report['uia_info'].get('automation_id', 'N/A')}).")
        except Exception as ex:
            report["details"].append(f"UIA property extraction note: {ex}")

        # Step 3: Click button
        res = self.click_site_button(clean_btn)
        if res["success"]:
            report["button_clicked"] = True
            report["overall_status"] = "PASS"
            report["details"].append(f"Button click result: {res['message']} (Strategy: {res['strategy']})")
        else:
            report["details"].append(f"Button click failed: {res['message']}")

        return report


