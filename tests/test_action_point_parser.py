import os
import tempfile
import pytest
import openpyxl

from app.action_point_automation.file_parser import (
    parse_action_point_file,
    validate_headers,
    _normalize_header_string
)
from app.action_point_automation.models import ActionClassification


def test_normalize_header_string():
    assert _normalize_header_string("Item Name") == "item_name"
    assert _normalize_header_string("Item-Code") == "item_code"
    assert _normalize_header_string("  ITEM PRICE  ") == "item_price"
    assert _normalize_header_string("Sub-Category") == "sub_category"
    assert _normalize_header_string("Sub Category") == "sub_category"
    assert _normalize_header_string("Status") == "status"


def test_validate_headers_valid():
    headers = ["Item Name", "Item Code", "Item Price", "Category", "Sub-Category", "Status"]
    col_map, errors = validate_headers(headers)
    assert len(errors) == 0
    assert col_map["item_name"] == 0
    assert col_map["item_code"] == 1
    assert col_map["item_price"] == 2
    assert col_map["category"] == 3
    assert col_map["sub_category"] == 4
    assert col_map["status"] == 5


def test_validate_headers_missing_column():
    headers = ["Item Name", "Item Code", "Category", "Sub-Category", "Status"]
    col_map, errors = validate_headers(headers)
    assert len(errors) == 1
    assert "Missing required header" in errors[0]
    assert "Item Price" in errors[0]


def test_validate_headers_duplicate_column():
    headers = ["Item Name", "Item Code", "Item Price", "Category", "Sub-Category", "Status", "Code"]
    col_map, errors = validate_headers(headers)
    assert len(errors) == 1
    assert "Ambiguous or duplicate header for 'item_code'" in errors[0]


def test_parse_csv_valid_with_leading_zeros():
    csv_content = """Item Name,Item Code,Item Price,Category,Sub-Category,Status
Chicken Tikka,0042,450.00,Starters,Non-Veg Starters,Category Update
Paneer Tikka,0099,350.00,Starters,Veg Starters,Category Update
Cold Coffee,0105,180.00,Beverages,Cold Beverages,Active
"""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv_content)
        temp_path = f.name

    try:
        items, summary, struct_errors = parse_action_point_file(temp_path)
        assert len(struct_errors) == 0
        assert summary.total_rows == 3
        assert summary.action_point_rows == 2
        assert summary.unsupported_status_rows == 1
        assert summary.invalid_rows == 0

        # Check leading zeros preservation
        assert items[0].item_code == "0042"
        assert items[0].item_name == "Chicken Tikka"
        assert items[0].classification == ActionClassification.CATEGORY_UPDATE
        assert items[0].is_valid is True

        assert items[1].item_code == "0099"
        assert items[1].classification == ActionClassification.CATEGORY_UPDATE

        # Check unsupported status
        assert items[2].item_code == "0105"
        assert items[2].classification == ActionClassification.UNSUPPORTED_STATUS
        assert items[2].original_status == "Active"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_parse_csv_blank_rows_and_invalid_prices():
    csv_content = """Item Name,Item Code,Item Price,Category,Sub-Category,Status
Dal Makhani,0021,300,Mains,Veg Mains,Category Update
,,,,,
Butter Naan,0022,-50,Breads,Tandoori Breads,Category Update
Raita,0023,invalid_price,Sides,Accompaniments,Category Update
"""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv_content)
        temp_path = f.name

    try:
        items, summary, struct_errors = parse_action_point_file(temp_path)
        assert len(struct_errors) == 0
        # Blank row is skipped completely
        assert summary.total_rows == 3
        assert summary.valid_rows == 1
        assert summary.invalid_rows == 2

        # Item with negative price
        assert items[1].is_valid is False
        assert any("negative" in err.lower() for err in items[1].validation_errors)

        # Item with non-numeric price
        assert items[2].is_valid is False
        assert any("not a valid numeric value" in err.lower() for err in items[2].validation_errors)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_parse_csv_duplicate_item_codes():
    csv_content = """Item Name,Item Code,Item Price,Category,Sub-Category,Status
Soup 1,0088,150,Soups,Veg Soups,Category Update
Soup 2,0088,160,Soups,Veg Soups,Category Update
"""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv_content)
        temp_path = f.name

    try:
        items, summary, struct_errors = parse_action_point_file(temp_path)
        assert len(struct_errors) == 0
        assert summary.total_rows == 2
        assert summary.invalid_rows == 2
        assert "0088" in summary.duplicate_item_codes
        assert any("Duplicate Item Code '0088'" in err for err in items[0].validation_errors)
        assert any("Duplicate Item Code '0088'" in err for err in items[1].validation_errors)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_parse_xlsx_valid():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Item Name", "Item Code", "Item Price", "Category", "Sub-Category", "Status"])
    ws.append(["Fish Curry", "0077", 650.50, "Mains", "Coastal Seafood", "category update"])
    ws.append(["Steamed Rice", "0078", "200", "Rice", "Basmati", "Category Update "])

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        temp_path = f.name

    try:
        wb.save(temp_path)
        wb.close()

        items, summary, struct_errors = parse_action_point_file(temp_path)
        assert len(struct_errors) == 0
        assert summary.total_rows == 2
        assert summary.valid_rows == 2
        assert summary.action_point_rows == 2
        assert items[0].item_code == "0077"
        assert items[1].item_code == "0078"
        assert items[0].classification == ActionClassification.CATEGORY_UPDATE
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_parse_status_variations_category_updated():
    csv_content = """Item Name,Item Code,Item Price,Category,Sub-Category,Status
Pasta Marinara,149000001,1150.00,Artisan Pasta,Penne,Category Updated
Club Sandwich,148000014,1250.00,Sandwiches,Club,category_updated
Millet Porridge,103000024,625.00,Breakfast,Cereals,Category Updates
Shrimp Bowl,241000002,1895.00,Bowls,Asian,category update
Orange Juice,101000005,250.00,Beverages,Fresh Juice,Price Update
"""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv_content)
        temp_path = f.name

    try:
        items, summary, struct_errors = parse_action_point_file(temp_path)
        assert len(struct_errors) == 0
        assert summary.total_rows == 5
        assert summary.action_point_rows == 4
        assert summary.unsupported_status_rows == 1

        assert items[0].classification == ActionClassification.CATEGORY_UPDATE
        assert items[1].classification == ActionClassification.CATEGORY_UPDATE
        assert items[2].classification == ActionClassification.CATEGORY_UPDATE
        assert items[3].classification == ActionClassification.CATEGORY_UPDATE
        assert items[4].classification == ActionClassification.UNSUPPORTED_STATUS
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_parse_csv_items_without_subcategory():
    """Items without subcategory (blank, dash, None) should be valid and have empty subcategory."""
    csv_content = """Item Name,Item Code,Item Price,Category,Sub-Category,Status
Crown Royal,1010001,850.00,Canadian Whiskey,,Category Update
Jack Daniels,1010002,900.00,American Whiskey,-,Category Update
Wellness Bowl,1010003,550.00,Asian Wellness Box,None,Category Update
"""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv_content)
        temp_path = f.name

    try:
        items, summary, struct_errors = parse_action_point_file(temp_path)
        assert len(struct_errors) == 0
        assert summary.total_rows == 3
        assert summary.valid_rows == 3
        assert summary.invalid_rows == 0
        assert summary.action_point_rows == 3

        assert items[0].is_valid is True
        assert items[0].category == "Canadian Whiskey"
        assert items[0].subcategory == ""

        assert items[1].is_valid is True
        assert items[1].category == "American Whiskey"
        assert items[1].subcategory == ""

        assert items[2].is_valid is True
        assert items[2].category == "Asian Wellness Box"
        assert items[2].subcategory == ""
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_parse_csv_without_subcategory_header_column():
    """CSV file that omits the Sub-Category column completely is valid."""
    csv_content = """Item Name,Item Code,Item Price,Category,Status
Crown Royal,1010001,850.00,Canadian Whiskey,Category Update
Jim Beam,1010002,750.00,American Whiskey,Category Update
"""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv_content)
        temp_path = f.name

    try:
        items, summary, struct_errors = parse_action_point_file(temp_path)
        assert len(struct_errors) == 0
        assert summary.total_rows == 2
        assert summary.valid_rows == 2
        assert summary.invalid_rows == 0

        assert items[0].is_valid is True
        assert items[0].category == "Canadian Whiskey"
        assert items[0].subcategory == ""
        assert items[1].is_valid is True
        assert items[1].category == "American Whiskey"
        assert items[1].subcategory == ""
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

