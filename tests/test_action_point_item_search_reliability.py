import time
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.action_point_automation.portal_controller import ActionPointPortalController
from app.action_point_automation.workflow_runner import ActionPointWorkflowRunner
from app.action_point_automation.models import (
    ActionPointItem,
    ActionClassification,
    ActionPointStatusEnum,
    ExecutionMode
)
from app.database.db import init_db, add_site, get_all_sites
from app.database.models import Site


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()


@pytest.fixture
def mock_controller():
    ctrl = ActionPointPortalController(run_id="test_search_rel", site_name="ItemSearchReliabilitySite")
    ctrl.browser = AsyncMock()
    ctrl.context = AsyncMock()
    ctrl.page = AsyncMock()
    ctrl.page.is_closed = MagicMock(return_value=False)
    ctrl.page.url = "http://127.0.0.1:18001/zmp/itemConfiguration.do"
    ctrl.page.title = AsyncMock(return_value="Food Items Configuration Management")
    ctrl.page.inner_text = AsyncMock(return_value="Food Items Configuration Food Category Restaurant")
    ctrl.snapshot = AsyncMock(return_value=MagicMock(screenshot_path="dummy_screenshot.png"))
    return ctrl


# ==============================================================================
# 1. Item search followed by item checkbox selection
# ==============================================================================
@pytest.mark.asyncio
async def test_01_item_search_followed_by_checkbox_selection(mock_controller):
    """
    Search input is filled with exact item code preserving leading zeros.
    Matching row is found and its item checkbox is explicitly clicked and verified.
    """
    item = ActionPointItem(
        row_number=1,
        item_code="00149001",
        item_name="Pasta In Tomato Marinara Sauce",
        item_price="1150.00",
        category="Artisan Pasta & Risotto",
        subcategory="Penne I Spaghetti",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    search_input = AsyncMock()
    search_input.fill = AsyncMock()
    search_input.press = AsyncMock()
    search_btn = AsyncMock()
    search_btn.inner_text = AsyncMock(return_value="Search")
    search_btn.click = AsyncMock()

    mock_controller.find_element = AsyncMock(side_effect=[
        (search_input, "search_input"),
        (search_btn, "search_btn"),
        (AsyncMock(), "cat_panel"),
        (AsyncMock(), "rest_ird_default"),
        (AsyncMock(), "conf_btn")
    ])

    row = AsyncMock()
    chk_cell = AsyncMock()
    chk_cell.inner_text = AsyncMock(return_value="")
    code_cell = AsyncMock()
    code_cell.inner_text = AsyncMock(return_value="00149001")
    name_cell = AsyncMock()
    name_cell.inner_text = AsyncMock(return_value="Pasta In Tomato Marinara Sauce*")
    row.query_selector_all = AsyncMock(return_value=[chk_cell, code_cell, name_cell])

    item_chk = AsyncMock()
    # Initially False, then clicked, then True
    item_chk.is_checked = AsyncMock(side_effect=[False, True, True])
    item_chk.click = AsyncMock()
    row.query_selector = AsyncMock(return_value=item_chk)

    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])

    with patch.object(mock_controller, "_expand_and_select_category_subcategory", AsyncMock(return_value=(True, "OK"))):
        ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=True)
        assert ok is True
        assert "DRY_RUN" in msg
        # Exact code with leading zeros entered
        search_input.fill.assert_any_call("00149001")
        # Item checkbox clicked
        item_chk.click.assert_called_once()


# ==============================================================================
# 2. Configuration controls appearing after item selection
# ==============================================================================
@pytest.mark.asyncio
async def test_02_configuration_controls_appearing_after_item_selection(mock_controller):
    """
    Verifies that _wait_for_configuration_form_readiness observes the DOM
    and confirms Food Category and Restaurant controls are ready.
    """
    mock_controller.page = MagicMock()
    mock_controller.page.is_closed = MagicMock(return_value=False)

    eval_calls = [
        True,   # Food Category section present
        True    # Restaurant section present
    ]
    mock_controller.page.evaluate = AsyncMock(side_effect=eval_calls)
    mock_controller.page.wait_for_function = AsyncMock()

    loc = AsyncMock()
    loc.wait_for = AsyncMock()
    loc.first = loc
    mock_controller.page.locator = MagicMock(return_value=loc)

    ok, msg = await mock_controller._wait_for_configuration_form_readiness(timeout_ms=3000)
    assert ok is True
    assert "ready" in msg.lower()


# ==============================================================================
# 3. Category-only configuration with an empty subcategory
# ==============================================================================
@pytest.mark.asyncio
async def test_03_category_only_configuration_empty_subcategory(mock_controller):
    """
    When subcategory is empty / None / '-', category is selected,
    categories are NOT expanded, subcategories are NOT searched, and restaurant proceeds.
    """
    cat_elem = AsyncMock()
    parent_row = AsyncMock()
    cat_chk = AsyncMock()
    cat_chk.is_checked = AsyncMock(side_effect=[False, True])
    cat_chk.click = AsyncMock()
    parent_row.query_selector = AsyncMock(return_value=cat_chk)
    parent_row.evaluate_handle = AsyncMock(return_value=None)
    cat_elem.query_selector = AsyncMock(return_value=parent_row)

    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "cat_panel"))
    mock_controller.page.query_selector = AsyncMock(return_value=cat_elem)

    # Call with empty subcategory
    ok, msg = await mock_controller._expand_and_select_category_subcategory("Artisan Pasta & Risotto", "")
    assert ok is True
    assert "selected and verified" in msg
    cat_chk.click.assert_called_once()
    # Expansion evaluate was not called
    parent_row.evaluate.assert_not_called()


# ==============================================================================
# 4. Category plus subcategory configuration
# ==============================================================================
@pytest.mark.asyncio
async def test_04_category_plus_subcategory_configuration(mock_controller):
    """
    When subcategory is provided, parent category is verified,
    green '+' is clicked if collapsed, subcategory is located and selected.
    """
    cat_elem = AsyncMock()
    parent_row = AsyncMock()
    cat_chk = AsyncMock()
    cat_chk.is_checked = AsyncMock(return_value=True)

    plus_ctrl = AsyncMock()
    plus_ctrl.is_visible = AsyncMock(return_value=True)
    plus_ctrl.click = AsyncMock()
    plus_ctrl.evaluate = AsyncMock(return_value="img")

    sub_elem = AsyncMock()
    sub_chk = AsyncMock()
    sub_chk.is_visible = AsyncMock(return_value=True)
    sub_chk.is_checked = AsyncMock(side_effect=[False, True])
    sub_chk.click = AsyncMock()
    sub_elem.query_selector = AsyncMock(return_value=sub_chk)

    parent_row.evaluate = AsyncMock(side_effect=[False, True])
    parent_row.evaluate_handle = AsyncMock(return_value=None)
    cat_elem.query_selector = AsyncMock(return_value=parent_row)

    async def parent_qs(sel):
        if "checkbox" in sel:
            return cat_chk
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
    plus_ctrl.click.assert_called_once()
    sub_chk.click.assert_called_once()


# ==============================================================================
# 5. A collapsed parent requiring the green '+'
# ==============================================================================
@pytest.mark.asyncio
async def test_05_collapsed_parent_requiring_green_plus(mock_controller):
    """
    Proves that a collapsed category row detects is_expanded=False and clicks
    the green '+' expansion icon specifically on that category row.
    """
    cat_elem = AsyncMock()
    parent_row = AsyncMock()
    cat_chk = AsyncMock()
    cat_chk.is_checked = AsyncMock(return_value=True)

    plus_icon = AsyncMock()
    plus_icon.is_visible = AsyncMock(return_value=True)
    plus_icon.click = AsyncMock()
    plus_icon.evaluate = AsyncMock(return_value="img")

    sub_elem = AsyncMock()
    sub_chk = AsyncMock()
    sub_chk.is_visible = AsyncMock(return_value=True)
    sub_chk.is_checked = AsyncMock(side_effect=[False, True])
    sub_elem.query_selector = AsyncMock(return_value=sub_chk)

    parent_row.evaluate = AsyncMock(side_effect=[False, True])
    parent_row.evaluate_handle = AsyncMock(return_value=None)
    cat_elem.query_selector = AsyncMock(return_value=parent_row)

    async def parent_qs(sel):
        if "checkbox" in sel:
            return cat_chk
        if "plus" in sel:
            return plus_icon
        if "Penne I Spaghetti" in sel:
            return sub_elem
        return None

    parent_row.query_selector = AsyncMock(side_effect=parent_qs)
    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "panel"))
    mock_controller.page.query_selector = AsyncMock(return_value=cat_elem)

    ok, msg = await mock_controller._expand_and_select_category_subcategory("Artisan Pasta & Risotto", "Penne I Spaghetti")
    assert ok is True
    plus_icon.click.assert_called_once()


# ==============================================================================
# 6. An already-checked category or restaurant
# ==============================================================================
@pytest.mark.asyncio
async def test_06_already_checked_category_or_restaurant(mock_controller):
    """
    If category or restaurant is already checked, the automation leaves it checked
    and does NOT click it (preventing toggling off).
    """
    # 1. Already checked category
    cat_elem = AsyncMock()
    parent_row = AsyncMock()
    cat_chk = AsyncMock()
    cat_chk.is_checked = AsyncMock(return_value=True)
    cat_chk.click = AsyncMock()
    parent_row.query_selector = AsyncMock(return_value=cat_chk)
    parent_row.evaluate_handle = AsyncMock(return_value=None)
    cat_elem.query_selector = AsyncMock(return_value=parent_row)

    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "cat_panel"))
    mock_controller.page.query_selector = AsyncMock(return_value=cat_elem)

    ok, msg, _ = await mock_controller._select_category("Artisan Pasta & Risotto")
    assert ok is True
    # Crucial: click is NOT called since it was already checked!
    cat_chk.click.assert_not_called()

    # 2. Already checked restaurant
    item = ActionPointItem(
        row_number=1,
        item_code="149000001",
        item_name="Pasta In Tomato Marinara Sauce",
        item_price="1150.00",
        category="Artisan Pasta & Risotto",
        subcategory=None,
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    search_input = AsyncMock()
    search_btn = AsyncMock()
    search_btn.inner_text = AsyncMock(return_value="Search")
    rest_elem = AsyncMock()
    rest_chk = AsyncMock()
    rest_chk.is_checked = AsyncMock(return_value=True)
    rest_chk.click = AsyncMock()
    rest_elem.query_selector = AsyncMock(return_value=rest_chk)

    mock_controller.find_element = AsyncMock(side_effect=[
        (search_input, "search_input"),
        (search_btn, "search_btn"),
        (rest_elem, "rest_ird_default")
    ])

    row = AsyncMock()
    td_code = AsyncMock()
    td_code.inner_text = AsyncMock(return_value="149000001")
    td_name = AsyncMock()
    td_name.inner_text = AsyncMock(return_value="Pasta In Tomato Marinara Sauce")
    row.query_selector_all = AsyncMock(return_value=[td_code, td_name])
    item_chk = AsyncMock()
    item_chk.is_checked = AsyncMock(return_value=True)
    row.query_selector = AsyncMock(return_value=item_chk)
    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])

    with patch.object(mock_controller, "_expand_and_select_category_subcategory", AsyncMock(return_value=(True, "OK"))):
        ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=True)
        assert ok is True
        # Restaurant checkbox was already checked: click is NOT called!
        rest_chk.click.assert_not_called()


# ==============================================================================
# 7. A hidden subcategory that becomes visible after expansion
# ==============================================================================
@pytest.mark.asyncio
async def test_07_hidden_subcategory_becomes_visible_after_expansion(mock_controller):
    """
    Subcategory element initially not visible in DOM is not clicked until
    expansion renders it visible.
    """
    cat_elem = AsyncMock()
    parent_row = AsyncMock()
    cat_chk = AsyncMock()
    cat_chk.is_checked = AsyncMock(return_value=True)

    plus_ctrl = AsyncMock()
    plus_ctrl.is_visible = AsyncMock(return_value=True)
    plus_ctrl.click = AsyncMock()
    plus_ctrl.evaluate = AsyncMock(return_value="img")

    parent_row.evaluate = AsyncMock(side_effect=[False, True])
    parent_row.evaluate_handle = AsyncMock(return_value=None)
    cat_elem.query_selector = AsyncMock(return_value=parent_row)

    sub_elem = AsyncMock()
    sub_chk = AsyncMock()
    # Initially hidden, then visible after expansion
    sub_elem.is_visible = AsyncMock(side_effect=[False, True, True])
    sub_chk.is_visible = AsyncMock(side_effect=[False, True, True])
    sub_chk.is_checked = AsyncMock(side_effect=[False, True])
    sub_chk.click = AsyncMock()
    sub_elem.query_selector = AsyncMock(return_value=sub_chk)

    async def parent_qs(sel):
        if "checkbox" in sel:
            return cat_chk
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
    plus_ctrl.click.assert_called_once()
    sub_chk.click.assert_called_once()


# ==============================================================================
# 8. Preventing Configure from being clicked during search
# ==============================================================================
@pytest.mark.asyncio
async def test_08_preventing_configure_clicked_during_search(mock_controller):
    """
    If the search button query matches a Configure button, the search routine
    safely detects it and falls back to Enter, preventing unintended submission.
    """
    item = ActionPointItem(
        row_number=1,
        item_code="149000001",
        item_name="Pasta In Tomato Marinara Sauce",
        item_price="1150.00",
        category="Artisan Pasta & Risotto",
        subcategory=None,
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    search_input = AsyncMock()
    search_input.press = AsyncMock()
    # Malformed selector accidentally matched Configure button
    conf_as_search_btn = AsyncMock()
    conf_as_search_btn.inner_text = AsyncMock(return_value="Configure")
    conf_as_search_btn.click = AsyncMock()

    rest_elem = AsyncMock()
    rest_chk = AsyncMock()
    rest_chk.is_checked = AsyncMock(return_value=True)
    rest_elem.query_selector = AsyncMock(return_value=rest_chk)

    mock_controller.find_element = AsyncMock(side_effect=[
        (search_input, "search_input"),
        (conf_as_search_btn, "search_btn"),
        (rest_elem, "rest_ird_default")
    ])

    row = AsyncMock()
    td_code = AsyncMock()
    td_code.inner_text = AsyncMock(return_value="149000001")
    td_name = AsyncMock()
    td_name.inner_text = AsyncMock(return_value="Pasta In Tomato Marinara Sauce")
    row.query_selector_all = AsyncMock(return_value=[td_code, td_name])
    item_chk = AsyncMock()
    item_chk.is_checked = AsyncMock(return_value=True)
    row.query_selector = AsyncMock(return_value=item_chk)
    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])

    with patch.object(mock_controller, "_expand_and_select_category_subcategory", AsyncMock(return_value=(True, "OK"))):
        ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=True)
        assert ok is True
        # Configure button was NOT clicked during search!
        conf_as_search_btn.click.assert_not_called()
        # Fallback to Enter on search input was executed instead
        search_input.press.assert_called_with("Enter")


# ==============================================================================
# 9. Correct saved-state verification
# ==============================================================================
@pytest.mark.asyncio
async def test_09_correct_saved_state_verification(mock_controller):
    """
    In live execution, Configure is clicked, portal confirms success,
    persisted state is verified, and item is recorded in processed_items.
    """
    item = ActionPointItem(
        row_number=1,
        item_code="149000001",
        item_name="Pasta In Tomato Marinara Sauce",
        item_price="1150.00",
        category="Artisan Pasta & Risotto",
        subcategory="Penne I Spaghetti",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    search_input = AsyncMock()
    search_btn = AsyncMock()
    search_btn.inner_text = AsyncMock(return_value="Search")
    rest_elem = AsyncMock()
    rest_chk = AsyncMock()
    rest_chk.is_checked = AsyncMock(return_value=True)
    rest_elem.query_selector = AsyncMock(return_value=rest_chk)

    conf_btn = AsyncMock()
    conf_btn.click = AsyncMock()

    mock_controller.find_element = AsyncMock(side_effect=[
        (search_input, "search_input"),
        (search_btn, "search_btn"),
        (rest_elem, "rest_ird_default"),
        (conf_btn, "conf_btn")
    ])

    row = AsyncMock()
    td_chk = AsyncMock()
    td_code = AsyncMock()
    td_code.inner_text = AsyncMock(return_value="149000001")
    td_name = AsyncMock()
    td_name.inner_text = AsyncMock(return_value="Pasta In Tomato Marinara Sauce*")
    row.query_selector_all = AsyncMock(return_value=[td_chk, td_code, td_name])
    item_chk = AsyncMock()
    item_chk.is_checked = AsyncMock(return_value=True)
    row.query_selector = AsyncMock(return_value=item_chk)

    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.page.wait_for_load_state = AsyncMock()
    mock_controller.page.inner_text = AsyncMock(return_value="Configuration saved successfully")

    with patch.object(mock_controller, "_expand_and_select_category_subcategory", AsyncMock(return_value=(True, "OK"))):
        ok, msg, ss = await mock_controller.configure_food_item(item, dry_run=False)
        assert ok is True
        assert "SUCCESS: Item configuration saved and verified" in msg
        conf_btn.click.assert_called_once()
        assert "149000001" in mock_controller.processed_items


# ==============================================================================
# 10. Failure handling without duplicate creation
# ==============================================================================
@pytest.mark.asyncio
async def test_10_failure_handling_without_duplicate_creation():
    """
    When item configuration fails, the error is isolated, screenshot captured,
    and neither create_category nor create_subcategory is invoked.
    """
    runner = ActionPointWorkflowRunner()
    sites = get_all_sites()
    site_id = sites[0].id if sites else add_site(Site(name="Recovery Site 2", launcher_button="RS2", enabled=True, local_port=18002))

    items = [
        ActionPointItem(
            row_number=2,
            item_code="149000001",
            item_name="Pasta Marinara",
            item_price="1150.00",
            category="Artisan Pasta & Risotto",
            subcategory="MissingPenne",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        ),
        ActionPointItem(
            row_number=3,
            item_code="149000002",
            item_name="Risotto Funghi",
            item_price="1250.00",
            category="Artisan Pasta & Risotto",
            subcategory="ValidRisotto",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        )
    ]

    mock_ctrl = AsyncMock()
    mock_ctrl.initialize = AsyncMock()
    mock_ctrl.navigate_and_authenticate = AsyncMock(return_value=(True, "Success"))
    mock_ctrl.inspect_existing_categories = AsyncMock(return_value=(["Artisan Pasta & Risotto"], {"Artisan Pasta & Risotto": ["ValidRisotto", "MissingPenne"]}))
    mock_ctrl.navigate_to_item_configuration = AsyncMock(return_value=(True, "Loaded"))
    mock_ctrl.page.is_closed = MagicMock(return_value=False)

    mock_ctrl.configure_food_item = AsyncMock(side_effect=[
        (False, "BLOCKED — Subcategory 'MissingPenne' not found under category 'Artisan Pasta & Risotto'", "fail.png"),
        (True, "SUCCESS: Item configuration saved and verified.", "success.png")
    ])

    with patch("app.action_point_automation.workflow_runner.tunnel_manager.start_and_verify_tunnel", AsyncMock(return_value=(True, "OK", []))):
        with patch("app.action_point_automation.workflow_runner.ActionPointPortalController", return_value=mock_ctrl):
            result = await runner.execute_run(
                site_id=site_id,
                filename="recovery_test_subcat.csv",
                items=items,
                mode=ExecutionMode.LIVE
            )

    # Creation methods were NEVER called for the failed item
    mock_ctrl.create_category.assert_not_called()
    mock_ctrl.create_subcategory.assert_not_called()

    # Batch continued safely
    assert mock_ctrl.configure_food_item.call_count == 2
    assert result["summary"]["failed_rows"] + result["summary"]["blocked_rows"] == 1
    assert result["summary"]["successful_rows"] == 1


# ==============================================================================
# 11. Direct path navigation and post-selection page load snapshot
# ==============================================================================
@pytest.mark.asyncio
async def test_11_direct_path_navigation_and_post_selection_snapshot(mock_controller):
    """
    1. navigate_to_item_configuration goes directly to configureFoodItem.do path without sidebar clicking.
    2. Takes items_configuration_page_loaded snapshot after search box appears.
    3. configure_food_item selects item checkbox and takes item_{code}_selected_page_loaded snapshot before category selection.
    """
    mock_controller.page.url = "about:blank"
    mock_controller.page.goto = AsyncMock()
    mock_controller.portal_base_url = "http://localhost:56865"

    search_box = AsyncMock()
    search_box.is_visible = AsyncMock(return_value=True)
    mock_controller.page.wait_for_selector = AsyncMock(return_value=search_box)
    mock_controller.find_element = AsyncMock(return_value=(search_box, "search_box"))

    # Test direct navigation
    ok, msg = await mock_controller.navigate_to_item_configuration(force=True)
    assert ok is True
    mock_controller.page.goto.assert_called_with("http://localhost:56865/configureFoodItem.do", timeout=15000, wait_until="domcontentloaded")

    # Snapshot on page load was captured
    mock_controller.snapshot.assert_any_call("items_configuration_page_loaded", expected_state="ITEMS_CONFIG_LOADED", take_screenshot=True)

    # Test post-item-selection snapshot
    item = ActionPointItem(
        row_number=1,
        item_code="149000001",
        item_name="Penne Pomodoro",
        item_price="1200.00",
        category="Artisan Pasta & Risotto",
        subcategory="Penne I Spaghetti",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    search_input = AsyncMock()
    search_btn = AsyncMock()
    search_btn.inner_text = AsyncMock(return_value="Search")
    rest_elem = AsyncMock()
    rest_elem.is_checked = AsyncMock(return_value=True)
    conf_btn = AsyncMock()

    mock_controller.find_element = AsyncMock(side_effect=[
        (search_input, "search_input"),
        (search_btn, "search_btn"),
        (rest_elem, "rest_ird_default"),
        (conf_btn, "conf_btn")
    ])

    row = AsyncMock()
    c1, c2, c3 = AsyncMock(), AsyncMock(), AsyncMock()
    c1.inner_text = AsyncMock(return_value="")
    c2.inner_text = AsyncMock(return_value="149000001")
    c3.inner_text = AsyncMock(return_value="Penne Pomodoro")
    row.query_selector_all = AsyncMock(return_value=[c1, c2, c3])

    item_chk = AsyncMock()
    item_chk.is_checked = AsyncMock(side_effect=[False, True, True])
    row.query_selector = AsyncMock(return_value=item_chk)
    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])

    with patch.object(mock_controller, "_expand_and_select_category_subcategory", AsyncMock(return_value=(True, "OK"))):
        with patch.object(mock_controller, "_wait_for_configuration_form_readiness", AsyncMock(return_value=(True, "Ready"))):
            ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=True)
            assert ok is True
            # Verified post-selection snapshot was captured
            mock_controller.snapshot.assert_any_call(
                f"item_{item.item_code}_selected_page_loaded",
                expected_state="ITEM_SELECTED_PAGE_LOADED",
                take_screenshot=True,
                row_number=item.row_number,
                item_code=item.item_code
            )


# ==============================================================================
# 12. Correct item-row checkbox selection (scoped to matching row, never global)
# ==============================================================================
@pytest.mark.asyncio
async def test_12_correct_item_row_checkbox_selection(mock_controller):
    """
    Validates that item checkbox selection strictly targets the exact matching row
    and never uses global checkbox selectors that might match other rows.
    """
    item = ActionPointItem(
        row_number=1,
        item_code="149000001",
        item_name="Pasta In Tomato Marinara Sauce",
        item_price="1150.00",
        category="Artisan Pasta & Risotto",
        subcategory=None,
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    search_input = AsyncMock()
    search_btn = AsyncMock()
    search_btn.inner_text = AsyncMock(return_value="Search")
    rest_elem = AsyncMock()
    rest_chk = AsyncMock()
    rest_chk.is_checked = AsyncMock(return_value=True)
    rest_elem.query_selector = AsyncMock(return_value=rest_chk)

    mock_controller.find_element = AsyncMock(side_effect=[
        (search_input, "search_input"),
        (search_btn, "search_btn"),
        (rest_elem, "rest_ird_default")
    ])

    # Two rows in table: row 0 is wrong item, row 1 is exact match
    row_wrong = AsyncMock()
    rw_c1, rw_c2 = AsyncMock(), AsyncMock()
    rw_c1.inner_text = AsyncMock(return_value="999999999")
    rw_c2.inner_text = AsyncMock(return_value="Wrong Dish")
    row_wrong.query_selector_all = AsyncMock(return_value=[rw_c1, rw_c2])
    wrong_chk = AsyncMock()
    wrong_chk.is_checked = AsyncMock(return_value=False)
    wrong_chk.click = AsyncMock()
    row_wrong.query_selector = AsyncMock(return_value=wrong_chk)

    row_correct = AsyncMock()
    rc_c1, rc_c2 = AsyncMock(), AsyncMock()
    rc_c1.inner_text = AsyncMock(return_value="149000001")
    rc_c2.inner_text = AsyncMock(return_value="Pasta In Tomato Marinara Sauce")
    row_correct.query_selector_all = AsyncMock(return_value=[rc_c1, rc_c2])
    correct_chk = AsyncMock()
    correct_chk.is_checked = AsyncMock(side_effect=[False, True, True])
    correct_chk.click = AsyncMock()
    row_correct.query_selector = AsyncMock(return_value=correct_chk)

    mock_controller.page.query_selector_all = AsyncMock(return_value=[row_wrong, row_correct])

    with patch.object(mock_controller, "_select_category", AsyncMock(return_value=(True, "OK", AsyncMock()))):
        with patch.object(mock_controller, "_wait_for_configuration_form_readiness", AsyncMock(return_value=(True, "Ready"))):
            ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=True)
            assert ok is True
            # Verified: the correct row's checkbox was clicked, NOT the wrong row's checkbox!
            correct_chk.click.assert_called_once()
            wrong_chk.click.assert_not_called()
            assert mock_controller.last_item_stages["item_checkbox_selected"] is True


# ==============================================================================
# 13. Failure to select the checkbox without proceeding (fail closed, no force click)
# ==============================================================================
@pytest.mark.asyncio
async def test_13_failure_to_select_checkbox_without_proceeding(mock_controller):
    """
    If checkbox verification fails after click, execution stops immediately:
    - Failure stage is SELECT_ITEM.
    - Does NOT force-click first cell.
    - Does NOT proceed to category selection, restaurant selection, or configure.
    """
    item = ActionPointItem(
        row_number=1,
        item_code="149000001",
        item_name="Pasta In Tomato Marinara Sauce",
        item_price="1150.00",
        category="Artisan Pasta & Risotto",
        subcategory=None,
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    search_input = AsyncMock()
    search_btn = AsyncMock()
    search_btn.inner_text = AsyncMock(return_value="Search")
    mock_controller.find_element = AsyncMock(side_effect=[
        (search_input, "search_input"),
        (search_btn, "search_btn")
    ])

    row = AsyncMock()
    c1, c2 = AsyncMock(), AsyncMock()
    c1.inner_text = AsyncMock(return_value="149000001")
    c2.inner_text = AsyncMock(return_value="Pasta In Tomato Marinara Sauce")
    row.query_selector_all = AsyncMock(return_value=[c1, c2])

    item_chk = AsyncMock()
    # Checkbox remains unchecked even after click
    item_chk.is_checked = AsyncMock(return_value=False)
    item_chk.click = AsyncMock()
    first_td = AsyncMock()
    first_td.click = AsyncMock()

    async def row_qs(sel):
        if "checkbox" in sel:
            return item_chk
        if "td:first-child" in sel:
            return first_td
        return None

    row.query_selector = AsyncMock(side_effect=row_qs)
    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])

    mock_select_cat = AsyncMock(return_value=(True, "OK", AsyncMock()))
    with patch.object(mock_controller, "_select_category", mock_select_cat):
        ok, msg, ss = await mock_controller.configure_food_item(item, dry_run=True)
        assert ok is False
        assert "SELECT_ITEM" in msg
        assert mock_controller.last_failure_stage == "SELECT_ITEM"
        assert mock_controller.last_item_stages["item_checkbox_selected"] is False
        # Category selection was NEVER attempted!
        mock_select_cat.assert_not_called()


# ==============================================================================
# 14. Hidden or duplicate checkboxes resolved safely
# ==============================================================================
@pytest.mark.asyncio
async def test_14_hidden_or_duplicate_checkboxes(mock_controller):
    """
    When item row contains styled/nested checkbox elements, it safely resolves
    the clickable checkbox target within the row without leaking to global elements.
    """
    item = ActionPointItem(
        row_number=1,
        item_code="149000001",
        item_name="Pasta In Tomato Marinara Sauce",
        item_price="1150.00",
        category="Artisan Pasta & Risotto",
        subcategory=None,
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    search_input = AsyncMock()
    search_btn = AsyncMock()
    search_btn.inner_text = AsyncMock(return_value="Search")
    rest_elem = AsyncMock()
    rest_chk = AsyncMock()
    rest_chk.is_checked = AsyncMock(return_value=True)
    rest_elem.query_selector = AsyncMock(return_value=rest_chk)

    mock_controller.find_element = AsyncMock(side_effect=[
        (search_input, "search_input"),
        (search_btn, "search_btn"),
        (rest_elem, "rest_ird_default")
    ])

    row = AsyncMock()
    c1, c2 = AsyncMock(), AsyncMock()
    c1.inner_text = AsyncMock(return_value="149000001")
    c2.inner_text = AsyncMock(return_value="Pasta In Tomato Marinara Sauce")
    row.query_selector_all = AsyncMock(return_value=[c1, c2])

    input_chk = AsyncMock()
    input_chk.is_checked = AsyncMock(side_effect=[False, True, True])
    input_chk.click = AsyncMock()

    async def row_qs(sel):
        if sel == "input[type='checkbox'], input[type='radio']":
            return None
        if "td:first-child input" in sel:
            return input_chk
        return None

    row.query_selector = AsyncMock(side_effect=row_qs)
    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])

    with patch.object(mock_controller, "_select_category", AsyncMock(return_value=(True, "OK", AsyncMock()))):
        with patch.object(mock_controller, "_wait_for_configuration_form_readiness", AsyncMock(return_value=(True, "Ready"))):
            ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=True)
            assert ok is True
            input_chk.click.assert_called_once()
            assert mock_controller.last_item_stages["item_checkbox_selected"] is True


# ==============================================================================
# 15. Parent category lookup after a save (spacer rows and trailing colon handling)
# ==============================================================================
@pytest.mark.asyncio
async def test_15_parent_category_lookup_after_save_with_spacer_rows(mock_controller):
    """
    Validates that expand_category_subcategories safely handles empty spacer rows
    and trailing punctuation, correctly discovering child subcategories under the parent.
    """
    parent_row = AsyncMock()
    parent_row.evaluate = AsyncMock(return_value="300")
    plus_icon = AsyncMock()
    plus_icon.is_visible = AsyncMock(return_value=True)
    plus_icon.click = AsyncMock()
    parent_row.query_selector = AsyncMock(return_value=plus_icon)

    parent_td = AsyncMock()
    parent_td.inner_text = AsyncMock(return_value="Pavilion Juicery- Freshly Squeezed")
    parent_row.query_selector_all = AsyncMock(return_value=[parent_td])

    spacer_row = AsyncMock()
    spacer_row.query_selector_all = AsyncMock(return_value=[])

    child_row = AsyncMock()
    child_td_name = AsyncMock()
    child_td_name.inner_text = AsyncMock(return_value="Caringly Selected Combinations")
    child_row.query_selector_all = AsyncMock(return_value=[child_td_name])
    child_row.get_attribute = AsyncMock(return_value="foodsubcategory catid300")

    mock_controller.page.query_selector_all = AsyncMock(return_value=[parent_row, spacer_row, child_row])

    subcategories = await mock_controller.expand_category_subcategories(
        parent_category="Pavilion Juicery- Freshly Squeezed",
        parent_row=parent_row
    )
    assert len(subcategories) >= 1
    assert "Caringly Selected Combinations" in subcategories


# ==============================================================================
# 16. Subcategory save succeeds but verification locator fails (no blind retries)
# ==============================================================================
@pytest.mark.asyncio
async def test_16_subcategory_save_succeeds_but_verification_locator_fails(mock_controller):
    """
    When subcategory save form submits, but post-save inspection in View Food Category
    cannot verify the subcategory under the parent, it reports a clear inspection failure
    and does NOT retry creation.
    """
    mock_controller.navigate_to_food_categories = AsyncMock(return_value=(True, "Loaded"))
    parent_row = AsyncMock()
    parent_row.evaluate = AsyncMock(return_value="300")
    mock_controller.find_category_row_in_table = AsyncMock(return_value=(parent_row, 1, 1))

    add_btn = AsyncMock()
    add_btn.is_visible = AsyncMock(return_value=True)
    add_btn.click = AsyncMock()

    async def parent_qs(sel):
        if "add" in sel.lower() or "operation" in sel.lower():
            return add_btn
        return None

    parent_row.query_selector = AsyncMock(side_effect=parent_qs)

    async def page_qs(sel):
        if "Pavilion Juicery" in sel:
            return parent_row
        return None

    mock_controller.page.query_selector = AsyncMock(side_effect=page_qs)
    mock_controller.page.query_selector_all = AsyncMock(return_value=[parent_row])
    mock_controller.page.wait_for_load_state = AsyncMock()
    mock_controller.page.inner_text = AsyncMock(return_value="Sub Category added successfully")

    name_input = AsyncMock()
    name_input.fill = AsyncMock()
    save_btn = AsyncMock()
    save_btn.click = AsyncMock()

    async def fe_mock(selectors, timeout_ms=5000):
        for s in selectors:
            if "name" in s.lower() or "input" in s.lower():
                return name_input, s
            if "save" in s.lower() or "submit" in s.lower():
                return save_btn, s
        return None, ""

    mock_controller.find_element = AsyncMock(side_effect=fe_mock)
    mock_controller.expand_category_subcategories = AsyncMock(return_value=[])

    ok, msg = await mock_controller.create_subcategory(
        parent_category="Pavilion Juicery- Freshly Squeezed",
        subcategory_name="Caringly Selected Combinations:"
    )

    assert ok is False
    assert "could not be verified" in msg or "VERIFICATION FAILED" in msg
    assert save_btn.click.call_count == 1


# ==============================================================================
# 17. Uncertain save outcome without duplicate retries
# ==============================================================================
@pytest.mark.asyncio
async def test_17_uncertain_save_outcome_without_duplicate_retries():
    """
    When item configuration encounters an uncertain timeout or portal error,
    the workflow isolates the row as FAILED/BLOCKED and does not trigger duplicate retries.
    """
    runner = ActionPointWorkflowRunner()
    sites = get_all_sites()
    site_id = sites[0].id if sites else add_site(Site(name="Uncertain Outcome Site", launcher_button="UOS", enabled=True, local_port=18003))

    items = [
        ActionPointItem(
            row_number=2,
            item_code="149000001",
            item_name="Pasta Marinara",
            item_price="1150.00",
            category="Artisan Pasta & Risotto",
            subcategory="Penne I Spaghetti",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        )
    ]

    mock_ctrl = AsyncMock()
    mock_ctrl.initialize = AsyncMock()
    mock_ctrl.navigate_and_authenticate = AsyncMock(return_value=(True, "Success"))
    mock_ctrl.inspect_existing_categories = AsyncMock(return_value=(["Artisan Pasta & Risotto"], {"Artisan Pasta & Risotto": ["Penne I Spaghetti"]}))
    mock_ctrl.navigate_to_item_configuration = AsyncMock(return_value=(True, "Loaded"))
    mock_ctrl.page.is_closed = MagicMock(return_value=False)

    mock_ctrl.configure_food_item = AsyncMock(side_effect=PlaywrightTimeoutError("Save timed out"))

    with patch("app.action_point_automation.workflow_runner.tunnel_manager.start_and_verify_tunnel", AsyncMock(return_value=(True, "OK", []))):
        with patch("app.action_point_automation.workflow_runner.ActionPointPortalController", return_value=mock_ctrl):
            result = await runner.execute_run(
                site_id=site_id,
                filename="uncertain_test.csv",
                items=items,
                mode=ExecutionMode.LIVE
            )

    mock_ctrl.create_category.assert_not_called()
    mock_ctrl.create_subcategory.assert_not_called()
    assert result["summary"]["failed_rows"] == 1
    assert result["summary"]["successful_rows"] == 0


# ==============================================================================
# 18. Category-only rows (subcategory skipped) full pipeline
# ==============================================================================
@pytest.mark.asyncio
async def test_18_category_only_rows_full_pipeline(mock_controller):
    """
    Validates category-only row:
    - Step 5 selects category checkbox.
    - Step 6 records subcategory_skipped = True without expanding.
    - Step 7 selects restaurant.
    - Step 8 submits Configure.
    - Step 9 verifies persisted state.
    """
    item = ActionPointItem(
        row_number=1,
        item_code="149000001",
        item_name="Pasta In Tomato Marinara Sauce",
        item_price="1150.00",
        category="Artisan Pasta & Risotto",
        subcategory=None,
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    search_input = AsyncMock()
    search_btn = AsyncMock()
    search_btn.inner_text = AsyncMock(return_value="Search")
    rest_elem = AsyncMock()
    rest_chk = AsyncMock()
    rest_chk.is_checked = AsyncMock(return_value=True)
    rest_elem.query_selector = AsyncMock(return_value=rest_chk)
    conf_btn = AsyncMock()

    mock_controller.find_element = AsyncMock(side_effect=[
        (search_input, "search_input"),
        (search_btn, "search_btn"),
        (rest_elem, "rest_ird_default"),
        (conf_btn, "conf_btn")
    ])

    row = AsyncMock()
    c1, c2 = AsyncMock(), AsyncMock()
    c1.inner_text = AsyncMock(return_value="149000001")
    c2.inner_text = AsyncMock(return_value="Pasta In Tomato Marinara Sauce")
    row.query_selector_all = AsyncMock(return_value=[c1, c2])
    item_chk = AsyncMock()
    item_chk.is_checked = AsyncMock(side_effect=[False, True, True])
    row.query_selector = AsyncMock(return_value=item_chk)
    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.page.inner_text = AsyncMock(return_value="Configuration saved successfully")

    with patch.object(mock_controller, "_select_category", AsyncMock(return_value=(True, "OK", AsyncMock()))) as mock_sel_cat:
        with patch.object(mock_controller, "_expand_and_select_subcategory", AsyncMock()) as mock_sub:
            with patch.object(mock_controller, "_wait_for_configuration_form_readiness", AsyncMock(return_value=(True, "Ready"))):
                ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=False)
                assert ok is True
                mock_sel_cat.assert_called_once()
                mock_sub.assert_not_called()
                assert mock_controller.last_item_stages["item_found"] is True
                assert mock_controller.last_item_stages["item_checkbox_selected"] is True
                assert mock_controller.last_item_stages["category_selected"] is True
                assert mock_controller.last_item_stages["subcategory_skipped"] is True
                assert mock_controller.last_item_stages["subcategory_selected"] is False
                assert mock_controller.last_item_stages["restaurant_selected"] is True
                assert mock_controller.last_item_stages["configure_submitted"] is True
                assert mock_controller.last_item_stages["persisted_verified"] is True


# ==============================================================================
# 19. Category-plus-subcategory rows full pipeline
# ==============================================================================
@pytest.mark.asyncio
async def test_19_category_plus_subcategory_rows_full_pipeline(mock_controller):
    """
    Validates category + subcategory row:
    - Step 5 selects category.
    - Step 6 expands parent using green '+' and selects child checkbox.
    - Step 7 selects restaurant.
    - Step 8 submits Configure.
    - Step 9 verifies persisted state.
    """
    item = ActionPointItem(
        row_number=1,
        item_code="149000001",
        item_name="Pasta In Tomato Marinara Sauce",
        item_price="1150.00",
        category="Artisan Pasta & Risotto",
        subcategory="Penne I Spaghetti",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    search_input = AsyncMock()
    search_btn = AsyncMock()
    search_btn.inner_text = AsyncMock(return_value="Search")
    rest_elem = AsyncMock()
    rest_chk = AsyncMock()
    rest_chk.is_checked = AsyncMock(return_value=True)
    rest_elem.query_selector = AsyncMock(return_value=rest_chk)
    conf_btn = AsyncMock()

    mock_controller.find_element = AsyncMock(side_effect=[
        (search_input, "search_input"),
        (search_btn, "search_btn"),
        (rest_elem, "rest_ird_default"),
        (conf_btn, "conf_btn")
    ])

    row = AsyncMock()
    c1, c2 = AsyncMock(), AsyncMock()
    c1.inner_text = AsyncMock(return_value="149000001")
    c2.inner_text = AsyncMock(return_value="Pasta In Tomato Marinara Sauce")
    row.query_selector_all = AsyncMock(return_value=[c1, c2])
    item_chk = AsyncMock()
    item_chk.is_checked = AsyncMock(side_effect=[False, True, True])
    row.query_selector = AsyncMock(return_value=item_chk)
    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.page.inner_text = AsyncMock(return_value="Configuration saved successfully")

    with patch.object(mock_controller, "_select_category", AsyncMock(return_value=(True, "OK", AsyncMock()))) as mock_sel_cat:
        with patch.object(mock_controller, "_expand_and_select_subcategory", AsyncMock(return_value=(True, "Sub OK"))) as mock_sub:
            with patch.object(mock_controller, "_wait_for_configuration_form_readiness", AsyncMock(return_value=(True, "Ready"))):
                ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=False)
                assert ok is True
                mock_sel_cat.assert_called_once()
                mock_sub.assert_called_once()
                assert mock_controller.last_item_stages["item_found"] is True
                assert mock_controller.last_item_stages["item_checkbox_selected"] is True
                assert mock_controller.last_item_stages["category_selected"] is True
                assert mock_controller.last_item_stages["subcategory_selected"] is True
                assert mock_controller.last_item_stages["subcategory_skipped"] is False
                assert mock_controller.last_item_stages["restaurant_selected"] is True
                assert mock_controller.last_item_stages["configure_submitted"] is True
                assert mock_controller.last_item_stages["persisted_verified"] is True


# ==============================================================================
# 20. Successful independent verification after Configure
# ==============================================================================
@pytest.mark.asyncio
async def test_20_successful_independent_verification_after_configure(mock_controller):
    """
    Validates independent verification after Configure:
    - Verifies absence of errors.
    - Confirms success notification / persisted state.
    - Confirms item added to processed_items.
    """
    item = ActionPointItem(
        row_number=1,
        item_code="149000001",
        item_name="Pasta In Tomato Marinara Sauce",
        item_price="1150.00",
        category="Artisan Pasta & Risotto",
        subcategory=None,
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    search_input = AsyncMock()
    search_btn = AsyncMock()
    search_btn.inner_text = AsyncMock(return_value="Search")
    rest_elem = AsyncMock()
    rest_chk = AsyncMock()
    rest_chk.is_checked = AsyncMock(return_value=True)
    rest_elem.query_selector = AsyncMock(return_value=rest_chk)
    conf_btn = AsyncMock()
    conf_btn.click = AsyncMock()

    mock_controller.find_element = AsyncMock(side_effect=[
        (search_input, "search_input"),
        (search_btn, "search_btn"),
        (rest_elem, "rest_ird_default"),
        (conf_btn, "conf_btn")
    ])

    row = AsyncMock()
    c1, c2 = AsyncMock(), AsyncMock()
    c1.inner_text = AsyncMock(return_value="149000001")
    c2.inner_text = AsyncMock(return_value="Pasta In Tomato Marinara Sauce")
    row.query_selector_all = AsyncMock(return_value=[c1, c2])
    item_chk = AsyncMock()
    item_chk.is_checked = AsyncMock(side_effect=[False, True, True])
    row.query_selector = AsyncMock(return_value=item_chk)
    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.page.inner_text = AsyncMock(return_value="Item configured successfully")

    with patch.object(mock_controller, "_select_category", AsyncMock(return_value=(True, "OK", AsyncMock()))):
        with patch.object(mock_controller, "_wait_for_configuration_form_readiness", AsyncMock(return_value=(True, "Ready"))):
            ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=False)
            assert ok is True
            assert "SUCCESS: Item configuration saved and verified" in msg
            assert "149000001" in mock_controller.processed_items
            assert mock_controller.last_item_stages["persisted_verified"] is True

