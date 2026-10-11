"""Portable, human-readable verification sheet; not an inventory import."""

from __future__ import annotations

from datetime import date

from .decisions import facility_call_plan


def call_worksheet(cases: list[dict], as_of: date, capacity: int = 10) -> str:
    calls = facility_call_plan(cases, capacity=capacity)
    lines = [
        "SUPPLYSIGNAL — DEMONSTRATION CALL WORKSHEET",
        f"Decision date: {as_of.isoformat()} (fixed simulation date)",
        "Real registry locations; simulated inventory. Not a movement authorisation.",
        "This snapshot will not update when new evidence arrives.",
        "Call order is exploratory; unlisted facilities may also need attention.",
        "Use an approved contact list. Do not record patient details.",
        "Record unknown as UNKNOWN, never zero. Keep promised and received stock separate.",
        "After reconnecting, reconcile against the latest history before manual entry.",
        "This worksheet has no automatic upload or synchronisation.",
        "",
    ]
    for number, call in enumerate(calls, 1):
        lines.extend([
            f"CALL {number}: {call['facility_name']} [{call['facility_id']}]",
            "Contact outcome: reached / unanswered / unavailable / other: __________",
            "Contact date/time: __________  Officer role: __________",
            "Reported obstacle (if known): power / network / staff unavailable / other / unknown",
        ])
        for case in cases:
            if case["facility_id"] != call["facility_id"]:
                continue
            lines.extend([
                f"  Product: {case['commodity_name']} [{case['commodity_id']}]",
                f"  Signal: {case['signal']}",
                f"  Next check: {case['next_step']}",
                f"  Last monthly report: {case.get('last_report_period', 'unknown')}",
                "  Count date/time: __________  Usable units counted / UNKNOWN: __________",
                "  Confirm formulation, unit, expiry and storage condition: __________",
                "  Received units + receipt date/reference (if any): __________",
                "  Promised units + expected date (not available stock): __________",
                "  Follow-up / responsible role / next contact date: __________",
            ])
        lines.extend(["Do not infer a shortage or a cause from an unanswered call.", "", "-" * 72, ""])
    if not calls:
        lines.append("No flagged cases in this snapshot; this is not proof of universal availability.")
    return "\n".join(lines)
