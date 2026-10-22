import re
import logging
from typing import List, Dict, Any, Tuple, Optional, Set

from app.action_point_automation.models import (
    ActionPointItem,
    ActionClassification,
    ActionPointStatusEnum,
    ItemExecutionResult
)

logger = logging.getLogger("ActionPoint_Validator")


import html


def normalize_category_name(name: str) -> str:
    """
    Normalizes category/subcategory name for exact, case-insensitive comparison:
    - Decodes HTML entities (e.g. &amp; -> &)
    - Strips HTML tags (<[^>]+>)
    - Replaces non-breaking spaces (\u00a0) with standard space
    - Strips zero-width and invisible characters
    - Strips leading/trailing tree-expander symbols (+, bullets, dashes)
    - Collapses multiple whitespace characters to a single space
    - Case-folds to lower
    """
    if not name:
        return ""
    text = html.unescape(str(name))
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    # Normalize unicode apostrophes, single quotes, quotes and dashes
    text = re.sub(r"[\u2018\u2019\u201a\u201b\u2032\u0060\u00b4]", "'", text)
    text = re.sub(r"[\u201c\u201d\u201e\u201f]", '"', text)
    text = re.sub(r"[\u2013\u2014]", "-", text)
    # Strip leading/trailing expansion markers like '+', '-', ':', '.'
    text = re.sub(r"^[\s\+\u2795\u2796\u2022\-\:\.]+", "", text)
    text = re.sub(r"[\s\+\u2795\u2796\u2022\-\:\.]+$", "", text)
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned.lower()


def match_category(requested_category: str, existing_categories: List[str]) -> Optional[str]:
    """
    Finds exact normalized match of requested_category in existing_categories list.
    Returns the original casing of the matched category if found, else None.
    """
    req_norm = normalize_category_name(requested_category)
    for cat in existing_categories:
        if normalize_category_name(cat) == req_norm:
            return cat
    return None


def match_subcategory(
    requested_subcategory: str,
    parent_category: str,
    category_tree: Dict[str, List[str]]
) -> Optional[str]:
    """
    Verifies that requested_subcategory exists under parent_category in category_tree.
    Returns original casing of matched subcategory, else None.
    """
    matched_parent = match_category(parent_category, list(category_tree.keys()))
    if not matched_parent:
        return None

    subcategories = category_tree.get(matched_parent, [])
    req_sub_norm = normalize_category_name(requested_subcategory)
    for sub in subcategories:
        if normalize_category_name(sub) == req_sub_norm:
            return sub
    return None


def build_dry_run_plan(
    items: List[ActionPointItem],
    existing_categories: List[str],
    category_tree: Dict[str, List[str]],
    portal_items_by_code: Optional[Dict[str, Dict[str, Any]]] = None,
    restaurant_available: bool = True
) -> Tuple[List[ItemExecutionResult], Dict[str, Any]]:
    """
    Constructs a deterministic dry-run plan mapping every source row to its projected outcome.
    Validates categories, subcategories, item codes, and restaurant readiness without mutations.
    """
    results: List[ItemExecutionResult] = []
    planned_categories_to_create: Set[str] = set()
    planned_subcategories_to_create: Set[str] = set()
    verified_subcategories: Set[str] = set()
    unresolved_subcategories: Set[str] = set()

    for item in items:
        res = ItemExecutionResult(
            row_number=item.row_number,
            item_code=item.item_code,
            item_name=item.item_name,
            requested_category=item.category,
            requested_subcategory=item.subcategory,
            original_status=item.original_status,
            classification=item.classification,
            status=ActionPointStatusEnum.DRY_RUN
        )

        # 1. Invalid Row Check
        if not item.is_valid:
            res.status = ActionPointStatusEnum.FAILED
            res.failure_reason = "; ".join(item.validation_errors)
            results.append(res)
            continue

        # 2. Unsupported Status Check
        if item.classification == ActionClassification.UNSUPPORTED_STATUS:
            res.status = ActionPointStatusEnum.SKIPPED_UNSUPPORTED_STATUS
            res.failure_reason = f"Unsupported status '{item.original_status}'. Only 'Category Update' is configured."
            results.append(res)
            continue

        # 3. Category Update Classification
        matched_cat = match_category(item.category, existing_categories)
        if matched_cat:
            res.category_created = False
        else:
            # Planned category creation
            planned_categories_to_create.add(item.category.strip())
            res.category_created = True

        # Check subcategory (only when provided)
        has_subcat = bool(item.subcategory and str(item.subcategory).strip() and str(item.subcategory).strip().lower() not in ("-", "none", "nan", "n/a", "null", ""))
        if has_subcat:
            matched_sub = match_subcategory(item.subcategory, item.category, category_tree)
            if matched_sub:
                res.subcategory_verified = True
                verified_subcategories.add(f"{item.category} -> {item.subcategory}")
            else:
                # Subcategory missing under parent category
                res.subcategory_verified = False
                unresolved_subcategories.add(f"{item.category} -> {item.subcategory}")
                planned_subcategories_to_create.add(f"{item.category} -> {item.subcategory}")
                # If category will be created brand new or subcategory is missing,
                # note that subcategory cannot be verified
                if not matched_cat:
                    res.status = ActionPointStatusEnum.BLOCKED
                    res.failure_reason = f"Category '{item.category}' must be created first; subcategory '{item.subcategory}' is unverified."
                else:
                    res.status = ActionPointStatusEnum.BLOCKED
                    res.failure_reason = f"BLOCKED — Subcategory '{item.subcategory}' does not exist under category '{item.category}'."
        else:
            # Category has no subcategory; verify category-only directly
            res.subcategory_verified = True

        # Check Restaurant
        if not restaurant_available:
            res.restaurant_verified = False
            if res.status != ActionPointStatusEnum.BLOCKED:
                res.status = ActionPointStatusEnum.BLOCKED
                res.failure_reason = "BLOCKED — Restaurant 'IRD - DEFAULT' was not detected in portal."
        else:
            res.restaurant_verified = True

        # Check Item in Portal (if item dictionary provided during dry run)
        if portal_items_by_code is not None:
            portal_match = portal_items_by_code.get(item.item_code)
            if portal_match:
                res.item_found = True
                portal_name = portal_match.get("name", "")
                if normalize_category_name(portal_name) != normalize_category_name(item.item_name):
                    logger.warning(
                        f"Row {item.row_number}: Item Code '{item.item_code}' name mismatch: "
                        f"File '{item.item_name}' vs Portal '{portal_name}'"
                    )
            else:
                res.item_found = False
                res.status = ActionPointStatusEnum.FAILED
                res.failure_reason = f"FAILED — Item Code '{item.item_code}' not found in portal."

        if res.status == ActionPointStatusEnum.DRY_RUN and not res.failure_reason:
            res.failure_reason = "Dry run validated. Ready for live execution."

        results.append(res)

    plan_summary = {
        "total_items": len(results),
        "valid_items": sum(1 for r in results if r.status in (ActionPointStatusEnum.DRY_RUN, ActionPointStatusEnum.SUCCESS)),
        "blocked_items": sum(1 for r in results if r.status == ActionPointStatusEnum.BLOCKED),
        "skipped_items": sum(1 for r in results if r.status == ActionPointStatusEnum.SKIPPED_UNSUPPORTED_STATUS),
        "failed_items": sum(1 for r in results if r.status == ActionPointStatusEnum.FAILED),
        "categories_to_create": sorted(list(planned_categories_to_create)),
        "subcategories_to_create": sorted(list(planned_subcategories_to_create)),
        "verified_subcategories": sorted(list(verified_subcategories)),
        "unresolved_subcategories": sorted(list(unresolved_subcategories))
    }

    return results, plan_summary
