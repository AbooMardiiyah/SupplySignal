"""Small append-only SQLite log for officer stock verification.

These observations are separate from model-training reports. They change the
current decision state, not the historical LMIS data or fitted model.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path


DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "operational" / "observations.sqlite3"
EVENT_TYPES = {"stock_count", "receipt_confirmed", "receipt_expected"}
CASE_EVENT_TYPES = {"contact_attempted", "facility_unreachable", "referred_to_lga", "follow_up_completed"}


def list_case_events(db_path: Path = DEFAULT_DB, as_of: date | None = None) -> list[dict]:
    """Return the append-only follow-up trail, separate from stock evidence."""
    if not db_path.exists():
        return []
    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='case_events'"
        ).fetchone()
        if not exists:
            return []
        where = "WHERE event_date <= ?" if as_of else ""
        args = (as_of.isoformat(),) if as_of else ()
        rows = connection.execute(
            "SELECT id, facility_id, commodity_id, event_type, event_date, "
            f"note, recorded_by, recorded_at FROM case_events {where} ORDER BY id",
            args,
        ).fetchall()
    return [dict(row) for row in rows]


def record_case_event(
    facility_id: str,
    commodity_id: str,
    event_type: str,
    event_date: date,
    *,
    note: str,
    recorded_by: str,
    db_path: Path = DEFAULT_DB,
    as_of: date | None = None,
) -> int:
    """Record contact progress; it never changes inventory or closes a supply alert."""
    if not facility_id.strip() or not commodity_id.strip():
        raise ValueError("Facility and commodity are required")
    if event_type not in CASE_EVENT_TYPES:
        raise ValueError("Unknown follow-up type")
    if as_of is not None and event_date > as_of:
        raise ValueError("A follow-up cannot occur after the decision date")
    if not recorded_by.strip() or len(recorded_by) > 100:
        raise ValueError("Recorder name or role is required (maximum 100 characters)")
    if not note.strip() or len(note) > 500:
        raise ValueError("A follow-up note is required (maximum 500 characters)")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS case_events ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "facility_id TEXT NOT NULL, commodity_id TEXT NOT NULL, "
            "event_type TEXT NOT NULL, event_date TEXT NOT NULL, "
            "note TEXT NOT NULL, recorded_by TEXT NOT NULL, recorded_at TEXT NOT NULL)"
        )
        latest = connection.execute(
            "SELECT MAX(event_date) FROM case_events WHERE facility_id = ? AND commodity_id = ?",
            (facility_id, commodity_id),
        ).fetchone()[0]
        if latest and event_date.isoformat() < latest:
            raise ValueError("Backdated follow-ups need a separate reconciliation process")
        cursor = connection.execute(
            "INSERT INTO case_events (facility_id, commodity_id, event_type, event_date, "
            "note, recorded_by, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                facility_id.strip(), commodity_id.strip(), event_type, event_date.isoformat(),
                note.strip(), recorded_by.strip(), datetime.now(timezone.utc).isoformat(),
            ),
        )
        return int(cursor.lastrowid)


def list_events(db_path: Path = DEFAULT_DB, as_of: date | None = None) -> list[dict]:
    if not db_path.exists():
        return []
    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='observations'"
        ).fetchone()
        if not exists:
            return []
        where = "WHERE event_date <= ?" if as_of else ""
        args = (as_of.isoformat(),) if as_of else ()
        rows = connection.execute(
            f"SELECT id, facility_id, commodity_id, event_type, units, event_date, "
            f"expected_date, reference, note, recorded_by, recorded_at FROM observations {where} ORDER BY id",
            args,
        ).fetchall()
    return [dict(row) for row in rows]


def record_event(
    facility_id: str,
    commodity_id: str,
    event_type: str,
    units: int,
    event_date: date,
    *,
    expected_date: date | None = None,
    reference: str = "",
    note: str = "",
    recorded_by: str = "",
    db_path: Path = DEFAULT_DB,
    as_of: date | None = None,
) -> int:
    if not facility_id.strip() or not commodity_id.strip():
        raise ValueError("Facility and commodity are required")
    if event_type not in EVENT_TYPES:
        raise ValueError("Unknown observation type")
    if isinstance(units, bool) or not isinstance(units, int) or units < 0:
        raise ValueError("Units must be a nonnegative whole number")
    if event_type != "stock_count" and units == 0:
        raise ValueError("A receipt must contain at least one unit")
    if as_of is not None and event_date > as_of:
        raise ValueError("An observation cannot occur after the decision date")
    if event_type == "receipt_expected":
        if expected_date is None or expected_date < event_date:
            raise ValueError("Expected receipts need an arrival date on or after observation date")
    elif expected_date is not None:
        raise ValueError("Only expected receipts may have an expected arrival date")
    if event_type == "receipt_confirmed" and not reference.strip():
        raise ValueError("A confirmed receipt needs a delivery reference")
    if not recorded_by.strip() or len(recorded_by) > 100:
        raise ValueError("Recorder name or role is required (maximum 100 characters)")
    if len(note) > 500 or len(reference) > 100:
        raise ValueError("Reference or note is too long")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS observations ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "facility_id TEXT NOT NULL, commodity_id TEXT NOT NULL, "
            "event_type TEXT NOT NULL, units INTEGER NOT NULL, event_date TEXT NOT NULL, "
            "expected_date TEXT, reference TEXT NOT NULL, note TEXT NOT NULL, "
            "recorded_by TEXT NOT NULL, "
            "recorded_at TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS unique_confirmed_delivery "
            "ON observations (facility_id, commodity_id, reference) "
            "WHERE event_type = 'receipt_confirmed'"
        )
        latest = connection.execute(
            "SELECT MAX(event_date) FROM observations WHERE facility_id = ? AND commodity_id = ?",
            (facility_id, commodity_id),
        ).fetchone()[0]
        if latest and event_date.isoformat() < latest:
            raise ValueError("Backdated observations need a separate reconciliation process")
        try:
            cursor = connection.execute(
                "INSERT INTO observations (facility_id, commodity_id, event_type, units, "
                "event_date, expected_date, reference, note, recorded_by, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    facility_id, commodity_id, event_type, units, event_date.isoformat(),
                    expected_date.isoformat() if expected_date else None,
                    reference.strip(), note.strip(), recorded_by.strip(), datetime.now(timezone.utc).isoformat(),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError("This delivery reference was already recorded for this facility and product") from error
        return int(cursor.lastrowid)
