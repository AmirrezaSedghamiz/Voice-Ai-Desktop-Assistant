"""
Datetime parser supporting English and Persian relative durations and expressions.
Operates completely offline with zero external dependencies.
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone

# Persian and Arabic digit translation table
DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_digits(text: str) -> str:
    """Converts Persian and Arabic digits to ASCII digits."""
    return text.translate(DIGIT_MAP)


def parse_datetime_expression(
    expr: str,
    base_dt: datetime | None = None,
) -> datetime | None:
    """
    Parses a date/time expression in English or Persian into a timezone-aware UTC datetime.
    Supports relative offsets (e.g. 'in 45 minutes', '۴۵ دقیقه دیگه', 'فردا')
    and ISO 8601 strings.
    """
    if not expr or not isinstance(expr, str):
        return None

    cleaned = normalize_digits(expr.strip())
    now = base_dt if base_dt is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # 1. Try ISO 8601 parsing first
    try:
        dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass

    lower = cleaned.lower()

    # 2. English relative minutes: 'in 45 minutes', '45 mins', 'in 15 min'
    m = re.search(r"(?:in\s+)?(\d+)\s*(?:minutes?|mins?|min)\b", lower)
    if m:
        mins = int(m.group(1))
        return now + timedelta(minutes=mins)

    # Persian relative minutes: '۴۵ دقیقه دیگه', 'در ۴۵ دقیقه', '۱۵ دقیقه بعد', 'نیم ساعت'
    if "نیم ساعت" in lower or "نیم‌ساعت" in lower:
        return now + timedelta(minutes=30)

    m = re.search(r"(?:در\s+)?(\d+)\s*دقیقه(?:\s+(?:دیگه|بعد|دیگر))?", lower)
    if m:
        mins = int(m.group(1))
        return now + timedelta(minutes=mins)

    # 3. English relative hours: 'in 2 hours', '1 hr'
    m = re.search(r"(?:in\s+)?(\d+)\s*(?:hours?|hrs?|hr)\b", lower)
    if m:
        hrs = int(m.group(1))
        return now + timedelta(hours=hrs)

    # Persian relative hours: 'یک ساعت دیگه', '۲ ساعت بعد', 'در ۳ ساعت'
    if re.search(r"(?:یک|یه)\s*ساعت(?:\s+(?:دیگه|بعد|دیگر))?", lower):
        return now + timedelta(hours=1)

    m = re.search(r"(?:در\s+)?(\d+)\s*ساعت(?:\s+(?:دیگه|بعد|دیگر))?", lower)
    if m:
        hrs = int(m.group(1))
        return now + timedelta(hours=hrs)

    # 4. English relative days: 'in 3 days'
    m = re.search(r"(?:in\s+)?(\d+)\s*(?:days?)\b", lower)
    if m:
        days = int(m.group(1))
        return now + timedelta(days=days)

    # Persian relative days: '۲ روز دیگه', '۳ روز بعد'
    m = re.search(r"(?:در\s+)?(\d+)\s*روز(?:\s+(?:دیگه|بعد|دیگر))?", lower)
    if m:
        days = int(m.group(1))
        return now + timedelta(days=days)

    # 5. 'tomorrow' / 'فردا'
    if "tomorrow" in lower or "فردا" in lower:
        # Default to tomorrow at 09:00 AM UTC (or 24 hours later)
        tomorrow_date = (now + timedelta(days=1)).date()
        # Check if a specific time is mentioned, e.g. 'tomorrow at 5pm' or 'فردا ساعت ۵'
        tm_match = re.search(r"(?:at\s+|ساعت\s+)(\d{1,2})(?::(\d{2}))?\s*(am|pm|صبح|عصر|شب)?", lower)
        if tm_match:
            hour = int(tm_match.group(1))
            minute = int(tm_match.group(2) or 0)
            ampm = tm_match.group(3)
            if ampm in ("pm", "عصر", "شب") and hour < 12:
                hour += 12
            elif ampm in ("am", "صبح") and hour == 12:
                hour = 0
            return datetime.combine(tomorrow_date, time(hour, minute), tzinfo=timezone.utc)
        return datetime.combine(tomorrow_date, time(9, 0), tzinfo=timezone.utc)

    # 6. 'tonight' / 'امشب'
    if "tonight" in lower or "امشب" in lower:
        tonight_date = now.date()
        return datetime.combine(tonight_date, time(20, 0), tzinfo=timezone.utc)

    # 7. Fixed time today: 'at 5pm', 'at 17:00', 'ساعت ۱۷'
    time_match = re.search(r"(?:at\s+|ساعت\s+)(\d{1,2})(?::(\d{2}))?\s*(am|pm|صبح|عصر|شب)?", lower)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        ampm = time_match.group(3)
        if ampm in ("pm", "عصر", "شب") and hour < 12:
            hour += 12
        elif ampm in ("am", "صبح") and hour == 12:
            hour = 0
        target_dt = datetime.combine(now.date(), time(hour, minute), tzinfo=timezone.utc)
        if target_dt <= now:
            target_dt += timedelta(days=1)
        return target_dt

    return None
