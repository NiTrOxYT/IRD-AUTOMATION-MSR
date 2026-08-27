import os
import sys
import json
import asyncio
import logging
import threading
import subprocess
import webbrowser
from pathlib import Path
from typing import List, Dict, Any, Optional

# Ensure project root is in sys.path for top-level app imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
from app.app_logging.logger import setup_global_logging, get_recent_logs, memory_log_handler
from app.automation.workflow_runner import workflow_runner
from app.launcher.window_inspector import inspect_all_windows
from app.launcher.launcher_manager import LauncherManager
from app.tunneling import port_manager, putty_manager, tunnel_manager
from app.diagnostics import package_validator

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
main_event_loop: Optional[asyncio.AbstractEventLoop] = None

@app.on_event("startup")
async def startup_event():
    global main_event_loop
    main_event_loop = asyncio.get_running_loop()

def safe_broadcast(payload: dict):
    global main_event_loop
    try:
        loop = main_event_loop
        if loop is None or not loop.is_running():
            loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(ws_manager.broadcast_json(payload), loop)
    except Exception:
        pass

# Hook memory log stream to WebSocket broadcast
def on_new_log(log_entry: dict):
    safe_broadcast({"type": "log", "data": log_entry})

memory_log_handler.add_listener(on_new_log)

# Hook workflow status changes to WebSocket broadcast
def on_workflow_status(status_payload: dict):
    safe_broadcast({"type": "status", "data": status_payload})

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
            "notes": s.notes,
            "site_ip": s.site_ip or s.remote_host,
            "site_port": getattr(s, "site_port", 80) or 80,
            "local_port": s.local_port or 18001,
            "web_url": s.web_url or f"http://127.0.0.1:{s.local_port or 18001}"
        })
    return res

@app.post("/api/sites")
async def create_site(data: dict):
    from app.database.db import validate_site_port, validate_local_port_collision

    site_port_raw = data.get("site_port", 80)
    p_ok, p_err = validate_site_port(site_port_raw)
    if not p_ok:
        raise HTTPException(status_code=400, detail=p_err)

    local_port = int(data.get("local_port", 18001))
    enabled = bool(data.get("enabled", True))
    c_ok, c_err = validate_local_port_collision(None, local_port, enabled)
    if not c_ok:
        raise HTTPException(status_code=400, detail=c_err)

    site = Site(
        name=data.get("name", "").strip(),
        launcher_button=data.get("launcher_button", data.get("name", "")).strip(),
        url=data.get("url", "").strip(),
        idp_username=data.get("idp_username", "").strip(),
        idp_password=data.get("idp_password", ""),
        enabled=enabled,
        sort_order=int(data.get("sort_order", 0)),
        notes=data.get("notes", ""),
        site_ip=data.get("site_ip", "").strip(),
        site_port=int(site_port_raw),
        local_port=local_port
    )
    if not site.name:
        raise HTTPException(status_code=400, detail="Site Name is required.")

    new_id = add_site(site)
    return {"success": True, "site_id": new_id}

@app.put("/api/sites/{site_id}")
async def edit_site(site_id: int, data: dict):
    from app.database.db import validate_site_port, validate_local_port_collision

    existing = get_site_by_id(site_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Site not found.")

    existing.name = data.get("name", existing.name).strip()
    existing.launcher_button = data.get("launcher_button", existing.name).strip()
    existing.url = data.get("url", existing.url).strip()
    existing.idp_username = data.get("idp_username", existing.idp_username).strip()
    if "idp_password" in data and data["idp_password"]:
        existing.idp_password = data["idp_password"]
    existing.enabled = data.get("enabled", existing.enabled)
    existing.sort_order = int(data.get("sort_order", existing.sort_order))
    existing.notes = data.get("notes", existing.notes)

    if "site_ip" in data:
        existing.site_ip = data["site_ip"].strip()

    if "site_port" in data:
        p_ok, p_err = validate_site_port(data["site_port"])
        if not p_ok:
            raise HTTPException(status_code=400, detail=p_err)
        existing.site_port = int(data["site_port"])

    if "local_port" in data:
        target_local_port = int(data["local_port"])
        c_ok, c_err = validate_local_port_collision(site_id, target_local_port, existing.enabled)
        if not c_ok:
            raise HTTPException(status_code=400, detail=c_err)
        existing.local_port = target_local_port

    if "web_url" in data:
        existing.web_url = data["web_url"].strip()

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

@app.post("/api/sites/{site_id}/remote-connectivity-test")
async def test_remote_connectivity_endpoint(site_id: int):
    site = get_site_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found.")
    res = await tunnel_manager.test_remote_site_connectivity(site)
    return res


@app.post("/api/integration-test/run")
async def run_integration_test(data: dict):
    site_id = int(data.get("site_id", 0))
    stage = str(data.get("stage", "full_workflow"))
    logger.info(f"INFO | Integration test request received | Site ID: {site_id} | Stage: {stage}")
    if not site_id:
        raise HTTPException(status_code=400, detail="Site ID is required for integration test.")
    try:
        res = await workflow_runner.run_integration_test_stage(site_id, stage)
        return res
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"Error executing integration test stage '{stage}': {e}\n{tb}")
        return {
            "success": False,
            "stage": stage,
            "message": f"Server exception during integration test: {str(e)}",
            "traceback": tb,
            "details": [f"Exception: {str(e)}"]
        }

@app.post("/api/integration-test/stop")
async def stop_integration_test():
    logger.info("INFO | Integration test stop request received.")
    workflow_runner.stop_automation()
    return {"success": True, "message": "Integration test stop signal sent."}

@app.post("/api/tunnel/detect")
async def detect_putty():
    res = putty_manager.detect_executables()
    return res

@app.post("/api/sites/{site_id}/tunnel/test")
async def test_site_tunnel(site_id: int):
    site = get_site_by_id(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found.")
    timeout = int(get_all_settings().get("tunnel_start_timeout", 30))
    ok, msg, details = await tunnel_manager.start_and_verify_tunnel(site, timeout_seconds=timeout)
    return {
        "success": ok,
        "site": site.name,
        "message": msg,
        "details": details
    }

@app.get("/api/tunnels/status")
async def get_tunnels_status():
    sites = get_all_sites()
    return [tunnel_manager.get_tunnel_status(s) for s in sites]

@app.get("/api/diagnostics/package-health")
async def get_package_health():
    return package_validator.validate_package_health()

@app.post("/api/tunnel/test-plink")
async def test_plink():
    return putty_manager.test_plink_executable()

@app.get("/api/tunnel/info")
async def get_tunnel_info():
    return putty_manager.detect_executables()





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
    if hasattr(os, "startfile"):
        getattr(os, "startfile")(path)
    return {"success": True}

@app.get("/api/open-folder/downloads")
async def open_downloads_folder():
    path = str(DOWNLOADS_DIR)
    if hasattr(os, "startfile"):
        getattr(os, "startfile")(path)
    return {"success": True}

# --- PHASE 5B: REAL FNB TUNNEL ENDPOINTS ---

@app.get("/api/fnb-tunnel/config")
async def get_fnb_config():
    from app.database.db import get_site_by_id, get_site_by_name, get_all_sites, get_office_ssh_config
    all_s = get_all_sites()
    site = get_site_by_id(1) or get_site_by_name("FNB") or (all_s[0] if all_s else None)
    if not site:
        raise HTTPException(status_code=404, detail="FNB Site configuration not found.")

    off_ssh = get_office_ssh_config()
    return {
        "site_id": site.id,
        "name": site.name,
        "enabled": site.enabled,
        "site_ip": site.site_ip or site.remote_host or "127.0.0.1",
        "ssh_host": site.ssh_host or off_ssh.get("ssh_host") or "111.93.205.187",
        "ssh_port": site.ssh_port or off_ssh.get("ssh_port") or 22,
        "ssh_username": site.ssh_username or off_ssh.get("ssh_username") or "sourik",
        "auth_type": site.auth_type or off_ssh.get("auth_type") or "password",
        "ssh_key_path": site.ssh_key_path or off_ssh.get("ssh_key_path") or "",
        "has_ssh_password": bool(site.ssh_password or off_ssh.get("password_configured")),
        "local_port": site.local_port or 18001,
        "web_url": site.web_url or f"http://127.0.0.1:{site.local_port or 18001}"
    }


@app.post("/api/fnb-tunnel/config")
async def update_fnb_config(data: dict):
    from app.database.db import get_site_by_id, get_site_by_name, update_site
    site = get_site_by_id(1) or get_site_by_name("FNB")
    if not site:
        raise HTTPException(status_code=404, detail="FNB Site configuration not found.")

    if "ssh_host" in data:
        site.ssh_host = data["ssh_host"].strip()
    if "ssh_port" in data:
        site.ssh_port = int(data["ssh_port"])
    if "ssh_username" in data:
        site.ssh_username = data["ssh_username"].strip()
    if "auth_type" in data:
        site.auth_type = data["auth_type"].strip()
    if "ssh_key_path" in data:
        site.ssh_key_path = data["ssh_key_path"].strip()
    if "ssh_password" in data and data["ssh_password"]:
        site.ssh_password = data["ssh_password"]
    if "local_port" in data:
        site.local_port = int(data["local_port"])
    if "remote_host" in data:
        site.remote_host = data["remote_host"].strip()
    if "remote_port" in data:
        site.remote_port = int(data["remote_port"])
    if "tunnel_type" in data:
        site.tunnel_type = data["tunnel_type"].strip()
    if "web_url" in data:
        site.web_url = data["web_url"].strip()

    update_site(site)
    return {"success": True, "message": "FNB SSH Tunnel configuration updated successfully."}

# --- OFFICE SSH SERVER ENDPOINTS ---

@app.get("/api/settings/ssh")
async def get_office_ssh_settings():
    from app.database.db import get_office_ssh_config
    return get_office_ssh_config()

@app.post("/api/settings/ssh")
async def update_office_ssh_settings(data: dict):
    from app.database.db import set_office_ssh_config
    set_office_ssh_config(data)
    return {"success": True, "message": "Office SSH configuration saved."}

@app.post("/api/settings/ssh/test")
async def test_office_ssh():
    res = await tunnel_manager.test_office_ssh_connection()
    return res

@app.get("/api/settings/tunnel")
async def get_global_tunnel_settings():
    from app.database.db import get_global_tunnel_config
    return get_global_tunnel_config()

@app.post("/api/settings/tunnel")
async def update_global_tunnel_settings(data: dict):
    from app.database.db import set_global_tunnel_config
    set_global_tunnel_config(data)
    return {"success": True, "message": "Global Reverse SSH Tunnel configuration saved."}



@app.post("/api/fnb-tunnel/test")
async def run_fnb_tunnel_test(data: dict = None):
    from app.database.db import get_site_by_id, get_site_by_name
    site = get_site_by_id(1) or get_site_by_name("FNB")
    if not site:
        raise HTTPException(status_code=404, detail="FNB site record not found.")

    keep_running = bool((data or {}).get("keep_running", False))
    res = await tunnel_manager.run_fnb_tunnel_test(site, keep_running=keep_running)
    return res

@app.post("/api/fnb-tunnel/webpage-test")
async def run_fnb_webpage_test():
    from app.database.db import get_site_by_id, get_site_by_name
    site = get_site_by_id(1) or get_site_by_name("FNB")
    if not site:
        raise HTTPException(status_code=404, detail="FNB site record not found.")

    res = await tunnel_manager.open_fnb_webpage_test(site)
    return res

@app.post("/api/fnb-tunnel/playwright-test")
async def run_fnb_playwright_test():
    from app.database.db import get_site_by_id, get_site_by_name, get_all_sites
    all_s = get_all_sites()
    site = get_site_by_id(1) or get_site_by_name("FNB") or (all_s[0] if all_s else None)
    if not site:
        raise HTTPException(status_code=404, detail="FNB site record not found.")

    res = await tunnel_manager.test_playwright_tunnel(site)
    return res

@app.post("/api/fnb-tunnel/login-workflow")
async def run_fnb_login_workflow(data: dict = None):
    from app.database.db import get_site_by_id, get_site_by_name, get_all_sites, get_global_tunnel_config
    all_s = get_all_sites()
    site = get_site_by_id(1) or get_site_by_name("FNB") or (all_s[0] if all_s else None)
    if not site:
        raise HTTPException(status_code=404, detail="FNB site record not found.")

    # 1. Ensure Reverse Tunnel is started and 3-tier validated
    t_res = await tunnel_manager.run_fnb_tunnel_test(site, keep_running=True)
    if t_res["result_status"] != "REAL FNB TUNNEL — PASS" and t_res["checks"].get("fnb_service") != "PASS":
        # Do NOT open browser if tunnel validation failed
        return {
            "success": False,
            "result_status": "TUNNEL_FAILED",
            "failure_code": t_res.get("failure_code", "TUNNEL_ESTABLISH_FAILED"),
            "logs": t_res.get("logs", []) + ["CRITICAL: Reverse SSH Tunnel validation failed. Aborting browser login workflow."],
            "formatted_summary": t_res.get("formatted_summary", "")
        }

    # 2. Compute Target Web URL
    g_tunnel = get_global_tunnel_config()
    local_port = site.local_port or 18001
    tmpl = g_tunnel.get("web_url_template", "http://127.0.0.1:{local_port}")
    web_url = tmpl.format(local_port=local_port) if "{local_port}" in tmpl else f"http://127.0.0.1:{local_port}"

    # 3. Execute Phase 6 Browser Login + Sync MyMenu Sequence
    from app.browser.browser_controller import browser_controller
    res = await browser_controller.run_fnb_login_and_sync_mymenu(site, web_url)
    return res

@app.post("/api/fnb-tunnel/fetch-workflow")
async def run_fnb_fetch_workflow(data: dict = None):
    from app.database.db import get_site_by_id, get_site_by_name, get_all_sites, get_global_tunnel_config
    all_s = get_all_sites()
    site = get_site_by_id(1) or get_site_by_name("FNB") or (all_s[0] if all_s else None)
    if not site:
        raise HTTPException(status_code=404, detail="FNB site record not found.")

    # 1. Ensure Reverse Tunnel is started and 3-tier validated
    t_res = await tunnel_manager.run_fnb_tunnel_test(site, keep_running=True)
    if t_res["result_status"] != "REAL FNB TUNNEL — PASS" and t_res["checks"].get("fnb_service") != "PASS":
        # Do NOT open browser if tunnel validation failed
        return {
            "success": False,
            "result_status": "TUNNEL_FAILED",
            "failure_code": t_res.get("failure_code", "TUNNEL_ESTABLISH_FAILED"),
            "logs": t_res.get("logs", []) + ["CRITICAL: Reverse SSH Tunnel validation failed. Aborting Fetch Menu workflow."],
            "formatted_summary": t_res.get("formatted_summary", "")
        }

    # 2. Compute Target Web URL
    from app.database.models import get_site_web_url
    web_url = get_site_web_url(site)

    # 3. Execute Phase 7 FNB Fetch Menu Sequence
    from app.browser.browser_controller import browser_controller
    res = await browser_controller.run_fnb_fetch_menu_workflow(site, web_url)
    return res

@app.post("/api/diagnostics/stage-test")
async def run_stage_test(data: dict = None):
    data = data or {}
    site_id = data.get("site_id", 1)
    stage_key = data.get("stage_key", "backend_test")

    from app.database.db import get_site_by_id, get_all_sites
    from app.database.models import get_site_web_url
    all_s = get_all_sites()
    site = get_site_by_id(site_id) or (all_s[0] if all_s else None)
    if not site:
        raise HTTPException(status_code=404, detail="Site record not found.")

    web_url = get_site_web_url(site)


    logs = [f"Executing Integration Test Stage: '{stage_key}' for Site '{site.name}'..."]

    if stage_key == "backend_test":
        await asyncio.sleep(1.0)
        logs.append("✓ Diagnostic Backend Test PASS. Backend API is responsive.")
        return {"success": True, "stage": stage_key, "logs": logs, "result": "PASS"}

    elif stage_key == "package_check":
        from app.diagnostics.package_validator import package_validator
        res = package_validator.run_full_validation()
        logs.append(f"Package Validation Result: {res['overall_status']}")
        return {"success": res["all_ok"], "stage": stage_key, "logs": logs, "result": res["overall_status"]}

    elif stage_key == "plink_check":
        res = await tunnel_manager.test_office_ssh_connection()
        return {"success": res.get("success", False), "stage": stage_key, "logs": logs + res.get("logs", []), "result": res.get("result_message", "COMPLETED")}

    elif stage_key in ("start_tunnel", "port_check"):
        res = await tunnel_manager.run_fnb_tunnel_test(site, keep_running=True)
        return {"success": res["result_status"] == "REAL FNB TUNNEL — PASS", "stage": stage_key, "logs": logs + res.get("logs", []), "result": res["result_status"]}

    elif stage_key == "tunnel_webpage":
        res = await tunnel_manager.open_fnb_webpage_test(site)
        return {"success": res.get("result") == "PASS", "stage": stage_key, "logs": logs + res.get("logs", []), "result": res.get("result", "COMPLETED")}

    elif stage_key in ("login", "sync_mymenu"):
        from app.browser.browser_controller import browser_controller
        res = await browser_controller.run_fnb_login_and_sync_mymenu(site, web_url)
        return {"success": res.get("result_status") == "PASS", "stage": stage_key, "logs": logs + res.get("logs", []), "result": res.get("result_status", "COMPLETED")}

    elif stage_key in ("fetch_menu", "full_workflow"):
        from app.browser.browser_controller import browser_controller
        res = await browser_controller.run_fnb_fetch_menu_workflow(site, web_url)
        return {"success": res.get("result_status") == "PASS", "stage": stage_key, "logs": logs + res.get("logs", []), "result": res.get("result_status", "COMPLETED")}

    else:
        logs.append(f"Stage '{stage_key}' is not executed in Phase 7.")
        return {"success": True, "stage": stage_key, "logs": logs, "result": "NOT EXECUTED"}




@app.get("/api/fnb-tunnel/status")
async def get_fnb_tunnel_status():
    from app.database.db import get_site_by_id, get_site_by_name
    site = get_site_by_id(1) or get_site_by_name("FNB")
    if not site:
        return {"status": "STOPPED", "message": "FNB site record not found."}

    return tunnel_manager.get_tunnel_status(site)

@app.post("/api/fnb-tunnel/stop")
async def stop_fnb_tunnel():
    from app.database.db import get_site_by_id, get_site_by_name
    site = get_site_by_id(1) or get_site_by_name("FNB")
    if site:
        tunnel_manager.stop_tunnel(site)
    return {"success": True, "status": "STOPPED"}

@app.get("/api/fnb-tunnel/command")
async def get_fnb_tunnel_command():
    from app.database.db import get_site_by_id, get_site_by_name
    site = get_site_by_id(1) or get_site_by_name("FNB")
    if not site:
        return {"command": "FNB Site not found"}

    try:
        detected = putty_manager.detect_executables()
        plink_path = detected["plink"] or "tools/putty/plink.exe"
        cmd = putty_manager.build_plink_command(site, plink_path)
        scrubbed = putty_manager.scrub_sensitive_info(" ".join(cmd))
        return {"command": scrubbed, "raw_args": [putty_manager.scrub_sensitive_info(arg) for arg in cmd]}
    except Exception as e:
        return {"command": f"Error constructing command: {e}"}

@app.get("/api/database/site-count-audit")
async def site_count_audit():
    sites = get_all_sites()
    total = len(sites)
    enabled = len([s for s in sites if s.enabled])
    expected = 21
    extra_sites = [s.name for s in sites[21:]] if total > 21 else []

    return {
        "total_database_records": total,
        "enabled_sites": enabled,
        "expected_production_sites": expected,
        "extra_sites": extra_sites,
        "explanation": f"Database has {total} records ({enabled} enabled). Sites 1 to 21 correspond to standard 21 production sites (FNB, Site 02..21). Record #22 '{', '.join(extra_sites)}' is an extra record present in database."
    }



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
