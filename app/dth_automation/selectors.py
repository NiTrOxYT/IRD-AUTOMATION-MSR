import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("DTH_Selectors")

DEFAULT_DTH_SELECTORS: Dict[str, Dict[str, Any]] = {
    "nav_service_setup": {
        "primary": "text='Service Setup', a:has-text('Service Setup'), button:has-text('Service Setup')",
        "fallbacks": ["[data-testid='service-setup']", ".nav-link:has-text('Service')", "a[href*='service']"],
        "desc": "Main navigation 'Service Setup' menu"
    },
    "nav_dth_channel_config": {
        "primary": "text='DTH Channel Configuration', a:has-text('DTH Channel Configuration'), a[href*='channel']",
        "fallbacks": ["text='DTH Program Configuration'", "a:has-text('Channel Configuration')", "a[href*='create-stb-channel']"],
        "desc": "Sub-navigation 'DTH Channel Configuration' link"
    },
    "btn_add_new_channel": {
        "primary": "button:has-text('Add New Channel'), a:has-text('Add New Channel'), input[value='Add New Channel']",
        "fallbacks": ["button:has-text('Add Channel')", "button:has-text('New Channel')", "#btnAddChannel", ".add-channel-btn"],
        "desc": "'Add New Channel' action button"
    },
    "input_channel_number": {
        "primary": "input[name='channelNumber'], input[name='channel_number'], #channelNumber",
        "fallbacks": ["input[id*='channel']", "input[name*='number']", "input[placeholder*='Channel No']"],
        "desc": "Channel Number text field"
    },
    "input_channel_name": {
        "primary": "input[name='channelName'], input[name='name'], #channelName",
        "fallbacks": ["input[id*='name']", "input[placeholder*='Channel Name']", "input[name*='channelName']"],
        "desc": "Channel Name text field"
    },
    "input_channel_osd": {
        "primary": "input[name='osdName'], input[name='osd'], #osdName",
        "fallbacks": ["input[id*='osd']", "input[name*='osd']", "input[placeholder*='OSD']"],
        "desc": "OSD Name text field"
    },
    "input_channel_image": {
        "primary": "input[type='file'][name*='image'], input[type='file'][name*='logo'], input[type='file']",
        "fallbacks": ["#channelLogo", "#imageFile", "input[name='logo']", "input[name='file']"],
        "desc": "Channel Logo File Upload input"
    },
    "category_checkboxes": {
        "primary": "input[type='checkbox'][name*='category'], input[type='checkbox'][name*='genre']",
        "fallbacks": [".category-checkbox", "input[type='checkbox']"],
        "desc": "Category checkboxes in channel form"
    },
    "btn_save_channel": {
        "primary": "button[type='submit']:has-text('Save'), button:has-text('Save'), input[value='Save']",
        "fallbacks": ["button:has-text('Submit')", "input[type='submit']", "#btnSave", ".save-channel-btn"],
        "desc": "Save Channel Form button"
    },
    "btn_cancel_channel": {
        "primary": "button:has-text('Cancel'), a:has-text('Cancel')",
        "fallbacks": ["#btnCancel", ".cancel-btn"],
        "desc": "Cancel Channel Form button"
    },
    "channel_table": {
        "primary": "table#channelTable, table.channel-list, table:has-text('Channel')",
        "fallbacks": ["table", ".data-table"],
        "desc": "Channel listing table"
    },
    "msg_success": {
        "primary": ".alert-success, .toast-success, text='Channel created successfully', text='Saved successfully'",
        "fallbacks": [".success-message", "text='Operation Successful'"],
        "desc": "Portal success toast or banner"
    },
    "msg_error": {
        "primary": ".alert-danger, .toast-error, .error-message",
        "fallbacks": [".invalid-feedback", "text='Error occurred'"],
        "desc": "Portal error toast or banner"
    }
}


class DthSelectorRegistry:
    """
    Centralized selector registry for DTH Portal elements.
    Configurable and fallback-aware.
    """
    _overrides: Dict[str, List[str]] = {}

    @classmethod
    def set_override(cls, key: str, selectors: List[str]):
        cls._overrides[key] = selectors

    @classmethod
    def get_selectors(cls, key: str) -> List[str]:
        if key in cls._overrides and cls._overrides[key]:
            return cls._overrides[key]

        spec = DEFAULT_DTH_SELECTORS.get(key)
        if not spec:
            return [f".{key}"]

        selectors: List[str] = []
        if "primary" in spec and spec["primary"]:
            primaries = [p.strip() for p in spec["primary"].split(",") if p.strip()]
            selectors.extend(primaries)
        if "fallbacks" in spec and spec["fallbacks"]:
            selectors.extend(spec["fallbacks"])

        # Deduplicate preserving order
        seen = set()
        dedup = []
        for s in selectors:
            if s not in seen:
                seen.add(s)
                dedup.append(s)
        return dedup
