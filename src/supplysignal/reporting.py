"""Shared reporting assumptions; these are demo policy, not national guidance."""

from datetime import date

REPORT_DUE_DAY = 10


def latest_due_month(as_of: date, due_day: int = REPORT_DUE_DAY) -> date:
    """Last month's report becomes due on due_day of the current month."""
    if not 1 <= due_day <= 28:
        raise ValueError("Reporting due day must be between 1 and 28")
    index = as_of.year * 12 + as_of.month - 1
    index -= 1 if as_of.day >= due_day else 2
    return date(index // 12, index % 12 + 1, 1)
