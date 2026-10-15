import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("DTH_Selectors")

DEFAULT_DTH_SELECTORS: Dict[str, Dict[str, Any]] = {
    "login_username": {
        "primary": "input[name='j_username'], input[name='username'], input[name='userId']",
        "fallbacks": ["#username", "#user", "#userId", "input[type='text'][tabindex='1']", "input[type='text']"],
        "desc": "Portal Login Username input field"
    },
    "login_password": {
        "primary": "input[name='j_password'], input[name='password'], input[name='pwd']",
        "fallbacks": ["#password", "#pass", "input[type='password'][tabindex='2']", "input[type='password']"],
        "desc": "Portal Login Password input field"
    },
    "login_submit": {
        "primary": "input[type='submit'][value*='Login'], button[type='submit']:has-text('Login'), input[value='Login']",
        "fallbacks": ["form[name='loginForm'] input[type='submit']", "button[type='submit']", "input[type='submit']"],
        "desc": "Portal Login Submit button"
    },
    "indicator_authenticated": {
        "primary": "a[href*='j_spring_security_logout'], a:has-text('LOGOUT'), text='LOGOUT'",
        "fallbacks": ["a:has-text('Application Dashboard')", "a[href*='main-menu.do']", "text='Smartler Management Portal'"],
        "desc": "Element confirming active authenticated session"
    },
    "nav_service_setup": {
        "primary": "text='Service Setup', a:has-text('Service Setup'), button:has-text('Service Setup')",
        "fallbacks": ["[data-testid='service-setup']", ".nav-link:has-text('Service')", "a[href*='service']"],
        "desc": "Main navigation 'Service Setup' menu"
    },
    "nav_dth_channel_config": {
        "primary": "a[href*='manage-stb-channels'], a:has-text('DTH Program Configuration'), text='DTH Program Configuration', text='DTH Channel Configuration'",
        "fallbacks": ["a:has-text('DTH Program Configuration')", "a:has-text('Manage STB Channels')", "a:has-text('Channel Configuration')"],
        "desc": "Sub-navigation 'DTH Program Configuration' / 'manage-stb-channels' link"
    },
    "btn_add_new_channel": {
        "primary": "a.k-grid-add, .k-grid-add, a:has-text('Add new Channel'), a:has-text('Add New Channel'), button:has-text('Add New Channel'), input[value='Add New Channel']",
        "fallbacks": ["a.k-button:has-text('Add')", "a:has-text('Add Channel')", "button:has-text('Add Channel')", "#btnAddChannel", ".add-channel-btn"],
        "desc": "'Add New Channel' action button"
    },
    "btn_edit_channel": {
        "primary": "a.k-grid-edit, a:has-text('Edit'), button:has-text('Edit'), a[href*='edit']",
        "fallbacks": ["a[href*='modify']", "button[title*='Edit']", ".btn-edit", "a:has-text('Modify')"],
        "desc": "Edit channel link or button in portal channel row"
    },
    "input_channel_number": {
        "primary": "#row_newentry input#channelNumber, #channelNumber, #row_newentry input[name='channelNumber'], input[name='channelNumber']",
        "fallbacks": ["input[name='channel_number']", "input[name*='channelNumber']", "input[name*='channelNo']", "input[id*='channel']"],
        "desc": "Channel Number text field"
    },
    "input_channel_name": {
        "primary": "#row_newentry input#name, #name, #row_newentry input[name='name'], input[name='name']",
        "fallbacks": ["input[name*='channelName']", "input[name*='stbChannelName']", "input[name*='channel_name']", "input[id*='name']", "input[placeholder*='Channel Name']"],
        "desc": "Channel Name text field"
    },
    "input_channel_osd": {
        "primary": "#row_newentry input#osd, #osd, #row_newentry input[name='osd'], input[name='osd']",
        "fallbacks": ["input[name*='osdName']", "input[name*='stbOsdName']", "input[id*='osd']", "input[name*='osd']", "input[placeholder*='OSD']"],
        "desc": "OSD Name text field"
    },
    "input_channel_image": {
        "primary": "#row_newentry #addnewcmsimage, #addnewcmsimage, #row_newentry input[type='file'], input[name='cmsImage'], input[type='file'][name*='image']",
        "fallbacks": ["#channelLogo", "#imageFile", "input[name='logo']", "input[name='file']", "input[name*='stb']"],
        "desc": "Channel Logo File Upload input"
    },
    "category_checkboxes": {
        "primary": "#row_newentry .multiselect input[type='checkbox'], .multiselect input[type='checkbox'], input[type='checkbox'][name='stbChannelCategories']",
        "fallbacks": [".category-checkbox", "input[type='checkbox']"],
        "desc": "Category checkboxes in channel form"
    },
    "btn_save_channel": {
        "primary": "#row_newentry a.k-grid-update, a.k-grid-update, a.k-primary:has-text('Save'), a:has-text('Save'), input[value='Save']",
        "fallbacks": ["a.button:has-text('Save')", "button:has-text('Submit')", "input[type='submit']", "#btnSave", ".save-channel-btn"],
        "desc": "Save Channel Form button"
    },
    "btn_cancel_channel": {
        "primary": "#row_newentry a.k-grid-cancel, a.k-grid-cancel, a:has-text('Cancel'), button:has-text('Cancel')",
        "fallbacks": ["#btnCancel", ".cancel-btn"],
        "desc": "Cancel Channel Form button"
    },
    "channel_table": {
        "primary": "table#datatable, table.tablesorter, table#channelTable, table:has-text('Channel')",
        "fallbacks": ["table[id*='channel']", "table[class*='channel']", "table:has(th:has-text('Channel'))", "table", ".data-table"],
        "desc": "Channel listing table"
    },
    "msg_success": {
        "primary": ".alert-success, .toast-success, text='Channel created successfully', text='Saved successfully'",
        "fallbacks": [".success-message", "text='Operation Successful'", "text='Channel updated successfully'"],
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
