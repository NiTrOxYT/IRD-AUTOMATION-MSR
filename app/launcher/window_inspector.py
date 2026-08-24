import logging
import platform
from typing import List, Dict, Any

logger = logging.getLogger("IRD_WindowInspector")

def inspect_all_windows() -> List[Dict[str, Any]]:
    """
    Scans active Windows top-level windows and button controls.
    Returns details for UI diagnostics.
    """
    windows_info = []
    if platform.system() != "Windows":
        return [{"title": "Non-Windows environment", "process": "N/A", "buttons": []}]

    try:
        import win32gui
        import win32process
        import psutil
        from pywinauto import Desktop

        def enum_windows_callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                if title:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    proc_name = "Unknown"
                    proc_path = ""
                    try:
                        p = psutil.Process(pid)
                        proc_name = p.name()
                        proc_path = p.exe()
                    except Exception:
                        pass

                    # Enum child buttons
                    child_buttons = []
                    def enum_child_callback(child_hwnd, child_extra):
                        class_name = win32gui.GetClassName(child_hwnd)
                        child_text = win32gui.GetWindowText(child_hwnd).strip()
                        if "button" in class_name.lower() or child_text:
                            if child_text:
                                child_buttons.append({"text": child_text, "class": class_name})

                    try:
                        win32gui.EnumChildWindows(hwnd, enum_child_callback, None)
                    except Exception:
                        pass

                    windows_info.append({
                        "hwnd": hwnd,
                        "title": title,
                        "pid": pid,
                        "process_name": proc_name,
                        "process_path": proc_path,
                        "buttons": child_buttons
                    })

        win32gui.EnumWindows(enum_windows_callback, None)
    except Exception as e:
        logger.error(f"Error inspecting windows: {e}")
        windows_info.append({"title": f"Scan error: {str(e)}", "buttons": []})

    return windows_info
