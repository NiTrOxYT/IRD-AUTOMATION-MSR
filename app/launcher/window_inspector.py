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

        try:
            win32gui.EnumWindows(enum_windows_callback, None)
        except Exception:
            # Fallback to ctypes
            import ctypes
            EnumWindows = ctypes.windll.user32.EnumWindows
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
            GetWindowTextW = ctypes.windll.user32.GetWindowTextW
            IsWindowVisible = ctypes.windll.user32.IsWindowVisible

            def foreach_window(hwnd, lParam):
                if IsWindowVisible(hwnd):
                    buff = ctypes.create_unicode_buffer(512)
                    GetWindowTextW(hwnd, buff, 512)
                    title = buff.value.strip()
                    if title:
                        windows_info.append({
                            "hwnd": hwnd,
                            "title": title,
                            "pid": 0,
                            "process_name": "Desktop Process",
                            "process_path": "",
                            "buttons": []
                        })
                return True

            EnumWindows(EnumWindowsProc(foreach_window), 0)
    except Exception as e:
        logger.error(f"Error inspecting windows: {e}")
        windows_info.append({"title": f"Scan note: {str(e)}", "buttons": []})

    return windows_info

