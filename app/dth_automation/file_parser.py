import os
import csv
import io
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

import openpyxl

from app.dth_automation.models import ChannelItem

logger = logging.getLogger("DTH_FileParser")

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit
MAX_ROW_COUNT = 5000  # 5,000 channels max per batch

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}

COLUMN_ALIASES = {
    "channel_number": ["channel_number", "channel_no", "channel_num", "channel", "lcn", "ch_no"],
    "name": ["name", "channel_name", "title"],
    "osd": ["osd", "osd_name", "osd_text"],
    "image": ["image", "image_name", "image_file", "logo", "icon", "channel_logo"],
    "categories": ["categories", "category", "genre", "genres"]
}

REQUIRED_COLUMNS = ["channel_number", "name", "categories"]
OPTIONAL_COLUMNS = ["osd", "image"]


def _normalize_header(header: str) -> str:
    cleaned = str(header or "").strip().lower().replace(" ", "_").replace("-", "_")
    for canonical, aliases in COLUMN_ALIASES.items():
        if cleaned in aliases:
            return canonical
    return cleaned


def _clean_cell(val: Any) -> str:
    if val is None:
        return ""
    # Treat float like 101.0 from excel as 101
    if isinstance(val, float) and val.is_integer():
        return str(int(val)).strip()
    return str(val).strip()


def parse_dth_file(file_path: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Parses a CSV or XLSX file and extracts raw channel records.
    Returns: (records, structural_errors)
    Each record has keys: row_number, channel_number, name, osd, image, raw_categories.
    """
    path = Path(file_path)
    if not path.exists():
        return [], [f"File not found: {file_path}"]

    ext = path.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return [], [f"Unsupported file format '{ext}'. Only .csv and .xlsx files are supported."]

    file_size = path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        return [], [f"File size exceeds 10MB limit ({file_size / (1024*1024):.2f}MB)."]

    if ext == ".csv":
        return _parse_csv(path)
    elif ext == ".xlsx":
        return _parse_xlsx(path)
    return [], ["Unsupported format"]


def _parse_csv(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
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
        # Fallback with replacement
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            return [], [f"Failed to decode CSV file: {str(e)}"]

    reader = csv.reader(io.StringIO(content))
    rows = list(reader)

    if not rows:
        return [], ["CSV file is empty."]

    # First row is header
    raw_headers = rows[0]
    header_map = {}
    for idx, h in enumerate(raw_headers):
        canonical = _normalize_header(h)
        if canonical in COLUMN_ALIASES:
            header_map[canonical] = idx

    missing_headers = [col for col in REQUIRED_COLUMNS if col not in header_map]
    if missing_headers:
        return [], [f"Missing required columns in CSV header: {', '.join(missing_headers)}. Found headers: {raw_headers}"]

    records: List[Dict[str, Any]] = []
    data_rows = rows[1:]

    if len(data_rows) > MAX_ROW_COUNT:
        return [], [f"Row count exceeds maximum limit of {MAX_ROW_COUNT} rows (found {len(data_rows)} rows)."]

    for row_idx, row in enumerate(data_rows, start=2):
        # Skip completely empty rows
        if not any(c.strip() for c in row):
            continue

        def get_col(col_name: str) -> str:
            col_idx = header_map.get(col_name)
            if col_idx is not None and col_idx < len(row):
                return _clean_cell(row[col_idx])
            return ""

        name_val = get_col("name")
        osd_val = get_col("osd") or name_val

        records.append({
            "row_number": row_idx,
            "channel_number": get_col("channel_number"),
            "name": name_val,
            "osd": osd_val,
            "image": get_col("image"),
            "raw_categories": get_col("categories")
        })

    return records, []


def _parse_xlsx(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    try:
        wb = openpyxl.load_workbook(filename=str(path), read_only=True, data_only=True)
    except Exception as e:
        return [], [f"Failed to read XLSX workbook: {str(e)}"]

    sheet = wb.active
    if sheet is None:
        return [], ["XLSX workbook has no active worksheet."]

    rows_iter = sheet.iter_rows(values_only=True)
    try:
        raw_headers = next(rows_iter)
    except StopIteration:
        return [], ["XLSX worksheet is empty."]

    header_map = {}
    for idx, h in enumerate(raw_headers):
        if h is not None:
            canonical = _normalize_header(str(h))
            if canonical in COLUMN_ALIASES:
                header_map[canonical] = idx

    missing_headers = [col for col in REQUIRED_COLUMNS if col not in header_map]
    if missing_headers:
        return [], [f"Missing required columns in XLSX header: {', '.join(missing_headers)}. Found: {raw_headers}"]

    records: List[Dict[str, Any]] = []
    row_count = 0

    for row_idx, row in enumerate(rows_iter, start=2):
        row_count += 1
        if row_count > MAX_ROW_COUNT:
            wb.close()
            return [], [f"Row count exceeds maximum limit of {MAX_ROW_COUNT} rows."]

        # Check if row is empty
        if not row or not any(c is not None and str(c).strip() for c in row):
            continue

        def get_col(col_name: str) -> str:
            col_idx = header_map.get(col_name)
            if col_idx is not None and col_idx < len(row):
                return _clean_cell(row[col_idx])
            return ""

        name_val = get_col("name")
        osd_val = get_col("osd") or name_val

        records.append({
            "row_number": row_idx,
            "channel_number": get_col("channel_number"),
            "name": name_val,
            "osd": osd_val,
            "image": get_col("image"),
            "raw_categories": get_col("categories")
        })

    wb.close()
    return records, []
