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
                "login_username": ["input[name='username']", "input[type='email']", "#username"],
                "login_password": ["input[name='password']", "input[type='password']", "#password"],
                "login_submit": ["button[type='submit']", "input[type='submit']", "button:has-text('Login')", "button:has-text('Sign In')"],
                "sync_mymenu": ["text='Sync MyMenu'", "a:has-text('Sync MyMenu')", "button:has-text('Sync MyMenu')"],
                "fetch_menu": ["button:has-text('Fetch Menu')", "input[value='Fetch Menu']", "text='Fetch Menu'"],
                "process_latest_menu": ["button:has-text('Process Latest Menu')", "input[value='Process Latest Menu']", "text='Process Latest Menu'"],
                "download_action_point": ["button:has-text('Download Action Point')", "a:has-text('Download Action Point')", "text='Download Action Point'"]
            }
            return defaults.get(step_key, [f"text='{step_key}'"])

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
