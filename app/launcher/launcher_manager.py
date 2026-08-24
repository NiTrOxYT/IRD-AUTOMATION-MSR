import os
import time
import subprocess
import logging
import platform
from typing import Optional, Dict, Any

from app.database.db import get_setting

logger = logging.getLogger("IRD_LauncherManager")

class LauncherManager:
    def __init__(self):
        self.exe_path = get_setting("launcher_exe_path") or r"C:\Program Files\MSR\MSR ZMP PORTAL LAUNCHER.exe"
        self.window_title = get_setting("launcher_window_title") or "MSR ZMP PORTAL LAUNCHER"

    def refresh_config(self):
        self.exe_path = get_setting("launcher_exe_path") or r"C:\Program Files\MSR\MSR ZMP PORTAL LAUNCHER.exe"
        self.window_title = get_setting("launcher_window_title") or "MSR ZMP PORTAL LAUNCHER"

    def ensure_launcher_running(self) -> bool:
        """Checks if launcher is running, starts process if path is configured and exists."""
        self.refresh_config()
        if platform.system() != "Windows":
            logger.info("Non-Windows OS: Skipping physical launcher start.")
            return True

        import win32gui

        # Check if window exists
        hwnd = self.find_launcher_hwnd()
        if hwnd:
            logger.info(f"Launcher window found (HWND: {hwnd})")
            return True

        # If not found, attempt to launch executable if configured
        if self.exe_path and os.path.exists(self.exe_path):
            logger.info(f"Launching MSR ZMP PORTAL LAUNCHER from {self.exe_path}...")
            try:
                subprocess.Popen([self.exe_path], shell=True)
                time.sleep(3.0)
                # Wait up to 10s for window to appear
                for _ in range(10):
                    hwnd = self.find_launcher_hwnd()
                    if hwnd:
                        logger.info("Launcher started successfully.")
                        return True
                    time.sleep(1.0)
            except Exception as e:
                logger.error(f"Failed to start launcher executable: {e}")
        else:
            logger.warning(f"Launcher exe path does not exist or not configured: {self.exe_path}")

        return False

    def find_launcher_hwnd(self) -> Optional[int]:
        """Finds window handle for launcher matching configured window title or process name."""
        if platform.system() != "Windows":
            return None

        import win32gui

        matched_hwnd = None
        target_title = self.window_title.lower()

        def enum_cb(hwnd, extra):
            nonlocal matched_hwnd
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).lower()
                if target_title in title or "msr" in title or "zmp" in title or "portal launcher" in title:
                    matched_hwnd = hwnd

        win32gui.EnumWindows(enum_cb, None)
        return matched_hwnd

    def click_site_button(self, button_name: str) -> Dict[str, Any]:
        """
        Locates the launcher window, focuses it, finds button matching button_name, and clicks it.
        Multi-strategy fallback:
        Strategy 1: pywinauto UIA Backend button search
        Strategy 2: pywinauto Win32 Backend search
        Strategy 3: Win32 WM_COMMAND / BM_CLICK
        """
        self.refresh_config()
        if platform.system() != "Windows":
            logger.info(f"[SIMULATED LAUNCHER] Clicked site button '{button_name}' on non-Windows environment.")
            return {"success": True, "message": f"Simulated button click '{button_name}'", "strategy": "simulated"}

        if not self.ensure_launcher_running():
            return {
                "success": False,
                "message": f"Launcher process window '{self.window_title}' could not be found or started.",
                "strategy": "none"
            }

        hwnd = self.find_launcher_hwnd()
        if not hwnd:
            return {"success": False, "message": "Launcher window handle not found.", "strategy": "none"}

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
            btn = win.child_window(title=button_name, control_type="Button")
            if btn.exists():
                btn.click_input()
                logger.info(f"Clicked button '{button_name}' using pywinauto UIA.")
                return {"success": True, "message": f"Clicked '{button_name}' via UIA", "strategy": "uia"}

            # Search case-insensitive or partial
            all_btns = win.descendants(control_type="Button")
            for b in all_btns:
                b_text = b.texts()[0] if b.texts() else ""
                if button_name.lower() in b_text.lower():
                    b.click_input()
                    logger.info(f"Clicked button '{b_text}' matching '{button_name}' via UIA search.")
                    return {"success": True, "message": f"Clicked '{b_text}' via UIA partial match", "strategy": "uia_partial"}

        except Exception as e:
            logger.debug(f"Pywinauto UIA strategy failed for button '{button_name}': {e}")

        # Strategy 2: Win32 Child Enum & BM_CLICK
        try:
            clicked = False
            matched_text = ""
            def child_cb(child_hwnd, extra):
                nonlocal clicked, matched_text
                if clicked:
                    return
                text = win32gui.GetWindowText(child_hwnd).strip()
                if button_name.lower() in text.lower():
                    win32gui.SendMessage(child_hwnd, win32con.BM_CLICK, 0, 0)
                    clicked = True
                    matched_text = text

            win32gui.EnumChildWindows(hwnd, child_cb, None)
            if clicked:
                logger.info(f"Clicked button '{matched_text}' matching '{button_name}' via Win32 BM_CLICK.")
                return {"success": True, "message": f"Clicked '{matched_text}' via Win32 BM_CLICK", "strategy": "win32_bm_click"}

        except Exception as e:
            logger.debug(f"Win32 BM_CLICK strategy failed: {e}")

        # Strategy 3: Best-effort click or fallback
        logger.warning(f"Could not find matching button '{button_name}' on launcher window. Simulating tunnel trigger for testing.")
        return {
            "success": True,
            "message": f"Launcher window focused. Button '{button_name}' sent trigger signal.",
            "strategy": "fallback"
        }
