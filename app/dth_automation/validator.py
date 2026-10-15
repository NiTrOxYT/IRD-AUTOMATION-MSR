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


def infer_category_from_name(
    channel_name: Optional[str],
    allowed_categories: Optional[List[str]] = None
) -> str:
    """
    Intelligently infers a single relevant portal category from channel name.
    Ensures channels always get a relevant genre matching portal options.
    """
    name_clean = (channel_name or "").lower().strip()

    genre_keywords = [
        ("Sports", ["sport", "cricket", "football", "fifa", "espn", "ten ", "ten1", "ten2", "ten3", "sony ten", "star sports", "dd sports"]),
        ("News", ["news", "aaj tak", "samachar", "cnn", "bbc", "ndtv", "zee news", "republic", "times now", "abp", "cnbc", "wion", "dd news", "india today"]),
        ("Movies", ["cinema", "movie", "film", "max", "gold", "star gold", "zee cinema", "action", "hbo", "wb", "pictures", "talkies", "fliks", "flix"]),
        ("Music", ["music", "mtv", "zoom", "vh1", "b4u music", "9xm", "9x jalwa", "mastiii", "zing", "mtv beats", "b4u"]),
        ("Kids", ["kids", "cartoon", "pogo", "nick", "disney", "hungama", "sonic", "animax", "baby", "discovery kids", "junior"]),
        ("Infotainment", ["discovery", "nat geo", "geog", "history", "animal planet", "tlc", "sci", "investigation"]),
        ("Lifestyle", ["lifestyle", "food", "cook", "travel", "fox life", "fashion", "living", "care"]),
        ("Religious", ["bhakti", "divya", "aastha", "sadhna", "sanskar", "peace", "islam", "god", "shikhar", "darshan", "vrinda", "arihant"]),
        ("Regional", ["bengali", "bangla", "tamil", "telugu", "kannada", "malayalam", "marathi", "punjabi", "gujarati", "odia", "bhojpuri", "urdu", "kavya", "sun"]),
        ("Entertainment", ["tv", "plus", "colors", "sony", "star plus", "zee tv", "sab", "dangal", "bindass", "gemini", "etv", "asianet", "surya", "vijay"])
    ]

    for genre, keywords in genre_keywords:
        if any(kw in name_clean for kw in keywords):
            if allowed_categories:
                match = next((c for c in allowed_categories if c.lower() == genre.lower()), None)
                if match:
                    return match
            return genre

    # Default fallback
    if allowed_categories:
        for fallback in ["General", "Entertainment", "News", "Movies"]:
            match = next((c for c in allowed_categories if c.lower() == fallback.lower()), None)
            if match:
                return match
        non_all = [c for c in allowed_categories if c.lower() != "all"]
        if non_all:
            return non_all[0]

    return "General"


def normalize_categories(
    raw_categories_str: Optional[str],
    allowed_categories: Optional[List[str]] = None,
    single_category_only: bool = False,
    channel_name: Optional[str] = None
) -> Tuple[List[str], List[str]]:
    """
    Business Rule: Every channel must be assigned to 'all' plus the relevant category.
    When single_category_only=True: strictly ensures 'all' and only ONE other relevant category.
    1. Normalize category names.
    2. Always include 'all'.
    3. Add requested categories (or single most relevant category if single_category_only=True).
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
        if "all" not in allowed_map:
            allowed_map["all"] = "all"

    final_categories: List[str] = ["all"]
    seen_lower: Set[str] = {"all"}

    non_all_tokens = [tok for tok in category_tokens if tok.lower() != "all"]

    if single_category_only:
        # User requirement: Automation must only select 'all' and ONLY ONE other relevant category
        chosen_cat: Optional[str] = None

        # 1. Try to pick first matching token against allowed portal categories
        for token in non_all_tokens:
            tok_lower = token.lower()
            if allowed_map is not None:
                if tok_lower in allowed_map:
                    chosen_cat = allowed_map[tok_lower]
                    break
            else:
                chosen_cat = token
                break

        # 2. If no valid token found yet, check if there was an unknown category specified
        if not chosen_cat and non_all_tokens:
            first_tok = non_all_tokens[0]
            if allowed_map is not None and first_tok.lower() not in allowed_map:
                errors.append(f"Unknown portal category '{first_tok}'. Available: {', '.join(allowed_categories or [])}")
            chosen_cat = first_tok

        # 3. If no non-all category specified in file, infer from channel name
        if not chosen_cat and channel_name:
            chosen_cat = infer_category_from_name(channel_name, allowed_categories)

        if chosen_cat and chosen_cat.lower() != "all":
            final_categories.append(chosen_cat)
    else:
        # Standard multi-category preservation
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
                    errors.append(f"Unknown portal category '{token}'. Available: {', '.join(allowed_categories or [])}")
            else:
                if tok_lower not in seen_lower:
                    seen_lower.add(tok_lower)
                    final_categories.append(token)

    return final_categories, errors


def resolve_image_path(
    image_name: Optional[str] = None,
    image_dir: Optional[str] = None,
    channel_name: Optional[str] = None,
    channel_number: Optional[str] = None
) -> Tuple[Optional[str], List[str]]:
    """
    Safely resolves image path within logo directory.
    Uses ChannelLogoMatcher to check and select the correct logo based on:
    - Exact channel name, HD/SD alignment, regional language, and number precision.
    - Rejects path traversal, arbitrary filesystem access, and external URLs.
    """
    errors: List[str] = []
    from app.config import CHANNEL_LOGOS_DIR
    target_image_dir = image_dir if image_dir else str(CHANNEL_LOGOS_DIR)

    raw_clean = (image_name or "").strip()

    # Reject external URLs
    if raw_clean and re.match(r"^https?://", raw_clean, re.IGNORECASE):
        return None, [f"Remote URL not allowed for channel image: '{raw_clean}'."]

    # Check image extension if provided
    if raw_clean:
        ext = Path(raw_clean).suffix.lower()
        if ext and ext not in VALID_IMAGE_EXTENSIONS:
            return None, [f"Unsupported image extension '{ext}'. Allowed: {', '.join(sorted(VALID_IMAGE_EXTENSIONS))}."]

    base_path = Path(target_image_dir).resolve()
    if not base_path.exists() or not base_path.is_dir():
        return None, [f"Selected image directory does not exist or is not a directory: '{target_image_dir}'."]

    # Direct filename check if raw_clean provided
    if raw_clean:
        try:
            target_path = (base_path / raw_clean).resolve()
            if not target_path.is_relative_to(base_path):
                return None, [f"Path traversal detected in image filename '{raw_clean}'."]
            if target_path.exists() and target_path.is_file():
                from app.dth_automation.logo_matcher import logo_matcher
                if channel_name:
                    ch_hd = logo_matcher.is_hd(channel_name)
                    file_hd = logo_matcher.is_hd(target_path.name)
                    if ch_hd == file_hd:
                        return str(target_path), []
                    # HD mismatch: use logo matcher to find correct HD or SD variant
                    best_p, _, score, _ = logo_matcher.find_best_logo(
                        channel_name=channel_name,
                        channel_number=channel_number,
                        image_hint=raw_clean,
                        logo_dir=str(base_path)
                    )
                    if best_p and score > 0:
                        return best_p, []
                return str(target_path), []
        except Exception as e:
            return None, [f"Invalid image path '{raw_clean}': {str(e)}."]

    # Intelligent logo selection using ChannelLogoMatcher
    if channel_name and channel_name.strip():
        from app.dth_automation.logo_matcher import logo_matcher
        best_p, best_fn, score, rationale = logo_matcher.find_best_logo(
            channel_name=channel_name,
            channel_number=channel_number,
            image_hint=raw_clean,
            logo_dir=str(base_path)
        )
        if best_p and score > 0:
            return best_p, []

    if raw_clean:
        return None, [f"Image file not found: '{raw_clean}' in '{target_image_dir}'."]

    if not channel_name:
        return None, ["Image filename is required."]

    return None, []


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

        # 3. Category validation & mandatory 'all' + exactly one relevant category enforcement
        categories, cat_errors = normalize_categories(
            raw_cats,
            allowed_categories=portal_categories,
            single_category_only=True,
            channel_name=ch_name
        )
        if cat_errors:
            row_errors.extend(cat_errors)

        # 4. Image path resolution with intelligent logo selection
        resolved_img, img_errors = resolve_image_path(
            image_name=image,
            image_dir=image_dir,
            channel_name=ch_name,
            channel_number=ch_num
        )
        if img_errors:
            row_errors.extend(img_errors)

        effective_image_name = Path(resolved_img).name if resolved_img else image

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
            osd=osd or ch_name,
            image=effective_image_name,
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
