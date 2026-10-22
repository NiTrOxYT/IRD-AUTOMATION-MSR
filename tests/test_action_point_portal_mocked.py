import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.action_point_automation.portal_controller import ActionPointPortalController
from app.action_point_automation.models import ActionPointItem, ActionClassification


@pytest.fixture
def mock_controller():
    ctrl = ActionPointPortalController(run_id=999, site_name="MockSite")
    ctrl.browser = AsyncMock()
    ctrl.browser.close = AsyncMock()
    ctrl.page = AsyncMock()
    ctrl.page.is_closed = MagicMock(return_value=False)
    ctrl.page.close = AsyncMock()
    ctrl.page.url = "http://127.0.0.1:18001/zmp/main-menu.do"
    ctrl.page.title = AsyncMock(return_value="Zenith Media Portal")
    ctrl.page.screenshot = AsyncMock()
    ctrl.page.go_back = AsyncMock()
    return ctrl


def setup_mock_login_elements(mock_controller):
    user_input = AsyncMock()
    pass_input = AsyncMock()
    submit_btn = AsyncMock()

    async def mock_find_element(selectors, timeout_ms=5000):
        if any("username" in s or "user" in s for s in selectors):
            return user_input, selectors[0]
        if any("password" in s for s in selectors):
            return pass_input, selectors[0]
        if any("submit" in s or "login" in s.lower() for s in selectors):
            return submit_btn, selectors[0]
        return None, ""

    mock_controller.find_element = AsyncMock(side_effect=mock_find_element)
    return user_input, pass_input, submit_btn


@pytest.mark.asyncio
async def test_whitelabel_recovery_back_to_login_and_succeeds(mock_controller):
    """Scenario 1: White-label error -> Back -> login page -> successful login."""
    setup_mock_login_elements(mock_controller)

    state = {"stage": "initial_login"}

    async def mock_content():
        if state["stage"] == "whitelabel":
            return "<html><body>Whitelabel Error Page This application has no explicit mapping for /error</body></html>"
        elif state["stage"] == "authenticated":
            return "<html><body>Food Category View Food Category Sync MyMenu</body></html>"
        else:
            return "<html><body><form id='login-form'></form></body></html>"

    async def mock_title():
        if state["stage"] == "whitelabel":
            return "Whitelabel Error Page"
        elif state["stage"] == "authenticated":
            return "Zenith Media Portal"
        return "Login"

    mock_controller.page.content = AsyncMock(side_effect=mock_content)
    mock_controller.page.title = AsyncMock(side_effect=mock_title)

    async def mock_execute_login(*args, **kwargs):
        if state["stage"] == "initial_login":
            state["stage"] = "whitelabel"
            mock_controller.page.url = "http://127.0.0.1:18001/zmp/main-menu.do"
            return True, "Login submitted"
        else:
            state["stage"] = "authenticated"
            mock_controller.page.url = "http://127.0.0.1:18001/zmp/main-menu.do"
            return True, "Login submitted"

    mock_controller._execute_login_submission = AsyncMock(side_effect=mock_execute_login)

    async def mock_go_back(**kwargs):
        state["stage"] = "back_on_login"
        mock_controller.page.url = "http://127.0.0.1:18001/login"
        return AsyncMock()

    mock_controller.page.go_back = AsyncMock(side_effect=mock_go_back)

    auth_ok, msg = await mock_controller.navigate_and_authenticate(
        portal_url="http://127.0.0.1:18001/login",
        username="admin",
        password="secret"
    )

    assert auth_ok is True
    assert msg == "Login successful"
    mock_controller.page.go_back.assert_called_once()
    mock_controller.page.close.assert_not_called()


@pytest.mark.asyncio
async def test_whitelabel_recovery_repeated_bounded_retry(mock_controller):
    """Scenario 2: White-label error -> Back -> login page -> another white-label error -> bounded retry."""
    setup_mock_login_elements(mock_controller)

    state = {"on_login": True}

    async def mock_content():
        if state["on_login"]:
            return "<html><body><form id='login'></form></body></html>"
        return "<html><body>Whitelabel Error Page This application has no explicit mapping for /error</body></html>"

    async def mock_title():
        if state["on_login"]:
            return "Login"
        return "Whitelabel Error Page"

    mock_controller.page.content = AsyncMock(side_effect=mock_content)
    mock_controller.page.title = AsyncMock(side_effect=mock_title)

    async def mock_execute_login(*args, **kwargs):
        state["on_login"] = False
        mock_controller.page.url = "http://127.0.0.1:18001/zmp/main-menu.do"
        return True, "Login submitted"

    mock_controller._execute_login_submission = AsyncMock(side_effect=mock_execute_login)

    async def mock_go_back(**kwargs):
        state["on_login"] = True
        mock_controller.page.url = "http://127.0.0.1:18001/login"
        return AsyncMock()

    mock_controller.page.go_back = AsyncMock(side_effect=mock_go_back)

    auth_ok, msg = await mock_controller.navigate_and_authenticate(
        portal_url="http://127.0.0.1:18001/login",
        username="admin",
        password="secret",
        max_recovery_attempts=2
    )

    assert auth_ok is False
    assert "Repeated Whitelabel Error Page after maximum recovery attempts (2)" in msg
    assert mock_controller.page.go_back.call_count == 2
    mock_controller.page.close.assert_not_called()


@pytest.mark.asyncio
async def test_whitelabel_recovery_back_timeout(mock_controller):
    """Scenario 3: Back navigation timeout."""
    setup_mock_login_elements(mock_controller)

    state = {"stage": "login"}

    async def mock_content():
        if state["stage"] == "whitelabel":
            return "<html><body>Whitelabel Error Page This application has no explicit mapping for /error</body></html>"
        return "<html><body><form id='login'></form></body></html>"

    async def mock_title():
        if state["stage"] == "whitelabel":
            return "Whitelabel Error Page"
        return "Login"

    mock_controller.page.content = AsyncMock(side_effect=mock_content)
    mock_controller.page.title = AsyncMock(side_effect=mock_title)

    async def mock_execute(*args, **kwargs):
        state["stage"] = "whitelabel"
        return True, "Login submitted"

    mock_controller._execute_login_submission = AsyncMock(side_effect=mock_execute)
    mock_controller.page.go_back = AsyncMock(side_effect=PlaywrightTimeoutError("Navigation timeout of 15000ms exceeded"))

    auth_ok, msg = await mock_controller.navigate_and_authenticate(
        portal_url="http://127.0.0.1:18001/login",
        username="admin",
        password="secret"
    )

    assert auth_ok is False
    assert "Browser Back navigation timed out" in msg
    mock_controller.page.close.assert_not_called()


@pytest.mark.asyncio
async def test_whitelabel_recovery_back_unexpected_page(mock_controller):
    """Scenario 4: Back navigation returning to an unexpected page."""
    setup_mock_login_elements(mock_controller)

    state = {"stage": "login"}

    async def mock_content():
        if state["stage"] == "login":
            return "<html><body><form id='login'></form></body></html>"
        elif state["stage"] == "whitelabel":
            return "<html><body>Whitelabel Error Page This application has no explicit mapping for /error</body></html>"
        else:
            return "<html><body>404 Not Found - Unexpected Server Page</body></html>"

    async def mock_title():
        if state["stage"] == "login":
            return "Login"
        elif state["stage"] == "whitelabel":
            return "Whitelabel Error Page"
        return "404 Not Found"

    mock_controller.page.content = AsyncMock(side_effect=mock_content)
    mock_controller.page.title = AsyncMock(side_effect=mock_title)

    execute_calls = []
    async def mock_execute(*args, **kwargs):
        execute_calls.append(True)
        state["stage"] = "whitelabel"
        return True, "Login submitted"

    mock_controller._execute_login_submission = AsyncMock(side_effect=mock_execute)

    async def mock_go_back(**kwargs):
        state["stage"] = "unexpected"
        mock_controller.page.url = "http://127.0.0.1:18001/unexpected-404"
        mock_controller.find_element = AsyncMock(return_value=(None, ""))
        return AsyncMock()

    mock_controller.page.go_back = AsyncMock(side_effect=mock_go_back)

    auth_ok, msg = await mock_controller.navigate_and_authenticate(
        portal_url="http://127.0.0.1:18001/login",
        username="admin",
        password="secret"
    )

    assert auth_ok is False
    assert "did not return to a usable login page" in msg
    assert len(execute_calls) == 1
    mock_controller.page.close.assert_not_called()


@pytest.mark.asyncio
async def test_whitelabel_recovery_login_submission_fails(mock_controller):
    """Scenario 5: Login submission failing after recovery."""
    setup_mock_login_elements(mock_controller)

    state = {"stage": "initial"}

    async def mock_content():
        if state["stage"] == "whitelabel":
            return "<html><body>Whitelabel Error Page This application has no explicit mapping for /error</body></html>"
        return "<html><body><form id='login'></form></body></html>"

    mock_controller.page.content = AsyncMock(side_effect=mock_content)
    mock_controller.page.title = AsyncMock(return_value="Zenith Media Portal")

    async def mock_execute(*args, **kwargs):
        if state["stage"] == "initial":
            state["stage"] = "whitelabel"
            return True, "Login submitted"
        else:
            return False, "Authentication failed: Invalid credentials rejected by portal."

    mock_controller._execute_login_submission = AsyncMock(side_effect=mock_execute)

    async def mock_go_back(**kwargs):
        state["stage"] = "back_on_login"
        return AsyncMock()

    mock_controller.page.go_back = AsyncMock(side_effect=mock_go_back)

    auth_ok, msg = await mock_controller.navigate_and_authenticate(
        portal_url="http://127.0.0.1:18001/login",
        username="admin",
        password="wrong_password"
    )

    assert auth_ok is False
    assert "Invalid credentials" in msg
    mock_controller.page.close.assert_not_called()


@pytest.mark.asyncio
async def test_whitelabel_recovery_browser_remains_open(mock_controller):
    """Scenario 6: Browser remains open throughout recovery attempts."""
    setup_mock_login_elements(mock_controller)
    mock_controller.browser = AsyncMock()

    state = {"stage": "login"}

    async def mock_content():
        if state["stage"] == "whitelabel":
            return "<html><body>Whitelabel Error Page This application has no explicit mapping for /error</body></html>"
        return "<html><body><form id='login'></form></body></html>"

    mock_controller.page.content = AsyncMock(side_effect=mock_content)
    mock_controller.page.title = AsyncMock(return_value="Whitelabel Error Page")

    async def mock_execute(*args, **kwargs):
        state["stage"] = "whitelabel"
        return True, "Login submitted"

    mock_controller._execute_login_submission = AsyncMock(side_effect=mock_execute)
    mock_controller.page.go_back = AsyncMock()

    auth_ok, msg = await mock_controller.navigate_and_authenticate(
        portal_url="http://127.0.0.1:18001/login",
        username="admin",
        password="secret",
        max_recovery_attempts=2
    )

    assert auth_ok is False
    mock_controller.page.close.assert_not_called()
    mock_controller.browser.close.assert_not_called()


@pytest.mark.asyncio
async def test_existing_successful_login_remains_unchanged(mock_controller):
    """Scenario 7: Existing successful login behavior remains unchanged."""
    setup_mock_login_elements(mock_controller)

    # Case A: Normal direct login
    state = {"logged_in": False}
    async def mock_content():
        if state["logged_in"]:
            return "<html><body>Food Category View Food Category Sync MyMenu</body></html>"
        return "<html><body><form id='login'></form></body></html>"

    mock_controller.page.content = AsyncMock(side_effect=mock_content)
    mock_controller.page.title = AsyncMock(return_value="Zenith Portal")

    async def mock_execute(*args, **kwargs):
        state["logged_in"] = True
        return True, "Login submitted"

    mock_controller._execute_login_submission = AsyncMock(side_effect=mock_execute)

    auth_ok, msg = await mock_controller.navigate_and_authenticate(
        portal_url="http://127.0.0.1:18001/login",
        username="admin",
        password="secret"
    )

    assert auth_ok is True
    assert msg == "Login successful"
    mock_controller.page.go_back.assert_not_called()

    # Case B: Already authenticated session
    mock_controller.page.content = AsyncMock(return_value="<html><body>Food Category Sync MyMenu</body></html>")
    auth_ok2, msg2 = await mock_controller.navigate_and_authenticate(
        portal_url="http://127.0.0.1:18001/zmp/main-menu.do",
        username="admin",
        password="secret"
    )
    assert auth_ok2 is True
    assert msg2 == "Already authenticated"
    mock_controller.page.go_back.assert_not_called()


@pytest.mark.asyncio
async def test_inspect_existing_categories(mock_controller):
    # Mock table rows returning categories
    row1 = AsyncMock()
    row1.inner_text = AsyncMock(return_value="Starters\tVeg Starters, Non-Veg Starters")
    td1 = AsyncMock()
    td1.inner_text = AsyncMock(return_value="Starters")
    td2 = AsyncMock()
    td2.inner_text = AsyncMock(return_value="Veg Starters, Non-Veg Starters")
    row1.query_selector_all = AsyncMock(return_value=[td1, td2])

    row2 = AsyncMock()
    row2.inner_text = AsyncMock(return_value="Beverages\tHot, Cold")
    td3 = AsyncMock()
    td3.inner_text = AsyncMock(return_value="Beverages")
    td4 = AsyncMock()
    td4.inner_text = AsyncMock(return_value="Hot, Cold")
    row2.query_selector_all = AsyncMock(return_value=[td3, td4])

    mock_controller.page.query_selector_all = AsyncMock(return_value=[row1, row2])

    categories, tree = await mock_controller.inspect_existing_categories()
    assert "Starters" in categories
    assert "Beverages" in categories
    assert "Veg Starters" in tree["Starters"]
    assert "Non-Veg Starters" in tree["Starters"]


@pytest.mark.asyncio
async def test_create_category_workflow(mock_controller):
    name_input = AsyncMock()
    disp_input = AsyncMock()
    disp_input.input_value = AsyncMock(return_value="")
    img_input = AsyncMock()
    save_btn = AsyncMock()

    mock_controller.find_element = AsyncMock(side_effect=[
        (AsyncMock(), "nav_cat"),          # Menu
        (AsyncMock(), "nav_add_cat"),      # Add Food Category
        (name_input, "input_cat_name"),    # Category name input
        (disp_input, "disp_input"),        # Display name input
        (img_input, "img_input"),          # Category image upload
        (save_btn, "btn_save"),            # Save button
    ])

    # Mock inspect_existing_categories to confirm category creation
    with patch.object(mock_controller, "inspect_existing_categories", AsyncMock(return_value=(["Italian", "Starters"], {}))):
        ok, msg = await mock_controller.create_category("Italian")
        assert ok is True
        assert "created and verified" in msg
        name_input.fill.assert_called_with("Italian")
        disp_input.fill.assert_called_with("Italian")
        img_input.set_input_files.assert_called_once()
        save_btn.click.assert_called_once()


@pytest.mark.asyncio
async def test_configure_food_item_exact_match_dry_run_safety(mock_controller):
    """Verifies that in Dry-Run mode, Configure button is NEVER clicked."""
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
    search_btn = AsyncMock()
    mock_controller.find_element = AsyncMock(side_effect=[
        (search_input, "search_input"),
        (search_btn, "search_btn"),
        (AsyncMock(), "cat_panel"),
        (AsyncMock(), "rest_ird_default"),
        (AsyncMock(), "conf_btn")
    ])

    # Matching row with exact item code
    row = AsyncMock()
    td1 = AsyncMock()
    td1.inner_text = AsyncMock(return_value="0042")
    td2 = AsyncMock()
    td2.inner_text = AsyncMock(return_value="Chicken Tikka")
    row.query_selector_all = AsyncMock(return_value=[td1, td2])
    row.inner_text = AsyncMock(return_value="0042 Chicken Tikka")
    row.query_selector = AsyncMock(return_value=AsyncMock())

    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])
    mock_controller.page.query_selector = AsyncMock(return_value=AsyncMock())

    ok, msg, ss = await mock_controller.configure_food_item(item, dry_run=True)
    assert ok is True
    assert "DRY_RUN" in msg

    # Assert search input was filled with exact code "0042"
    search_input.fill.assert_any_call("0042")


@pytest.mark.asyncio
async def test_configure_food_item_not_found(mock_controller):
    item = ActionPointItem(
        row_number=5,
        item_code="9999",
        item_name="Phantom Dish",
        item_price="100",
        category="Starters",
        subcategory="Veg Starters",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "search_input"))
    mock_controller.page.query_selector_all = AsyncMock(return_value=[])  # Empty search results

    ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=False)
    assert ok is False
    assert "FAILED — ITEM NOT FOUND" in msg


@pytest.mark.asyncio
async def test_configure_food_item_ambiguous_match(mock_controller):
    item = ActionPointItem(
        row_number=6,
        item_code="0010",
        item_name="Naan",
        item_price="50",
        category="Breads",
        subcategory="Indian",
        original_status="Category Update",
        normalized_status="category update",
        classification=ActionClassification.CATEGORY_UPDATE,
        is_valid=True
    )

    mock_controller.find_element = AsyncMock(return_value=(AsyncMock(), "search_input"))

    # Two rows with identical code
    r1 = AsyncMock()
    td1 = AsyncMock()
    td1.inner_text = AsyncMock(return_value="0010")
    r1.query_selector_all = AsyncMock(return_value=[td1])

    r2 = AsyncMock()
    td2 = AsyncMock()
    td2.inner_text = AsyncMock(return_value="0010")
    r2.query_selector_all = AsyncMock(return_value=[td2])

    mock_controller.page.query_selector_all = AsyncMock(return_value=[r1, r2])

    ok, msg, _ = await mock_controller.configure_food_item(item, dry_run=False)
    assert ok is False
    assert "BLOCKED — AMBIGUOUS ITEM MATCH" in msg


@pytest.mark.asyncio
async def test_create_category_missing_image_preflight_fails(mock_controller):
    ok, msg = await mock_controller.create_category("Starters", image_path=r"C:\nonexistent\missing.png")
    assert ok is False
    assert "Preflight error" in msg


@pytest.mark.asyncio
async def test_create_subcategory_workflow(mock_controller):
    # Setup row with parent category "Starters"
    row = AsyncMock()
    td_name = AsyncMock()
    td_name.inner_text = AsyncMock(return_value="Starters")
    td_op = AsyncMock()
    file_plus_icon = AsyncMock()
    td_op.query_selector = AsyncMock(return_value=file_plus_icon)
    row.query_selector_all = AsyncMock(return_value=[td_name, td_op])
    row.query_selector = AsyncMock(return_value=file_plus_icon)

    mock_controller.page.query_selector_all = AsyncMock(return_value=[row])

    sub_name_input = AsyncMock()
    img_input = AsyncMock()
    save_btn = AsyncMock()

    mock_controller.find_element = AsyncMock(side_effect=[
        (sub_name_input, "sub_name_input"),
        (img_input, "img_input"),
        (save_btn, "save_btn")
    ])

    with patch.object(mock_controller, "inspect_existing_categories", AsyncMock(return_value=(["Starters"], {"Starters": ["Veg Starters"]}))):
        with patch.object(mock_controller, "expand_category_subcategories", AsyncMock(return_value=["Veg Starters", "Non-Veg Starters"])):
            ok, msg = await mock_controller.create_subcategory("Starters", "Non-Veg Starters")
            assert ok is True
            assert "created and verified" in msg
            sub_name_input.fill.assert_called_with("Non-Veg Starters")
            img_input.set_input_files.assert_called_once()
            save_btn.click.assert_called_once()


@pytest.mark.asyncio
async def test_create_subcategory_missing_image_preflight_fails(mock_controller):
    ok, msg = await mock_controller.create_subcategory("Starters", "Non-Veg Starters", image_path=r"C:\nonexistent\missing.png")
    assert ok is False
    assert "Preflight error" in msg

