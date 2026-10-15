import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.controller_automation.models import (
    ControllerCloneRequest,
    TestConnectionRequest,
    TestConnectionResult,
    ControllerRunStatus,
    ControllerSettingsUpdate
)
from app.controller_automation.workflow_runner import controller_workflow_runner
from app.database.db import (
    get_all_sites,
    get_all_controller_settings,
    save_controller_settings,
    get_controller_runs_history,
    get_controller_run_by_uuid,
    get_controller_dashboard_metrics
)

logger = logging.getLogger("Controller_Router")

controller_router = APIRouter()


@controller_router.get("/status", response_model=ControllerRunStatus)
async def get_controller_status():
    """Returns current live workflow runner status and progress."""
    return controller_workflow_runner.current_status


@controller_router.post("/run")
async def start_controller_run(req: ControllerCloneRequest):
    """
    Initiates Room Controller configuration cloning/provisioning.
    Executes in background thread and reports real-time logs via WebSocket/polling.
    """
    if controller_workflow_runner.is_running():
        raise HTTPException(
            status_code=409,
            detail="A controller provisioning workflow is already running. Please wait for it to complete or stop it."
        )

    # Validate IP address inputs
    if not req.current_room_ip.strip():
        raise HTTPException(status_code=400, detail="Current Room Controller IP is required.")
    if not req.similar_room_ip.strip():
        raise HTTPException(status_code=400, detail="Similar Room Controller IP is required.")
    if not req.site_ip.strip():
        raise HTTPException(status_code=400, detail="Site Server IP is required.")

    # Merge default settings if not explicitly specified
    settings = get_all_controller_settings()
    if not req.jump_host:
        req.jump_host = settings.get("jump_host", "111.93.205.187")
    if not req.jump_username:
        req.jump_username = settings.get("jump_username", "sourik")
    if not req.jump_password:
        req.jump_password = settings.get("jump_password", "s0urik@@")

    try:
        run_uuid = controller_workflow_runner.start_run(req)
        return {
            "status": "STARTED",
            "run_uuid": run_uuid,
            "target_ip": req.target_ip,
            "is_new_controller": req.is_new_controller,
            "message": f"Controller provisioning started for Room {req.current_room_no} ({req.target_ip})"
        }
    except Exception as e:
        logger.exception(f"Failed to start controller run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@controller_router.post("/test-connection", response_model=TestConnectionResult)
async def test_controller_connection(req: TestConnectionRequest):
    """
    Non-destructive connectivity test through Jump Server -> Site Server -> Target & Similar Controllers.
    Discovers which candidate root password works for the controllers.
    """
    settings = get_all_controller_settings()
    if not req.jump_host:
        req.jump_host = settings.get("jump_host", "111.93.205.187")
    if not req.jump_username:
        req.jump_username = settings.get("jump_username", "sourik")
    if not req.jump_password:
        req.jump_password = settings.get("jump_password", "s0urik@@")

    try:
        result = controller_workflow_runner.test_connection(req)
        return result
    except Exception as e:
        logger.exception(f"Connection test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@controller_router.post("/stop")
async def stop_controller_run():
    """Cancels and stops the active controller provisioning workflow."""
    stopped = controller_workflow_runner.cancel_run()
    if not stopped:
        return {"status": "NOT_RUNNING", "message": "No active controller run was executing."}
    return {"status": "STOP_REQUESTED", "message": "Cancellation request sent to workflow runner."}


@controller_router.get("/history")
async def list_controller_history(limit: int = 50):
    """Returns list of past controller provisioning runs."""
    return get_controller_runs_history(limit=limit)


@controller_router.get("/history/{run_uuid}")
async def get_controller_run_detail(run_uuid: str):
    """Returns details and logs for a specific run."""
    run = get_controller_run_by_uuid(run_uuid)
    if not run:
        raise HTTPException(status_code=404, detail="Controller run not found.")
    return run


@controller_router.get("/settings")
async def get_controller_settings():
    """Returns current controller tool settings."""
    return get_all_controller_settings()


@controller_router.post("/settings")
async def update_controller_settings(update: ControllerSettingsUpdate):
    """Updates controller configuration settings."""
    data = {k: v for k, v in update.model_dump().items() if v is not None}
    if data:
        save_controller_settings(data)
    return {"status": "UPDATED", "settings": get_all_controller_settings()}


@controller_router.get("/metrics")
async def get_controller_metrics():
    """Returns summary statistics for the Controller tool."""
    return get_controller_dashboard_metrics()


@controller_router.get("/sites")
async def list_controller_sites():
    """Returns sites configured in the system, suitable for Controller clone selection."""
    sites = get_all_sites()
    settings = get_all_controller_settings()
    default_port = int(settings.get("site_default_port", "2222"))
    return [
        {
            "id": s.id,
            "name": s.name,
            "site_ip": s.site_ip,
            "site_port": s.ssh_port if (s.ssh_port and s.ssh_port != 22) else default_port,
            "enabled": s.enabled
        }
        for s in sites if s.enabled and s.site_ip
    ]
