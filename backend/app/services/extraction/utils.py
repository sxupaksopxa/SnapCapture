import logging
import re
from datetime import datetime

import dateparser

logger = logging.getLogger(__name__)


def convert_12h(hour: int, ampm: str) -> str:
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:00"


def extract_and_remove_time(text: str) -> tuple[str, str | None]:
    """Extract the first time expression found and return the text with it removed."""
    time_result = None
    spans_to_remove = []

    explicit_patterns = [
        (
            r"\b(\d{1,2})[:.](\d{2})\s*[hH]?\s+(?:to|bis|[-\u2013])\s+(\d{1,2})[:.](\d{2})\s*[hH]?\b",
            lambda m: f"{int(m.group(1)):02d}:{m.group(2)}-{int(m.group(3)):02d}:{m.group(4)}",
        ),
        (
            r"\b(\d{1,2})[:.](\d{2})\s*[hH]?\s+(\d{1,2})[:.](\d{2})\s*[hH]?\b",
            lambda m: f"{int(m.group(1)):02d}:{m.group(2)}-{int(m.group(3)):02d}:{m.group(4)}",
        ),
        (
            r"\b(\d{1,2}):(\d{2})\s*[hH]?\b",
            lambda m: f"{int(m.group(1)):02d}:{m.group(2)}",
        ),
        # German dot-style time: 14.00h or 14.00 h
        (
            r"\b(\d{1,2})\.(\d{2})\s*[hH]\b",
            lambda m: f"{int(m.group(1)):02d}:{m.group(2)}",
        ),
        # Military time: 1700, 0900 (not preceded/followed by other digits or a dot)
        (
            r"(?<![\d.])(?:at\s+)?(\d{2})(\d{2})(?!\d)(?:\s*h\b)?",
            lambda m: (
                f"{int(m.group(1)):02d}:{m.group(2)}"
                if 0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2)) <= 59
                else None
            ),
        ),
        (
            r"\b(\d{1,2})\s*[uU][hH][rR]\b",
            lambda m: f"{int(m.group(1)):02d}:00",
        ),
        (
            r"\b(\d{1,2})\s*([aApP]\.?[mM]\.?)\b",
            lambda m: convert_12h(int(m.group(1)), m.group(2).lower().replace(".", "")),
        ),
    ]

    for pattern, formatter in explicit_patterns:
        match = re.search(pattern, text)
        if match:
            time_result = formatter(match)
            if time_result:
                spans_to_remove.append(match.span())
                break

    if not time_result:
        word_patterns = [
            (r"\bbefore\s+noon\b", "11:00", re.IGNORECASE),
            (r"\bafter\s+noon\b", "13:00", re.IGNORECASE),
            (r"\bmorning\b", "09:00", re.IGNORECASE),
            (r"\bafternoon\b", "14:00", re.IGNORECASE),
            (r"\bevening\b", "18:00", re.IGNORECASE),
            (r"\bnight\b", "21:00", re.IGNORECASE),
            (r"\bnoon\b", "12:00", re.IGNORECASE),
            (r"\bmidnight\b", "00:00", re.IGNORECASE),
            (r"\bvormittag\b", "09:00", re.IGNORECASE),
            (r"\bnachmittag\b", "14:00", re.IGNORECASE),
            (r"\babend\b", "18:00", re.IGNORECASE),
            (r"\bnacht\b", "21:00", re.IGNORECASE),
            (r"\bmittag\b", "12:00", re.IGNORECASE),
        ]
        for pattern, time_val, flags in word_patterns:
            match = re.search(pattern, text, flags)
            if match:
                time_result = time_val
                spans_to_remove.append(match.span())
                break

    cleaned = text
    for start, end in sorted(spans_to_remove, reverse=True):
        cleaned = cleaned[:start] + cleaned[end:]

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned, time_result


def normalize_date(
    original_date: str | None, base_date: datetime | None = None
) -> tuple[str | None, str | None]:
    """Return (normalized_date, normalized_time) from original_date text."""
    if not original_date:
        return None, None

    base_date = base_date or datetime.now()

    cleaned_text, time_str = extract_and_remove_time(original_date)

    # Fast-path for short European dates like 12.06 or 12/06
    short_date_match = re.search(r"^\s*(\d{1,2})[./](\d{1,2})\s*$", cleaned_text)
    if short_date_match:
        day, month = int(short_date_match.group(1)), int(short_date_match.group(2))
        if 1 <= day <= 31 and 1 <= month <= 12:
            date_str = f"{day:02d}.{month:02d}.{base_date.year}"
            logger.info("Short-date parsed '%s' -> %s", original_date, date_str)
            return date_str, time_str

    if cleaned_text:
        parsed = dateparser.parse(
            cleaned_text,
            settings={
                "PREFER_DATES_FROM": "future",
                "DATE_ORDER": "DMY",
                "RELATIVE_BASE": base_date,
            },
        )
        if parsed:
            date_str = parsed.strftime("%d.%m.%Y")
            logger.info(
                "Normalized '%s' -> date=%s time=%s", original_date, date_str, time_str
            )
            return date_str, time_str

        # Fallback: use search_dates to find dates embedded in longer phrases
        from dateparser.search import search_dates
        found = search_dates(
            cleaned_text,
            settings={
                "PREFER_DATES_FROM": "future",
                "DATE_ORDER": "DMY",
                "RELATIVE_BASE": base_date,
            },
        )
        if found:
            date_str = found[0][1].strftime("%d.%m.%Y")
            logger.info(
                "Search-normalized '%s' -> date=%s time=%s", original_date, date_str, time_str
            )
            return date_str, time_str

    if time_str:
        logger.info("Extracted time only from '%s': %s", original_date, time_str)

    return None, time_str


def ensure_required_dates(item) -> None:
    """Ensure every event has a date and every task has a due_date.
    Falls back to today's date if nothing else is available."""
    from datetime import datetime
    today = datetime.now().strftime("%d.%m.%Y")

    if item.type == "event":
        if not item.date:
            # Try one more normalization from original_date
            if item.original_date:
                normalized, _ = normalize_date(item.original_date)
                if normalized:
                    item.date = normalized
            if not item.date:
                item.date = today
                logger.info("Event '%s' had no date — defaulted to today (%s)", item.title, today)
    elif item.type == "task":
        if not item.due_date:
            # Try one more normalization from original_date
            if item.original_date:
                normalized, _ = normalize_date(item.original_date)
                if normalized:
                    item.due_date = normalized
            if not item.due_date:
                item.due_date = today
                logger.info("Task '%s' had no due_date — defaulted to today (%s)", item.title, today)
