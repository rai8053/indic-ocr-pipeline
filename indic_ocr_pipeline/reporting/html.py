"""HTML quality report generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def generate_report(
    pages: list[dict[str, Any]],
    output_path: Path,
    usage: dict[str, Any] | None = None,
) -> Path:
    """Generate a standalone HTML quality report for annotated pages.

    Includes per-page scores, validation results, overlay images, and an
    API usage summary.

    Args:
        pages: List of page result dicts, each with ``name``, ``validation``,
            ``scores``, and optional ``overlay`` keys.
        output_path: Destination path for the HTML file.
        usage: Optional usage summary dict with ``date``, ``total``,
            and ``providers`` keys.

    Returns:
        ``output_path`` for chaining.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = ""
    summary_ocr: list[float] = []
    summary_layout: list[float] = []
    summary_ro: list[float] = []
    summary_boxes: list[float] = []
    summary_rels: list[float] = []
    summary_overall: list[float] = []
    passed = 0
    failed = 0

    for p in pages:
        name = p.get("name", "unknown")
        overlay_rel = p.get("overlay", "")
        val = p.get("validation", {})
        scores = p.get("scores", {})
        checks = val.get("checks", {})

        valid = val.get("valid", False)
        if valid:
            passed += 1
        else:
            failed += 1

        errs = val.get("errors", [])
        warns = val.get("warnings", [])

        ocr_s = scores.get("ocr", 0)
        layout_s = scores.get("layout", 0)
        ro_s = scores.get("reading_order", 0)
        box_s = scores.get("boxes", 0)
        rel_s = scores.get("relations", 0)
        overall_s = scores.get("overall", 0)

        summary_ocr.append(ocr_s)
        summary_layout.append(layout_s)
        summary_ro.append(ro_s)
        summary_boxes.append(box_s)
        summary_rels.append(rel_s)
        summary_overall.append(overall_s)

        checks_html = ""
        for ck, cv in sorted(checks.items()):
            if isinstance(cv, dict):
                valid_count = cv.get("valid", 0)
                invalid_count = cv.get("invalid", 0)
                total_count = valid_count + invalid_count
                status_str = f"{valid_count}/{total_count}" if total_count > 0 else "N/A"
                checks_html += f"<tr><td>{ck}</td><td>{status_str}</td><td>-</td></tr>"
            else:
                checks_html += f"<tr><td>{ck}</td><td>{cv}</td><td>-</td></tr>"

        err_html = ""
        for e in errs:
            err_html += f'<li class="error">{e}</li>'
        for w in warns:
            err_html += f'<li class="warning">{w}</li>'
        if not err_html:
            err_html = '<li class="pass">No issues</li>'

        rows += f"""
        <div class="page">
            <h2>{name}</h2>
            <div class="scores">
                <div>OCR: <b>{ocr_s}%</b></div>
                <div>Layout: <b>{layout_s}%</b></div>
                <div>Reading Order: <b>{ro_s}%</b></div>
                <div>Boxes: <b>{box_s}%</b></div>
                <div>Relations: <b>{rel_s}%</b></div>
                <div>Overall: <b>{overall_s}%</b></div>
                <div>Status: <b class="{'pass' if valid else 'fail'}">{'PASS' if valid else 'FAIL'}</b></div>
            </div>
            <div class="overlay">
                <img src="{overlay_rel}" alt="Overlay for {name}" style="max-width:100%">
            </div>
            <table>
                <tr><th>Check</th><th>Result</th><th>Details</th></tr>
                {checks_html}
            </table>
            <ul>{err_html}</ul>
        </div>
        """

    usage_html = ""
    if usage:
        usage_date = usage.get("date", "")
        usage_provs = usage.get("providers", {})
        usage_total = usage.get("total", 0)
        if usage_provs:
            usage_items = "".join(
                f'<div class="summary-item"><div class="value">{c}</div><div class="label">{p}</div></div>'
                for p, c in sorted(usage_provs.items())
            )
            usage_html = f"""
            <div class="usage">
                <h2>API Usage <span class="usage-date">({usage_date})</span></h2>
                <div class="summary-grid">
                    {usage_items}
                    <div class="summary-item"><div class="value">{usage_total}</div><div class="label">Total Calls</div></div>
                </div>
            </div>"""

    def avg(lst):
        return int(sum(lst) / len(lst)) if lst else 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>RFQ OCR Pipeline Report</title>
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
h1 {{ color: #333; }}
.summary {{ background: #fff; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
.summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 10px; }}
.summary-item {{ padding: 10px; background: #f9f9f9; border-radius: 4px; text-align: center; }}
.summary-item .value {{ font-size: 24px; font-weight: bold; }}
.summary-item .label {{ font-size: 12px; color: #666; }}
.usage {{ background: #fff; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
.usage-date {{ font-size: 14px; color: #999; font-weight: normal; }}
.page {{ background: #fff; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
.scores {{ display: flex; gap: 15px; flex-wrap: wrap; margin-bottom: 15px; }}
.scores > div {{ padding: 8px 12px; background: #f0f0f0; border-radius: 4px; font-size: 14px; }}
.overlay {{ margin: 10px 0; }}
.overlay img {{ border: 1px solid #ddd; border-radius: 4px; }}
table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 13px; }}
th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
th {{ background: #f0f0f0; }}
.pass {{ color: green; font-weight: bold; }}
.fail {{ color: red; font-weight: bold; }}
.warning {{ color: orange; }}
.error {{ color: red; }}
ul {{ list-style: none; padding: 0; }}
li {{ padding: 4px 0; font-size: 13px; }}
li::before {{ content: "\\2022"; margin-right: 8px; }}
li.error::before {{ content: "\\2716"; color: red; }}
li.warning::before {{ content: "\\26A0"; color: orange; }}
li.pass::before {{ content: "\\2714"; color: green; }}
</style>
</head>
<body>
<h1>RFQ OCR Pipeline Quality Report</h1>
<div class="summary">
    <h2>Summary</h2>
    <div class="summary-grid">
        <div class="summary-item"><div class="value">{passed}/{passed+failed}</div><div class="label">Passed Pages</div></div>
        <div class="summary-item"><div class="value">{avg(summary_overall)}%</div><div class="label">Avg Overall Score</div></div>
        <div class="summary-item"><div class="value">{avg(summary_ocr)}%</div><div class="label">Avg OCR Score</div></div>
        <div class="summary-item"><div class="value">{avg(summary_layout)}%</div><div class="label">Avg Layout Score</div></div>
        <div class="summary-item"><div class="value">{avg(summary_ro)}%</div><div class="label">Avg Reading Order Score</div></div>
        <div class="summary-item"><div class="value">{avg(summary_boxes)}%</div><div class="label">Avg Box Score</div></div>
    </div>
</div>
{usage_html}
{rows}
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    return output_path
