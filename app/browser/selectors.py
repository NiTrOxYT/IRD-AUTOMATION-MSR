import json
import logging
from typing import List, Dict, Any
from app.database.db import get_all_selectors, get_selector

logger = logging.getLogger("IRD_Selectors")

class SelectorRegistry:
    @staticmethod
    def get_selectors_for_step(step_key: str) -> List[str]:
        """
        Returns an ordered list of Playwright selectors for a given step.
        Combines primary_selector and fallbacks.
        """
        sel = get_selector(step_key)
        if not sel:
            # Fallback hardcoded list
            defaults = {
                "idp_username": [
                    "input[name='username']", "input[type='text']", "input[type='email']", "input[autocomplete='username']",
                    "#username", "#user", "#email", "#userId", "input[name*='user']", "input[id*='user']",
                    "input[placeholder*='User']", "input[placeholder*='Email']", "input[name='login']"
                ],
                "login_username": [
                    "input[name='username']", "input[type='text']", "input[type='email']", "input[autocomplete='username']",
                    "#username", "#user", "#email", "#userId", "input[name*='user']", "input[id*='user']",
                    "input[placeholder*='User']", "input[placeholder*='Email']", "input[name='login']"
                ],
                "idp_password": [
                    "input[name='password']", "input[type='password']", "input[autocomplete='current-password']",
                    "#password", "#pass", "input[id*='pass']", "input[name*='pass']", "input[placeholder*='Password']"
                ],
                "login_password": [
                    "input[name='password']", "input[type='password']", "input[autocomplete='current-password']",
                    "#password", "#pass", "input[id*='pass']", "input[name*='pass']", "input[placeholder*='Password']"
                ],
                "login_button": [
                    "button[type='submit']", "input[type='submit']", "button:has-text('Sign In')", "button:has-text('Log In')",
                    "button:has-text('Login')", "a:has-text('Log In')", "#loginBtn", ".login-button", "button:has-text('Submit')", "button:has-text('Proceed')"
                ],
                "login_submit": [
                    "button[type='submit']", "input[type='submit']", "button:has-text('Sign In')", "button:has-text('Log In')",
                    "button:has-text('Login')", "a:has-text('Log In')", "#loginBtn", ".login-button", "button:has-text('Submit')", "button:has-text('Proceed')"
                ],
                "sync_mymenu": [
                    "text='Sync MyMenu'", "a:has-text('Sync MyMenu')", "button:has-text('Sync MyMenu')",
                    "[data-testid='sync-mymenu']", "#sync-mymenu", "[aria-label='Sync MyMenu']", "a[href*='sync']",
                    ".nav-link:has-text('Sync')", "text='MyMenu Sync'", "a[href*='main-menu']", "text='Sync'", "text='MyMenu'",
                    "a:has-text('Sync')", "button:has-text('Sync')", "a[href*='zmp']"
                ],

                "fetch_menu": [
                    "button:has-text('Fetch Menu')",
                    "input[value='Fetch Menu']",
                    "a:has-text('Fetch Menu')",
                    ".fetch-menu-btn",
                    "button[id*='fetch']",
                    "text='Fetch Menu'",
                    "a:has-text('Fetch')",
                    "button:has-text('Fetch')",
                    "input[value*='Fetch']",
                    "a[href*='fetch']",
                    "[aria-label*='Fetch']"
                ],
                "fetch_menu_loading": [
                    ".spinner", ".loading", ".loader", "[aria-busy='true']", "button[disabled]",
                    "text='Loading'", "text='Fetching'", "text='Please wait'"
                ],
                "invalid_credentials_notice": [

                    ".alert-danger", ".error-message", ".invalid-feedback", "text='Invalid username or password'",
                    "text='Authentication failed'", "text='Invalid credentials'", "text='Login failed'"
                ],
                "process_latest_menu": [
                    "button:has-text('Process Latest Menu')", "input[value='Process Latest Menu']", "text='Process Latest Menu'",
                    ".process-menu-btn", "button[id*='process']", "button:has-text('Process Menu')", "button:has-text('Process')"
                ],
                "download_action_point": [
                    "button:has-text('Download Action Points')", "a:has-text('Download Action Points')", "text='Download Action Points'",
                    "button:has-text('Download Action Point')", "a:has-text('Download Action Point')", "text='Download Action Point'",
                    "a[href*='download']", ".download-btn", "button:has-text('Download')", "a:has-text('Download CSV')"
                ],
                "download_action_points": [
                    "button:has-text('Download Action Points')", "a:has-text('Download Action Points')", "text='Download Action Points'",
                    "button:has-text('Download Action Point')", "a:has-text('Download Action Point')", "text='Download Action Point'",
                    "a[href*='download']", ".download-btn", "button:has-text('Download')", "a:has-text('Download CSV')"
                ],
                "fetch_menu_loading": [
                    ".spinner-border", ".loading", ".spinner", ".progress-bar", "text='Processing...'", "text='Loading...'"
                ]
            }
            return defaults.get(step_key, [f".{step_key}"])

        selectors = []
        if sel.primary_selector:
            # Split comma-separated primary items if present
            primary_items = [p.strip() for p in sel.primary_selector.split(",") if p.strip()]
            selectors.extend(primary_items)

        if sel.fallback_selectors:
            try:
                fallbacks = json.loads(sel.fallback_selectors)
                if isinstance(fallbacks, list):
                    selectors.extend(fallbacks)
            except Exception:
                pass

        # Deduplicate preserving order
        seen = set()
        dedup = []
        for s in selectors:
            if s not in seen:
                seen.add(s)
                dedup.append(s)
        return dedup

