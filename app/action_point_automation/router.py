import os
import shutil
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from app.config import DOWNLOADS_DIR, REPORTS_DIR
from app.action_point_automation.models import (
    ValidateFileResponse,
    FileValidationSummary,
    StartActionPointRunRequest,
    ExecutionMode
)
from app.action_point_automation.file_parser import parse_action_point_file
from app.action_point_automation.workflow_runner import action_point_workflow_runner
from app.database.db import (
    get_site_by_id,
    get_action_point_runs,
    get_action_point_run_details
)

logger = logging.getLogger("ActionPoint_Router")
action_point_router = APIRouter()

UPLOAD_DIR = DOWNLOADS_DIR / "action_point_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@action_point_router.post("/upload", response_model=ValidateFileResponse)
async def upload_and_validate_file(file: UploadFile = File(...)):
    """
    Receives and validates action point CSV/XLSX file.
    Validates required headers, price format, and duplicate item codes.
    Returns preview items and validation summary.
    """
    filename = file.filename or "unknown.csv"
    ext = Path(filename).suffix.lower()
    if ext not in (".csv", ".xlsx"):
        raise HTTPException(status_code=400, detail=f"Unsupported file format '{ext}'. Only .csv and .xlsx are supported.")

    target_path = UPLOAD_DIR / filename
    try:
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")

    items, summary, struct_errors = parse_action_point_file(str(target_path))

    return ValidateFileResponse(
        success=len(struct_errors) == 0,
        filename=filename,
        summary=summary,
        items=items,
        structural_errors=struct_errors
    )


@action_point_router.post("/run")
async def start_action_point_run(request: StartActionPointRunRequest):
    """
    Initiates Dry-Run or Live Execution for Action Point Configuration.
    Requires explicit user confirmation on the frontend.
    """
    if action_point_workflow_runner.is_running:
        raise HTTPException(status_code=409, detail="An Action Point workflow is already running. Please wait for it to complete.")

    site = get_site_by_id(request.site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site ID {request.site_id} not found.")

    target_path = UPLOAD_DIR / request.filename
    if not target_path.exists():
        raise HTTPException(status_code=404, detail=f"Uploaded file '{request.filename}' not found on server.")

    # Parse items if not passed in request body
    items = request.items
    if not items:
        items, _, struct_errors = parse_action_point_file(str(target_path))
        if struct_errors:
            raise HTTPException(status_code=400, detail=f"File validation errors: {struct_errors}")

    if not items:
        raise HTTPException(status_code=400, detail="No valid action point items to execute.")

    # Execute asynchronously in background task
    asyncio.create_task(
        action_point_workflow_runner.execute_run(
            site_id=request.site_id,
            filename=request.filename,
            items=items,
            mode=request.mode,
            capture_success_screenshots=request.capture_success_screenshots
        )
    )

    return {
        "success": True,
        "message": f"Action Point {request.mode.value} execution initiated for site '{site.name}'.",
        "site_id": site.id,
        "site_name": site.name,
        "filename": request.filename,
        "mode": request.mode.value
    }


@action_point_router.post("/stop")
async def stop_action_point_run():
    """Requests graceful stop of running action point workflow."""
    if not action_point_workflow_runner.is_running:
        return {"success": False, "message": "No action point workflow is actively running."}

    action_point_workflow_runner.stop_workflow()
    return {"success": True, "message": "Action Point workflow stop requested."}


@action_point_router.get("/status")
async def get_action_point_status():
    """Returns real-time execution status of the workflow runner."""
    return {
        "is_running": action_point_workflow_runner.is_running,
        "run_id": action_point_workflow_runner.current_run_id,
        "site_id": action_point_workflow_runner.current_site_id,
        "site_name": action_point_workflow_runner.current_site_name,
        "mode": action_point_workflow_runner.current_mode.value,
        "status": action_point_workflow_runner.current_status.value,
        "operation": action_point_workflow_runner.current_operation,
        "current_item": action_point_workflow_runner.current_item_identifier,
        "progress_percentage": round(action_point_workflow_runner.progress_percentage, 1)
    }


@action_point_router.get("/history")
async def list_action_point_runs(limit: int = Query(50, ge=1, le=200)):
    """Returns recent Action Point configuration runs."""
    return get_action_point_runs(limit=limit)


@action_point_router.get("/runs/{run_id}")
async def get_action_point_run(run_id: int):
    """Returns detailed results and per-item status for a specific run."""
    details = get_action_point_run_details(run_id)
    if not details:
        raise HTTPException(status_code=404, detail=f"Action point run #{run_id} not found.")
    return details


@action_point_router.get("/runs/{run_id}/report/{report_format}")
async def download_action_point_report(run_id: int, report_format: str):
    """Downloads generated execution report (csv, json, or xlsx)."""
    details = get_action_point_run_details(run_id)
    if not details:
        raise HTTPException(status_code=404, detail=f"Run #{run_id} not found.")

    site_name = details.get("site_name", "site")
    clean_site = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in site_name)
    mode = str(details.get("mode", "dry_run")).lower()
    run_date = details.get("run_date", "")

    fmt = report_format.lower()
    if fmt not in ("csv", "json", "xlsx"):
        raise HTTPException(status_code=400, detail="Invalid format. Supported formats: csv, json, xlsx")

    base_name = f"{run_date}_{clean_site}_run_{run_id}_{mode}.{fmt}"
    report_file = REPORTS_DIR / "action_point" / base_name

    if not report_file.exists():
        # Fallback wildcard search
        target_dir = REPORTS_DIR / "action_point"
        matches = list(target_dir.glob(f"*_run_{run_id}_*.{fmt}"))
        if matches:
            report_file = matches[0]
        else:
            raise HTTPException(status_code=404, detail=f"Report file not found for run #{run_id} in {fmt} format.")

    media_types = {
        "csv": "text/csv",
        "json": "application/json",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    }

    return FileResponse(
        path=str(report_file),
        media_type=media_types[fmt],
        filename=report_file.name
    )
