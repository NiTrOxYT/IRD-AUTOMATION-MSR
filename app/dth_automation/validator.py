import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Set, Optional

from app.dth_automation.models import (
    ChannelItem,
    ChannelValidationResult,
    DthItemState,
    DthBatchValidationResponse
)

logger = logging.getLogger("DTH_Validator")

VALID_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

DEFAULT_PORTAL_CATEGORIES = [
    "all",
    "Entertainment",
    "News",
    "Sports",
    "Movies",
    "Music",
    "Kids",
    "Infotainment",
    "Lifestyle",
    "Regional",
    "Religious",
    "General"
]


def normalize_categories(raw_categories_str: str, allowed_categories: Optional[List[str]] = None) -> Tuple[List[str], List[str]]:
    """
    Business Rule 5: Every channel must be assigned to 'all' plus the categories explicitly requested.
    1. Normalize category names.
    2. Always include 'all'.
    3. Add all requested categories.
    4. Deduplicate categories case-insensitively.
    5. Verify requested category names against actual portal options if provided.
    Returns: (final_categories_list, errors_list)
    """
    errors: List[str] = []
    category_tokens = [c.strip() for c in re.split(r"[,;|]+", raw_categories_str or "") if c.strip()]

    # Normalize allowed categories mapping if provided
    allowed_map: Optional[Dict[str, str]] = None
    if allowed_categories:
        allowed_map = {c.strip().lower(): c.strip() for c in allowed_categories if c.strip()}
        # Always ensure 'all' is an allowed category
        if "all" not in allowed_map:
            allowed_map["all"] = "all"

    final_categories: List[str] = ["all"]
    seen_lower: Set[str] = {"all"}

    for token in category_tokens:
        tok_lower = token.lower()
        if tok_lower == "all":
            continue

        if allowed_map is not None:
            if tok_lower in allowed_map:
                c_name = allowed_map[tok_lower]
                if tok_lower not in seen_lower:
                    seen_lower.add(tok_lower)
                    final_categories.append(c_name)
            else:
                errors.append(f"Unknown portal category '{token}'. Available: {', '.join(allowed_categories)}")
        else:
            if tok_lower not in seen_lower:
                seen_lower.add(tok_lower)
                final_categories.append(token)

    return final_categories, errors


def resolve_image_path(image_name: str, image_dir: Optional[str]) -> Tuple[Optional[str], List[str]]:
    """
    Safely resolves image path within explicitly selected image directory.
    Rejects path traversal, arbitrary filesystem access, external URLs, and missing files.
    """
    errors: List[str] = []
    if not image_name or not image_name.strip():
        return None, ["Image filename is required."]

    raw_clean = image_name.strip()

    # Reject external URLs
    if re.match(r"^https?://", raw_clean, re.IGNORECASE):
        return None, [f"Remote URL not allowed for channel image: '{raw_clean}'."]

    # Check image extension
    ext = Path(raw_clean).suffix.lower()
    if ext not in VALID_IMAGE_EXTENSIONS:
        return None, [f"Unsupported image extension '{ext}'. Allowed: {', '.join(sorted(VALID_IMAGE_EXTENSIONS))}."]

    if not image_dir:
        # Image dir not configured yet; return unverified relative name
        return None, []

    base_path = Path(image_dir).resolve()
    if not base_path.exists() or not base_path.is_dir():
        return None, [f"Selected image directory does not exist or is not a directory: '{image_dir}'."]

    try:
        # Check for path traversal or escaping base_path
        target_path = (base_path / raw_clean).resolve()
        if not target_path.is_relative_to(base_path):
            return None, [f"Path traversal detected in image filename '{raw_clean}'."]
    except Exception as e:
        return None, [f"Invalid image path '{raw_clean}': {str(e)}."]

    if not target_path.exists():
        return None, [f"Image file not found: '{raw_clean}' in '{image_dir}'."]

    if not target_path.is_file():
        return None, [f"Image target is not a valid file: '{raw_clean}'."]

    return str(target_path), []


def validate_channel_batch(
    raw_records: List[Dict[str, Any]],
    image_dir: Optional[str] = None,
    portal_categories: Optional[List[str]] = None,
    portal_existing_channel_numbers: Optional[Set[str]] = None,
    portal_existing_channel_names: Optional[Set[str]] = None
) -> Tuple[List[ChannelItem], List[ChannelValidationResult]]:
    """
    Executes preflight validation on channel records:
    - Enforces required fields (channel_number, name, osd, image)
    - Detects within-file duplicate channel numbers and names
    - Validates category tokens and enforces mandatory 'all'
    - Resolves and verifies image paths safely
    - Flags portal duplicates as SKIPPED_DUPLICATE
    """
    items: List[ChannelItem] = []
    results: List[ChannelValidationResult] = []

    seen_file_channel_numbers: Dict[str, int] = {}
    seen_file_channel_names: Dict[str, int] = {}

    existing_nums = portal_existing_channel_numbers or set()
    existing_names = portal_existing_channel_names or set()

    for rec in raw_records:
        row_num = rec.get("row_number", 0)
        ch_num = str(rec.get("channel_number", "")).strip()
        ch_name = str(rec.get("name", "")).strip()
        osd = str(rec.get("osd", "")).strip()
        image = str(rec.get("image", "")).strip()
        raw_cats = str(rec.get("raw_categories", "")).strip()

        row_errors: List[str] = []
        row_warnings: List[str] = []

        # 1. Field presence and format validation
        if not ch_num:
            row_errors.append("Channel number is required.")
        elif not re.match(r"^[0-9a-zA-Z\-_]+$", ch_num):
            row_errors.append(f"Channel number '{ch_num}' contains invalid characters.")

        if not ch_name:
            row_errors.append("Channel name is required.")
        elif len(ch_name) > 100:
            row_errors.append(f"Channel name exceeds 100 characters ({len(ch_name)} chars).")

        if not osd:
            row_errors.append("OSD name is required.")
        elif len(osd) > 50:
            row_errors.append(f"OSD name exceeds 50 characters ({len(osd)} chars).")

        # 2. File duplicate detection
        if ch_num:
            num_key = ch_num.lower()
            if num_key in seen_file_channel_numbers:
                prev_row = seen_file_channel_numbers[num_key]
                row_errors.append(f"Duplicate channel number '{ch_num}' in file (previously seen on row {prev_row}).")
            else:
                seen_file_channel_numbers[num_key] = row_num

        if ch_name:
            name_key = ch_name.lower()
            if name_key in seen_file_channel_names:
                prev_row = seen_file_channel_names[name_key]
                row_warnings.append(f"Duplicate channel name '{ch_name}' in file (previously seen on row {prev_row}).")
            else:
                seen_file_channel_names[name_key] = row_num

        # 3. Category validation & mandatory 'all' enforcement
        categories, cat_errors = normalize_categories(raw_cats, portal_categories)
        if cat_errors:
            row_errors.extend(cat_errors)

        # 4. Image path resolution
        resolved_img, img_errors = resolve_image_path(image, image_dir)
        if img_errors:
            row_errors.extend(img_errors)

        # 5. Determine State
        status = DthItemState.READY
        if row_errors:
            status = DthItemState.INVALID
        else:
            # Check portal duplicate (CREATE ONLY policy)
            if ch_num.lower() in {str(n).lower() for n in existing_nums}:
                status = DthItemState.SKIPPED_DUPLICATE
                row_warnings.append(f"Channel number '{ch_num}' already exists in portal. Marked SKIPPED_DUPLICATE.")
            elif ch_name.lower() in {str(n).lower() for n in existing_names}:
                status = DthItemState.SKIPPED_DUPLICATE
                row_warnings.append(f"Channel name '{ch_name}' already exists in portal. Marked SKIPPED_DUPLICATE.")

        channel_item = ChannelItem(
            row_number=row_num,
            channel_number=ch_num,
            name=ch_name,
            osd=osd,
            image=image,
            categories=categories,
            raw_categories=raw_cats,
            resolved_image_path=resolved_img
        )
        items.append(channel_item)

        results.append(ChannelValidationResult(
            row_number=row_num,
            channel_number=ch_num,
            name=ch_name,
            status=status,
            errors=row_errors,
            warnings=row_warnings,
            resolved_categories=categories,
            resolved_image_path=resolved_img
        ))

    return items, results
