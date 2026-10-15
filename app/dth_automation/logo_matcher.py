import os
import re
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set

logger = logging.getLogger("DTH_LogoMatcher")

DEFAULT_CHANNEL_LOGOS_DIR = Path(r"C:\IRD AUTO\data\channel_logo")

REGIONAL_LANGUAGES = {
    "hindi", "tamil", "telugu", "telegu", "kannada", "malayalam",
    "marathi", "bengali", "bangla", "gujarati", "punjabi", "oriya",
    "odia", "bhojpuri", "urdu", "assamese", "nepali", "santhali"
}

GENERIC_CHANNEL_WORDS = {
    "tv", "channel", "television", "network", "entertainment", "india"
}

VALID_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


class ChannelLogoMatcher:
    """
    Intelligent logo selector for DTH channel automation.
    Scans the channel logo directory and identifies the optimal, high-quality,
    exact-matching logo for a channel by evaluating:
    1. Direct filename hints (if provided in CSV/Excel)
    2. HD vs SD format alignment (never assigns an HD logo to SD channel, and vice versa)
    3. Regional language specificity (never assigns Tamil/Telugu logo to generic channel)
    4. Exact channel number / numeral matching (e.g. Ten 1 vs Ten 2 vs Ten 3)
    5. Brand keyword weighting (filters out generic words like 'channel', 'tv')
    6. Clean base file preference (prioritizes clean files over _1, _(k), or scraped duplicates)
    """

    _cache_dir: Optional[Path] = None
    _cached_files: List[str] = []
    _cached_mtime: float = 0.0

    @classmethod
    def get_available_logos(cls, logo_dir: Optional[Path] = None) -> List[str]:
        """Returns indexed list of available logo filenames with caching."""
        target_dir = Path(logo_dir or DEFAULT_CHANNEL_LOGOS_DIR)
        if not target_dir.exists() or not target_dir.is_dir():
            return []

        try:
            mtime = target_dir.stat().st_mtime
            if cls._cache_dir == target_dir and cls._cached_mtime == mtime and cls._cached_files:
                return cls._cached_files

            files = [
                f.name for f in target_dir.glob("*.*")
                if f.suffix.lower() in VALID_IMAGE_EXTENSIONS
            ]
            cls._cache_dir = target_dir
            cls._cached_mtime = mtime
            cls._cached_files = files
            return files
        except Exception as e:
            logger.debug(f"[DTH LogoMatcher] Error reading logo dir {target_dir}: {e}")
            return []

    @classmethod
    def clean_tokens(cls, text: str) -> List[str]:
        """Tokenizes text while splitting digit-word transitions (e.g. ten1 -> ten, 1)."""
        if not text:
            return []
        s = text.lower().replace("&", "and")
        s = re.sub(r'([a-z]+)(\d+)', r'\1 \2', s)
        s = re.sub(r'(\d+)([a-z]+)', r'\1 \2', s)
        s = re.sub(r'[^a-z0-9]', ' ', s)
        return [t for t in s.split() if t]

    @classmethod
    def is_hd(cls, text: str) -> bool:
        """Determines if text specifies High Definition (HD/FHD/UHD/4K)."""
        if not text:
            return False
        tl = text.lower()
        if re.search(r'\b(hd|fhd|uhd|4k)\b|\+hd\b|hd\+', tl):
            return True
        tokens = re.split(r'[-_.\s]+', tl)
        return "hd" in tokens or "4k" in tokens or "fhd" in tokens

    @classmethod
    def score_candidate(
        cls,
        channel_name: str,
        filename: str,
        image_hint: Optional[str] = None
    ) -> float:
        """
        Calculates match score between channel requirements and candidate filename.
        Higher score indicates better quality/specificity match. Negative indicates mismatch.
        """
        ch_clean = channel_name.strip()
        ch_tok_list = cls.clean_tokens(ch_clean)
        ch_toks = set(ch_tok_list)
        f_stem = Path(filename).stem
        if f_stem.lower().endswith(".png"):  # double extension fix (e.g. foo.png.png)
            f_stem = Path(f_stem).stem

        # Channel trailing number check (e.g. 'Star Sports 1' ends with '1')
        last_ch_num = ch_tok_list[-1] if (ch_tok_list and ch_tok_list[-1].isdigit()) else None

        # Strip duplicate index suffixes (_1, _(k), etc.) only if not the channel numeral
        f_stem_core = f_stem
        suffix_match = re.search(r'(_\d+|\(k\)|\(\d+\))$', f_stem)
        if suffix_match:
            suff = suffix_match.group(1)
            suff_digit = re.sub(r'\D', '', suff)
            # If the suffix digit is identical to the channel's final number, check if it's the only one
            if suff_digit and last_ch_num and suff_digit == last_ch_num:
                # Keep it as channel number
                f_stem_core = f_stem
            else:
                f_stem_core = f_stem[:suffix_match.start()]

        f_toks = set(cls.clean_tokens(f_stem_core))

        if not ch_toks or not f_toks:
            return -999.0

        # Disallow matching solely on generic words (e.g. 'channel.png' matching 'Discovery Channel')
        overlap = ch_toks.intersection(f_toks)
        distinctive_ch = ch_toks - GENERIC_CHANNEL_WORDS
        if distinctive_ch and overlap.issubset(GENERIC_CHANNEL_WORDS):
            return -999.0

        # Exact stem match (dashes, spaces, underscores normalized)
        norm_ch = "".join(ch_tok_list)
        norm_f = "".join(cls.clean_tokens(f_stem_core))
        if norm_ch and norm_ch == norm_f:
            base_score = 250.0
        else:
            base_score = 0.0

        if not overlap and base_score == 0:
            return -999.0

        score = base_score + (len(overlap) * 35.0)

        # Extra tokens penalty (e.g. logo has additional words channel doesn't)
        extra_f = f_toks - ch_toks
        score -= len(extra_f) * 8.0

        # Missing tokens penalty (e.g. channel has words logo doesn't)
        missing_ch = ch_toks - f_toks
        score -= len(missing_ch) * 15.0

        # Channel numbers / digits agreement
        ch_digits = {t for t in ch_toks if t.isdigit()}
        f_digits = {t for t in f_toks if t.isdigit()}
        if ch_digits:
            if not ch_digits.issubset(f_digits):
                return -999.0  # Mismatched channel numeral (e.g. Star Sports 1 vs Star Sports 2)
            extra_digits = f_digits - ch_digits
            if extra_digits:
                score -= 100.0  # File has different numeral
        else:
            if f_digits:
                score -= 40.0  # Channel has no numbers, file has numbers

        # Regional language specificity
        for lang in REGIONAL_LANGUAGES:
            if lang in f_toks and lang not in ch_toks:
                score -= 60.0  # Generic channel should not get language-specific logo
            elif lang in ch_toks and lang in f_toks:
                score += 45.0  # Language-specific channel matched language logo

        # HD format alignment
        ch_is_hd = cls.is_hd(ch_clean)
        f_is_hd = cls.is_hd(f_stem)
        if ch_is_hd == f_is_hd:
            score += 40.0
        else:
            # Heavy penalty if SD channel gets HD logo, or HD channel gets SD logo
            score -= 80.0

        # Image hint alignment if user provided one
        if image_hint and image_hint.strip():
            hint_stem = Path(image_hint.strip()).stem.lower()
            if hint_stem in f_stem.lower() or f_stem.lower() in hint_stem:
                score += 50.0

        # Clean file preference (avoid _1, _(k), scraped artifacts)
        if not re.search(r'(_\d+|\(k\)|\(\d+\))$', f_stem):
            score += 25.0
        else:
            score -= 15.0

        if not filename.lower().endswith(".png.png"):
            score += 10.0
        else:
            score -= 40.0

        # Formatting bonus for direct naming match
        ch_under = ch_clean.lower().replace(" ", "_")
        ch_dash = ch_clean.lower().replace(" ", "-")
        if f_stem.lower() == ch_under or f_stem.lower() == ch_dash or f_stem.lower() == ch_clean.lower():
            score += 30.0

        return score

    @classmethod
    def find_best_logo(
        cls,
        channel_name: str,
        channel_number: Optional[str] = None,
        image_hint: Optional[str] = None,
        logo_dir: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str], float, str]:
        """
        Locates the most appropriate logo file for a given channel.
        Returns:
            (resolved_path, matched_filename, score, rationale)
        """
        target_dir = Path(logo_dir or DEFAULT_CHANNEL_LOGOS_DIR).resolve()
        if not target_dir.exists() or not target_dir.is_dir():
            return None, None, 0.0, f"Directory does not exist: {target_dir}"

        all_logos = cls.get_available_logos(target_dir)
        if not all_logos:
            return None, None, 0.0, f"No logo files found in {target_dir}"

        # 1. Exact Match via Image Hint if supplied
        if image_hint and image_hint.strip():
            hint_clean = image_hint.strip()
            direct_p = target_dir / hint_clean
            if direct_p.exists() and direct_p.is_file():
                ch_hd = cls.is_hd(channel_name)
                hint_hd = cls.is_hd(hint_clean)
                if ch_hd == hint_hd:
                    return str(direct_p), direct_p.name, 350.0, "Exact filename match from input file"

            # Case-insensitive / extension-flexible hint match
            hint_stem = Path(hint_clean).stem.lower()
            for f in all_logos:
                if Path(f).stem.lower() == hint_stem:
                    cand_p = target_dir / f
                    if cand_p.is_file():
                        ch_hd = cls.is_hd(channel_name)
                        cand_hd = cls.is_hd(f)
                        if ch_hd == cand_hd:
                            return str(cand_p), f, 320.0, "Case-insensitive hint match from input file"

        # 2. Intelligent Scoring against all candidates in directory
        if not channel_name or not channel_name.strip():
            return None, None, 0.0, "Empty channel name"

        scored: List[Tuple[float, str]] = []
        for filename in all_logos:
            sc = cls.score_candidate(channel_name, filename, image_hint=image_hint)
            if sc > 0:
                scored.append((sc, filename))

        if not scored:
            # 3. Channel number fallback if files are named by channel number
            if channel_number:
                num_clean = str(channel_number).strip()
                for ext in (".png", ".jpg", ".jpeg"):
                    num_file = f"{num_clean}{ext}"
                    np = target_dir / num_file
                    if np.exists() and np.is_file():
                        return str(np), num_file, 100.0, f"Matched by channel number {num_clean}"

            return None, None, 0.0, f"No matching logo found for '{channel_name}'"

        # Sort descending by score, tie-break by file size (prefer richer image)
        scored.sort(
            key=lambda x: (
                x[0],
                (target_dir / x[1]).stat().st_size if (target_dir / x[1]).exists() else 0
            ),
            reverse=True
        )

        top_score, top_file = scored[0]
        resolved = str(target_dir / top_file)
        return resolved, top_file, top_score, f"Selected via intelligent score ({round(top_score, 1)} pts)"


logo_matcher = ChannelLogoMatcher()
