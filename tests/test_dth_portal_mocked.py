import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.dth_automation.models import ChannelItem, DthItemState
from app.dth_automation.portal_controller import DthPortalController


class TestDthPortalMocked(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.controller = DthPortalController()
        # Mock Playwright Page
        self.mock_page = MagicMock()
        self.mock_page.is_closed = MagicMock(return_value=False)
        self.mock_page.goto = AsyncMock(return_value=None)
        self.mock_page.wait_for_load_state = AsyncMock(return_value=None)
        self.mock_page.close = AsyncMock(return_value=None)
        self.mock_page.url = "http://localhost:18001/zmp/channels.do"

        self.controller.page = self.mock_page
        self.controller.is_connected = True

        self.sample_channel = ChannelItem(
            row_number=2,
            channel_number="101",
            name="News 24",
            osd="News 24",
            image="news.png",
            categories=["all", "News"]
        )

    async def asyncTearDown(self):
        await self.controller.close()

    def _make_mock_element(self):
        el = MagicMock()
        el.first = el
        el.count = AsyncMock(return_value=1)
        el.is_visible = AsyncMock(return_value=True)
        el.click = AsyncMock(return_value=None)
        el.fill = AsyncMock(return_value=None)
        el.all = AsyncMock(return_value=[])
        el.inner_text = AsyncMock(return_value="")
        el.get_attribute = AsyncMock(return_value="")
        el.evaluate = AsyncMock(return_value="")
        return el

    async def test_read_available_categories_defaults(self):
        mock_loc = self._make_mock_element()
        mock_loc.all = AsyncMock(return_value=[])
        self.mock_page.locator = MagicMock(return_value=mock_loc)

        cats = await self.controller.read_available_categories()
        self.assertIn("all", cats)
        self.assertIn("News", cats)
        self.assertIn("Entertainment", cats)

    async def test_create_channel_success_with_toast(self):
        mock_elem = self._make_mock_element()
        self.mock_page.locator = MagicMock(return_value=mock_elem)

        state, reason, verified = await self.controller.create_channel(self.sample_channel)
        self.assertEqual(state, DthItemState.SUCCESS)
        self.assertTrue(verified)

    async def test_create_channel_portal_error(self):
        def locator_side_effect(sel):
            el = self._make_mock_element()
            if any(err_k in sel for err_k in ["alert-danger", "error", "invalid-feedback"]):
                el.count = AsyncMock(return_value=1)
                el.is_visible = AsyncMock(return_value=True)
                el.inner_text = AsyncMock(return_value="Channel number already assigned to another frequency")
            elif any(succ_k in sel for succ_k in ["success", "Saved", "Successful", "toast-success"]):
                el.count = AsyncMock(return_value=0)
                el.is_visible = AsyncMock(return_value=False)
            elif any(form_k in sel for form_k in ["channelNumber", "channelName", "osdName", "btn_save", "Save", "button", "input"]):
                el.count = AsyncMock(return_value=1)
                el.is_visible = AsyncMock(return_value=True)
            else:
                el.count = AsyncMock(return_value=0)
                el.is_visible = AsyncMock(return_value=False)
            el.first = el
            return el

        self.mock_page.locator = MagicMock(side_effect=locator_side_effect)

        state, reason, verified = await self.controller.create_channel(self.sample_channel)
        self.assertEqual(state, DthItemState.FAILED)
        self.assertIn("Channel number already assigned", reason)
        self.assertFalse(verified)

    async def test_create_channel_timeout_and_reconciliation_found(self):
        def locator_side_effect(sel):
            el = self._make_mock_element()
            if any(k in sel for k in ["Save", "submit", "btn_save"]):
                el.click = AsyncMock(side_effect=PlaywrightTimeoutError("Save timeout"))
            return el

        self.mock_page.locator = MagicMock(side_effect=locator_side_effect)

        # Patch get_existing_channels_from_portal to simulate channel found in table after timeout
        with patch.object(
            self.controller,
            "get_existing_channels_from_portal",
            AsyncMock(return_value=({"101"}, {"news 24"}))
        ):
            state, reason, verified = await self.controller.create_channel(self.sample_channel)
            self.assertEqual(state, DthItemState.SUCCESS)
            self.assertTrue(verified)
            self.assertIn("Verified present in portal channel table", reason)

    async def test_create_channel_timeout_and_reconciliation_not_found(self):
        def locator_side_effect(sel):
            el = self._make_mock_element()
            if any(k in sel for k in ["Save", "submit", "btn_save"]):
                el.click = AsyncMock(side_effect=PlaywrightTimeoutError("Save timeout"))
            return el

        self.mock_page.locator = MagicMock(side_effect=locator_side_effect)

        with patch.object(
            self.controller,
            "get_existing_channels_from_portal",
            AsyncMock(return_value=(set(), set()))
        ):
            state, reason, verified = await self.controller.create_channel(self.sample_channel)
            self.assertEqual(state, DthItemState.UNKNOWN)
            self.assertFalse(verified)
            self.assertIn("ambiguous", reason)

    async def test_emergency_stop_lifecycle(self):
        await self.controller.emergency_stop()
        self.assertTrue(self.controller.stop_requested)
        self.assertFalse(self.controller.is_connected)


if __name__ == "__main__":
    unittest.main()
