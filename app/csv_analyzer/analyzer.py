import os
import csv
import logging
from typing import Dict, Any, List, Tuple
from pathlib import Path

logger = logging.getLogger("IRD_CSVAnalyzer")

ENCODINGS_TO_TRY = ["utf-8-sig", "utf-8", "cp1252", "latin-1", "iso-8859-1"]

def is_header_or_title_record(rec_str: str) -> bool:
    s = rec_str.lower().strip()
    if s in ("no action point", "no action points"):
        return False
    if s in ("action points", "action point"):
        return True
    header_markers = ["restaurant name", "restaurant id", "item name", "item code", "item price", "category", "sub-category", "status"]
    matched = [m for m in header_markers if m in s]
    if len(matched) >= 3:
        return True
    return False

def analyze_action_point_csv(file_path: str) -> Dict[str, Any]:
    """
    Reads downloaded CSV file safely using encoding fallbacks.
    Inspects the 3RD LINE of the CSV file.
    If the 3rd line contains 'No Action Point' -> NO ACTION POINT (OK / CLEAR).
    Otherwise (anything other than 'No Action Point') -> ACTION POINT FOUND.
    """
    path = Path(file_path)
    if not path.exists():
        logger.error(f"CSV file does not exist: {file_path}")
        return {
            "status": "FAILED",
            "action_point_status": "FAILED",
            "first_3_lines": [],
            "third_line": "",
            "all_lines": [],
            "total_rows": 0,
            "error": "CSV file missing"
        }

    lines: List[str] = []
    rows: List[List[str]] = []
    successful_encoding = None

    for enc in ENCODINGS_TO_TRY:
        try:
            with open(path, "r", encoding=enc, errors="replace") as f:
                raw_content = f.read()
                lines = [l.strip() for l in raw_content.splitlines() if l.strip()]
                f.seek(0)
                reader = csv.reader(f)
                rows = [row for row in reader if row and any(cell.strip() for cell in row)]
                successful_encoding = enc
                break
        except Exception as ex:
            logger.debug(f"Failed opening CSV with encoding {enc}: {ex}")
            continue

    if not lines and not rows:
        logger.warning(f"CSV file is empty or could not be read: {file_path}")
        return {
            "status": "COMPLETED",
            "action_point_status": "NO ACTION POINT",
            "first_3_lines": [],
            "third_line": "<Empty File>",
            "all_lines": [],
            "total_rows": 0,
            "error": "CSV file empty"
        }

    raw_records = rows if rows else [[l] for l in lines]
    first_3_inspected = []

    for idx, rec in enumerate(raw_records[:3]):
        line_num = idx + 1
        rec_str = " ".join(rec).replace('"', '').replace("'", "").strip() if isinstance(rec, list) else str(rec).strip()
        
        if "no action point" in rec_str.lower():
            rec_status = "NO ACTION POINT"
        elif idx == 0 and "action point" in rec_str.lower():
            rec_status = "TITLE"
        elif idx == 1 and ("restaurant" in rec_str.lower() or "item" in rec_str.lower() or "status" in rec_str.lower()):
            rec_status = "HEADER"
        else:
            rec_status = "ACTION POINT FOUND"

        first_3_inspected.append({
            "line": line_num,
            "raw_text": rec_str,
            "status": rec_status
        })

    # Target 3rd line of the CSV file
    if len(raw_records) >= 3:
        third_rec = raw_records[2]
        third_line_text = " ".join(third_rec).replace('"', '').replace("'", "").strip() if isinstance(third_rec, list) else str(third_rec).strip()
    elif len(raw_records) > 0:
        third_rec = raw_records[-1]
        third_line_text = " ".join(third_rec).replace('"', '').replace("'", "").strip() if isinstance(third_rec, list) else str(third_rec).strip()
    else:
        third_line_text = ""

    # Check 3rd line rule: If 3rd line contains 'No Action Point' -> CLEAR (OK). Else -> ACTION POINT FOUND.
    if "no action point" in third_line_text.lower():
        overall_ap_status = "CLEAR"
        any_action_point_found = False
    else:
        overall_ap_status = "ACTION POINT FOUND"
        any_action_point_found = True

    logger.info(f"Inspected CSV '{path.name}' 3rd line: '{third_line_text}'. Result: {overall_ap_status}")

    return {
        "status": "COMPLETED",
        "action_point_status": overall_ap_status,
        "action_point_found": any_action_point_found,
        "first_3_lines": first_3_inspected,
        "third_line": third_line_text,
        "all_lines": lines,
        "total_rows": len(raw_records),
        "encoding": successful_encoding,
        "error": ""
    }
