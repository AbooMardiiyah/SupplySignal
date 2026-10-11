"""Canonical data contracts for facility-commodity reporting."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Provenance(StrEnum):
    OBSERVED = "observed"
    DERIVED = "derived"
    SIMULATED = "simulated"


class AlertType(StrEnum):
    SUPPLY = "supply"
    REPORTING = "reporting"
    REDISTRIBUTION = "redistribution"
    ESCALATION = "escalation"


MONTHLY_REPORT_COLUMNS = (
    "facility_id",
    "commodity_id",
    "period",
    "opening_stock",
    "receipts",
    "consumption",
    "losses",
    "adjustments",
    "closing_stock",
    "stockout_days",
    "submitted_at",
    "source",
)


@dataclass(frozen=True)
class TransferPolicy:
    """Hard constraints used before recommending a donor transfer."""

    safety_stock_periods: float = 1.0
    max_distance_km: float = 75.0
    require_high_confidence_donor: bool = True
