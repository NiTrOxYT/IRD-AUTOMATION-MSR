import pytest
from unittest.mock import AsyncMock, patch

from app.database.db import (
    init_db,
    add_site,
    get_all_sites,
    get_action_point_run_details
)
from app.database.models import Site
from app.action_point_automation.models import (
    ActionPointItem,
    ActionClassification,
    ExecutionMode,
    RunState
)
from app.action_point_automation.workflow_runner import ActionPointWorkflowRunner


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


@pytest.mark.asyncio
async def test_workflow_runner_dry_run_end_to_end():
    runner = ActionPointWorkflowRunner()

    # Create dummy site if needed
    sites = get_all_sites()
    if not sites:
        site_id = add_site(Site(name="Workflow Test Hotel", launcher_button="WF1", enabled=True, local_port=18001))
    else:
        site_id = sites[0].id

    items = [
        ActionPointItem(
            row_number=2,
            item_code="0042",
            item_name="Kebab",
            item_price="300",
            category="Starters",
            subcategory="Non-Veg",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        ),
        ActionPointItem(
            row_number=3,
            item_code="0043",
            item_name="Coke",
            item_price="80",
            category="Beverages",
            subcategory="Cold Drinks",
            original_status="Active",
            normalized_status="active",
            classification=ActionClassification.UNSUPPORTED_STATUS,
            is_valid=True
        )
    ]

    status_events = []
    runner.add_status_listener(lambda payload: status_events.append(payload))

    # Mock tunnel and portal controller
    mock_ctrl = AsyncMock()
    mock_ctrl.initialize = AsyncMock()
    mock_ctrl.navigate_and_authenticate = AsyncMock(return_value=(True, "Success"))
    mock_ctrl.inspect_existing_categories = AsyncMock(return_value=(["Starters"], {"Starters": ["Non-Veg"]}))
    mock_ctrl.navigate_to_item_configuration = AsyncMock(return_value=(True, "Loaded"))
    mock_ctrl.configure_food_item = AsyncMock(return_value=(True, "DRY_RUN: Pre-save checks verified.", None))
    mock_ctrl.close = AsyncMock()

    with patch("app.action_point_automation.workflow_runner.tunnel_manager.start_and_verify_tunnel", AsyncMock(return_value=(True, "Tunnel OK", []))):
        with patch("app.action_point_automation.workflow_runner.ActionPointPortalController", return_value=mock_ctrl):
            result = await runner.execute_run(
                site_id=site_id,
                filename="test_workflow.csv",
                items=items,
                mode=ExecutionMode.DRY_RUN
            )

    assert result["success"] is True
    assert result["status"] == RunState.COMPLETED.value
    assert len(status_events) > 0

    # Verify DB persistence
    run_id = result["run_id"]
    db_details = get_action_point_run_details(run_id)
    assert db_details is not None
    assert db_details["total_rows"] == 2
    assert db_details["successful_rows"] == 1
    assert db_details["skipped_rows"] == 1
    assert len(db_details["items"]) == 2


@pytest.mark.asyncio
async def test_workflow_runner_live_creates_category_and_subcategory():
    runner = ActionPointWorkflowRunner()
    sites = get_all_sites()
    site_id = sites[0].id if sites else add_site(Site(name="Live Test Hotel", launcher_button="LT1", enabled=True, local_port=18001))

    items = [
        ActionPointItem(
            row_number=2,
            item_code="0099",
            item_name="Biryani",
            item_price="500",
            category="Main Course",
            subcategory="Rice Dishes",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        )
    ]

    mock_ctrl = AsyncMock()
    mock_ctrl.initialize = AsyncMock()
    mock_ctrl.navigate_and_authenticate = AsyncMock(return_value=(True, "Success"))
    # Initial state: no Main Course category
    mock_ctrl.inspect_existing_categories = AsyncMock(return_value=(["Starters"], {"Starters": ["Veg"]}))
    mock_ctrl.create_category = AsyncMock(return_value=(True, "Category created"))
    mock_ctrl.create_subcategory = AsyncMock(return_value=(True, "Subcategory created"))
    mock_ctrl.navigate_to_item_configuration = AsyncMock(return_value=(True, "Loaded"))
    mock_ctrl.configure_food_item = AsyncMock(return_value=(True, "SUCCESS: Configured and verified.", "ss_test.png"))
    mock_ctrl.close = AsyncMock()

    with patch("app.action_point_automation.workflow_runner.tunnel_manager.start_and_verify_tunnel", AsyncMock(return_value=(True, "Tunnel OK", []))):
        with patch("app.action_point_automation.workflow_runner.ActionPointPortalController", return_value=mock_ctrl):
            result = await runner.execute_run(
                site_id=site_id,
                filename="live_test.csv",
                items=items,
                mode=ExecutionMode.LIVE
            )

    assert result["success"] is True
    # Verify both category and subcategory creation workflows were invoked with image
    mock_ctrl.create_category.assert_called_once()
    mock_ctrl.create_subcategory.assert_called_once()
    mock_ctrl.configure_food_item.assert_called_once()

    db_details = get_action_point_run_details(result["run_id"])
    assert db_details["successful_rows"] == 1
    assert db_details["items"][0]["category_created"] == 1
    assert db_details["items"][0]["subcategory_created"] == 1


@pytest.mark.asyncio
async def test_workflow_runner_live_preflight_missing_image_fails():
    runner = ActionPointWorkflowRunner()
    sites = get_all_sites()
    site_id = sites[0].id if sites else add_site(Site(name="Live Test Hotel", launcher_button="LT1", enabled=True, local_port=18001))

    items = [
        ActionPointItem(
            row_number=2,
            item_code="0099",
            item_name="Biryani",
            item_price="500",
            category="Main Course",
            subcategory="Rice Dishes",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        )
    ]

    with patch("os.path.isfile", return_value=False):
        result = await runner.execute_run(
            site_id=site_id,
            filename="preflight_test.csv",
            items=items,
            mode=ExecutionMode.LIVE
        )

    assert result["success"] is False
    assert "Preflight Error" in result["message"]


@pytest.mark.asyncio
async def test_workflow_runner_item_without_subcategory():
    """Items without a subcategory should be configured directly without attempting subcategory creation."""
    runner = ActionPointWorkflowRunner()
    sites = get_all_sites()
    site_id = sites[0].id if sites else add_site(Site(name="Live Test Hotel", launcher_button="LT1", enabled=True, local_port=18001))

    items = [
        ActionPointItem(
            row_number=2,
            item_code="1010001",
            item_name="Canadian Club",
            item_price="750",
            category="Canadian Whiskey",
            subcategory="",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        )
    ]

    mock_ctrl = AsyncMock()
    mock_ctrl.initialize = AsyncMock()
    mock_ctrl.navigate_and_authenticate = AsyncMock(return_value=(True, "Success"))
    mock_ctrl.inspect_existing_categories = AsyncMock(return_value=(["Canadian Whiskey"], {"Canadian Whiskey": []}))
    mock_ctrl.create_category = AsyncMock()
    mock_ctrl.create_subcategory = AsyncMock()
    mock_ctrl.navigate_to_item_configuration = AsyncMock(return_value=(True, "Loaded"))
    mock_ctrl.configure_food_item = AsyncMock(return_value=(True, "SUCCESS: Configured and verified.", "ss_test.png"))
    mock_ctrl.close = AsyncMock()

    with patch("app.action_point_automation.workflow_runner.tunnel_manager.start_and_verify_tunnel", AsyncMock(return_value=(True, "Tunnel OK", []))):
        with patch("app.action_point_automation.workflow_runner.ActionPointPortalController", return_value=mock_ctrl):
            result = await runner.execute_run(
                site_id=site_id,
                filename="no_subcat_test.csv",
                items=items,
                mode=ExecutionMode.LIVE
            )

    assert result["success"] is True
    # Subcategory creation must NOT be called for category-only item
    mock_ctrl.create_subcategory.assert_not_called()
    mock_ctrl.configure_food_item.assert_called_once()

    db_details = get_action_point_run_details(result["run_id"])
    assert db_details["successful_rows"] == 1
    assert db_details["items"][0]["subcategory_created"] == 0
    assert db_details["items"][0]["subcategory_verified"] == 1

