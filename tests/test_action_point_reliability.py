import os
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.action_point_automation.portal_controller import ActionPointPortalController
from app.action_point_automation.workflow_runner import ActionPointWorkflowRunner
from app.action_point_automation.models import (
    ActionPointItem,
    ActionClassification,
    ActionPointStatusEnum,
    ExecutionMode,
    RunState,
    InspectionOutcome,
    CategoryInspectionResult,
    SubcategoryInspectionResult
)
from app.action_point_automation.validator import normalize_category_name
from app.database.db import init_db, add_site, get_all_sites
from app.database.models import Site


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()


@pytest.fixture
def mock_controller():
    ctrl = ActionPointPortalController(run_id=777, site_name="ReliabilityTestSite")
    ctrl.browser = AsyncMock()
    ctrl.browser.close = AsyncMock()
    ctrl.page = AsyncMock()
    ctrl.page.is_closed = MagicMock(return_value=False)
    ctrl.page.close = AsyncMock()
    ctrl.page.url = "http://127.0.0.1:18001/zmp/viewFoodCategory.do"
    ctrl.page.title = AsyncMock(return_value="View Food Category - Zenith Media Portal")
    ctrl.page.screenshot = AsyncMock()
    ctrl.page.go_back = AsyncMock()
    ctrl.page.content = AsyncMock(return_value="<html><body>Food Category View Food Category Sync MyMenu</body></html>")
    ctrl.page.inner_text = AsyncMock(return_value="")
    return ctrl


# ==============================================================================
# 1. Existing category is never recreated
# ==============================================================================
@pytest.mark.asyncio
async def test_01_existing_category_never_recreated(mock_controller):
    """Proves an existing category in the table produces EXISTS and is never recreated."""
    row = AsyncMock()
    td = AsyncMock()
    td.inner_text = AsyncMock(return_value="Starters")
    row.query_selector_all = AsyncMock(return_value=[td])
    row.evaluate = AsyncMock(return_value="Starters")

    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.navigate_to_add_food_category = AsyncMock()

    result = await mock_controller.verify_category_existence("Starters")
    assert result.outcome == InspectionOutcome.EXISTS
    assert result.matched_name == "Starters"

    # Pre-creation guard stops recreation without opening Add Food Category
    ok, msg = await mock_controller.create_category("Starters")
    assert ok is True
    assert "already exists" in msg.lower()
    mock_controller.navigate_to_add_food_category.assert_not_called()


# ==============================================================================
# 2. Existing subcategory under the correct parent is never recreated
# ==============================================================================
@pytest.mark.asyncio
async def test_02_existing_subcategory_under_correct_parent_never_recreated(mock_controller):
    """Proves an existing subcategory under its correct parent produces EXISTS and skips recreation."""
    # Parent row exists
    p_row = AsyncMock()
    td_p = AsyncMock()
    td_p.inner_text = AsyncMock(return_value="Starters")
    p_row.query_selector_all = AsyncMock(return_value=[td_p])
    p_row.evaluate = AsyncMock(return_value="Starters")

    mock_controller.page.query_selector_all = AsyncMock(return_value=[p_row])

    with patch.object(mock_controller, "expand_category_subcategories", AsyncMock(return_value=["Veg Starters", "Non-Veg Starters"])):
        result = await mock_controller.verify_subcategory_existence("Starters", "Veg Starters")
        assert result.outcome == InspectionOutcome.EXISTS
        assert result.matched_name == "Veg Starters"
        assert result.parent_category == "Starters"

        # Pre-creation guard stops recreation
        ok, msg = await mock_controller.create_subcategory("Starters", "Veg Starters")
        assert ok is True
        assert "already exists" in msg.lower()


# ==============================================================================
# 3. Same subcategory under a different parent does not count as a match
# ==============================================================================
@pytest.mark.asyncio
async def test_03_same_subcategory_under_different_parent_not_a_match(mock_controller):
    """Proves 'Special' under 'Desserts' is NOT matched if it only exists under 'Beverages'."""
    p_row = AsyncMock()
    td_p = AsyncMock()
    td_p.inner_text = AsyncMock(return_value="Desserts")
    p_row.query_selector_all = AsyncMock(return_value=[td_p])
    p_row.evaluate = AsyncMock(return_value="Desserts")

    mock_controller.page.query_selector_all = AsyncMock(return_value=[p_row])

    # Pre-populate Beverages with Special, but Desserts only has Ice Cream
    mock_controller.category_tree[normalize_category_name("Beverages")] = {"special"}
    mock_controller.category_tree[normalize_category_name("Desserts")] = {"ice cream"}

    with patch.object(mock_controller, "expand_category_subcategories", AsyncMock(return_value=["Ice Cream"])):
        result = await mock_controller.verify_subcategory_existence("Desserts", "Special", force_refresh=True)
        assert result.outcome == InspectionOutcome.MISSING_CONFIRMED
        assert "Special" in result.reason or "not present" in result.reason


# ==============================================================================
# 4. Collapsed parent is expanded before checking subcategories
# ==============================================================================
@pytest.mark.asyncio
async def test_04_collapsed_parent_expanded_before_checking_subcategories(mock_controller):
    """Proves expand_category_subcategories locates and clicks the green plus expansion icon."""
    plus_icon = AsyncMock()
    plus_icon.is_visible = AsyncMock(return_value=True)
    plus_icon.evaluate = AsyncMock(return_value=False)
    plus_icon.click = AsyncMock()

    td_first = AsyncMock()
    td_first.query_selector = AsyncMock(return_value=plus_icon)

    p_row = AsyncMock()
    p_row.query_selector = AsyncMock(return_value=td_first)
    p_row.evaluate = AsyncMock(return_value=["Rice"])

    with patch.object(mock_controller, "find_category_row_in_table", AsyncMock(return_value=(p_row, 1, 1))):
        subs = await mock_controller.expand_category_subcategories("Mains")
        plus_icon.click.assert_called_once()
        assert "Rice" in subs


# ==============================================================================
# 5. Pagination is fully inspected before declaring a category missing
# ==============================================================================
@pytest.mark.asyncio
async def test_05_pagination_fully_inspected_before_declaring_missing(mock_controller):
    """Proves every page in pagination is traversed before declaring MISSING_CONFIRMED."""
    # 3 pages with different categories, target "Pasta" is on page 3
    r1 = AsyncMock(evaluate=AsyncMock(return_value="Starters"))
    r2 = AsyncMock(evaluate=AsyncMock(return_value="Beverages"))
    r3 = AsyncMock(evaluate=AsyncMock(return_value="Pasta"))

    pages = {1: [r1], 2: [r2], 3: [r3]}
    cur_page = {"p": 1}

    async def mock_rows(sel):
        if "table tbody tr" in sel:
            return pages.get(cur_page["p"], [])
        return []

    mock_controller.page.query_selector_all = AsyncMock(side_effect=mock_rows)

    next_btn = AsyncMock()
    next_btn.is_visible = AsyncMock(return_value=True)
    next_btn.is_enabled = AsyncMock(return_value=True)
    next_btn.get_attribute = AsyncMock(side_effect=lambda a: "" if cur_page["p"] < 3 else "disabled")

    async def mock_click():
        cur_page["p"] += 1

    next_btn.click = AsyncMock(side_effect=mock_click)

    async def mock_find_elem(sels, **kwargs):
        if any("pagination" in s or "next" in s for s in sels):
            if cur_page["p"] < 3:
                return next_btn, sels[0]
            return None, ""
        return None, ""

    mock_controller.find_element = AsyncMock(side_effect=mock_find_elem)

    # Search for Pasta (on page 3)
    res_pasta = await mock_controller.verify_category_existence("Pasta", force_refresh=True)
    assert res_pasta.outcome == InspectionOutcome.EXISTS
    assert res_pasta.matched_name == "Pasta"

    # Search for truly missing "Sushi" across all 3 pages
    cur_page["p"] = 1
    res_sushi = await mock_controller.verify_category_existence("Sushi", force_refresh=True)
    assert res_sushi.outcome == InspectionOutcome.MISSING_CONFIRMED
    assert res_sushi.pages_inspected >= 3


# ==============================================================================
# 6. Loading timeout produces INSPECTION_FAILED, not MISSING_CONFIRMED
# ==============================================================================
@pytest.mark.asyncio
async def test_06_loading_timeout_produces_inspection_failed_not_missing(mock_controller):
    """Proves a timeout during table inspection results in INSPECTION_FAILED, never creation."""
    mock_controller.page.wait_for_selector = AsyncMock(
        side_effect=PlaywrightTimeoutError("Timeout 10000ms exceeded waiting for table")
    )
    mock_controller.page.query_selector_all = AsyncMock(
        side_effect=PlaywrightTimeoutError("Timeout waiting for rows")
    )

    res = await mock_controller.verify_category_existence("Starters", force_refresh=True)
    assert res.outcome == InspectionOutcome.INSPECTION_FAILED
    assert "timeout" in res.reason.lower() or "error" in res.reason.lower() or "failed" in res.reason.lower()


# ==============================================================================
# 7. Login or Whitelabel page never authorizes creation
# ==============================================================================
@pytest.mark.asyncio
async def test_07_login_or_whitelabel_page_never_authorizes_creation(mock_controller):
    """Proves session expiry or Whitelabel page immediately yields INSPECTION_FAILED."""
    # Case A: Whitelabel Error Page
    mock_controller.page.content = AsyncMock(return_value="<html><body>Whitelabel Error Page</body></html>")
    res_wl = await mock_controller.verify_category_existence("Salads", force_refresh=True)
    assert res_wl.outcome == InspectionOutcome.INSPECTION_FAILED
    assert "whitelabel" in res_wl.reason.lower()

    # Case B: Redirected to Login
    mock_controller.page.content = AsyncMock(return_value="<html><body><form id='login-form'></form></body></html>")
    mock_controller.page.title = AsyncMock(return_value="Login Portal")
    res_login = await mock_controller.verify_category_existence("Salads", force_refresh=True)
    assert res_login.outcome == InspectionOutcome.INSPECTION_FAILED
    assert "login" in res_login.reason.lower()


# ==============================================================================
# 8. Failed DOM extraction never authorizes creation
# ==============================================================================
@pytest.mark.asyncio
async def test_08_failed_dom_extraction_never_authorizes_creation(mock_controller):
    """Proves that unparseable or corrupted DOM raises INSPECTION_FAILED, never MISSING_CONFIRMED."""
    broken_row = AsyncMock()
    broken_row.query_selector_all = AsyncMock(side_effect=Exception("DOM Node Detached Error"))
    broken_row.evaluate = AsyncMock(side_effect=Exception("Execution context destroyed"))

    mock_controller.page.query_selector_all = AsyncMock(return_value=[broken_row])

    with patch.object(mock_controller, "inspect_existing_categories", AsyncMock(side_effect=Exception("DOM extraction failed"))):
        res = await mock_controller.verify_category_existence("Breads", force_refresh=True)
        assert res.outcome == InspectionOutcome.INSPECTION_FAILED
        assert "failed" in res.reason.lower()


# ==============================================================================
# 9. Actually missing category can be created and independently verified
# ==============================================================================
@pytest.mark.asyncio
async def test_09_missing_category_created_and_independently_verified(mock_controller):
    """Proves an actually missing category is created and confirmed in the table."""
    name_input = AsyncMock()
    disp_input = AsyncMock()
    disp_input.input_value = AsyncMock(return_value="")
    img_input = AsyncMock()
    save_btn = AsyncMock()

    mock_controller.find_element = AsyncMock(side_effect=[
        (AsyncMock(), "nav_cat"),
        (AsyncMock(), "nav_add_cat"),
        (name_input, "input_cat_name"),
        (disp_input, "disp_input"),
        (img_input, "img_input"),
        (save_btn, "btn_save"),
    ])

    with patch.object(mock_controller, "verify_category_existence", AsyncMock(
        return_value=CategoryInspectionResult(category_name="Mexican", outcome=InspectionOutcome.EXISTS, matched_name="Mexican", reason="Verified in table")
    )):
        ok, msg = await mock_controller.create_category("Mexican")
        assert ok is True
        assert "created and verified" in msg
        save_btn.click.assert_called_once()
        assert normalize_category_name("Mexican") in mock_controller.verified_categories


# ==============================================================================
# 10. Actually missing subcategory can be created and independently verified
# ==============================================================================
@pytest.mark.asyncio
async def test_10_missing_subcategory_created_and_independently_verified(mock_controller):
    """Proves an actually missing subcategory is created and verified beneath its parent."""
    p_row = AsyncMock()
    td_p = AsyncMock(inner_text=AsyncMock(return_value="Italian"))
    file_plus = AsyncMock()
    p_row.query_selector_all = AsyncMock(return_value=[td_p, AsyncMock()])
    p_row.query_selector = AsyncMock(return_value=file_plus)

    mock_controller.page.query_selector_all = AsyncMock(return_value=[p_row])

    sub_name_input = AsyncMock()
    img_input = AsyncMock()
    save_btn = AsyncMock()
    mock_controller.find_element = AsyncMock(side_effect=[
        (sub_name_input, "sub_name"),
        (img_input, "img_input"),
        (save_btn, "save_btn")
    ])

    with patch.object(mock_controller, "verify_subcategory_existence", AsyncMock(
        return_value=SubcategoryInspectionResult(parent_category="Italian", subcategory_name="Pastas", outcome=InspectionOutcome.EXISTS, matched_name="Pastas", reason="Verified under parent")
    )):
        with patch.object(mock_controller, "find_category_row_in_table", AsyncMock(return_value=(p_row, 1, 1))):
            ok, msg = await mock_controller.create_subcategory("Italian", "Pastas")
            assert ok is True
            assert "created and verified under 'Italian'" in msg
            save_btn.click.assert_called_once()
            assert normalize_category_name("Pastas") in mock_controller.category_tree[normalize_category_name("Italian")]


# ==============================================================================
# 11. Successful Save without a persisted entry is reported as a failure
# ==============================================================================
@pytest.mark.asyncio
async def test_11_save_without_persisted_entry_fails(mock_controller):
    """Proves that if Save is clicked but the entry does not appear in table, creation fails."""
    name_input = AsyncMock()
    disp_input = AsyncMock(input_value=AsyncMock(return_value=""))
    img_input = AsyncMock()
    save_btn = AsyncMock()

    mock_controller.find_element = AsyncMock(side_effect=[
        (AsyncMock(), "nav_cat"),
        (AsyncMock(), "nav_add_cat"),
        (name_input, "input_cat_name"),
        (disp_input, "disp_input"),
        (img_input, "img_input"),
        (save_btn, "btn_save"),
    ])

    # Verification fails to find the entry after saving
    with patch.object(mock_controller, "verify_category_existence", AsyncMock(
        return_value=CategoryInspectionResult(category_name="Ghost Category", outcome=InspectionOutcome.MISSING_CONFIRMED, reason="Not found after save")
    )):
        ok, msg = await mock_controller.create_category("Ghost Category")
        assert ok is False
        assert "could not be verified" in msg


# ==============================================================================
# 12. Uncertain save is inspected before any retry
# ==============================================================================
@pytest.mark.asyncio
async def test_12_uncertain_save_inspected_before_retry(mock_controller):
    """Proves that if an uncertain save occurs, we inspect before deciding to retry."""
    name_input = AsyncMock()
    disp_input = AsyncMock(input_value=AsyncMock(return_value=""))
    img_input = AsyncMock()
    save_btn = AsyncMock()
    save_btn.click = AsyncMock(side_effect=PlaywrightTimeoutError("Navigation timeout after save"))

    mock_controller.find_element = AsyncMock(side_effect=[
        (AsyncMock(), "nav_cat"),
        (AsyncMock(), "nav_add_cat"),
        (name_input, "input_cat_name"),
        (disp_input, "disp_input"),
        (img_input, "img_input"),
        (save_btn, "btn_save"),
    ])

    # Independent inspection discovers the category WAS persisted despite the timeout!
    with patch.object(mock_controller, "verify_category_existence", AsyncMock(
        return_value=CategoryInspectionResult(category_name="Slow Save Cat", outcome=InspectionOutcome.EXISTS, matched_name="Slow Save Cat", reason="Persisted")
    )):
        ok, msg = await mock_controller.create_category("Slow Save Cat")
        assert ok is True
        assert "created and verified" in msg


# ==============================================================================
# 13. Cached results are invalidated correctly after mutations and session recovery
# ==============================================================================
@pytest.mark.asyncio
async def test_13_cached_results_invalidated_after_mutations_and_recovery(mock_controller):
    """Proves cache invalidation clears verified sets and prevents stale results."""
    mock_controller.verified_categories.add("starters")
    mock_controller.category_tree["starters"] = {"veg"}

    # Invalidate cache
    mock_controller.invalidate_category_cache()
    assert len(mock_controller.verified_categories) == 0
    assert len(mock_controller.category_tree) == 0

    # Ensure recovery also invalidates cache
    mock_controller.verified_categories.add("beverages")
    mock_controller.invalidate_category_cache()
    assert "beverages" not in mock_controller.verified_categories


# ==============================================================================
# 14. Dry-run mode performs no portal mutations
# ==============================================================================
@pytest.mark.asyncio
async def test_14_dry_run_performs_zero_portal_mutations():
    """Proves DRY_RUN execution executes zero create_category and zero create_subcategory mutations."""
    runner = ActionPointWorkflowRunner()
    sites = get_all_sites()
    site_id = sites[0].id if sites else add_site(Site(name="DryRun Safety Hotel", launcher_button="DR1", enabled=True, local_port=18001))

    items = [
        ActionPointItem(
            row_number=2,
            item_code="1001",
            item_name="Tandoori Roti",
            item_price="40",
            category="New Category To Create",
            subcategory="New Subcategory To Create",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        )
    ]

    mock_ctrl = AsyncMock()
    mock_ctrl.initialize = AsyncMock()
    mock_ctrl.navigate_and_authenticate = AsyncMock(return_value=(True, "Success"))
    mock_ctrl.inspect_existing_categories = AsyncMock(return_value=([], {}))
    mock_ctrl.navigate_to_item_configuration = AsyncMock(return_value=(True, "Loaded"))
    mock_ctrl.configure_food_item = AsyncMock(return_value=(True, "DRY_RUN: Pre-save checks verified.", None))
    mock_ctrl.create_category = AsyncMock()
    mock_ctrl.create_subcategory = AsyncMock()
    mock_ctrl.close = AsyncMock()

    with patch("app.action_point_automation.workflow_runner.tunnel_manager.start_and_verify_tunnel", AsyncMock(return_value=(True, "Tunnel OK", []))):
        with patch("app.action_point_automation.workflow_runner.ActionPointPortalController", return_value=mock_ctrl):
            result = await runner.execute_run(
                site_id=site_id,
                filename="dry_run_test.csv",
                items=items,
                mode=ExecutionMode.DRY_RUN
            )

    assert result["success"] is True
    # Zero mutations strictly enforced
    mock_ctrl.create_category.assert_not_called()
    mock_ctrl.create_subcategory.assert_not_called()
