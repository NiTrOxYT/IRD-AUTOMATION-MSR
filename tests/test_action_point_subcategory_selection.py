import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.action_point_automation.models import ActionPointItem, ActionClassification, ExecutionMode
from app.action_point_automation.portal_controller import ActionPointPortalController
from app.action_point_automation.workflow_runner import ActionPointWorkflowRunner
from app.database.models import Site
from app.database.db import get_all_sites, add_site


@pytest.fixture
def mock_controller():
    ctrl = ActionPointPortalController(run_id="test_subcat", site_name="Test Hotel")
    ctrl.browser = AsyncMock()
    ctrl.context = AsyncMock()
    ctrl.page = AsyncMock()
    ctrl.page.is_closed = MagicMock(return_value=False)
    ctrl.snapshot = AsyncMock(return_value=MagicMock(screenshot_path="dummy.png"))
    return ctrl


@pytest.mark.asyncio
async def test_01_collapsed_parent_category_expanded(mock_controller):
    """Collapsed parent category has its green '+' clicked, subcategories appear, and checkbox is checked."""
    cat_elem = AsyncMock()
    parent_row = AsyncMock()
    plus_ctrl = AsyncMock()
    plus_ctrl.is_visible = AsyncMock(return_value=True)
    plus_ctrl.click = AsyncMock()
    plus_ctrl.evaluate = AsyncMock(return_value="img")

    # Parent row evaluation: not expanded initially
    parent_row.evaluate = AsyncMock(side_effect=[
        False,  # is_expanded check before click
        True    # check_rendered after click
    ])
    parent_row.evaluate_handle = AsyncMock(return_value=None)
    parent_row.query_selector = AsyncMock(side_effect=lambda sel: plus_ctrl if "plus" in sel else None)
    cat_elem.evaluate_handle = AsyncMock(return_value=None)
    cat_elem.query_selector = AsyncMock(return_value=parent_row)

    sub_elem = AsyncMock()
    sub_chk = AsyncMock()
    sub_chk.is_checked = AsyncMock(side_effect=[False, True])  # unchecked initially, checked after click
    sub_chk.click = AsyncMock()
    sub_chk.evaluate = AsyncMock(return_value=True)
    sub_elem.query_selector = AsyncMock(return_value=sub_chk)

    # Subcategory lookup inside parent_row
    async def parent_qs(sel):
        if "plus" in sel:
            return plus_ctrl
        if "Cereals and Such" in sel:
            return sub_elem
        return None

    parent_row.query_selector = AsyncMock(side_effect=parent_qs)

    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "panel"))
    mock_controller.page.query_selector = AsyncMock(return_value=cat_elem)

    ok, msg = await mock_controller._expand_and_select_category_subcategory("24X7 Breakfasts", "Cereals and Such")
    assert ok is True
    assert "selected and verified" in msg
    plus_ctrl.click.assert_called_once()
    sub_chk.click.assert_called_once()


@pytest.mark.asyncio
async def test_02_parent_category_already_expanded(mock_controller):
    """Parent category already expanded does NOT click the expansion control (avoids collapsing)."""
    cat_elem = AsyncMock()
    parent_row = AsyncMock()
    plus_ctrl = AsyncMock()
    plus_ctrl.click = AsyncMock()

    # DOM evaluate reports already expanded
    parent_row.evaluate = AsyncMock(return_value=True)
    parent_row.evaluate_handle = AsyncMock(return_value=None)
    cat_elem.evaluate_handle = AsyncMock(return_value=None)
    cat_elem.query_selector = AsyncMock(return_value=parent_row)

    sub_elem = AsyncMock()
    sub_chk = AsyncMock()
    sub_chk.is_checked = AsyncMock(return_value=True)  # already checked
    sub_elem.query_selector = AsyncMock(return_value=sub_chk)

    async def parent_qs(sel):
        if "plus" in sel:
            return plus_ctrl
        if "Penne I Spaghetti" in sel:
            return sub_elem
        return None

    parent_row.query_selector = AsyncMock(side_effect=parent_qs)

    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "panel"))
    mock_controller.page.query_selector = AsyncMock(return_value=cat_elem)

    ok, msg = await mock_controller._expand_and_select_category_subcategory("Artisan Pasta & Risotto", "Penne I Spaghetti")
    assert ok is True
    assert "selected and verified" in msg
    plus_ctrl.click.assert_not_called()


@pytest.mark.asyncio
async def test_03_multiple_categories_similarly_named_subcategories(mock_controller):
    """Similarly named subcategories across multiple categories are strictly scoped to the requested parent."""
    # Parent A: Breakfast (has subcategory 'Eggs')
    # Parent B: Dinner (also has subcategory 'Eggs')
    row_breakfast = AsyncMock()
    row_breakfast.evaluate = AsyncMock(return_value=True)
    row_breakfast.evaluate_handle = AsyncMock(return_value=None)

    sub_eggs_breakfast = AsyncMock()
    chk_eggs_breakfast = AsyncMock()
    chk_eggs_breakfast.is_checked = AsyncMock(side_effect=[False, True])
    chk_eggs_breakfast.click = AsyncMock()
    sub_eggs_breakfast.query_selector = AsyncMock(return_value=chk_eggs_breakfast)

    row_dinner = AsyncMock()
    sub_eggs_dinner = AsyncMock()
    chk_eggs_dinner = AsyncMock()
    chk_eggs_dinner.click = AsyncMock()

    async def b_qs(sel):
        if "Eggs" in sel:
            return sub_eggs_breakfast
        return None

    row_breakfast.query_selector = AsyncMock(side_effect=b_qs)

    async def page_qs(sel):
        if "Breakfast" in sel:
            return row_breakfast
        if "Dinner" in sel:
            return row_dinner
        return None

    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "panel"))
    mock_controller.page.query_selector = AsyncMock(side_effect=page_qs)

    # Request Breakfast -> Eggs
    ok, msg = await mock_controller._expand_and_select_category_subcategory("Breakfast", "Eggs")
    assert ok is True
    # Breakfast eggs checkbox was clicked
    chk_eggs_breakfast.click.assert_called_once()
    # Dinner eggs checkbox was NOT touched
    chk_eggs_dinner.click.assert_not_called()


@pytest.mark.asyncio
async def test_04_hidden_subcategory_element_before_expansion(mock_controller):
    """A hidden subcategory element is not clicked until parent expansion renders it visible."""
    cat_elem = AsyncMock()
    parent_row = AsyncMock()
    plus_ctrl = AsyncMock()
    plus_ctrl.is_visible = AsyncMock(return_value=True)
    plus_ctrl.click = AsyncMock()
    plus_ctrl.evaluate = AsyncMock(return_value="img")

    # Not expanded initially
    parent_row.evaluate = AsyncMock(side_effect=[False, True])
    parent_row.evaluate_handle = AsyncMock(return_value=None)
    cat_elem.query_selector = AsyncMock(return_value=parent_row)

    sub_elem = AsyncMock()
    sub_chk = AsyncMock()
    # Hidden before expansion, visible after
    sub_chk.is_visible = AsyncMock(side_effect=[False, True, True])
    sub_chk.is_checked = AsyncMock(side_effect=[False, True])
    sub_chk.click = AsyncMock()
    sub_elem.query_selector = AsyncMock(return_value=sub_chk)

    async def parent_qs(sel):
        if "plus" in sel:
            return plus_ctrl
        if "Waffles" in sel:
            return sub_elem
        return None

    parent_row.query_selector = AsyncMock(side_effect=parent_qs)

    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "panel"))
    mock_controller.page.query_selector = AsyncMock(return_value=cat_elem)

    ok, msg = await mock_controller._expand_and_select_category_subcategory("Breakfast", "Waffles")
    assert ok is True
    plus_ctrl.click.assert_called_once()
    sub_chk.click.assert_called_once()


@pytest.mark.asyncio
async def test_05_missing_subcategory_fails_safely(mock_controller):
    """Missing subcategory under a valid parent fails cleanly without clicking unrelated elements."""
    cat_elem = AsyncMock()
    parent_row = AsyncMock()
    plus_ctrl = AsyncMock()
    plus_ctrl.is_visible = AsyncMock(return_value=True)
    plus_ctrl.click = AsyncMock()
    plus_ctrl.evaluate = AsyncMock(return_value="img")

    parent_row.evaluate = AsyncMock(return_value=True)  # expanded
    parent_row.evaluate_handle = AsyncMock(return_value=None)
    parent_row.query_selector = AsyncMock(return_value=None)  # subcategory not found
    cat_elem.query_selector = AsyncMock(return_value=parent_row)

    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "panel"))
    mock_controller.page.query_selector = AsyncMock(side_effect=lambda sel: cat_elem if "Desserts" in sel else None)

    ok, msg = await mock_controller._expand_and_select_category_subcategory("Desserts", "NonExistentGelato")
    assert ok is False
    assert "BLOCKED — Subcategory 'NonExistentGelato' not found under category 'Desserts'" in msg


@pytest.mark.asyncio
async def test_06_checkbox_selection_verification_failure(mock_controller):
    """Subcategory checkbox that remains unchecked after clicking reports verification failure."""
    cat_elem = AsyncMock()
    parent_row = AsyncMock()
    parent_row.evaluate = AsyncMock(return_value=True)
    parent_row.evaluate_handle = AsyncMock(return_value=None)
    cat_elem.query_selector = AsyncMock(return_value=parent_row)

    sub_elem = AsyncMock()
    sub_chk = AsyncMock()
    # Checkbox refuses to check (e.g. disabled or click intercepted)
    sub_chk.is_checked = AsyncMock(return_value=False)
    sub_chk.evaluate = AsyncMock(return_value=False)
    sub_chk.click = AsyncMock()
    sub_elem.query_selector = AsyncMock(return_value=sub_chk)

    async def parent_qs(sel):
        if "Smoothies" in sel:
            return sub_elem
        return None

    parent_row.query_selector = AsyncMock(side_effect=parent_qs)

    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "panel"))
    mock_controller.page.query_selector = AsyncMock(return_value=cat_elem)

    ok, msg = await mock_controller._expand_and_select_category_subcategory("Beverages", "Smoothies")
    assert ok is False
    assert "FAILED — SELECT_SUBCATEGORY: Subcategory checkbox for 'Smoothies' could not be verified as checked" in msg


@pytest.mark.asyncio
async def test_07_recovery_after_failed_selection_no_duplicate_creations():
    """Item configuration failure isolates the row and does NOT trigger duplicate category/subcategory creation."""
    runner = ActionPointWorkflowRunner()
    sites = get_all_sites()
    site_id = sites[0].id if sites else add_site(Site(name="Recovery Site", launcher_button="RS", enabled=True, local_port=18001))

    items = [
        ActionPointItem(
            row_number=2,
            item_code="9001",
            item_name="Item Fail Subcat",
            item_price="200",
            category="Main Course",
            subcategory="MissingSub",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        ),
        ActionPointItem(
            row_number=3,
            item_code="9002",
            item_name="Item Success",
            item_price="300",
            category="Main Course",
            subcategory="ValidSub",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        )
    ]

    mock_ctrl = AsyncMock()
    mock_ctrl.initialize = AsyncMock()
    mock_ctrl.navigate_and_authenticate = AsyncMock(return_value=(True, "Success"))
    mock_ctrl.inspect_existing_categories = AsyncMock(return_value=(["Main Course"], {"Main Course": ["ValidSub", "MissingSub"]}))
    mock_ctrl.navigate_to_item_configuration = AsyncMock(return_value=(True, "Loaded"))
    mock_ctrl.page.is_closed = MagicMock(return_value=False)

    # First item fails subcategory selection on form, second item succeeds
    mock_ctrl.configure_food_item = AsyncMock(side_effect=[
        (False, "BLOCKED — Subcategory 'MissingSub' not found", None),
        (True, "SUCCESS: Item configuration saved and verified.", "success.png")
    ])

    with patch("app.action_point_automation.workflow_runner.tunnel_manager.start_and_verify_tunnel", AsyncMock(return_value=(True, "OK", []))):
        with patch("app.action_point_automation.workflow_runner.ActionPointPortalController", return_value=mock_ctrl):
            result = await runner.execute_run(
                site_id=site_id,
                filename="recovery_test.csv",
                items=items,
                mode=ExecutionMode.LIVE
            )

    # Verify category and subcategory creation was NEVER called for the failed item
    mock_ctrl.create_category.assert_not_called()
    mock_ctrl.create_subcategory.assert_not_called()

    # Second item was processed
    assert mock_ctrl.configure_food_item.call_count == 2
    assert result["summary"]["failed_rows"] + result["summary"]["blocked_rows"] == 1
    assert result["summary"]["successful_rows"] == 1
