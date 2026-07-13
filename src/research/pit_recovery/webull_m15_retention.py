from __future__ import annotations

from typing import Any


def retention_boundary_from_matrix(matrix: list[dict[str, Any]]) -> dict[str, Any]:
    supported_dates = sorted(
        {
            str(row.get("session_date"))
            for row in matrix
            if row.get("symbol") == "SOXX" and row.get("interval") == "M15" and "SUPPORTED" in str(row.get("status"))
        }
    )
    statuses = {str(row.get("status")) for row in matrix if row.get("symbol") == "SOXX" and row.get("interval") == "M15"}
    if not supported_dates:
        if "AUTH_BLOCKED" in statuses:
            status = "AUTH_BLOCKED"
        elif "START_END_IGNORED" in statuses:
            status = "START_END_IGNORED"
        elif "NOT_ENTITLED" in statuses:
            status = "NOT_ENTITLED"
        elif "NO_DATA" in statuses:
            status = "NO_DATA"
        else:
            status = "UNKNOWN"
        return {
            "earliest_verified_soxx_m15_date": "",
            "latest_verified_soxx_m15_date": "",
            "retention_status": status,
            "coarse_yearly_probe_complete": False,
            "monthly_narrowing_complete": False,
            "session_level_verification_complete": False,
        }
    return {
        "earliest_verified_soxx_m15_date": supported_dates[0],
        "latest_verified_soxx_m15_date": supported_dates[-1],
        "retention_status": "WEBULL_M15_2022_2025_SUPPORTED" if supported_dates[0][:4] <= "2022" else "WEBULL_M15_PARTIAL",
        "coarse_yearly_probe_complete": True,
        "monthly_narrowing_complete": False,
        "session_level_verification_complete": True,
    }


def webull_terminal_status(boundary: dict[str, Any]) -> str:
    status = str(boundary.get("retention_status", "UNKNOWN"))
    if status == "WEBULL_M15_2022_2025_SUPPORTED":
        return "WEBULL_M15_2022_2025_SUPPORTED"
    if status == "AUTH_BLOCKED":
        return "WEBULL_M15_BLOCKED"
    if status in {"START_END_IGNORED", "RECENT_ONLY"}:
        return "WEBULL_M15_RECENT_ONLY"
    if status == "NOT_ENTITLED":
        return "WEBULL_M15_NOT_ENTITLED"
    return "WEBULL_M15_PARTIAL"
