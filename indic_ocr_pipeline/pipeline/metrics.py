"""Pipeline metrics — validation and scoring aggregation."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def validate_and_score_pages(
    json_files: list[Path],
) -> list[tuple[Path, dict[str, Any], dict[str, Any]]]:
    """Run validation and scoring on a list of annotation files.

    Args:
        json_files: Sorted list of annotation JSON paths.

    Returns:
        List of ``(json_path, validation_result, scores)`` tuples.
    """
    from indic_ocr_pipeline.layout.validator import score_page, validate_page

    results: list[tuple[Path, dict, dict]] = []
    for j in json_files:
        r = validate_page(j)
        s = score_page(j)
        results.append((j, r, s))
    return results


def format_usage_for_report(usage_recorder: Any) -> dict[str, Any]:
    """Format usage tracker data for the HTML report.

    Args:
        usage_recorder: An ``UsageTracker`` instance.

    Returns:
        Dict with ``date``, ``total``, and ``providers`` keys.
    """
    result: dict[str, Any] = {
        "date": __import__("time").strftime("%Y-%m-%d"),
        "total": 0,
        "providers": {},
    }
    if usage_recorder:
        rd = usage_recorder.dashboard()
        result["providers"] = {
            p: d["today"]["requests"] for p, d in rd.get("providers", {}).items()
        }
        result["total"] = sum(result["providers"].values())
    return result
