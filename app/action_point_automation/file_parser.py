import os
import csv
import io
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Set

import openpyxl

from app.action_point_automation.models import (
    ActionPointItem,
    ActionClassification,
    FileValidationSummary
)

logger = logging.getLogger("ActionPoint_FileParser")

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit
MAX_ROW_COUNT = 5000                   # 5,000 items max per batch
ALLOWED_EXTENSIONS = {".csv", ".xlsx"}

REQUIRED_CANONICAL_COLUMNS = [
    "item_name",
    "item_code",
    "item_price",
    "category",
    "status"
]

OPTIONAL_CANONICAL_COLUMNS = [
    "sub_category"
]

ALL_CANONICAL_COLUMNS = REQUIRED_CANONICAL_COLUMNS + OPTIONAL_CANONICAL_COLUMNS

HEADER_ALIASES: Dict[str, List[str]] = {
    "item_name": ["item_name", "itemname", "item_title", "food_item_name", "food_name", "item"],
    "item_code": ["item_code", "itemcode", "code", "item_id", "food_code", "product_code"],
    "item_price": ["item_price", "itemprice", "price", "rate", "cost", "amount"],
    "category": ["category", "food_category", "parent_category", "main_category"],
    "sub_category": ["sub_category", "subcategory", "sub_cat", "subcat", "food_subcategory"],
    "status": ["status", "action", "action_status", "operation"]
}


def _normalize_header_string(header: Any) -> str:
    """Cleans and standardizes raw header string for alias matching."""
    if header is None:
        return ""
    # Strip whitespace, lower-case, replace spaces/hyphens with underscore
    text = str(header).strip().lower()
    text = re.sub(r"[\s\-]+", "_", text)
    # Match against canonical and aliases
    for canonical, aliases in HEADER_ALIASES.items():
        if text == canonical or text in aliases:
            return canonical
    return text


def _clean_cell_value(val: Any) -> str:
    """Stringifies cell value preserving formatting as faithfully as possible."""
    if val is None:
        return ""
    # If openpyxl gave float like 101.0 that was an integer, convert to '101'
    if isinstance(val, float) and val.is_integer():
        return str(int(val)).strip()
    return str(val).strip()


def validate_headers(headers: List[str]) -> Tuple[Dict[str, int], List[str]]:
    """
    Validates that all required headers are present, without duplicates or ambiguities.
    Returns: (mapping of canonical_name -> column_index, list_of_header_errors)
    """
    errors: List[str] = []
    canonical_map: Dict[str, int] = {}
    seen_canonical: Dict[str, List[int]] = {}

    for idx, raw_h in enumerate(headers):
        if not raw_h or not str(raw_h).strip():
            continue
        canon = _normalize_header_string(raw_h)
        if canon in ALL_CANONICAL_COLUMNS:
            if canon not in seen_canonical:
                seen_canonical[canon] = []
            seen_canonical[canon].append(idx)

    # Check for missing required columns
    for req in REQUIRED_CANONICAL_COLUMNS:
        if req not in seen_canonical:
            friendly = req.replace("_", " ").title()
            errors.append(f"Missing required header: '{friendly}' (expected column: '{req}')")

    # Check for duplicates across all recognized canonical columns
    for canon, indices in seen_canonical.items():
        if len(indices) > 1:
            errors.append(f"Ambiguous or duplicate header for '{canon}': found at columns {indices}")
        else:
            canonical_map[canon] = indices[0]

    return canonical_map, errors


def parse_action_point_file(file_path: str) -> Tuple[List[ActionPointItem], FileValidationSummary, List[str]]:
    """
    Parses a CSV or XLSX file, validates headers and rows, and classifies action points.
    Returns: (items, summary, structural_errors)
    """
    path = Path(file_path)
    if not path.exists():
        return [], FileValidationSummary(), [f"File not found: {file_path}"]

    ext = path.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return [], FileValidationSummary(), [f"Unsupported file format '{ext}'. Only .csv and .xlsx files are supported."]

    file_size = path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        return [], FileValidationSummary(), [f"File size exceeds 10MB limit ({file_size / (1024*1024):.2f}MB)."]

    if ext == ".csv":
        raw_rows, struct_errors = _read_csv_rows(path)
    else:
        raw_rows, struct_errors = _read_xlsx_rows(path)

    if struct_errors:
        return [], FileValidationSummary(), struct_errors

    if not raw_rows:
        return [], FileValidationSummary(), ["The uploaded file contains no data rows."]

    # Header validation
    header_row = raw_rows[0]
    header_col_map, header_errors = validate_headers(header_row)
    if header_errors:
        return [], FileValidationSummary(), header_errors

    data_rows = raw_rows[1:]
    if len(data_rows) > MAX_ROW_COUNT:
        return [], FileValidationSummary(), [f"File exceeds maximum allowed rows ({len(data_rows)} > {MAX_ROW_COUNT})."]

    items: List[ActionPointItem] = []
    seen_codes: Dict[str, List[int]] = {}
    valid_count = 0
    invalid_count = 0
    action_point_count = 0
    unsupported_status_count = 0
    categories_set: Set[str] = set()
    subcategories_set: Set[str] = set()

    for idx, row in enumerate(data_rows, start=2):
        # Skip completely blank rows
        if not any(str(c).strip() for c in row if c is not None):
            continue

        item_errors: List[str] = []

        def get_val(col_key: str) -> str:
            col_idx = header_col_map.get(col_key)
            if col_idx is not None and col_idx < len(row):
                return _clean_cell_value(row[col_idx])
            return ""

        raw_name = get_val("item_name")
        raw_code = get_val("item_code")
        raw_price = get_val("item_price")
        raw_category = get_val("category")
        raw_subcategory = get_val("sub_category")
        raw_status = get_val("status")

        # 1. Validate Item Name
        if not raw_name:
            item_errors.append("Item Name is required.")

        # 2. Validate Item Code (must preserve leading zeros)
        if not raw_code:
            item_errors.append("Item Code is required.")
        else:
            if raw_code not in seen_codes:
                seen_codes[raw_code] = []
            seen_codes[raw_code].append(idx)

        # 3. Validate Price (check valid numeric representation without mutating original string)
        if raw_price:
            cleaned_price = re.sub(r"^[₹$€£\s]+", "", raw_price).replace(",", "").strip()
            try:
                price_float = float(cleaned_price)
                if price_float < 0:
                    item_errors.append(f"Item Price cannot be negative ('{raw_price}').")
            except ValueError:
                item_errors.append(f"Item Price '{raw_price}' is not a valid numeric value.")
        else:
            item_errors.append("Item Price is required.")

        # 4. Validate Category
        if not raw_category:
            item_errors.append("Category is required.")
        else:
            categories_set.add(raw_category.strip())

        # 5. Validate Sub-Category (Optional: categories without subcategories are supported)
        clean_sub = ""
        if raw_subcategory and raw_subcategory.strip().lower() not in ("-", "none", "nan", "n/a", "null", ""):
            clean_sub = raw_subcategory.strip()
            subcategories_set.add(clean_sub)

        # 6. Normalize and Classify Status
        cleaned_status = re.sub(r"[\s_\-]+", " ", raw_status.strip().lower())
        normalized_status = cleaned_status
        if not raw_status.strip():
            item_errors.append("Status is required.")
            classification = ActionClassification.INVALID_DATA
        elif cleaned_status in (
            "category update",
            "category updated",
            "category updates",
            "update category",
            "updated category"
        ) or cleaned_status.startswith("category update") or cleaned_status.startswith("category updated"):
            classification = ActionClassification.CATEGORY_UPDATE
            action_point_count += 1
        else:
            classification = ActionClassification.UNSUPPORTED_STATUS
            unsupported_status_count += 1

        is_valid = len(item_errors) == 0
        if is_valid:
            valid_count += 1
        else:
            invalid_count += 1

        item = ActionPointItem(
            row_number=idx,
            item_code=raw_code,
            item_name=raw_name,
            item_price=raw_price,
            category=raw_category,
            subcategory=clean_sub,
            original_status=raw_status,
            normalized_status=normalized_status,
            classification=classification,
            is_valid=is_valid,
            validation_errors=item_errors
        )
        items.append(item)

    # Detect duplicate item codes in file
    duplicate_codes: List[str] = []
    for code, row_nums in seen_codes.items():
        if len(row_nums) > 1:
            duplicate_codes.append(code)
            # Annotate all rows that share this duplicate item code
            for item in items:
                if item.item_code == code:
                    item.is_valid = False
                    err_msg = f"Duplicate Item Code '{code}' found in source rows: {row_nums}"
                    if err_msg not in item.validation_errors:
                        item.validation_errors.append(err_msg)

    # Recalculate valid/invalid counts after duplicate marking
    valid_count = sum(1 for it in items if it.is_valid)
    invalid_count = sum(1 for it in items if not it.is_valid)

    summary = FileValidationSummary(
        total_rows=len(items),
        valid_rows=valid_count,
        invalid_rows=invalid_count,
        action_point_rows=action_point_count,
        unsupported_status_rows=unsupported_status_count,
        duplicate_item_codes=duplicate_codes,
        unique_categories=sorted(list(categories_set)),
        unique_subcategories=sorted(list(subcategories_set))
    )

    return items, summary, []


def _read_csv_rows(path: Path) -> Tuple[List[List[str]], List[str]]:
    encodings_to_try = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
    content: Optional[str] = None

    for enc in encodings_to_try:
        try:
            with open(path, "r", encoding=enc, errors="strict") as f:
                content = f.read()
                break
        except UnicodeDecodeError:
            continue
        except Exception as e:
            return [], [f"Failed to read CSV file: {str(e)}"]

    if content is None:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            return [], [f"Failed to decode CSV file: {str(e)}"]

    try:
        reader = csv.reader(io.StringIO(content))
        rows = [[cell.strip() for cell in r] for r in reader]
        return rows, []
    except Exception as e:
        return [], [f"Error parsing CSV content: {str(e)}"]


def _read_xlsx_rows(path: Path) -> Tuple[List[List[Any]], List[str]]:
    try:
        wb = openpyxl.load_workbook(filename=str(path), read_only=True, data_only=True)
        sheet = wb.active
        if not sheet:
            wb.close()
            return [], ["XLSX workbook has no active sheet."]

        rows: List[List[Any]] = []
        for r in sheet.iter_rows(values_only=True):
            # Convert None to empty string, keep strings and numbers
            row_vals = [_clean_cell_value(cell) if cell is not None else "" for cell in r]
            rows.append(row_vals)
        wb.close()
        return rows, []
    except Exception as e:
        return [], [f"Failed to open or read Excel file: {str(e)}"]
