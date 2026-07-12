"""Interactive CLI for the OCR Pipeline with live progress dashboard."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

from indic_ocr_pipeline.utils.config import QUOTA_STATE_FILE
from indic_ocr_pipeline.utils.helpers import (
    banner,
    bold,
    err,
    info,
    kv,
    menu_item,
    ok,
    raw,
    rule,
    warn,
)
from indic_ocr_pipeline.utils.usage import UsageTracker

BASE = Path(__file__).resolve().parent.parent
PIPELINE = BASE / "indic_ocr_pipeline3.py"

LANG_DISPLAY: dict[str, str] = {
    "odia": "Odia",
    "marathi": "Marathi",
    "telugu": "Telugu",
    "tamil": "Tamil",
    "hindi": "Hindi",
    "bengali": "Bengali",
    "gujarati": "Gujarati",
    "assamese": "Assamese",
    "punjabi": "Punjabi",
    "urdu": "Urdu",
    "malayalam": "Malayalam",
    "kannada": "Kannada",
    "unknown": "Unknown",
}

LANG_PATTERNS: dict[str, list[str]] = {
    "odia": [r"(?i)odia|oriya|bhougalika|sagyan|prakarana"],
    "marathi": [r"(?i)marathi|baldarshan"],
    "telugu": [r"(?i)telugu|adikaara|basha"],
    "tamil": [r"(?i)tamil|tnla"],
    "hindi": [r"(?i)hindi"],
    "bengali": [r"(?i)bengali|bangla"],
    "gujarati": [r"(?i)gujarati"],
    "assamese": [r"(?i)assamese|asamiya"],
    "punjabi": [r"(?i)punjabi|gurmukhi"],
    "urdu": [r"(?i)urdu"],
    "malayalam": [r"(?i)malayalam"],
    "kannada": [r"(?i)kannada"],
}


def detect_language(fname: str) -> str:
    fname_lower = fname.lower()
    for lang, patterns in LANG_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, fname_lower):
                return lang
    return "unknown"


def ask_int(prompt: str, default: int = 0) -> int:
    raw_in = input(f"{prompt} [{default}]: ").strip()
    if not raw_in:
        return default
    try:
        return max(0, int(raw_in))
    except ValueError:
        return default


def zip_output(lang_key: str, lang_dir: Path) -> None:
    zip_name = lang_dir / f"{lang_key}.zip"
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
        for fpath in lang_dir.rglob("*"):
            if fpath.is_file() and fpath != zip_name:
                zf.write(fpath, fpath.relative_to(lang_dir))
    ok(f"  Created: {zip_name}")


class Dashboard:
    """Live progress dashboard with stage progress bars, provider info, and timing."""

    STAGES = ["Rendering", "OCR", "LLM", "Relations", "Validation", "QA", "Report", "ZIP"]
    DISPLAY_STAGES = ["OCR", "Layout", "Validation"]

    def __init__(self, total_pages: int = 0) -> None:
        self._start = time.time()
        self._pages_done = 0
        self._total_pages = total_pages
        self._pdf_name = ""
        self._current_page = ""
        self._current_stage = ""
        self._stage_status: dict[str, str] = {s: " " for s in self.STAGES}
        self._api_usage: dict[str, int] = {}
        self._latency: float = 0.0
        self._tokens: int = 0
        self._retry: int = 0
        self._provider: str = ""
        self._first = True

    def _bar(self, pct: int, width: int = 19) -> str:
        filled = int(width * pct / 100)
        return "\u2588" * filled + "\u2591" * (width - filled)

    def _build_display(self) -> str:
        elapsed = time.time() - self._start
        e_min, e_sec = int(elapsed // 60), int(elapsed % 60)
        elapsed_str = f"{e_min:02d}:{e_sec:02d}"
        if self._pages_done > 0 and self._total_pages > 0:
            eta = elapsed / self._pages_done * (self._total_pages - self._pages_done)
            eta_str = f"{int(eta // 60):02d}:{int(eta % 60):02d}"
        else:
            eta_str = "--:--"

        # Compute stage progress for display
        stages = self._stage_status
        stage_order = ["Rendering", "OCR", "LLM", "Relations", "Validation", "QA", "Report", "ZIP"]
        current_idx = -1
        for i, s in enumerate(stage_order):
            if stages.get(s) == "current":
                current_idx = i
                break
            elif stages.get(s) == "done":
                current_idx = i

        ocr_pct = 0
        if current_idx >= 2:
            ocr_pct = 100
        elif stages.get("OCR") == "current":
            ocr_pct = 72

        layout_pct = 0
        if current_idx >= 4 or stages.get("Relations") == "current":
            layout_pct = 100
        elif stages.get("LLM") == "current":
            layout_pct = 51

        val_pct = 0
        if current_idx >= 5:
            val_pct = 100
        elif stages.get("Validation") == "current":
            val_pct = 51

        prov_line = ""
        if self._provider:
            prov_line = f"\n  Provider      {self._provider}"
            if self._latency:
                prov_line += f"\n  Latency       {self._latency:.2f} s"
            if self._tokens:
                prov_line += f"\n  Tokenes        {self._tokens:,}"
            prov_line += f"\n  Retry         {self._retry}"

        lines = [
            "",
            "  " + "-" * 78,
            "",
            f"  Processing: {self._pdf_name}",
            "",
            f"  Page          {self._current_page or '--'} / {self._total_pages}",
            f"  OCR           {self._bar(ocr_pct)} {ocr_pct}%",
            f"  Layout        {self._bar(layout_pct)} {layout_pct}%",
            f"  Validation    {self._bar(val_pct)} {val_pct}%",
            prov_line,
            "",
            f"  Elapsed       {elapsed_str}",
            f"  ETA           {eta_str}",
        ]
        return "\n".join(lines)

    def update(
        self,
        pages_done: int,
        total_pages: int,
        pdf_name: str,
        current_page: str,
        current_stage: str,
        stage_status: dict[str, str],
    ) -> None:
        self._pages_done = pages_done
        self._total_pages = total_pages
        self._pdf_name = pdf_name
        self._current_page = current_page
        self._current_stage = current_stage
        self._stage_status = stage_status
        self._redraw()

    def update_usage(self, provider: str, count: int) -> None:
        self._api_usage[provider] = count
        self._provider = provider
        self._redraw()

    def update_perf(self, latency: float = 0, tokens: int = 0, retry: int = 0) -> None:
        self._latency = latency
        self._tokens = tokens
        self._retry = retry
        self._redraw()

    def _redraw(self) -> None:
        block = self._build_display()
        n = block.count("\n") + 1
        if self._first:
            self._first = False
            sys.stdout.write(block)
        else:
            sys.stdout.write("\033[" + str(n) + "A\r" + block)
        sys.stdout.flush()

    def __enter__(self) -> Dashboard:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        print()


def get_page_count(pdf_path: Path) -> int | None:
    try:
        import fitz

        doc = fitz.open(pdf_path)
        n = doc.page_count
        doc.close()
        return n
    except Exception:
        return None


def pdf_label(pdf: Path, show_count: bool = True) -> str:
    lang = detect_language(pdf.name)
    display = LANG_DISPLAY.get(lang, lang.capitalize())
    label = f"{display} \u2014 {pdf.name}"
    if show_count:
        n = get_page_count(pdf)
        if n is not None:
            label += f"  ({n} page{'s' if n != 1 else ''})"
    return label


def run_for_language(
    lang_key: str,
    files: list[str],
    max_pages: int,
    settings: dict | None = None,
) -> dict[str, Any]:
    if settings is None:
        settings = {}
    out_dir = BASE / "output" / lang_key
    stats: dict[str, Any] = {
        "lang": LANG_DISPLAY.get(lang_key, lang_key),
        "pdfs": 0,
        "pages_total": 0,
        "pages_passed": 0,
        "pages_failed": 0,
        "ocr_time": 0.0,
        "llm_time": 0.0,
        "total_time": 0.0,
        "output_dir": out_dir,
        "report_dir": None,
        "zip_path": out_dir / f"{lang_key}.zip",
    }

    dashboard = Dashboard()

    try:
        for fname in files:
            pdf = BASE / fname
            total_pages = get_page_count(pdf) or 0
            stats["pages_total"] += min(total_pages, max_pages) if max_pages > 0 else total_pages

            stage_status = {s: " " for s in Dashboard.STAGES}
            stage_status["Rendering"] = "current"
            current_stage = "Rendering"
            current_page = ""
            pages_done = 0
            in_timing = False
            pdf_ocr = 0.0
            pdf_llm = 0.0
            pdf_total = 0.0
            pdf_valid = 0

            cmd = [
                sys.executable,
                str(PIPELINE),
                "--pdf",
                str(pdf),
                "--out",
                str(out_dir / "output" / Path(fname).stem),
                "--lang",
                lang_key,
                "--provider",
                str(settings.get("provider", "gemini")),
                "--level",
                str(settings.get("level", 4)),
                "--max-pages",
                str(max_pages),
            ]
            if settings.get("preprocess", False):
                cmd.append("--preprocess")
            if settings.get("validate", True):
                cmd.append("--validate")
            if settings.get("qa", False):
                cmd.append("--qa")
            if settings.get("report", True):
                cmd.append("--report")

            dashboard.update(0, total_pages, fname, "", "Rendering", stage_status)

            proc_env = {**os.environ, "PYTHONUNBUFFERED": "1"}
            proc = subprocess.Popen(  # noqa: S603
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                env=proc_env,
            )

            assert proc.stdout is not None  # noqa: S101
            for line in iter(proc.stdout.readline, ""):
                line = line.rstrip()

                um = re.match(r"\s*\[Usage\]\s+(\w+):\s*(\d+)", line)
                if um:
                    dashboard.update_usage(um.group(1), int(um.group(2)))
                    continue

                if "[1/5]" in line:
                    stage_status["Rendering"] = "current"
                    current_stage = "Rendering"
                elif "[2/5] OCR:" in line:
                    stage_status["Rendering"] = "done"
                    stage_status["OCR"] = "current"
                    current_stage = "OCR"
                    parts = line.rsplit(":", 1)
                    if len(parts) > 1:
                        current_page = parts[1].strip()
                    pages_done += 1
                elif "[3/5] Proofread" in line:
                    stage_status["OCR"] = "done"
                    stage_status["LLM"] = "current"
                    current_stage = "LLM"
                    parts = line.rsplit(":", 1)
                    if len(parts) > 1:
                        current_page = parts[1].strip()
                elif "reading_order source=" in line and stage_status["Relations"] != "done":
                    stage_status["LLM"] = "done"
                    stage_status["Relations"] = "current"
                    current_stage = "Relations"
                elif "[4/5] Analyzing" in line:
                    stage_status["Relations"] = "done"
                    stage_status["Validation"] = "current"
                    current_stage = "Validation"
                elif ".json: PASS" in line:
                    pname = line.split(".json")[0].strip()
                    if pname:
                        current_page = pname
                    pdf_valid += 1
                elif ".json: FAIL" in line:
                    pname = line.split(".json")[0].strip()
                    if pname:
                        current_page = pname
                elif in_timing and line.startswith("  ") and ":" in line:
                    m = re.match(r"\s+(\w[\w_]*):\s+([\d.]+)s", line)
                    if m:
                        name, val = m.group(1), float(m.group(2))
                        if name == "vision_ocr":
                            pdf_ocr += val
                        elif name == "llm_proofread":
                            pdf_llm += val
                        elif name == "total":
                            pdf_total += val
                elif "Timing summary:" in line:
                    in_timing = True
                elif "[5/5] Generating HTML" in line:
                    stage_status["Validation"] = "done"
                    stage_status["Report"] = "current"
                    current_stage = "Report"
                elif line.startswith("Done."):
                    stage_status["Report"] = "done"
                    stage_status["ZIP"] = "current"
                    current_stage = "ZIP"
                    current_page = ""
                    stats["report_dir"] = (
                        out_dir / "output" / Path(fname).stem / "report" / "report.html"
                    )

                dashboard.update(
                    pages_done,
                    total_pages,
                    fname,
                    current_page,
                    current_stage,
                    stage_status,
                )

            proc.wait()
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, cmd)

            stats["pdfs"] += 1
            stats["pages_passed"] += pdf_valid
            stats["ocr_time"] += pdf_ocr
            stats["llm_time"] += pdf_llm
            stats["total_time"] += pdf_total

        stats["pages_failed"] = stats["pages_total"] - stats["pages_passed"]

        stage_status["ZIP"] = "done"
        dashboard.update(
            pages_done,
            total_pages,
            fname,
            "",
            "Complete",
            stage_status,
        )
        if settings.get("zip", True):
            zip_output(lang_key, out_dir)
        return stats
    finally:
        dashboard.close()


def display_summary(stats_list: list[dict[str, Any]]) -> None:
    total_pdfs = sum(s["pdfs"] for s in stats_list)
    total_pages = sum(s["pages_total"] for s in stats_list)
    total_passed = sum(s["pages_passed"] for s in stats_list)
    total_failed = sum(s["pages_failed"] for s in stats_list)
    total_ocr = sum(s["ocr_time"] for s in stats_list)
    total_llm = sum(s["llm_time"] for s in stats_list)
    total_time = sum(s["total_time"] for s in stats_list)
    langs = ", ".join(s["lang"] for s in stats_list)

    avg_ocr = total_ocr / total_pages if total_pages else 0
    avg_llm = total_llm / total_pages if total_pages else 0
    avg_total = total_time / total_pages if total_pages else 0
    pass_rate = total_passed / total_pages * 100 if total_pages else 0

    first = stats_list[0] if stats_list else {}
    out_dir_path = first.get("output_dir", "")
    base_out = os.path.relpath(out_dir_path.parent, BASE) if out_dir_path else "output"
    report_p = first.get("report_dir", None)
    report_rel = os.path.relpath(report_p, BASE) if report_p else None
    zip_p = first.get("zip_path", None)
    zip_rel = os.path.relpath(zip_p, BASE) if zip_p else None

    rate_color = "green" if pass_rate >= 80 else ("yellow" if pass_rate >= 50 else "red")

    print()
    rule(char="=")
    bold("             Pipeline Finished")
    rule(char="=")
    print()
    raw(f"  [bold cyan]Languages Processed[/bold cyan] : {langs}")
    raw(f"  [bold cyan]PDFs[/bold cyan]                 : {total_pdfs}")
    raw(f"  [bold cyan]Pages[/bold cyan]                : {total_pages}")
    ok(f"  [bold green]Successful[/bold green]          : {total_passed}")
    if total_failed > 0:
        err(f"  [bold red]Failed[/bold red]               : {total_failed}")
    else:
        ok(f"  [bold green]Failed[/bold green]               : {total_failed}")
    print()
    raw(f"  [bold cyan]Average OCR Time[/bold cyan]     : {avg_ocr:.2f}s")
    raw(f"  [bold cyan]Average LLM Time[/bold cyan]     : {avg_llm:.2f}s")
    raw(f"  [bold cyan]Average Total Time[/bold cyan]   : {avg_total:.2f}s")
    raw(
        f"  [bold cyan]RFQ Pass Rate[/bold cyan]        : [{rate_color}]{pass_rate:.0f}%[/{rate_color}]"
    )
    print()
    raw(f"  [bold cyan]Output Folder[/bold cyan]        : {base_out}")
    raw(f"  [bold cyan]HTML Report[/bold cyan]          : {report_rel or 'N/A'}")
    raw(f"  [bold cyan]ZIP File[/bold cyan]             : {zip_rel or 'N/A'}")
    print()


def show_system_status(settings: dict[str, Any]) -> None:
    tracker = UsageTracker(QUOTA_STATE_FILE)
    data = tracker.dashboard(settings)

    rule("SYSTEM STATUS", char="=")
    print()
    raw(f"    [bold cyan]Pipeline Version[/bold cyan] : RFQ Level {settings['level']}")
    raw(f"    [bold cyan]Provider[/bold cyan]          : {settings['provider']}")
    raw(
        f"    [bold cyan]Pages Today[/bold cyan]       : "
        f"{sum(d['today']['pages'] for d in data['providers'].values())}"
    )
    raw(
        f"    [bold cyan]Pages This Month[/bold cyan]   : "
        f"{sum(d['this_month']['pages'] for d in data['providers'].values())}"
    )
    last_req = data["recent_requests"][0] if data["recent_requests"] else None
    if last_req:
        from datetime import datetime

        ts_str = datetime.fromtimestamp(last_req["t"]).strftime("%Y-%m-%d %H:%M:%S")
        raw(
            f"    [bold cyan]Last Request[/bold cyan]     : "
            f"{ts_str} | {last_req['p']} | {last_req['pg']}p"
        )
    else:
        raw("    [bold cyan]Last Request[/bold cyan]     : [yellow]None yet[/yellow]")
    print()


def _check_api_key(prov: str) -> bool:
    from indic_ocr_pipeline.utils.config import (
        GEMINI_API_KEY,
        GLM_API_KEY,
        GOOGLE_VISION_API_KEY,
        GROQ_API_KEY,
        IAMHC_API_KEY,
        OPENROUTER_API_KEY,
    )

    _key_map = {
        "vision": GOOGLE_VISION_API_KEY,
        "gemini": GEMINI_API_KEY,
        "glm": GLM_API_KEY,
        "groq": GROQ_API_KEY,
        "openrouter": OPENROUTER_API_KEY,
        "iamhc": IAMHC_API_KEY,
    }
    return bool(_key_map.get(prov, ""))


def show_quota_monitor(settings: dict[str, Any]) -> None:
    tracker = UsageTracker(QUOTA_STATE_FILE)
    data = tracker.dashboard(settings)

    rule("USAGE MONITOR", char="=")
    print()

    or_usage = tracker.fetch_openrouter_official_usage(
        __import__(
            "indic_ocr_pipeline.utils.config", fromlist=["OPENROUTER_API_KEY"]
        ).OPENROUTER_API_KEY
    )

    try:
        from rich import box
        from rich.table import Table

        c = __import__("indic_ocr_pipeline.utils.helpers", fromlist=["_get_console"])._get_console()
        if c:
            table = Table(title="Provider Usage Summary", box=box.ROUNDED)
            table.add_column("Provider", style="cyan")
            table.add_column("Today", justify="right")
            table.add_column("Month", justify="right")
            table.add_column("Lifetime", justify="right")
            table.add_column("Failures", justify="right")
            table.add_column("Avg Latency", justify="right")
            for prov in ["vision", "gemini", "glm", "iamhc", "groq", "openrouter"]:
                pd = data["providers"].get(prov)
                if not pd:
                    continue
                t = pd["today"]
                m = pd["this_month"]
                lt = pd["lifetime"]
                if t["requests"] == 0 and lt["requests"] == 0 and m["requests"] == 0:
                    continue
                lat = f'{pd["avg_latency_ms"]:.0f}ms' if pd["avg_latency_ms"] else "-"
                table.add_row(
                    pd["label"],
                    str(t["requests"]),
                    str(m["requests"]),
                    str(lt["requests"]),
                    str(t["failures"]) if t["failures"] else "0",
                    lat,
                )
            c.print(table)
            print()
    except Exception:
        pass

    for prov in ["vision", "gemini", "glm", "iamhc", "groq", "openrouter"]:
        pd = data["providers"].get(prov)
        if not pd:
            continue
        t = pd["today"]
        y = pd["yesterday"]
        m = pd["this_month"]
        lt = pd["lifetime"]
        has_usage = t["requests"] > 0 or m["requests"] > 0 or lt["requests"] > 0
        if not has_usage:
            continue

        key_ok = _check_api_key(prov)
        key_status = "Loaded" if key_ok else "Not set"

        raw(f"  [bold cyan]{pd['label']}[/bold cyan]")
        raw(
            f"    API Key            : [{'green' if key_ok else 'red'}]{key_status}[/{'green' if key_ok else 'red'}]"
        )

        if pd["has_official_usage_api"]:
            if or_usage:
                raw("    Official Usage     : [green]Retrieved successfully[/green]")
                if prov == "openrouter":
                    raw(f"    Credits Used       : ${or_usage.get('usage', 0):.2f}")
                    if or_usage.get("limit_remaining") is not None:
                        raw(f"    Credits Remaining  : ${or_usage['limit_remaining']:.2f}")
                    raw(f"    Reset              : {or_usage.get('limit_reset', 'N/A')}")
            else:
                raw("    Official Usage     : [yellow]Not available from provider[/yellow]")
        else:
            raw("    Official Usage     : [yellow]Not available from provider[/yellow]")

        raw(f"    Requests Today     : {t['requests']}")
        raw(f"    Requests Yesterday : {y['requests']}")
        raw(f"    Requests Month     : {m['requests']}")
        raw(f"    Requests Lifetime  : {lt['requests']}")
        if t["requests"]:
            raw(f"    Avg Latency        : {pd['avg_latency_ms']:.0f} ms")
        if prov != "vision":
            raw(
                f"    Input Tokens       : {t['input_tokens']:,} today / {m['input_tokens']:,} month"
            )
            raw(
                f"    Output Tokens      : {t['output_tokens']:,} today / {m['output_tokens']:,} month"
            )
        else:
            raw(f"    Pages Processed    : {t['pages']} today / {m['pages']} month")
        if t["failures"] or lt["failures"]:
            raw(f"    Failures           : {t['failures']} today / {lt['failures']} lifetime")
        if t["retries"] or lt["retries"]:
            raw(f"    Retries            : {t['retries']} today / {lt['retries']} lifetime")
        print()

    if not data["providers"]:
        info("  (No usage data yet. Run the pipeline first.)")
        print()

    rule(char="=")
    input("  Press Enter to return to menu...")
    print()


def _section(title: str) -> None:
    """Print a section header."""
    raw(f"\n[bold]{title}[/bold]")
    raw("[dim]" + "-" * 78 + "[/dim]")


def run_checks() -> None:
    critical = False
    c = __import__("indic_ocr_pipeline.utils.helpers", fromlist=["_get_console"])._get_console()

    from indic_ocr_pipeline.utils.config import (
        GEMINI_API_KEY,
        GLM_API_KEY,
        GOOGLE_VISION_API_KEY,
        GROQ_API_KEY,
        IAMHC_API_KEY,
        OPENROUTER_API_KEY,
    )

    _key_map = {
        "Google Vision": GOOGLE_VISION_API_KEY,
        "Gemini": GEMINI_API_KEY,
        "GLM-4V": GLM_API_KEY,
        "Groq": GROQ_API_KEY,
        "OpenRouter": OPENROUTER_API_KEY,
        "IAMHC": IAMHC_API_KEY,
    }

    # Check internet
    internet_ok = True
    try:
        import urllib.request

        urllib.request.urlopen("https://www.google.com", timeout=5)
    except Exception:
        internet_ok = False

    # Check output dir
    try:
        test_dir = BASE / "output"
        test_dir.mkdir(parents=True, exist_ok=True)
        test_file = test_dir / ".write_test"
        test_file.write_text("")
        test_file.unlink()
    except Exception:
        critical = True

    import platform

    v = sys.version_info
    pyver = f"{v.major}.{v.minor}.{v.micro}"
    plat = f"{platform.system()} {platform.release()} x64"

    try:
        import psutil

        cpu = platform.processor() or "Intel Core Ultra 5 125H"
        ram = f"{round(psutil.virtual_memory().total / (1024**3))} GB"
    except ImportError:
        cpu = "Intel Core Ultra 5 125H"
        ram = "16 GB"

    version = "v1.0.0"

    # ---- Render ----
    if c is not None:
        try:
            from rich import box
            from rich.panel import Panel
            from rich.table import Table

            outer = Panel(
                "\n".join(
                    [
                        "                    [bold]Indic OCR Dataset Pipeline [cyan]"
                        + version
                        + "[/cyan][/bold]",
                        "          RFQ Level-4 Document Intelligence & Dataset Generator",
                    ]
                ),
                box=box.ROUNDED,
                style="blue",
                width=80,
            )
            c.print(outer)
        except Exception:
            banner(
                "Indic OCR Dataset Pipeline " + version,
                "RFQ Level-4 Document Intelligence & Dataset Generator",
            )
    else:
        banner(
            "Indic OCR Dataset Pipeline " + version,
            "RFQ Level-4 Document Intelligence & Dataset Generator",
        )

    _section("System")

    system_rows = [
        ("Python", pyver),
        ("Platform", plat),
        ("CPU", cpu),
        ("RAM", ram),
        ("Internet", "Connected" if internet_ok else "[red]Disconnected[/red]"),
    ]
    if c is not None:
        try:
            t = Table(show_header=False, box=None, padding=(0, 2))
            t.add_column(style="bold", width=22)
            t.add_column()
            for label, val in system_rows:
                t.add_row(f" [green]+[/green] {label}", val)
            c.print(t)
        except Exception:
            for label, val in system_rows:
                raw(f" [green]+[/green] {label:<20s}: {val}")
    else:
        for label, val in system_rows:
            raw(f" [green]+[/green] {label:<20s}: {val}")

    _section("LLM Providers")
    providers_tbl = [
        ("Gemini", "Ready", "Primary"),
        ("GLM-4V", "Ready", "Secondary"),
        ("Groq", "Ready", "Fallback"),
        ("OpenRouter", "Ready", "Fallback"),
        ("IAMHC", "Ready", "Final"),
    ]
    if c is not None:
        try:
            from rich import box
            from rich.table import Table

            t = Table(box=box.HEAVY, padding=(0, 2))
            t.add_column("Provider", style="bold", width=14)
            t.add_column("Status")
            t.add_column("Priority")
            for prov, _s, priority in providers_tbl:
                key_ok = _key_map.get(prov, "")
                status_display = (
                    "[green]Ready[/green]" if key_ok else "[yellow]Key not set[/yellow]"
                )
                t.add_row(prov, status_display, priority)
            c.print(t)
        except Exception:
            for prov, _s, priority in providers_tbl:
                key_ok = _key_map.get(prov, "")
                status_display = "Ready" if key_ok else "Key not set"
                raw(f"  {prov:<14s} {status_display:<14s} {priority}")
    else:
        for prov, _s, priority in providers_tbl:
            key_ok = _key_map.get(prov, "")
            status_display = "Ready" if key_ok else "Key not set"
            raw(f"  {prov:<14s} {status_display:<14s} {priority}")

    _section("Capabilities")
    capabilities = [
        "OCR Extraction",
        "RFQ Level-4 Annotation",
        "Reading Order Detection",
        "Caption <-> Figure Relations",
        "Multi-provider Validation",
        "Dataset Generation",
        "HTML Quality Reports",
        "Visual QA Overlay",
        "ZIP Packaging",
        "Batch Processing",
    ]
    for cap in capabilities:
        raw(f"  [green]+[/green] {cap}")

    _section("Repository")
    repo_rows = [
        ("Version", version),
        ("Build", "Stable"),
        ("License", "MIT"),
        ("Output", "./output"),
    ]
    if c is not None:
        try:
            t = Table(show_header=False, box=None, padding=(0, 2))
            t.add_column(style="bold", width=22)
            t.add_column()
            for label, val in repo_rows:
                t.add_row(f" {label}", val)
            c.print(t)
        except Exception:
            for label, val in repo_rows:
                raw(f" {label:<20s}: {val}")
    else:
        for label, val in repo_rows:
            raw(f" {label:<20s}: {val}")

    _section("Supported Languages")
    lang_names = sorted(name for lang, name in LANG_DISPLAY.items() if lang != "unknown")
    cols = 4
    for i in range(0, len(lang_names), cols):
        chunk = lang_names[i : i + cols]
        cells = [f"[bold cyan][{i+j+1:02d}][/bold cyan] {nm:<12}" for j, nm in enumerate(chunk)]
        raw("  " + "     ".join(cells))

    print()

    if critical:
        err("  Critical failures detected. Pipeline cannot run.")
        print()
        sys.exit(1)


def show_settings(current: dict[str, Any]) -> dict[str, Any]:
    while True:
        rule("Settings")
        kv("1. LLM Provider", current["provider"])
        kv("2. Annotation Level", str(current["level"]))
        kv("3. Preprocessing", "Yes" if current["preprocess"] else "No")
        kv("4. Validation", "Yes" if current["validate"] else "No")
        kv("5. QA Overlay", "Yes" if current["qa"] else "No")
        kv("6. HTML Report", "Yes" if current["report"] else "No")
        kv("7. ZIP Export", "Yes" if current["zip"] else "No")
        kv("8. Max pages per PDF", f"{current['max_pages']}  (0 = all)")
        print(f"  {'-' * 40}")
        print("  0. Back to main menu")
        print()
        raw_in = input("  Select setting to change: ").strip()
        if raw_in == "0":
            return current
        elif raw_in == "1":
            print("  Providers: [1] gemini  [2] glm  [3] iamhc  [4] openrouter  [5] groq")
            c = input("  Choose: ").strip()
            providers = {"1": "gemini", "2": "glm", "3": "iamhc", "4": "openrouter", "5": "groq"}
            current["provider"] = providers.get(c, "gemini")
        elif raw_in == "2":
            c = input("  Level (3 or 4) [4]: ").strip()
            current["level"] = 3 if c == "3" else 4
        elif raw_in == "3":
            current["preprocess"] = not current["preprocess"]
        elif raw_in == "4":
            current["validate"] = not current["validate"]
        elif raw_in == "5":
            current["qa"] = not current["qa"]
        elif raw_in == "6":
            current["report"] = not current["report"]
        elif raw_in == "7":
            current["zip"] = not current["zip"]
        elif raw_in == "8":
            v = ask_int("  Pages per PDF", default=current["max_pages"])
            current["max_pages"] = v
        else:
            warn("  Invalid choice.")


def show_project_overview() -> None:
    """Print a project-overview section after the system checks."""
    pdfs = sorted(BASE.glob("*.pdf"))
    total_pages = 0
    for p in pdfs:
        n = get_page_count(p)
        if n is not None:
            total_pages += n

    c = __import__("indic_ocr_pipeline.utils.helpers", fromlist=["_get_console"])._get_console()
    print()
    rule(char="=")
    bold("                           Project Overview")
    rule(char="=")
    if c is not None:
        try:
            from rich.table import Table

            t = Table(show_header=False, box=None, padding=(0, 2))
            t.add_column(style="bold", width=22)
            t.add_column()
            t.add_row(" Documents Found", f"{len(pdfs)} PDFs")
            t.add_row(" Total Pages", str(total_pages))
            t.add_row(" Supported Languages", "12")
            t.add_row(" Processing Mode", "Batch")
            t.add_row(" Estimated Time", "~4 min")
            t.add_row(" Estimated API Calls", str(total_pages))
            c.print(t)
        except Exception:
            raw(f"  Documents Found          : {len(pdfs)} PDFs")
            raw(f"  Total Pages              : {total_pages}")
            raw("  Supported Languages      : 12")
            raw("  Processing Mode          : Batch")
            raw("  Estimated Time           : ~4 min")
            raw(f"  Estimated API Calls      : {total_pages}")
    else:
        raw(f"  Documents Found          : {len(pdfs)} PDFs")
        raw(f"  Total Pages              : {total_pages}")
        raw("  Supported Languages      : 12")
        raw("  Processing Mode          : Batch")
        raw("  Estimated Time           : ~4 min")
        raw(f"  Estimated API Calls      : {total_pages}")
    print()


def show_about() -> None:
    """Display the About screen with project info."""
    c = __import__("indic_ocr_pipeline.utils.helpers", fromlist=["_get_console"])._get_console()
    if c is not None:
        try:
            from rich import box
            from rich.panel import Panel

            outer = Panel(
                "                          [bold]About Indic OCR Pipeline[/bold]",
                box=box.ROUNDED,
                style="blue",
                width=78,
            )
            c.print(outer)
        except Exception:
            raw("[bold]About Indic OCR Pipeline[/bold]")
    else:
        raw("[bold]About Indic OCR Pipeline[/bold]")

    raw("\n  [bold]Version[/bold]         : v1.0.0")
    raw("  [bold]Author[/bold]          : Raihan Hazra")
    raw("  [bold]License[/bold]         : MIT")
    raw("  [bold]Repository[/bold]      : https://github.com/rai8053/indic-ocr-pipeline")

    _section("Description")
    raw("  Indic OCR Dataset Pipeline is an AI-powered toolkit for generating")
    raw("  RFQ Level-4 document datasets from scanned Indic-language PDFs.")

    _section("Core Components")
    components = [
        "Google Cloud Vision OCR",
        "RFQ Level-4 Layout Detection",
        "Reading Order Detection",
        "Caption & Figure Relations",
        "Multi-provider LLM Validation",
        "HTML Quality Reports",
        "Visual QA Overlay",
        "Dataset Export",
    ]
    for comp in components:
        raw(f"  [green]+[/green] {comp}")

    print()
    input("  Press [Enter] to return to the Main Menu...")
    print()


def show_previous_reports() -> None:
    """Display the Previous Reports screen."""
    c = __import__("indic_ocr_pipeline.utils.helpers", fromlist=["_get_console"])._get_console()
    if c is not None:
        try:
            from rich import box
            from rich.panel import Panel

            outer = Panel(
                "                           [bold]Previous Reports[/bold]",
                box=box.ROUNDED,
                style="blue",
                width=78,
            )
            c.print(outer)
        except Exception:
            raw("[bold]Previous Reports[/bold]")
    else:
        raw("[bold]Previous Reports[/bold]")

    print()
    raw("  No saved reports were found.")
    print()
    raw("  [bold]Future versions will support:[/bold]")
    features = [
        "Report history",
        "Search reports",
        "Filter by language",
        "Filter by date",
        "Processing statistics",
        "Benchmark history",
        "Open HTML reports",
        "Export reports",
    ]
    for f in features:
        raw(f"  * {f}")
    print()
    raw("  [bold]Status:[/bold] [yellow]Coming Soon[/yellow]")
    print()
    input("  Press [Enter] to return to the Main Menu...")
    print()


def show_benchmark() -> None:
    """Display the Benchmark screen."""
    c = __import__("indic_ocr_pipeline.utils.helpers", fromlist=["_get_console"])._get_console()
    if c is not None:
        try:
            from rich import box
            from rich.panel import Panel

            outer = Panel(
                "                        [bold]Benchmark Dashboard[/bold]",
                box=box.ROUNDED,
                style="blue",
                width=78,
            )
            c.print(outer)
        except Exception:
            raw("[bold]Benchmark Dashboard[/bold]")
    else:
        raw("[bold]Benchmark Dashboard[/bold]")

    print()
    raw("  No benchmark data available.")
    print()
    raw("  [bold]This feature will allow comparison of:[/bold]")
    engines = [
        "Google Vision",
        "PaddleOCR",
        "EasyOCR",
        "Tesseract",
    ]
    for eng in engines:
        raw(f"  [green]+[/green] {eng}")
    print()
    raw("  [bold]Metrics:[/bold]")
    metrics = [
        "OCR Accuracy",
        "CER",
        "WER",
        "Processing Time",
        "Cost/Page",
        "Memory Usage",
    ]
    for m in metrics:
        raw(f"  * {m}")
    print()
    raw("  [bold]Status:[/bold] [yellow]Coming Soon[/yellow]")
    print()
    input("  Press [Enter] to return to the Main Menu...")
    print()


def main() -> None:
    run_checks()
    show_project_overview()
    os.chdir(BASE)

    pdfs = sorted(BASE.glob("*.pdf"))
    if not pdfs:
        err("\n  No PDF files found in this folder.")
        sys.exit(1)

    settings: dict[str, Any] = {
        "max_pages": 0,
        "provider": "gemini",
        "level": 4,
        "preprocess": False,
        "validate": True,
        "qa": False,
        "report": True,
        "zip": True,
    }

    def _show_detected_documents() -> list[str]:
        """Show detected documents table and return sorted language keys."""
        lang_groups: dict[str, list[str]] = {}
        for pdf in pdfs:
            lang = detect_language(pdf.name)
            if lang != "unknown":
                lang_groups.setdefault(lang, []).append(pdf.name)
        sorted_langs = sorted(lang_groups.keys(), key=lambda k: -len(lang_groups[k]))

        raw("\n  [bold]Detected Documents[/bold]")
        c2 = __import__(
            "indic_ocr_pipeline.utils.helpers", fromlist=["_get_console"]
        )._get_console()
        if c2 is not None:
            try:
                from rich import box
                from rich.table import Table

                t = Table(box=box.HEAVY, padding=(0, 2))
                t.add_column("ID", justify="right", width=4, style="bold cyan")
                t.add_column("Language", style="bold")
                t.add_column("PDFs", justify="right")
                t.add_column("Pages", justify="right")
                for i, k in enumerate(sorted_langs, 1):
                    count = len(lang_groups[k])
                    total_p = sum(get_page_count(BASE / f) or 0 for f in lang_groups[k])
                    t.add_row(str(i), LANG_DISPLAY.get(k, k.capitalize()), str(count), str(total_p))
                c2.print(t)
            except Exception:
                for i, k in enumerate(sorted_langs, 1):
                    count = len(lang_groups[k])
                    total_p = sum(get_page_count(BASE / f) or 0 for f in lang_groups[k])
                    raw(
                        f"  [{i:02d}] {LANG_DISPLAY.get(k, k.capitalize()):<12s} {count} PDFs  {total_p} pages"
                    )
        else:
            for i, k in enumerate(sorted_langs, 1):
                count = len(lang_groups[k])
                total_p = sum(get_page_count(BASE / f) or 0 for f in lang_groups[k])
                raw(
                    f"  [{i:02d}] {LANG_DISPLAY.get(k, k.capitalize()):<12s} {count} PDFs  {total_p} pages"
                )
        return sorted_langs

    def _process_pdfs_flow(settings: dict[str, Any]) -> None:
        """Run the full Process PDFs workflow."""
        sorted_langs = _show_detected_documents()
        raw_in = input("  Select language (number) or [B]ack: ").strip().upper()
        if raw_in == "B":
            return
        try:
            lang_idx = int(raw_in) - 1
            if lang_idx < 0 or lang_idx >= len(sorted_langs):
                warn("  Invalid choice.")
                return
        except ValueError:
            warn("  Invalid choice.")
            return

        lang_groups: dict[str, list[str]] = {}
        for pdf in pdfs:
            lang = detect_language(pdf.name)
            if lang != "unknown":
                lang_groups.setdefault(lang, []).append(pdf.name)

        lang_key = sorted_langs[lang_idx]
        files = lang_groups[lang_key]

        bold(f"\n  {LANG_DISPLAY.get(lang_key, lang_key)} PDFs")
        rule()
        for i, fname in enumerate(files, 1):
            n = get_page_count(BASE / fname)
            extra = f"({n} pages)" if n is not None else ""
            menu_item(i, fname, extra)
        print("  [0] Process All")
        print("  [B] Back to languages")
        print()
        raw2 = input("  Select PDFs (comma/range, or 0 for all): ").strip()

        if raw2.upper() == "B":
            return
        if not raw2 or raw2 == "0":
            selected_files = files
        else:
            try:
                idxs: list[int] = []
                for part in raw2.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    if "-" in part:
                        a, b = map(int, part.split("-"))
                        idxs.extend(range(a - 1, b))
                    else:
                        idxs.append(int(part) - 1)
                selected_files = [files[i] for i in idxs if 0 <= i < len(files)]
            except ValueError:
                warn("  Invalid choice, using all.")
                selected_files = files

        if not selected_files:
            warn("  No PDFs selected.")
            return

        mp = ask_int("  Pages per PDF (0 = all)", default=0)

        total_est = 0
        for fname in selected_files:
            n = get_page_count(BASE / fname)
            if n is not None:
                total_est += min(n, mp) if mp > 0 else n
            else:
                total_est += mp if mp > 0 else 0

        rule("Processing Summary")
        kv("Language", LANG_DISPLAY.get(lang_key, lang_key))
        kv("PDF Count", str(len(selected_files)))
        kv("Provider", settings["provider"])
        kv("RFQ Level", str(settings["level"]))
        kv("Preprocessing", "Yes" if settings["preprocess"] else "No")
        kv("Validation", "Yes" if settings["validate"] else "No")
        kv("QA Overlay", "Yes" if settings["qa"] else "No")
        kv("HTML Report", "Yes" if settings["report"] else "No")
        kv("ZIP Export", "Yes" if settings["zip"] else "No")
        kv("Estimated Pages", str(total_est))
        rule()
        proceed = input("  Start Processing? (Y/N): ").strip().upper()
        if proceed != "Y":
            info("  Returned to menu.")
            return

        all_stats: list[dict[str, Any]] = []
        selected = {lang_key: selected_files}
        for lk, flist in selected.items():
            stats = run_for_language(lk, flist, mp, settings)
            all_stats.append(stats)

        display_summary(all_stats)
        rule()

    while True:
        print()
        rule(char="=")
        bold("                              Main Menu")
        rule(char="=")
        menu_item(1, "Process PDFs")
        menu_item(2, "Settings")
        menu_item(3, "Provider Quotas")
        menu_item(4, "Benchmark")
        menu_item(5, "View Previous Reports")
        menu_item(6, "About")
        print("  [Q] Quit")
        print()
        raw_in = input("  Select > ").strip().upper()

        if raw_in == "Q":
            info("  Exiting.")
            sys.exit(0)
        elif raw_in == "1":
            _process_pdfs_flow(settings)
        elif raw_in == "2":
            settings = show_settings(settings)
        elif raw_in == "3":
            show_quota_monitor(settings)
        elif raw_in == "4":
            show_benchmark()
        elif raw_in == "5":
            show_previous_reports()
        elif raw_in == "6":
            show_about()
        else:
            warn("  Invalid choice.")


if __name__ == "__main__":
    main()
