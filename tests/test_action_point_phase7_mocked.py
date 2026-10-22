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
    RunState
)
from app.action_point_automation.validator import (
    match_category,
    match_subcategory,
    normalize_category_name
)
from app.database.db import init_db, add_site, get_all_sites
from app.database.models import Site


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()


@pytest.fixture
def mock_controller():
    ctrl = ActionPointPortalController(run_id=888, site_name="Phase7Site")
    ctrl.browser = AsyncMock()
    ctrl.browser.close = AsyncMock()
    ctrl.page = AsyncMock()
    ctrl.page.is_closed = MagicMock(return_value=False)
    ctrl.page.close = AsyncMock()
    ctrl.page.url = "http://127.0.0.1:18001/zmp/main-menu.do"
    ctrl.page.title = AsyncMock(return_value="Zenith Media Portal")
    ctrl.page.screenshot = AsyncMock()
    ctrl.page.go_back = AsyncMock()
    ctrl.page.content = AsyncMock(return_value="<html><body>Portal Content</body></html>")
    ctrl.page.inner_text = AsyncMock(return_value="")
    return ctrl


# ==============================================================================
# PHASE 7: CATEGORY DETECTION (1 - 10)
# ==============================================================================

def test_01_existing_category_identical_spelling():
    categories = ["Starters", "Beverages", "Desserts"]
    assert match_category("Beverages", categories) == "Beverages"
    assert match_category("Starters", categories) == "Starters"


def test_02_existing_category_different_capitalization():
    categories = ["BEVERAGES", "starters", "Main Course"]
    assert match_category("Beverages", categories) == "BEVERAGES"
    assert match_category("Starters", categories) == "starters"


def test_03_existing_category_surrounding_whitespace_and_html_entities():
    categories = ["  Beverages  \n", "Starters &amp; Snacks\u00a0"]
    assert match_category("Beverages", categories) == "  Beverages  \n"
    assert match_category("Starters & Snacks", categories) == "Starters &amp; Snacks\u00a0"


@pytest.mark.asyncio
async def test_04_existing_category_on_another_page(mock_controller):
    # Page 1 has Starters, Page 2 has Beverages
    row1 = AsyncMock()
    td1 = AsyncMock()
    td1.inner_text = AsyncMock(return_value="Starters")
    row1.query_selector_all = AsyncMock(return_value=[td1])

    row2 = AsyncMock()
    td2 = AsyncMock()
    td2.inner_text = AsyncMock(return_value="Beverages")
    row2.query_selector_all = AsyncMock(return_value=[td2])

    page_calls = {"count": 0}

    async def mock_query_all(sel):
        if "table tbody tr" in sel:
            page_calls["count"] += 1
            if page_calls["count"] == 1:
                return [row1]
            return [row2]
        return []

    mock_controller.page.query_selector_all = AsyncMock(side_effect=mock_query_all)

    # Next page button returns enabled on first call, disabled on second
    next_btn = AsyncMock()
    next_btn.is_visible = AsyncMock(return_value=True)
    next_btn.is_enabled = AsyncMock(return_value=True)
    next_btn.get_attribute = AsyncMock(side_effect=lambda a: "" if page_calls["count"] == 1 else "disabled")

    async def mock_find(sels, **kwargs):
        if any("pagination" in s or "next" in s for s in sels):
            if page_calls["count"] == 1:
                return next_btn, sels[0]
            return None, ""
        return AsyncMock(), sels[0]

    mock_controller.find_element = AsyncMock(side_effect=mock_find)

    cats, _ = await mock_controller.inspect_existing_categories()
    assert "Starters" in cats
    assert "Beverages" in cats


def test_05_similar_but_distinct_category_names():
    categories = ["Beverages Premium", "Beverages Special"]
    # Exact normalized equality must reject Beverages
    assert match_category("Beverages", categories) is None


@pytest.mark.asyncio
async def test_06_category_under_different_restaurant(mock_controller):
    row = AsyncMock()
    td_name = AsyncMock()
    td_name.inner_text = AsyncMock(return_value="Banquet Menu")
    td_img = AsyncMock()
    td_img.inner_text = AsyncMock(return_value="")
    td_rest = AsyncMock()
    td_rest.inner_text = AsyncMock(return_value="Banquet Hall")
    row.query_selector_all = AsyncMock(return_value=[td_name, td_img, td_rest])

    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "elem"))

    cats, _ = await mock_controller.inspect_existing_categories()
    assert "Banquet Menu" in cats
    details = mock_controller.category_dom_details.get(normalize_category_name("Banquet Menu"))
    assert details is not None
    assert details["restaurant"] == "Banquet Hall"


@pytest.mark.asyncio
async def test_07_inactive_category_behavior(mock_controller):
    # Col 0: Name, Col 1: Img, Col 2: Rest, Col 3: Seq, Col 4: Active ("false")
    row = AsyncMock()
    td0 = AsyncMock()
    td0.inner_text = AsyncMock(return_value="Old Inactive Category")
    td1 = AsyncMock()
    td1.inner_text = AsyncMock(return_value="")
    td2 = AsyncMock()
    td2.inner_text = AsyncMock(return_value="")
    td3 = AsyncMock()
    td3.inner_text = AsyncMock(return_value="")
    td4 = AsyncMock()
    td4.inner_text = AsyncMock(return_value="false")
    row.query_selector_all = AsyncMock(return_value=[td0, td1, td2, td3, td4])

    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "elem"))

    cats, _ = await mock_controller.inspect_existing_categories()
    assert "Old Inactive Category" not in cats
    assert normalize_category_name("Old Inactive Category") not in mock_controller.verified_categories


@pytest.mark.asyncio
async def test_08_category_table_still_loading(mock_controller):
    # Table element not found / loading
    mock_controller.find_element = AsyncMock(return_value=(None, ""))
    mock_controller.page.query_selector = AsyncMock(return_value=None)

    cats, tree = await mock_controller.inspect_existing_categories()
    assert mock_controller.last_category_inspection_error is not None
    assert "BLOCKED — CATEGORY VERIFICATION INCOMPLETE" in mock_controller.last_category_inspection_error


@pytest.mark.asyncio
async def test_09_category_inspection_timeout(mock_controller):
    mock_controller.find_element = AsyncMock(side_effect=PlaywrightTimeoutError("Timeout waiting for table"))

    cats, tree = await mock_controller.inspect_existing_categories()
    assert mock_controller.last_category_inspection_error is not None
    assert "BLOCKED — CATEGORY VERIFICATION INCOMPLETE" in mock_controller.last_category_inspection_error


@pytest.mark.asyncio
async def test_10_no_duplicate_creation_when_category_is_cached(mock_controller):
    mock_controller.verified_categories.add(normalize_category_name("Starters"))

    # Attempt creation of Starters
    save_btn = AsyncMock()
    mock_controller.find_element = AsyncMock(return_value=(save_btn, "save_btn"))

    ok, msg = await mock_controller.create_category("Starters")
    assert ok is True
    assert "already exists" in msg
    save_btn.click.assert_not_called()


# ==============================================================================
# PHASE 7: SUBCATEGORY DETECTION (11 - 18)
# ==============================================================================

def test_11_existing_subcategory_under_correct_parent():
    tree = {"Starters": ["Veg Starters", "Non-Veg Starters"]}
    assert match_subcategory("Veg Starters", "Starters", tree) == "Veg Starters"


def test_12_same_subcategory_name_under_different_parent():
    tree = {
        "Desserts": ["Cold"],
        "Beverages": ["Hot"]
    }
    # Cold exists under Desserts, not Beverages
    assert match_subcategory("Cold", "Beverages", tree) is None
    assert match_subcategory("Cold", "Desserts", tree) == "Cold"


@pytest.mark.asyncio
async def test_13_existing_subcategory_visible_only_after_expansion(mock_controller):
    parent_row = AsyncMock()
    td_p = AsyncMock()
    td_p.inner_text = AsyncMock(return_value="Starters")
    expand_icon = AsyncMock()
    expand_icon.is_visible = AsyncMock(return_value=True)
    expand_icon.click = AsyncMock()
    expand_icon.evaluate = AsyncMock(return_value=False)
    expand_icon.query_selector = AsyncMock(return_value=None)

    td_p.query_selector = AsyncMock(return_value=expand_icon)
    parent_row.query_selector_all = AsyncMock(return_value=[td_p])
    parent_row.query_selector = AsyncMock(side_effect=lambda sel: td_p if "td" in sel else expand_icon)

    # After expansion, sibling row appears
    child_row = AsyncMock()
    child_row.get_attribute = AsyncMock(return_value="sub-category-row")
    child_row.query_selector = AsyncMock(return_value=None)
    td_c = AsyncMock()
    td_c.inner_text = AsyncMock(return_value="Paneer Tikka")
    child_row.query_selector_all = AsyncMock(return_value=[td_c])

    mock_controller.page.query_selector_all = AsyncMock(return_value=[parent_row, child_row])
    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "elem"))

    subs = await mock_controller.expand_category_subcategories("Starters")
    assert "Paneer Tikka" in subs
    expand_icon.click.assert_called_once()


@pytest.mark.asyncio
async def test_14_expansion_timeout(mock_controller):
    # Parent row not found
    mock_controller.page.query_selector_all = AsyncMock(return_value=[])
    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "elem"))

    subs = await mock_controller.expand_category_subcategories("NonExistentParent")
    assert subs == []


@pytest.mark.asyncio
async def test_15_missing_subcategory_created_exactly_once(mock_controller):
    parent_row = AsyncMock()
    td_p = AsyncMock()
    td_p.inner_text = AsyncMock(return_value="Beverages")
    td_op = AsyncMock()
    file_plus_icon = AsyncMock()
    td_op.query_selector = AsyncMock(return_value=file_plus_icon)
    parent_row.query_selector_all = AsyncMock(return_value=[td_p, td_op])
    parent_row.query_selector = AsyncMock(return_value=file_plus_icon)

    mock_controller.page.query_selector_all = AsyncMock(return_value=[parent_row])

    sub_input = AsyncMock()
    save_btn = AsyncMock()
    mock_controller.find_element = AsyncMock(side_effect=[
        (sub_input, "sub_input"),
        (AsyncMock(), "img_input"),
        (save_btn, "save_btn")
    ])

    with patch.object(mock_controller, "inspect_existing_categories", AsyncMock(return_value=(["Beverages"], {"Beverages": []}))):
        with patch.object(mock_controller, "expand_category_subcategories", AsyncMock(return_value=["Smoothies"])):
            ok, msg = await mock_controller.create_subcategory("Beverages", "Smoothies")
            assert ok is True
            assert "created and verified" in msg
            save_btn.click.assert_called_once()
            # Verified cached
            assert normalize_category_name("Smoothies") in mock_controller.category_tree[normalize_category_name("Beverages")]


@pytest.mark.asyncio
async def test_16_correct_use_of_file_plus_creation_icon(mock_controller):
    parent_row = AsyncMock()
    td_p = AsyncMock()
    td_p.inner_text = AsyncMock(return_value="Beverages")
    green_plus_icon = AsyncMock()
    td_p.query_selector = AsyncMock(return_value=green_plus_icon)

    td_op = AsyncMock()
    file_plus_icon = AsyncMock()
    td_op.query_selector = AsyncMock(return_value=file_plus_icon)

    parent_row.query_selector_all = AsyncMock(return_value=[td_p, td_op])
    parent_row.query_selector = AsyncMock(return_value=file_plus_icon)

    mock_controller.page.query_selector_all = AsyncMock(return_value=[parent_row])
    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "elem"))

    with patch.object(mock_controller, "inspect_existing_categories", AsyncMock(return_value=(["Beverages"], {}))):
        with patch.object(mock_controller, "expand_category_subcategories", AsyncMock(return_value=["Cold Drinks"])):
            ok, _ = await mock_controller.create_subcategory("Beverages", "Cold Drinks")
            assert ok is True
            # The file-plus icon must have been clicked, NOT the green circular expansion icon
            file_plus_icon.click.assert_called_once()
            green_plus_icon.click.assert_not_called()


@pytest.mark.asyncio
async def test_17_subcategory_creation_verification_failure(mock_controller):
    parent_row = AsyncMock()
    td_p = AsyncMock()
    td_p.inner_text = AsyncMock(return_value="Starters")
    td_op = AsyncMock()
    file_plus = AsyncMock()
    td_op.query_selector = AsyncMock(return_value=file_plus)
    parent_row.query_selector_all = AsyncMock(return_value=[td_p, td_op])
    parent_row.query_selector = AsyncMock(return_value=file_plus)

    mock_controller.page.query_selector_all = AsyncMock(return_value=[parent_row])
    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "elem"))
    mock_controller.page.content = AsyncMock(return_value="<html><body>No match here</body></html>")

    # Post-creation inspection returns empty subcategories
    with patch.object(mock_controller, "inspect_existing_categories", AsyncMock(return_value=(["Starters"], {}))):
        with patch.object(mock_controller, "expand_category_subcategories", AsyncMock(return_value=[])):
            ok, msg = await mock_controller.create_subcategory("Starters", "GhostSub")
            assert ok is False
            assert "could not be verified" in msg


@pytest.mark.asyncio
async def test_18_no_duplicate_creation_when_verified_pair_cached(mock_controller):
    norm_p = normalize_category_name("Desserts")
    norm_s = normalize_category_name("Ice Cream")
    mock_controller.category_tree[norm_p] = {norm_s}

    save_btn = AsyncMock()
    mock_controller.find_element = AsyncMock(return_value=(save_btn, "save_btn"))

    ok, msg = await mock_controller.create_subcategory("Desserts", "Ice Cream")
    assert ok is True
    assert "already exists" in msg
    save_btn.click.assert_not_called()


# ==============================================================================
# PHASE 7: ITEM CONFIGURATION (19 - 30)
# ==============================================================================

@pytest.mark.asyncio
async def test_19_successful_item_configuration(mock_controller):
    item = ActionPointItem(
        row_number=2,
        item_code="0042",
        item_name="Chicken Tikka",
        item_price="450",
        category="Starters",
        subcategory="Non-Veg Starters",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
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
    td_code.inner_text = AsyncMock(return_value="0042")
    row.query_selector_all = AsyncMock(return_value=[td_code])
    chk = AsyncMock()
    chk.is_checked = AsyncMock(return_value=True)
    row.query_selector = AsyncMock(return_value=chk)

    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.page.query_selector = AsyncMock(return_value=chk)

    ok, msg, ss = await mock_controller.configure_food_item(item, dry_run=False)
    assert ok is True
    assert "SUCCESS" in msg
    conf_btn.click.assert_called_once()
    assert "0042" in mock_controller.processed_items


@pytest.mark.asyncio
async def test_20_item_code_with_leading_zeros(mock_controller):
    item = ActionPointItem(
        row_number=2,
        item_code="0007",
        item_name="Espresso",
        item_price="120",
        category="Beverages",
        subcategory="Hot",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    search_input = AsyncMock()
    mock_controller.find_element = AsyncMock(side_effect=[
        (search_input, "search_input"),
        (AsyncMock(), "search_btn"),
        (AsyncMock(), "cat_panel"),
        (AsyncMock(), "rest_default")
    ])

    # Row with exact leading zero code
    row = AsyncMock()
    td_code = AsyncMock()
    td_code.inner_text = AsyncMock(return_value="0007")
    row.query_selector_all = AsyncMock(return_value=[td_code])
    row.query_selector = AsyncMock(return_value=AsyncMock())

    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.page.query_selector = AsyncMock(return_value=AsyncMock())

    ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=True)
    assert ok is True
    search_input.fill.assert_any_call("0007")


@pytest.mark.asyncio
async def test_21_item_not_found(mock_controller):
    item = ActionPointItem(
        row_number=5,
        item_code="9999",
        item_name="Missing Item",
        item_price="100",
        category="Starters",
        subcategory="Veg Starters",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "search_input"))
    mock_controller.page.query_selector_all = AsyncMock(return_value=[])

    ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=False)
    assert ok is False
    assert "FAILED — ITEM NOT FOUND" in msg
    assert mock_controller.last_failure_stage == "VERIFY_ITEM_IDENTITY"


@pytest.mark.asyncio
async def test_22_ambiguous_item_result(mock_controller):
    item = ActionPointItem(
        row_number=6,
        item_code="1001",
        item_name="Duplicate Item",
        item_price="200",
        category="Starters",
        subcategory="Veg",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "search_input"))

    r1 = AsyncMock()
    td1 = AsyncMock()
    td1.inner_text = AsyncMock(return_value="1001")
    r1.query_selector_all = AsyncMock(return_value=[td1])

    r2 = AsyncMock()
    td2 = AsyncMock()
    td2.inner_text = AsyncMock(return_value="1001")
    r2.query_selector_all = AsyncMock(return_value=[td2])

    mock_controller.page.query_selector_all = AsyncMock(return_value=[r1, r2])

    ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=False)
    assert ok is False
    assert "BLOCKED — AMBIGUOUS ITEM MATCH" in msg
    assert mock_controller.last_failure_stage == "VERIFY_ITEM_IDENTITY"


@pytest.mark.asyncio
async def test_23_category_selection_failure(mock_controller):
    item = ActionPointItem(
        row_number=7,
        item_code="1002",
        item_name="Paneer Butter",
        item_price="350",
        category="NonExistentCategory",
        subcategory="Gravy",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    mock_controller.find_element = AsyncMock(side_effect=[
        (AsyncMock(), "search_input"),
        (AsyncMock(), "search_btn"),
        (AsyncMock(), "cat_panel")
    ])

    row = AsyncMock()
    td = AsyncMock()
    td.inner_text = AsyncMock(return_value="1002")
    row.query_selector_all = AsyncMock(return_value=[td])
    row.query_selector = AsyncMock(return_value=AsyncMock())
    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])

    # Category element returns None
    mock_controller.page.query_selector = AsyncMock(return_value=None)

    ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=False)
    assert ok is False
    assert "BLOCKED — Category" in msg
    assert mock_controller.last_failure_stage == "EXPAND_CATEGORY"


@pytest.mark.asyncio
async def test_24_subcategory_selection_failure(mock_controller):
    item = ActionPointItem(
        row_number=8,
        item_code="1003",
        item_name="Dal Makhani",
        item_price="300",
        category="Main Course",
        subcategory="GhostSub",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    mock_controller.find_element = AsyncMock(side_effect=[
        (AsyncMock(), "search_input"),
        (AsyncMock(), "search_btn"),
        (AsyncMock(), "cat_panel")
    ])

    row = AsyncMock()
    td = AsyncMock()
    td.inner_text = AsyncMock(return_value="1003")
    row.query_selector_all = AsyncMock(return_value=[td])
    row.query_selector = AsyncMock(return_value=AsyncMock())
    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])

    # Category element found, but subcategory element returns None
    cat_elem = AsyncMock()
    cat_elem.query_selector = AsyncMock(return_value=None)

    async def mock_qs(sel):
        if "Main Course" in sel:
            return cat_elem
        return None

    mock_controller.page.query_selector = AsyncMock(side_effect=mock_qs)

    ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=False)
    assert ok is False
    assert "BLOCKED — Subcategory" in msg
    assert mock_controller.last_failure_stage == "SELECT_SUBCATEGORY"


@pytest.mark.asyncio
async def test_25_missing_ird_default_restaurant(mock_controller):
    item = ActionPointItem(
        row_number=9,
        item_code="1004",
        item_name="Roti",
        item_price="50",
        category="Breads",
        subcategory="Indian",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    # Restaurant IRD - DEFAULT returns None
    mock_controller.find_element = AsyncMock(side_effect=[
        (AsyncMock(), "search_input"),
        (AsyncMock(), "search_btn"),
        (AsyncMock(), "cat_panel"),
        (None, "")  # Restaurant missing
    ])

    row = AsyncMock()
    td = AsyncMock()
    td.inner_text = AsyncMock(return_value="1004")
    row.query_selector_all = AsyncMock(return_value=[td])
    row.query_selector = AsyncMock(return_value=AsyncMock())
    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.page.query_selector = AsyncMock(return_value=AsyncMock())

    ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=False)
    assert ok is False
    assert "FAILED — RESTAURANT 'IRD - DEFAULT'" in msg
    assert mock_controller.last_failure_stage == "SELECT_RESTAURANT"


@pytest.mark.asyncio
async def test_26_save_timeout(mock_controller):
    item = ActionPointItem(
        row_number=10,
        item_code="1005",
        item_name="Naan",
        item_price="70",
        category="Breads",
        subcategory="Tandoor",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    conf_btn = AsyncMock()
    conf_btn.click = AsyncMock(side_effect=PlaywrightTimeoutError("Timeout clicking Configure"))

    mock_controller.find_element = AsyncMock(side_effect=[
        (AsyncMock(), "search_input"),
        (AsyncMock(), "search_btn"),
        (AsyncMock(), "cat_panel"),
        (AsyncMock(), "rest_panel"),
        (conf_btn, "conf_btn")
    ])

    row = AsyncMock()
    td = AsyncMock()
    td.inner_text = AsyncMock(return_value="1005")
    row.query_selector_all = AsyncMock(return_value=[td])
    row.query_selector = AsyncMock(return_value=AsyncMock())
    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.page.query_selector = AsyncMock(return_value=AsyncMock())

    with pytest.raises(PlaywrightTimeoutError):
        await mock_controller.configure_food_item(item, dry_run=False)


@pytest.mark.asyncio
async def test_27_save_committed_response_error(mock_controller):
    item = ActionPointItem(
        row_number=11,
        item_code="1006",
        item_name="Paratha",
        item_price="80",
        category="Breads",
        subcategory="Tandoor",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    conf_btn = AsyncMock()
    mock_controller.find_element = AsyncMock(side_effect=[
        (AsyncMock(), "search_input"),
        (AsyncMock(), "search_btn"),
        (AsyncMock(), "cat_panel"),
        (AsyncMock(), "rest_panel"),
        (conf_btn, "conf_btn")
    ])

    row = AsyncMock()
    td = AsyncMock()
    td.inner_text = AsyncMock(return_value="1006")
    row.query_selector_all = AsyncMock(return_value=[td])
    row.query_selector = AsyncMock(return_value=AsyncMock())
    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.page.query_selector = AsyncMock(return_value=AsyncMock())

    # Portal body returns error
    mock_controller.page.inner_text = AsyncMock(return_value="Internal Server Error: DB write rejected")

    ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=False)
    assert ok is False
    assert "Portal reported error" in msg


@pytest.mark.asyncio
async def test_28_post_save_verification_failure(mock_controller):
    item = ActionPointItem(
        row_number=12,
        item_code="1007",
        item_name="Pulao",
        item_price="250",
        category="Rice",
        subcategory="Veg Rice",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    conf_btn = AsyncMock()
    mock_controller.find_element = AsyncMock(side_effect=[
        (AsyncMock(), "search_input"),
        (AsyncMock(), "search_btn"),
        (AsyncMock(), "cat_panel"),
        (AsyncMock(), "rest_panel"),
        (conf_btn, "conf_btn")
    ])

    row = AsyncMock()
    td = AsyncMock()
    td.inner_text = AsyncMock(return_value="1007")
    row.query_selector_all = AsyncMock(return_value=[td])
    row.query_selector = AsyncMock(return_value=AsyncMock())
    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.page.query_selector = AsyncMock(return_value=AsyncMock())

    mock_controller.page.inner_text = AsyncMock(return_value="Validation error: Item code mismatch")

    ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=False)
    assert ok is False
    assert mock_controller.last_failure_stage == "VERIFY_SAVED_CONFIGURATION"


@pytest.mark.asyncio
async def test_29_one_item_fails_while_later_independent_rows_continue():
    runner = ActionPointWorkflowRunner()
    sites = get_all_sites()
    site_id = sites[0].id if sites else add_site(Site(name="Isolation Hotel", launcher_button="ISO", enabled=True, local_port=18001))

    items = [
        ActionPointItem(
            row_number=2,
            item_code="9999",  # Will fail (not found)
            item_name="Ghost Item",
            item_price="100",
            category="Starters",
            subcategory="Veg",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        ),
        ActionPointItem(
            row_number=3,
            item_code="0042",  # Will succeed
            item_name="Chicken Tikka",
            item_price="450",
            category="Starters",
            subcategory="Veg",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        )
    ]

    mock_ctrl = AsyncMock()
    mock_ctrl.initialize = AsyncMock()
    mock_ctrl.navigate_and_authenticate = AsyncMock(return_value=(True, "Success"))
    mock_ctrl.inspect_existing_categories = AsyncMock(return_value=(["Starters"], {"Starters": ["Veg"]}))
    mock_ctrl.navigate_to_item_configuration = AsyncMock(return_value=(True, "Loaded"))
    mock_ctrl.page = AsyncMock()
    mock_ctrl.page.is_closed = MagicMock(return_value=False)

    # First row fails, second succeeds
    mock_ctrl.configure_food_item = AsyncMock(side_effect=[
        (False, "FAILED — ITEM NOT FOUND: Item Code '9999' not found.", "ss1.png"),
        (True, "SUCCESS: Item configuration saved.", "ss2.png")
    ])

    with patch("app.action_point_automation.workflow_runner.tunnel_manager.start_and_verify_tunnel", AsyncMock(return_value=(True, "OK", []))):
        with patch("app.action_point_automation.workflow_runner.ActionPointPortalController", return_value=mock_ctrl):
            result = await runner.execute_run(
                site_id=site_id,
                filename="isolation_test.csv",
                items=items,
                mode=ExecutionMode.LIVE
            )

    assert result["success"] is True
    assert result["summary"]["failed_rows"] == 1
    assert result["summary"]["successful_rows"] == 1
    # Both items were processed!
    assert mock_ctrl.configure_food_item.call_count == 2


@pytest.mark.asyncio
async def test_30_session_loss_aborts_safely():
    runner = ActionPointWorkflowRunner()
    sites = get_all_sites()
    site_id = sites[0].id if sites else add_site(Site(name="Session Loss Hotel", launcher_button="SL", enabled=True, local_port=18001))

    items = [
        ActionPointItem(
            row_number=2,
            item_code="0001",
            item_name="Item 1",
            item_price="100",
            category="Starters",
            subcategory="Veg",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        ),
        ActionPointItem(
            row_number=3,
            item_code="0002",
            item_name="Item 2",
            item_price="200",
            category="Starters",
            subcategory="Veg",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        )
    ]

    mock_ctrl = AsyncMock()
    mock_ctrl.initialize = AsyncMock()
    mock_ctrl.navigate_and_authenticate = AsyncMock(return_value=(True, "Success"))
    mock_ctrl.inspect_existing_categories = AsyncMock(return_value=(["Starters"], {"Starters": ["Veg"]}))
    mock_ctrl.navigate_to_item_configuration = AsyncMock(return_value=(True, "Loaded"))

    # Browser closes after first failure
    mock_page = AsyncMock()
    mock_page.is_closed = MagicMock(return_value=True)
    mock_ctrl.page = mock_page

    mock_ctrl.configure_food_item = AsyncMock(return_value=(False, "Crash", None))

    with patch("app.action_point_automation.workflow_runner.tunnel_manager.start_and_verify_tunnel", AsyncMock(return_value=(True, "OK", []))):
        with patch("app.action_point_automation.workflow_runner.ActionPointPortalController", return_value=mock_ctrl):
            result = await runner.execute_run(
                site_id=site_id,
                filename="session_loss.csv",
                items=items,
                mode=ExecutionMode.LIVE
            )

    # Second item should be aborted because browser is closed
    assert mock_ctrl.configure_food_item.call_count == 1


# ==============================================================================
# PHASE 7: PERFORMANCE & SAFEGUARDS (31 - 35)
# ==============================================================================

@pytest.mark.asyncio
async def test_31_repeated_categories_inspected_only_as_necessary(mock_controller):
    # Populate cache
    mock_controller.verified_categories.add(normalize_category_name("Starters"))
    mock_controller.category_tree[normalize_category_name("Starters")] = {normalize_category_name("Veg Starters")}

    # expand_category_subcategories should return cached without re-inspecting page
    mock_controller.navigate_to_view_food_category = AsyncMock()

    subs = await mock_controller.expand_category_subcategories("Starters")
    assert "veg starters" in subs or "Veg Starters" in subs
    mock_controller.navigate_to_view_food_category.assert_not_called()


@pytest.mark.asyncio
async def test_32_unique_category_subcategory_planning_reduces_redundant_ops():
    runner = ActionPointWorkflowRunner()
    sites = get_all_sites()
    site_id = sites[0].id if sites else add_site(Site(name="Planning Hotel", launcher_button="PLN", enabled=True, local_port=18001))

    # 5 rows all using the same category & subcategory
    items = [
        ActionPointItem(
            row_number=i,
            item_code=f"00{i}",
            item_name=f"Dish {i}",
            item_price="100",
            category="Starters",
            subcategory="Veg Starters",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        )
        for i in range(1, 6)
    ]

    mock_ctrl = AsyncMock()
    mock_ctrl.initialize = AsyncMock()
    mock_ctrl.navigate_and_authenticate = AsyncMock(return_value=(True, "Success"))
    mock_ctrl.inspect_existing_categories = AsyncMock(return_value=(["Starters"], {"Starters": ["Veg Starters"]}))
    mock_ctrl.navigate_to_item_configuration = AsyncMock(return_value=(True, "Loaded"))
    mock_ctrl.configure_food_item = AsyncMock(return_value=(True, "Success", None))

    with patch("app.action_point_automation.workflow_runner.tunnel_manager.start_and_verify_tunnel", AsyncMock(return_value=(True, "OK", []))):
        with patch("app.action_point_automation.workflow_runner.ActionPointPortalController", return_value=mock_ctrl):
            result = await runner.execute_run(
                site_id=site_id,
                filename="plan_test.csv",
                items=items,
                mode=ExecutionMode.DRY_RUN
            )

    assert result["success"] is True
    # Initial inspection performed once, item configuration navigated once
    mock_ctrl.inspect_existing_categories.assert_called_once()
    mock_ctrl.navigate_to_item_configuration.assert_called_once()
    assert mock_ctrl.configure_food_item.call_count == 5


@pytest.mark.asyncio
async def test_33_screenshots_retained_around_state_changing_operations(mock_controller):
    item = ActionPointItem(
        row_number=2,
        item_code="0042",
        item_name="Chicken Tikka",
        item_price="450",
        category="Starters",
        subcategory="Non-Veg",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    mock_controller.find_element = AsyncMock(side_effect=[
        (AsyncMock(), "search_input"),
        (AsyncMock(), "search_btn"),
        (AsyncMock(), "cat_panel"),
        (AsyncMock(), "rest_panel"),
        (AsyncMock(), "conf_btn")
    ])

    row = AsyncMock()
    td = AsyncMock()
    td.inner_text = AsyncMock(return_value="0042")
    row.query_selector_all = AsyncMock(return_value=[td])
    row.query_selector = AsyncMock(return_value=AsyncMock())
    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.page.query_selector = AsyncMock(return_value=AsyncMock())

    snapshots_captured = []

    async def mock_snap(action, **kwargs):
        snapshots_captured.append(action)
        snap = MagicMock()
        snap.screenshot_path = f"{action}.png"
        return snap

    mock_controller.snapshot = AsyncMock(side_effect=mock_snap)

    ok, msg, ss = await mock_controller.configure_food_item(item, dry_run=False)
    assert ok is True
    # Verifies snapshots were captured before and after configure click
    assert any("pre_save" in s for s in snapshots_captured)
    assert any("post_save" in s for s in snapshots_captured)


@pytest.mark.asyncio
async def test_34_unchanged_read_only_state_does_not_cause_unnecessary_repeated_screenshots(mock_controller):
    mock_controller.verified_categories.add(normalize_category_name("Desserts"))
    mock_controller.category_tree[normalize_category_name("Desserts")] = {normalize_category_name("Ice Cream")}

    mock_controller.snapshot = AsyncMock()
    # Cache hit returns immediately without snapshots
    subs = await mock_controller.expand_category_subcategories("Desserts")
    mock_controller.snapshot.assert_not_called()


@pytest.mark.asyncio
async def test_35_dry_run_performs_zero_writes(mock_controller):
    item = ActionPointItem(
        row_number=2,
        item_code="0042",
        item_name="Chicken Tikka",
        item_price="450",
        category="Starters",
        subcategory="Non-Veg",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    conf_btn = AsyncMock()
    mock_controller.find_element = AsyncMock(side_effect=[
        (AsyncMock(), "search_input"),
        (AsyncMock(), "search_btn"),
        (AsyncMock(), "cat_panel"),
        (AsyncMock(), "rest_panel"),
        (conf_btn, "conf_btn")
    ])

    row = AsyncMock()
    td = AsyncMock()
    td.inner_text = AsyncMock(return_value="0042")
    row.query_selector_all = AsyncMock(return_value=[td])
    row.query_selector = AsyncMock(return_value=AsyncMock())
    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.page.query_selector = AsyncMock(return_value=AsyncMock())

    ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=True)
    assert ok is True
    assert "DRY_RUN" in msg
    # Configure button was NOT clicked in dry-run mode
    conf_btn.click.assert_not_called()
