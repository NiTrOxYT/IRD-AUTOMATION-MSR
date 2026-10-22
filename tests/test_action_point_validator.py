import pytest

from app.action_point_automation.validator import (
    normalize_category_name,
    match_category,
    match_subcategory,
    build_dry_run_plan
)
from app.action_point_automation.models import (
    ActionPointItem,
    ActionClassification,
    ActionPointStatusEnum
)


def test_normalize_category_name():
    assert normalize_category_name("  Food   Category  ") == "food category"
    assert normalize_category_name("STARTERS") == "starters"
    assert normalize_category_name("") == ""


def test_match_category_exact():
    existing = ["Starters", "Main Course", "Beverages", "Desserts"]
    assert match_category("starters", existing) == "Starters"
    assert match_category("  MAIN COURSE  ", existing) == "Main Course"
    assert match_category("Snacks", existing) is None


def test_match_subcategory_under_parent():
    tree = {
        "Starters": ["Veg Starters", "Non-Veg Starters"],
        "Beverages": ["Hot Beverages", "Cold Beverages"]
    }
    assert match_subcategory("veg starters", "Starters", tree) == "Veg Starters"
    assert match_subcategory("Cold Beverages", "beverages", tree) == "Cold Beverages"
    # Subcategory under wrong parent
    assert match_subcategory("Veg Starters", "Beverages", tree) is None
    # Subcategory does not exist anywhere
    assert match_subcategory("Mocktails", "Beverages", tree) is None


def test_build_dry_run_plan_comprehensive():
    items = [
        ActionPointItem(
            row_number=2,
            item_code="001",
            item_name="Spring Rolls",
            item_price="250",
            category="Starters",
            subcategory="Veg Starters",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        ),
        ActionPointItem(
            row_number=3,
            item_code="002",
            item_name="New Pizza",
            item_price="450",
            category="Italian",             # Missing category
            subcategory="Woodfired",        # Missing subcategory
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        ),
        ActionPointItem(
            row_number=4,
            item_code="003",
            item_name="Orange Juice",
            item_price="120",
            category="Beverages",
            subcategory="Fresh Juices",
            original_status="Price Update", # Unsupported status
            normalized_status="price update",
            classification=ActionClassification.UNSUPPORTED_STATUS,
            is_valid=True
        )
    ]

    existing_categories = ["Starters", "Beverages"]
    category_tree = {
        "Starters": ["Veg Starters", "Non-Veg Starters"],
        "Beverages": ["Fresh Juices", "Smoothies"]
    }

    results, summary = build_dry_run_plan(
        items=items,
        existing_categories=existing_categories,
        category_tree=category_tree,
        restaurant_available=True
    )

    assert summary["total_items"] == 3
    assert summary["valid_items"] == 1       # Row 2 (Starters -> Veg Starters)
    assert summary["blocked_items"] == 1     # Row 3 (Italian missing)
    assert summary["skipped_items"] == 1     # Row 4 (Price Update)
    assert "Italian" in summary["categories_to_create"]

    # Verify Row 2
    assert results[0].row_number == 2
    assert results[0].status == ActionPointStatusEnum.DRY_RUN
    assert results[0].subcategory_verified is True
    assert results[0].restaurant_verified is True

    # Verify Row 3
    assert results[1].row_number == 3
    assert results[1].status == ActionPointStatusEnum.BLOCKED
    assert "Italian" in results[1].failure_reason

    # Verify Row 4
    assert results[2].row_number == 4
    assert results[2].status == ActionPointStatusEnum.SKIPPED_UNSUPPORTED_STATUS
    assert "Unsupported status" in results[2].failure_reason


def test_build_dry_run_plan_missing_restaurant():
    items = [
        ActionPointItem(
            row_number=2,
            item_code="001",
            item_name="Soup",
            item_price="150",
            category="Starters",
            subcategory="Veg Starters",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        )
    ]
    results, summary = build_dry_run_plan(
        items=items,
        existing_categories=["Starters"],
        category_tree={"Starters": ["Veg Starters"]},
        restaurant_available=False  # IRD - DEFAULT unavailable
    )
    assert results[0].status == ActionPointStatusEnum.BLOCKED
    assert "IRD - DEFAULT" in results[0].failure_reason


def test_build_dry_run_plan_category_without_subcategory():
    """Items without a subcategory should be valid in dry-run without requiring subcategory creation."""
    items = [
        ActionPointItem(
            row_number=2,
            item_code="1010001",
            item_name="Canadian Whiskey 30ml",
            item_price="650",
            category="Canadian Whiskey",
            subcategory="",
            original_status="Category Update",
            normalized_status="category update",
            classification=ActionClassification.CATEGORY_UPDATE,
            is_valid=True
        )
    ]
    results, summary = build_dry_run_plan(
        items=items,
        existing_categories=["Canadian Whiskey"],
        category_tree={"Canadian Whiskey": []},
        restaurant_available=True
    )
    assert len(results) == 1
    assert results[0].status == ActionPointStatusEnum.DRY_RUN
    assert results[0].subcategory_verified is True
    assert results[0].restaurant_verified is True
    assert "Dry run validated" in results[0].failure_reason
    assert "Canadian Whiskey -> " not in summary.get("planned_subcategories_to_create", [])
