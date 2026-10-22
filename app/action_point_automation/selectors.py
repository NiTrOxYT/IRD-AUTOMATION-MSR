"""
Selector Registry for IRD Action Point Configuration
Provides robust Playwright selectors with hierarchical fallbacks for
Food Category navigation, inspection, creation, and Food Item Configuration.
"""

from typing import List, Dict


class ActionPointSelectors:
    """Ordered lists of selectors with resilient fallbacks."""

    # --- 1. FOOD CATEGORY NAVIGATION ---
    NAV_FOOD_CATEGORY: List[str] = [
        "a:has-text('Food Category')",
        "button:has-text('Food Category')",
        "span:has-text('Food Category')",
        ".nav-link:has-text('Food Category')",
        "text='Food Category'"
    ]

    NAV_VIEW_FOOD_CATEGORY: List[str] = [
        "a:has-text('View Food Category')",
        "a:has-text('View Food Categories')",
        "button:has-text('View Food Category')",
        "span:has-text('View Food Category')",
        "text='View Food Category'"
    ]

    NAV_ADD_FOOD_CATEGORY: List[str] = [
        "a:has-text('Add Food Category')",
        "button:has-text('Add Food Category')",
        "span:has-text('Add Food Category')",
        "text='Add Food Category'"
    ]

    # --- 2. VIEW FOOD CATEGORY PAGE ---
    CATEGORY_TABLE_ROWS: List[str] = [
        "table tbody tr",
        ".table tbody tr",
        "#categoryTable tbody tr",
        ".category-list-item"
    ]

    CATEGORY_TABLE_PAGINATION_NEXT: List[str] = [
        "ul.pagination li.next:not(.disabled) a",
        "li.next:not(.disabled) a",
        ".pagination .next:not(.disabled) a",
        "#categoryTable_next:not(.disabled) a",
        "#categoryTable_next:not(.disabled)",
        ".paginate_button.next:not(.disabled)",
        "a[rel='next']",
        "a:has-text('Next')",
        "button:has-text('Next')",
        "a:has-text('>')",
        "a:has-text('»')",
        "li:not(.disabled) a:has-text('Next')"
    ]

    # Green circular plus icon at the beginning of the category row (to expand subcategories)
    CATEGORY_EXPAND_GREEN_PLUS_CONTROL: List[str] = [
        "td:first-child img[src*='plus']",
        "td:first-child i.fa-plus-circle",
        "td:first-child i.fa-plus",
        "td:first-child .expand-plus",
        "td:first-child button.expand",
        "td:first-child svg.plus-icon",
        "img[src*='plus']",
        "i.fa-plus-circle",
        "i.fa-plus",
        "span.expand-plus",
        "button.expand",
        ".tree-expander",
        "button:has-text('+')",
        "span:has-text('+')"
    ]

    # File-plus icon in the Operation column (to open subcategory creation form)
    CATEGORY_OPERATION_FILE_PLUS_CONTROL: List[str] = [
        "td:last-child img[onclick*='addSubFoodCategory']",
        "td:last-child img[src*='add.png']",
        "td:last-child img[title='Add']",
        "td:last-child span[onclick*='addSubFoodCategory']",
        "img[onclick*='addSubFoodCategory']",
        "span[onclick*='addSubFoodCategory']",
        "td:last-child a[title*='Sub']",
        "td:last-child a[title*='Add']",
        "td:last-child a:has(i.fa-file-plus)",
        "td:last-child a:has(i.fa-plus)",
        "td:last-child img[src*='add']",
        "td:last-child img[src*='file']",
        "td.operation a[title*='Sub']",
        "td.operation a[title*='Add']",
        "a[title*='Add Sub']",
        "a[title*='Sub Category']",
        "a[href*='subCategory']",
        "a[href*='addSub']",
        "i.fa-file-circle-plus",
        "i.fa-file-plus",
        "i.fa-plus-square",
        "button[title*='Sub']"
    ]

    # --- 3. ADD FOOD CATEGORY FORM ---
    ADD_CATEGORY_NAME_INPUT: List[str] = [
        "input[name='categoryName']",
        "input[name='category_name']",
        "input[name='name']",
        "#categoryName",
        "#name",
        "input[placeholder*='Category Name']",
        "input[placeholder*='category']",
        "input[type='text']"
    ]

    ADD_CATEGORY_DISPLAY_NAME_INPUT: List[str] = [
        "input[name='displayName']",
        "input[name='display_name']",
        "input[placeholder*='Display Name']",
        "#displayName"
    ]

    ADD_CATEGORY_IMAGE_INPUT: List[str] = [
        "input[type='file'][name*='image']",
        "input[type='file'][name*='category']",
        "input[name='categoryImage']",
        "#categoryImage",
        "#foodCategoryImage",
        "input[type='file']"
    ]

    ADD_CATEGORY_RESTAURANT_SELECT: List[str] = [
        "select[name*='restaurant']",
        "select[name='restaurantId']",
        "#restaurant",
        "#restaurantId",
        ".restaurant-select"
    ]

    ADD_CATEGORY_SAVE_BTN: List[str] = [
        "button:has-text('Save')",
        "input[value='Save']",
        "button[type='submit']:has-text('Save')",
        "button:has-text('Add')",
        "input[value='Add']",
        "#btnSave",
        "#saveCategory"
    ]

    ADD_CATEGORY_SUCCESS_NOTICE: List[str] = [
        ".alert-success",
        ".success-message",
        "text='saved successfully'",
        "text='Category added'",
        "text='Success'",
        ".toast-success"
    ]

    # --- 3B. ADD SUBCATEGORY FORM ---
    ADD_SUBCATEGORY_NAME_INPUT: List[str] = [
        "input[name='subCategoryName']",
        "input[name='sub_category_name']",
        "input[name='subcategoryName']",
        "input[name='name']",
        "#subCategoryName",
        "#name",
        "input[placeholder*='Sub Category']",
        "input[placeholder*='Sub-Category']",
        "input[type='text']"
    ]

    ADD_SUBCATEGORY_PARENT_CATEGORY_FIELD: List[str] = [
        "#parentCategory",
        "input[name*='parent']",
        "select[name*='category']",
        ".parent-category-display",
        "span.parent-category"
    ]

    ADD_SUBCATEGORY_IMAGE_INPUT: List[str] = [
        "input[type='file'][name*='image']",
        "input[type='file'][name*='subCategory']",
        "#subCategoryImage",
        "input[name='subCategoryImage']",
        "input[type='file']"
    ]

    ADD_SUBCATEGORY_SAVE_BTN: List[str] = [
        "button:has-text('Save')",
        "input[value='Save']",
        "button[type='submit']:has-text('Save')",
        "#btnSave",
        "#saveSubCategory"
    ]

    ADD_SUBCATEGORY_SUCCESS_NOTICE: List[str] = [
        ".alert-success",
        ".success-message",
        "text='Sub Category added'",
        "text='saved successfully'",
        "text='Success'",
        ".toast-success"
    ]

    # --- 4. FOOD ITEM CONFIGURATION NAVIGATION ---
    NAV_FOOD_ITEM_CONFIG: List[str] = [
        "a:has-text('Food Item Configuration')",
        "button:has-text('Food Item Configuration')",
        "span:has-text('Food Item Configuration')",
        ".nav-link:has-text('Food Item')",
        "text='Food Item Configuration'"
    ]

    NAV_ITEMS_CONFIG: List[str] = [
        "a:has-text('Items Configuration')",
        "a:has-text('Item Configuration')",
        "button:has-text('Items Configuration')",
        "span:has-text('Items Configuration')",
        "text='Items Configuration'"
    ]

    # --- 5. ITEMS CONFIGURATION PAGE ---
    # Search input field for Item Code
    ITEM_SEARCH_INPUT: List[str] = [
        "input[type='search']",
        ".dataTables_filter input",
        "input[aria-controls]",
        "input[name='search']",
        "input[placeholder*='Search']",
        "input[name*='code']",
        "#itemSearch",
        "#searchCode",
        "input.search-input"
    ]

    ITEM_SEARCH_BTN: List[str] = [
        "button:has-text('Search')",
        "input[type='button'][value='Search']",
        "input[type='submit'][value='Search']",
        "#btnSearch",
        "button.search-btn",
        ".dataTables_filter button"
    ]

    # Table of items returned from search
    ITEM_TABLE_ROWS: List[str] = [
        "table.items-table tbody tr",
        ".item-list tbody tr",
        "table tbody tr",
        "#itemsTable tbody tr"
    ]

    # Category selection container
    CATEGORY_SELECTION_PANEL: List[str] = [
        ".box:has-text('Food Category')",
        "#categoryPanel",
        ".category-panel",
        "#categorySelection",
        ".category-tree",
        "div:has-text('Selected item\\'s food category')",
        "div:has-text('Food Category')"
    ]

    # Restaurant selection container
    RESTAURANT_SELECTION_PANEL: List[str] = [
        ".box:has-text('Restaurant')",
        "#restaurantPanel",
        ".restaurant-panel",
        "#restaurantSelection",
        "div:has-text('Restaurant and wing')",
        "div:has-text('Restaurant')"
    ]

    # Target restaurant: IRD - DEFAULT
    RESTAURANT_IRD_DEFAULT_OPTION: List[str] = [
        "label:has-text('IRD - DEFAULT')",
        "input[value='IRD - DEFAULT']",
        "input[value*='IRD - DEFAULT']",
        "option:has-text('IRD - DEFAULT')",
        "span:has-text('IRD - DEFAULT')",
        "text='IRD - DEFAULT'"
    ]

    # Final Configure save button
    CONFIGURE_SAVE_BTN: List[str] = [
        "button:has-text('Configure')",
        "input[value='Configure']",
        "button[type='submit']:has-text('Configure')",
        "#btnConfigure",
        ".configure-btn",
        "button:has-text('Submit')"
    ]

    # Save confirmation
    CONFIGURE_SUCCESS_NOTICE: List[str] = [
        ".alert-success",
        ".success-message",
        "text='configured successfully'",
        "text='Configuration saved'",
        "text='Updated successfully'",
        ".toast-success"
    ]
