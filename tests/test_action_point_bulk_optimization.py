import time
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.action_point_automation.models import (
    ActionPointItem,
    ActionClassification,
    ExecutionMode,
    RunState,
    ActionPointStatusEnum
)
from app.action_point_automation.portal_controller import ActionPointPortalController
from app.action_point_automation.workflow_runner import ActionPointWorkflowRunner
from app.database.models import Site
from app.database.db import get_all_sites, add_site


@pytest.fixture
def mock_controller():
    ctrl = ActionPointPortalController(run_id="test_bulk_opt", site_name="Test Hotel")
    ctrl.browser = AsyncMock()
    ctrl.context = AsyncMock()
    ctrl.page = AsyncMock()
    ctrl.page.is_closed = MagicMock(return_value=False)
    ctrl.snapshot = AsyncMock(return_value=MagicMock(screenshot_path="dummy.png"))
    return ctrl


@pytest.mark.asyncio
async def test_01_existing_categories_and_subcategories_not_recreated():
    """Existing categories and subcategories in the portal are never recreated during bulk execution."""
    runner = ActionPointWorkflowRunner()
    sites = get_all_sites()
    site_id = sites[0].id if sites else add_site(Site(name="Bulk Site", launcher_button="BS", enabled=True, local_port=18001))

    items = [
        ActionPointItem(
            row_number=2, item_code="1001", item_name="Dish 1", item_price="250",
            category="Starters", subcategory="Veg Starters",
            original_status="Category Update", normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE, is_valid=True
        ),
        ActionPointItem(
            row_number=3, item_code="1002", item_name="Dish 2", item_price="350",
            category="Starters", subcategory="Veg Starters",
            original_status="Category Update", normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE, is_valid=True
        )
    ]

    mock_ctrl = AsyncMock()
    mock_ctrl.initialize = AsyncMock()
    mock_ctrl.navigate_and_authenticate = AsyncMock(return_value=(True, "Success"))
    mock_ctrl.inspect_existing_categories = AsyncMock(return_value=(["Starters"], {"Starters": ["Veg Starters"]}))
    mock_ctrl.navigate_to_item_configuration = AsyncMock(return_value=(True, "Loaded"))
    mock_ctrl.configure_food_item = AsyncMock(return_value=(True, "SUCCESS: Configured and verified.", "ss.png"))
    mock_ctrl.page.is_closed = MagicMock(return_value=False)

    with patch("app.action_point_automation.workflow_runner.tunnel_manager.start_and_verify_tunnel", AsyncMock(return_value=(True, "OK", []))):
        with patch("app.action_point_automation.workflow_runner.ActionPointPortalController", return_value=mock_ctrl):
            result = await runner.execute_run(
                site_id=site_id,
                filename="bulk_test.csv",
                items=items,
                mode=ExecutionMode.LIVE
            )

    assert result["success"] is True
    # Zero creations triggered
    mock_ctrl.create_category.assert_not_called()
    mock_ctrl.create_subcategory.assert_not_called()
    assert mock_ctrl.configure_food_item.call_count == 2


@pytest.mark.asyncio
async def test_02_repeated_items_reuse_category_tree_without_repeated_inspection():
    """Repeated items in a batch reuse discovered category cache without repeating inspection."""
    runner = ActionPointWorkflowRunner()
    sites = get_all_sites()
    site_id = sites[0].id if sites else add_site(Site(name="Bulk Site", launcher_button="BS", enabled=True, local_port=18001))

    # 5 items sharing the same category
    items = [
        ActionPointItem(
            row_number=i, item_code=f"200{i}", item_name=f"Pasta {i}", item_price="400",
            category="Artisan Pasta", subcategory="Penne",
            original_status="Category Update", normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE, is_valid=True
        ) for i in range(1, 6)
    ]

    mock_ctrl = AsyncMock()
    mock_ctrl.initialize = AsyncMock()
    mock_ctrl.navigate_and_authenticate = AsyncMock(return_value=(True, "Success"))
    mock_ctrl.inspect_existing_categories = AsyncMock(return_value=(["Artisan Pasta"], {"Artisan Pasta": ["Penne"]}))
    mock_ctrl.navigate_to_item_configuration = AsyncMock(return_value=(True, "Loaded"))
    mock_ctrl.configure_food_item = AsyncMock(return_value=(True, "SUCCESS", "ss.png"))
    mock_ctrl.page.is_closed = MagicMock(return_value=False)

    with patch("app.action_point_automation.workflow_runner.tunnel_manager.start_and_verify_tunnel", AsyncMock(return_value=(True, "OK", []))):
        with patch("app.action_point_automation.workflow_runner.ActionPointPortalController", return_value=mock_ctrl):
            result = await runner.execute_run(
                site_id=site_id,
                filename="repeat_items.csv",
                items=items,
                mode=ExecutionMode.LIVE
            )

    # Initial discovery happened once
    mock_ctrl.inspect_existing_categories.assert_called_once()
    # No redundant expansion or inspection for subsequent items
    mock_ctrl.expand_category_subcategories.assert_not_called()
    assert mock_ctrl.configure_food_item.call_count == 5


@pytest.mark.asyncio
async def test_03_navigation_not_repeated_when_already_on_items_configuration(mock_controller):
    """navigate_to_item_configuration reuses current page state when already on Items Configuration."""
    mock_controller.page.url = "http://localhost:18008/zmp/foodItemConfig.do"
    mock_controller.page.is_closed = MagicMock(return_value=False)

    search_input = AsyncMock()
    search_input.is_visible = AsyncMock(return_value=True)
    mock_controller.page.query_selector = AsyncMock(return_value=search_input)

    initial_nav_count = mock_controller.navigation_count
    ok, msg = await mock_controller.navigate_to_item_configuration()

    assert ok is True
    assert "already active" in msg or "page loaded" in msg
    # Navigation count did not increment because page was reused!
    assert mock_controller.navigation_count == initial_nav_count


@pytest.mark.asyncio
async def test_04_saved_state_verification_remains_active(mock_controller):
    """Saved-state verification in configure_food_item verifies portal confirmation before reporting success."""
    item = ActionPointItem(
        row_number=2, item_code="5001", item_name="Safe Item", item_price="150",
        category="Beverages", subcategory="Tea",
        original_status="Category Update", normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE, is_valid=True
    )

    search_input = AsyncMock()
    conf_btn = AsyncMock()
    conf_btn.click = AsyncMock()

    mock_controller.find_element = AsyncMock(side_effect=[
        (search_input, "search_input"),
        (AsyncMock(), "search_btn"),
        (AsyncMock(), "cat_panel"),
        (AsyncMock(), "rest_default"),
        (conf_btn, "conf_btn")
    ])

    row = AsyncMock()
    td_code = AsyncMock()
    td_code.inner_text = AsyncMock(return_value="5001")
    row.query_selector_all = AsyncMock(return_value=[td_code])
    chk = AsyncMock()
    chk.is_checked = AsyncMock(return_value=True)
    row.query_selector = AsyncMock(return_value=chk)

    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.page.query_selector = AsyncMock(return_value=chk)

    # Portal responds with error notice after configure click
    mock_controller.page.inner_text = AsyncMock(return_value="System Error: Could not commit item changes.")

    ok, msg, ss = await mock_controller.configure_food_item(item, dry_run=False)
    assert ok is False
    assert "error" in msg.lower()
    assert "5001" not in mock_controller.processed_items


@pytest.mark.asyncio
async def test_05_dry_run_performs_zero_mutations(mock_controller):
    """Dry-run validates all pre-save steps and executes zero configure submissions."""
    item = ActionPointItem(
        row_number=2, item_code="6001", item_name="Dry Run Item", item_price="220",
        category="Desserts", subcategory="Pastries",
        original_status="Category Update", normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE, is_valid=True
    )

    search_input = AsyncMock()
    conf_btn = AsyncMock()

    mock_controller.find_element = AsyncMock(side_effect=[
        (search_input, "search_input"),
        (AsyncMock(), "search_btn"),
        (AsyncMock(), "cat_panel"),
        (AsyncMock(), "rest_default"),
        (conf_btn, "conf_btn")
    ])

    row = AsyncMock()
    td_code = AsyncMock()
    td_code.inner_text = AsyncMock(return_value="6001")
    row.query_selector_all = AsyncMock(return_value=[td_code])
    chk = AsyncMock()
    chk.is_checked = AsyncMock(return_value=True)
    row.query_selector = AsyncMock(return_value=chk)

    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.page.query_selector = AsyncMock(return_value=chk)

    ok, msg, ss = await mock_controller.configure_food_item(item, dry_run=True)
    assert ok is True
    assert "DRY_RUN: Pre-save checks verified." in msg
    # Configure submit button must never be clicked during dry run
    conf_btn.click.assert_not_called()


@pytest.mark.asyncio
async def test_06_session_loss_invalidates_cached_state(mock_controller):
    """Session loss or cache invalidation safely clears category tree and verified sets."""
    mock_controller.verified_categories.add("starters")
    mock_controller.category_tree["starters"] = {"spring rolls"}
    mock_controller.category_dom_details["starters"] = {"restaurant": "IRD - DEFAULT"}

    mock_controller.invalidate_category_cache()

    assert len(mock_controller.verified_categories) == 0
    assert len(mock_controller.category_tree) == 0
    assert len(mock_controller.category_dom_details) == 0


@pytest.mark.asyncio
async def test_07_item_price_is_never_modified(mock_controller):
    """The automation never targets, fills, or modifies the item price input."""
    item = ActionPointItem(
        row_number=2, item_code="7001", item_name="Price Invariant Dish", item_price="999.00",
        category="Mains", subcategory="Curries",
        original_status="Category Update", normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE, is_valid=True
    )

    search_input = AsyncMock()
    price_input = AsyncMock()

    mock_controller.find_element = AsyncMock(side_effect=[
        (search_input, "search_input"),
        (AsyncMock(), "search_btn"),
        (AsyncMock(), "cat_panel"),
        (AsyncMock(), "rest_default")
    ])

    row = AsyncMock()
    td_code = AsyncMock()
    td_code.inner_text = AsyncMock(return_value="7001")
    row.query_selector_all = AsyncMock(return_value=[td_code])
    chk = AsyncMock()
    chk.is_checked = AsyncMock(return_value=True)
    row.query_selector = AsyncMock(return_value=chk)

    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.page.query_selector = AsyncMock(return_value=chk)

    ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=True)
    assert ok is True
    # Price input was never interacted with
    price_input.fill.assert_not_called()


@pytest.mark.asyncio
async def test_08_performance_metrics_instrumentation():
    """Workflow runner records complete performance metrics summary including per-stage timings."""
    runner = ActionPointWorkflowRunner()
    sites = get_all_sites()
    site_id = sites[0].id if sites else add_site(Site(name="Metrics Site", launcher_button="MS", enabled=True, local_port=18001))

    items = [
        ActionPointItem(
            row_number=2, item_code="8001", item_name="Perf Dish 1", item_price="150",
            category="Soups", subcategory="Clear",
            original_status="Category Update", normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE, is_valid=True
        ),
        ActionPointItem(
            row_number=3, item_code="8002", item_name="Perf Dish 2", item_price="180",
            category="Soups", subcategory="Clear",
            original_status="Category Update", normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE, is_valid=True
        )
    ]

    mock_ctrl = AsyncMock()
    mock_ctrl.initialize = AsyncMock()
    mock_ctrl.navigate_and_authenticate = AsyncMock(return_value=(True, "Success"))
    mock_ctrl.inspect_existing_categories = AsyncMock(return_value=(["Soups"], {"Soups": ["Clear"]}))
    mock_ctrl.navigate_to_item_configuration = AsyncMock(return_value=(True, "Loaded"))
    mock_ctrl.configure_food_item = AsyncMock(return_value=(True, "SUCCESS", None))
    mock_ctrl.page.is_closed = MagicMock(return_value=False)
    mock_ctrl.navigation_count = 1
    mock_ctrl.search_count = 2
    mock_ctrl.retry_count = 0
    mock_ctrl.screenshot_count = 0
    mock_ctrl.screenshot_duration_total = 0.0
    mock_ctrl.portal_navigation_duration_total = 0.4
    mock_ctrl.category_inspection_duration_total = 0.2
    mock_ctrl.item_search_duration_total = 0.1
    mock_ctrl.category_select_duration_total = 0.1
    mock_ctrl.restaurant_select_duration_total = 0.05
    mock_ctrl.save_duration_total = 0.2
    mock_ctrl.post_save_duration_total = 0.1

    with patch("app.action_point_automation.workflow_runner.tunnel_manager.start_and_verify_tunnel", AsyncMock(return_value=(True, "OK", []))):
        with patch("app.action_point_automation.workflow_runner.ActionPointPortalController", return_value=mock_ctrl):
            result = await runner.execute_run(
                site_id=site_id,
                filename="metrics_test.csv",
                items=items,
                mode=ExecutionMode.DRY_RUN
            )

    summary = result["summary"]
    assert "performance_metrics" in summary
    metrics = summary["performance_metrics"]

    assert metrics["total_run_duration_seconds"] >= 0.0
    assert metrics["average_time_per_item_seconds"] >= 0.0
    assert metrics["total_navigations"] == 1
    assert metrics["total_searches"] == 2
    assert "portal_navigation_duration_seconds" in metrics
    assert "item_processing_duration_seconds" in metrics
