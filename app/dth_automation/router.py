import os
import shutil
import asyncio
import socket
import urllib.parse
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse

from app.config import BASE_DIR, DATA_DIR, REPORTS_DIR
from app.database.db import (
    get_all_sites,
    get_site_by_id,
    get_all_dth_sites,
    get_dth_site_by_id,
    get_dth_site_by_name,
    add_dth_site,
    update_dth_site,
    delete_dth_site,
    toggle_dth_site,
    get_dth_setting,
    set_dth_setting,
    get_all_dth_settings,
    update_dth_settings,
    get_dth_dashboard_metrics,
    get_dth_runs_history,
    get_dth_run_details
)
from app.dth_automation.models import (
    DthExecutionMode,
    DthRunState,
    DthItemState,
    StartDthRunRequest,
    DthBatchValidationResponse,
    DthSite,
    DthSiteCreateRequest,
    DthDashboardStats,
    DthSettingsModel
)
from app.dth_automation.file_parser import parse_dth_file
from app.dth_automation.validator import validate_channel_batch, DEFAULT_PORTAL_CATEGORIES
from app.dth_automation.selectors import DthSelectorRegistry, DEFAULT_DTH_SELECTORS
from app.dth_automation.workflow_runner import dth_workflow_runner

dth_router = APIRouter()

UPLOAD_DIR = DATA_DIR / "dth_uploads"
TEMPLATES_DIR = DATA_DIR / "templates"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


async def _check_connectivity(url_or_host: str, port: int = 80, timeout: float = 3.0) -> Dict[str, Any]:
    """Tests basic TCP reachability and HTTP status for portal URL."""
    try:
        parsed = urllib.parse.urlparse(url_or_host)
        host = parsed.hostname or url_or_host
        target_port = parsed.port or port
        if not target_port:
            target_port = 443 if parsed.scheme == "https" else 80

        # Run non-blocking TCP socket connect
        start_time = asyncio.get_event_loop().time()
        conn = asyncio.open_connection(host, target_port)
        reader, writer = await asyncio.wait_for(conn, timeout=timeout)
        elapsed = asyncio.get_event_loop().time() - start_time
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

        return {
            "success": True,
            "message": f"Connected to {host}:{target_port} successfully ({round(elapsed * 1000)}ms)",
            "latency_ms": round(elapsed * 1000)
        }
    except asyncio.TimeoutError:
        return {
            "success": False,
            "message": f"Connection timed out after {timeout}s",
            "latency_ms": None
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Connection failed: {str(e)}",
            "latency_ms": None
        }


# --- DTH DASHBOARD METRICS ---

@dth_router.get("/dashboard")
@dth_router.get("/stats")
async def get_dth_dashboard():
    """Returns dedicated DTH metrics, current execution state, and recent runs."""
    metrics = get_dth_dashboard_metrics()
    recent_runs = metrics.get("recent_runs", [])
    sites = get_all_dth_sites(include_passwords=False)
    status_payload = {
        "is_running": dth_workflow_runner.is_running,
        "run_id": dth_workflow_runner.current_run_id,
        "site_id": dth_workflow_runner.current_site_id,
        "site_name": dth_workflow_runner.current_site_name,
        "mode": dth_workflow_runner.current_mode.value,
        "status": dth_workflow_runner.current_status.value,
        "operation": dth_workflow_runner.current_operation,
        "current_channel": dth_workflow_runner.current_channel_identifier,
        "progress_percentage": dth_workflow_runner.progress_percentage
    }
    return {
        "success": True,
        "metrics": metrics,
        "recent_runs": recent_runs,
        "sites": sites,
        "execution": status_payload,
        "active_run": status_payload
    }


# --- DTH SITES CRUD ---

@dth_router.get("/sites")
async def list_dth_sites(enabled_only: bool = False):
    """Returns all configured DTH sites with credentials masked."""
    return get_all_dth_sites(enabled_only=enabled_only, include_passwords=False)


@dth_router.post("/sites")
async def create_dth_site_endpoint(req: DthSiteCreateRequest):
    """Adds a new DTH site configuration."""
    name_clean = req.name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="Site name is required.")

    existing = get_dth_site_by_name(name_clean)
    if existing:
        raise HTTPException(status_code=400, detail=f"DTH site '{name_clean}' already exists.")

    new_id = add_dth_site(req.model_dump())
    return {"success": True, "id": new_id, "site_id": new_id, "message": f"DTH Site '{name_clean}' created successfully."}


@dth_router.get("/sites/{site_id}")
async def get_dth_site_endpoint(site_id: int):
    """Fetches a specific DTH site."""
    site = get_dth_site_by_id(site_id, include_passwords=False)
    if not site:
        raise HTTPException(status_code=404, detail=f"DTH Site #{site_id} not found.")
    return {"success": True, "site": site}


@dth_router.put("/sites/{site_id}")
async def update_dth_site_endpoint(site_id: int, req: DthSiteCreateRequest):
    """Updates a DTH site configuration."""
    existing = get_dth_site_by_id(site_id, include_passwords=False)
    if not existing:
        raise HTTPException(status_code=404, detail=f"DTH Site #{site_id} not found.")

    name_clean = req.name.strip()
    other = get_dth_site_by_name(name_clean)
    if other and other["id"] != site_id:
        raise HTTPException(status_code=400, detail=f"Another DTH site with name '{name_clean}' already exists.")

    update_dth_site(site_id, req.model_dump())
    return {"success": True, "message": f"DTH Site #{site_id} updated successfully."}


@dth_router.delete("/sites/{site_id}")
async def delete_dth_site_endpoint(site_id: int):
    """Deletes a DTH site after ensuring it is not used in an active run."""
    existing = get_dth_site_by_id(site_id, include_passwords=False)
    if not existing:
        raise HTTPException(status_code=404, detail=f"DTH Site #{site_id} not found.")

    # Guard: Active run protection
    if dth_workflow_runner.is_running and dth_workflow_runner.current_site_id == site_id:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete DTH site while it is being actively used by a running DTH automation."
        )

    delete_dth_site(site_id)
    return {"success": True, "message": f"DTH Site #{site_id} deleted successfully."}


@dth_router.post("/sites/{site_id}/toggle")
async def toggle_dth_site_endpoint(site_id: int, enabled: Optional[bool] = None):
    """Enables or disables a DTH site, or flips current state if enabled is not specified."""
    existing = get_dth_site_by_id(site_id, include_passwords=False)
    if not existing:
        raise HTTPException(status_code=404, detail=f"DTH Site #{site_id} not found.")

    new_state = (not existing.get("enabled", True)) if enabled is None else enabled
    toggle_dth_site(site_id, new_state)
    return {"success": True, "enabled": new_state}


@dth_router.post("/sites/{site_id}/test")
async def test_dth_site_connectivity_endpoint(site_id: int):
    """Tests basic connectivity to a DTH site endpoint."""
    site = get_dth_site_by_id(site_id, include_passwords=False)
    if not site:
        site_ird = get_site_by_id(site_id)
        if not site_ird:
            raise HTTPException(status_code=404, detail=f"Site #{site_id} not found.")
        site = {
            "name": site_ird.name,
            "web_url": site_ird.web_url,
            "portal_url": site_ird.web_url,
            "local_port": site_ird.local_port,
            "site_ip": site_ird.site_ip,
            "site_port": site_ird.site_port
        }

    target = site.get("web_url") or site.get("portal_url") or f"http://127.0.0.1:{site.get('local_port', 18001)}/zmp/main-menu.do"
    result = await _check_connectivity(target, port=site.get("local_port", 18001))
    return {"success": result["success"], "details": result, "site_name": site["name"]}


@dth_router.post("/sites/import-ird")
async def import_ird_sites_to_dth():
    """Copies configured IRD sites into DTH sites if not already present."""
    ird_sites = get_all_sites()
    imported_count = 0
    for s in ird_sites:
        if not get_dth_site_by_name(s.name):
            add_dth_site({
                "name": s.name,
                "portal_url": s.web_url or f"http://localhost:{s.local_port}/zmp/main-menu.do",
                "local_port": s.local_port,
                "site_ip": s.site_ip,
                "site_port": s.site_port,
                "remote_host": s.remote_host,
                "remote_port": s.remote_port,
                "ssh_host": s.ssh_host,
                "ssh_port": s.ssh_port,
                "ssh_username": s.ssh_username,
                "ssh_key_path": s.ssh_key_path,
                "auth_type": s.auth_type,
                "putty_session": s.putty_session,
                "tunnel_type": s.tunnel_type,
                "web_url": s.web_url,
                "idp_username": s.idp_username,
                "idp_password": s.idp_password,
                "enabled": s.enabled,
                "notes": f"Imported from IRD site: {s.notes}"
            })
            imported_count += 1
    return {"success": True, "imported_count": imported_count}


# --- DTH SETTINGS ---

@dth_router.get("/settings")
async def get_dth_settings_endpoint():
    """Returns current DTH settings."""
    settings = get_all_dth_settings()
    return {"success": True, "settings": settings}


@dth_router.post("/settings")
async def update_dth_settings_endpoint(settings_data: Dict[str, Any]):
    """Updates DTH settings with safe validation."""
    if "default_mode" in settings_data and settings_data["default_mode"] not in ("DRY_RUN", "LIVE"):
        settings_data["default_mode"] = "DRY_RUN"

    update_dth_settings(settings_data)
    updated = get_all_dth_settings()
    return {"success": True, "settings": updated, "message": "DTH Settings saved successfully."}


# --- CHANNEL TEMPLATES & IMPORT ---

@dth_router.get("/template")
async def download_template(format: str = Query(default="csv", pattern="^(csv|xlsx)$")):
    """Downloads the official CSV or XLSX channel configuration template."""
    filename = f"dth_channel_template.{format}"
    file_path = TEMPLATES_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Template file '{filename}' not found.")
    media_type = "text/csv" if format == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return FileResponse(path=str(file_path), filename=filename, media_type=media_type)


@dth_router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Uploads a CSV or XLSX file and stores it in the uploads folder."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in [".csv", ".xlsx"]:
        raise HTTPException(status_code=400, detail="Only .csv and .xlsx files are allowed.")

    dest_path = UPLOAD_DIR / file.filename
    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")

    return {
        "success": True,
        "filename": file.filename,
        "file_path": str(dest_path),
        "size_bytes": dest_path.stat().st_size
    }


@dth_router.post("/validate")
async def validate_file(
    filename: str = Form(...),
    image_dir: Optional[str] = Form(default=None),
    site_id: Optional[int] = Form(default=None)
):
    """
    Parses and runs preflight validation on an uploaded file.
    Returns preview items, row-level validation errors, and duplicate warnings.
    """
    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found in upload directory.")

    raw_records, parse_errors = parse_dth_file(str(file_path))
    if parse_errors:
        return {
            "success": False,
            "filename": filename,
            "parse_errors": parse_errors,
            "total_rows": 0,
            "valid_rows": 0,
            "invalid_rows": 0,
            "duplicate_rows": 0,
            "items": [],
            "validation_results": []
        }

    items, validation_results = validate_channel_batch(
        raw_records,
        image_dir=image_dir,
        portal_categories=DEFAULT_PORTAL_CATEGORIES
    )

    valid_count = sum(1 for r in validation_results if r.status == DthItemState.READY)
    invalid_count = sum(1 for r in validation_results if r.status == DthItemState.INVALID)
    duplicate_count = sum(1 for r in validation_results if r.status == DthItemState.SKIPPED_DUPLICATE)

    return {
        "success": True,
        "filename": filename,
        "total_rows": len(items),
        "valid_rows": valid_count,
        "invalid_rows": invalid_count,
        "duplicate_rows": duplicate_count,
        "items": [it.model_dump() for it in items],
        "validation_results": [vr.model_dump() for vr in validation_results],
        "image_dir": image_dir,
        "portal_categories": DEFAULT_PORTAL_CATEGORIES
    }


# --- EXECUTION CONTROL ---

@dth_router.post("/execute")
async def execute_dth_batch(req: StartDthRunRequest, background_tasks: BackgroundTasks):
    """
    Starts DTH automation run in DRY_RUN or LIVE mode.
    Live mode requires explicit user authorization (req.authorized=True).
    """
    if dth_workflow_runner.is_running:
        raise HTTPException(status_code=409, detail="A DTH automation batch is already running.")

    file_path = UPLOAD_DIR / req.filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{req.filename}' not found.")

    # Check dth_sites first, fallback to sites
    dth_site = get_dth_site_by_id(req.site_id)
    if dth_site:
        site_id = dth_site["id"]
        site_name = dth_site["name"]
    else:
        site = get_site_by_id(req.site_id)
        if not site:
            raise HTTPException(status_code=404, detail=f"Site ID {req.site_id} not found.")
        site_id = site.id
        site_name = site.name

    if req.mode == DthExecutionMode.LIVE and not req.authorized:
        raise HTTPException(
            status_code=400,
            detail="Live channel creation requires explicit authorization confirmation."
        )

    # Launch execution as an asyncio task
    asyncio.create_task(dth_workflow_runner.execute_batch(
        file_path=str(file_path),
        image_dir=req.image_dir,
        site_id=req.site_id,
        mode=req.mode,
        channel_delay_seconds=req.channel_delay_seconds,
        authorized=req.authorized
    ))

    return {
        "success": True,
        "message": f"DTH {req.mode.value} execution initiated successfully.",
        "site_id": site_id,
        "site_name": site_name,
        "filename": req.filename,
        "mode": req.mode.value
    }


@dth_router.get("/status")
async def get_execution_status():
    """Returns real-time status of active or most recent DTH execution."""
    return {
        "is_running": dth_workflow_runner.is_running,
        "run_id": dth_workflow_runner.current_run_id,
        "site_id": dth_workflow_runner.current_site_id,
        "site_name": dth_workflow_runner.current_site_name,
        "mode": dth_workflow_runner.current_mode.value,
        "status": dth_workflow_runner.current_status.value,
        "operation": dth_workflow_runner.current_operation,
        "current_channel": dth_workflow_runner.current_channel_identifier,
        "progress_percentage": dth_workflow_runner.progress_percentage
    }


@dth_router.post("/stop")
async def stop_execution():
    """Requests graceful cancellation of active DTH automation."""
    if not dth_workflow_runner.is_running:
        return {"success": False, "message": "No active DTH automation is currently running."}

    dth_workflow_runner.stop_automation()
    return {"success": True, "message": "DTH stop requested successfully."}


# --- EXECUTION HISTORY & REPORTS ---

@dth_router.get("/history")
async def get_history(limit: int = Query(default=30, ge=1, le=100)):
    """Returns past DTH execution runs."""
    history = get_dth_runs_history(limit=limit)
    return {"success": True, "runs": history}


@dth_router.get("/runs/{run_id}")
async def get_run_details_by_id(run_id: int):
    """Returns detailed summary and row-level results for a specific DTH run."""
    details = get_dth_run_details(run_id)
    if not details:
        raise HTTPException(status_code=404, detail=f"DTH Run #{run_id} not found.")
    return {"success": True, "data": details}


@dth_router.get("/reports/{run_id}/csv")
async def download_csv_report(run_id: int):
    """Downloads execution CSV report for a given run ID."""
    dth_reports_dir = REPORTS_DIR / "dth"
    matches = list(dth_reports_dir.glob(f"*_dth_run_{run_id}.csv"))
    if not matches:
        raise HTTPException(status_code=404, detail=f"CSV report for Run #{run_id} not found.")
    return FileResponse(path=str(matches[0]), filename=matches[0].name, media_type="text/csv")


@dth_router.get("/reports/{run_id}/json")
async def download_json_report(run_id: int):
    """Downloads execution JSON report for a given run ID."""
    dth_reports_dir = REPORTS_DIR / "dth"
    matches = list(dth_reports_dir.glob(f"*_dth_run_{run_id}.json"))
    if not matches:
        raise HTTPException(status_code=404, detail=f"JSON report for Run #{run_id} not found.")
    return FileResponse(path=str(matches[0]), filename=matches[0].name, media_type="application/json")


# --- PORTAL METADATA & SELECTORS ---

@dth_router.get("/categories")
async def get_categories():
    """Returns default and discovered portal categories."""
    return {"success": True, "categories": DEFAULT_PORTAL_CATEGORIES}


@dth_router.get("/selectors")
async def get_selectors():
    """Returns current DTH portal selectors configuration."""
    return {"success": True, "selectors": DEFAULT_DTH_SELECTORS}


@dth_router.post("/selectors")
async def update_selector(key: str = Form(...), selectors_csv: str = Form(...)):
    """Overrides a DTH portal selector dynamically."""
    sels = [s.strip() for s in selectors_csv.split(",") if s.strip()]
    DthSelectorRegistry.set_override(key, sels)
    return {"success": True, "key": key, "selectors": sels}
