import os
import sys
import asyncio
import logging
import threading
import subprocess
import webbrowser
from pathlib import Path
from typing import List, Dict, Any, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.config import APP_NAME, APP_VERSION, DEFAULT_SETTINGS, DOWNLOADS_DIR, REPORTS_DIR, LOGS_DIR
from app.database.db import (
    init_db, get_all_sites, add_site, update_site, delete_site, update_site_order,
    get_site_by_id, get_all_settings, set_setting, get_runs_history, get_run_details,
    get_all_selectors, save_selector
)
from app.database.seed import seed_default_sites_if_empty
from app.database.models import Site
from app.logging.logger import setup_global_logging, get_recent_logs, memory_log_handler
from app.automation.workflow_runner import workflow_runner
from app.launcher.window_inspector import inspect_all_windows
from app.launcher.launcher_manager import LauncherManager

# 1. Setup Logging & DB
setup_global_logging()
logger = logging.getLogger("IRD_Main")

init_db()
seed_default_sites_if_empty()

# 2. FastAPI Application Setup
app = FastAPI(title=APP_NAME, version=APP_VERSION)

# WebSocket Connections Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_json(self, data: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(data)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

# Hook memory log stream to WebSocket broadcast
def on_new_log(log_entry: dict):
    asyncio.run_coroutine_threadsafe(
        ws_manager.broadcast_json({"type": "log", "data": log_entry}),
        loop=asyncio.get_event_loop()
    )

memory_log_handler.add_listener(on_new_log)

# Hook workflow status changes to WebSocket broadcast
def on_workflow_status(status_payload: dict):
    asyncio.run_coroutine_threadsafe(
        ws_manager.broadcast_json({"type": "status", "data": status_payload}),
        loop=asyncio.get_event_loop()
    )

workflow_runner.add_status_listener(on_workflow_status)

# --- REST API ENDPOINTS ---

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION}

@app.get("/api/sites")
async def list_sites():
    sites = get_all_sites()
    res = []
    for s in sites:
        res.append({
            "id": s.id,
            "name": s.name,
            "launcher_button": s.launcher_button,
            "url": s.url,
            "idp_username": s.idp_username,
            "has_password": bool(s.idp_password),
            "idp_password_masked": "●●●●●●●●" if s.idp_password else "",
            "enabled": s.enabled,
            "sort_order": s.sort_order,
            "notes": s.notes
        })
    return res

@app.post("/api/sites")
async def create_site(data: dict):
    site = Site(
        name=data.get("name", "").strip(),
        launcher_button=data.get("launcher_button", "").strip(),
        url=data.get("url", "").strip(),
        idp_username=data.get("idp_username", "").strip(),
        idp_password=data.get("idp_password", ""),
        enabled=data.get("enabled", True),
        sort_order=int(data.get("sort_order", 0)),
        notes=data.get("notes", "")
    )
    if not site.name or not site.launcher_button:
        raise HTTPException(status_code=400, detail="Site Name and Launcher Button are required.")

    new_id = add_site(site)
    return {"success": True, "site_id": new_id}

@app.put("/api/sites/{site_id}")
async def edit_site(site_id: int, data: dict):
    existing = get_site_by_id(site_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Site not found.")

    existing.name = data.get("name", existing.name).strip()
    existing.launcher_button = data.get("launcher_button", existing.launcher_button).strip()
    existing.url = data.get("url", existing.url).strip()
    existing.idp_username = data.get("idp_username", existing.idp_username).strip()
    if "idp_password" in data and data["idp_password"]:
        existing.idp_password = data["idp_password"]
    existing.enabled = data.get("enabled", existing.enabled)
    existing.sort_order = int(data.get("sort_order", existing.sort_order))
    existing.notes = data.get("notes", existing.notes)

    update_site(existing)
    return {"success": True}

@app.delete("/api/sites/{site_id}")
async def remove_site(site_id: int):
    delete_site(site_id)
    return {"success": True}

@app.post("/api/sites/reorder")
async def reorder_sites(data: list):
    update_site_order(data)
    return {"success": True}

@app.post("/api/sites/{site_id}/test")
async def test_site_connection(site_id: int):
    res = await workflow_runner.run_single_site_test(site_id)
    return res

@app.post("/api/integration-test/run")
async def run_integration_test(data: dict):
    site_id = int(data.get("site_id", 0))
    stage = str(data.get("stage", "full_workflow"))
    if not site_id:
        raise HTTPException(status_code=400, detail="Site ID is required for integration test.")
    res = await workflow_runner.run_integration_test_stage(site_id, stage)
    return res


@app.get("/api/settings")
async def get_settings():
    return get_all_settings()

@app.post("/api/settings")
async def update_settings(data: dict):
    for k, v in data.items():
        set_setting(k, v)
    return {"success": True}

@app.get("/api/selectors")
async def get_selectors():
    return get_all_selectors()

@app.post("/api/selectors")
async def update_selectors(data: dict):
    for step_key, spec in data.items():
        save_selector(
            step_key,
            spec.get("primary", ""),
            json.dumps(spec.get("fallbacks", [])),
            spec.get("description", "")
        )
    return {"success": True}

@app.post("/api/automation/start")
async def start_automation(data: dict):
    if workflow_runner.is_running:
        raise HTTPException(status_code=400, detail="Automation is already running.")

    selected_ids = data.get("site_ids", None)
    dry_run = bool(data.get("dry_run", False))
    resume_run_id = data.get("resume_run_id", None)

    # Launch background task
    asyncio.create_task(workflow_runner.start_batch_sync(
        selected_site_ids=selected_ids,
        dry_run=dry_run,
        resume_run_id=resume_run_id
    ))
    return {"success": True, "message": "Automation started."}

@app.post("/api/automation/stop")
async def stop_automation():
    workflow_runner.stop_automation()
    return {"success": True}

@app.get("/api/automation/status")
async def automation_status():
    return {
        "is_running": workflow_runner.is_running,
        "run_id": workflow_runner.current_run_id,
        "current_site_id": workflow_runner.current_site_id,
        "current_site_name": workflow_runner.current_site_name,
        "status": str(workflow_runner.current_status),
        "operation": workflow_runner.current_operation,
        "details": workflow_runner.current_status_details,
        "progress_percentage": workflow_runner.progress_percentage
    }

@app.get("/api/history")
async def run_history():
    return get_runs_history(limit=50)

@app.get("/api/history/{run_id}")
async def run_detail(run_id: int):
    details = get_run_details(run_id)
    if not details:
        raise HTTPException(status_code=404, detail="Run not found.")
    return details

@app.get("/api/diagnostics/windows")
async def scan_windows():
    return inspect_all_windows()

@app.post("/api/launcher/test")
async def test_launcher():
    mgr = LauncherManager()
    ok = mgr.ensure_launcher_running()
    return {"success": ok, "message": "Launcher process running and window detected." if ok else "Launcher window not found."}

@app.get("/api/logs/recent")
async def get_logs():
    return get_recent_logs(limit=200)

@app.get("/api/open-folder/reports")
async def open_reports_folder():
    path = str(REPORTS_DIR)
    if os.name == 'nt':
        os.startfile(path)
    return {"success": True}

@app.get("/api/open-folder/downloads")
async def open_downloads_folder():
    path = str(DOWNLOADS_DIR)
    if os.name == 'nt':
        os.startfile(path)
    return {"success": True}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

# Mount Static UI Files
UI_DIR = Path(__file__).parent / "ui"
app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")

@app.get("/")
async def serve_index():
    index_file = UI_DIR / "index.html"
    return FileResponse(str(index_file))

# --- SERVER & DESKTOP WINDOW MANAGEMENT ---

def start_desktop_app():
    port = int(DEFAULT_SETTINGS["port"])
    server_url = f"http://127.0.0.1:{port}"

    # Start FastAPI Uvicorn Server in daemon thread
    def run_server():
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    logger.info(f"IRD Sync Automation server started at {server_url}")

    # Launch PyWebView Native Desktop Window
    try:
        import webview
        logger.info("Opening PyWebView desktop window...")
        window = webview.create_window(
            title=f"{APP_NAME} v{APP_VERSION}",
            url=server_url,
            width=1400,
            height=900,
            resizable=True,
            min_size=(1024, 700)
        )
        webview.start()
    except Exception as e:
        logger.warning(f"PyWebView could not open window ({e}). Opening fallback in default browser...")
        webbrowser.open(server_url)
        # Keep process alive
        server_thread.join()

if __name__ == "__main__":
    start_desktop_app()
