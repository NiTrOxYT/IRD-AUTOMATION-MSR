import os
import csv
import logging
from typing import Dict, Any, List, Tuple
from pathlib import Path

logger = logging.getLogger("IRD_CSVAnalyzer")

ENCODINGS_TO_TRY = ["utf-8-sig", "utf-8", "cp1252", "latin-1", "iso-8859-1"]

def analyze_action_point_csv(file_path: str) -> Dict[str, Any]:
    """
    Reads downloaded CSV file safely using encoding fallbacks.
    Inspects line 3 (1-indexed, index 2).
    If line 3 contains 'No Action Point' -> NO ACTION POINT.
    Else -> ACTION POINT FOUND.
    """
    path = Path(file_path)
    if not path.exists():
        logger.error(f"CSV file does not exist: {file_path}")
        return {
            "status": "FAILED",
            "action_point_status": "FAILED",
            "third_line": "",
            "all_lines": [],
            "error": "CSV file missing"
        }

    lines: List[str] = []
    successful_encoding = None

    for enc in ENCODINGS_TO_TRY:
        try:
            with open(path, "r", encoding=enc, errors="replace") as f:
                lines = [line.strip() for line in f.readlines()]
                successful_encoding = enc
                break
        except Exception as ex:
            logger.debug(f"Failed opening CSV with encoding {enc}: {ex}")
            continue

    if not lines:
        logger.warning(f"CSV file is empty or could not be read: {file_path}")
        return {
            "status": "COMPLETED",
            "action_point_status": "NO ACTION POINT",
            "third_line": "<Empty File>",
            "all_lines": [],
            "error": "CSV file empty"
        }

    third_line = ""
    if len(lines) >= 3:
        third_line = lines[2].strip()
    elif len(lines) > 0:
        third_line = lines[-1].strip()

    # Clean quotes/commas from line 3 text if CSV formatted
    cleaned_third_line = third_line.replace('"', '').replace("'", "").strip()

    logger.info(f"Inspected CSV '{path.name}' (encoding: {successful_encoding}). Line 3 content: '{cleaned_third_line}'")

    if "no action point" in cleaned_third_line.lower():
        result_status = "NO ACTION POINT"
    else:
        result_status = "ACTION POINT FOUND"

    return {
        "status": "COMPLETED",
        "action_point_status": result_status,
        "third_line": cleaned_third_line,
        "first_3_lines": lines[:3],
        "encoding": successful_encoding,
        "error": ""
    }
