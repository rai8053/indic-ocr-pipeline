import os, sys, subprocess, zipfile, re, shutil, time
from pathlib import Path

from indic_ocr_pipeline.utils.helpers import (
    banner,
    rule,
    info,
    ok,
    warn,
    err,
    bold,
    raw,
    _get_console,
)
from indic_ocr_pipeline.utils.config import QUOTA_STATE_FILE
from indic_ocr_pipeline.utils.usage import UsageTracker, PROVIDER_INFO

BASE = Path(__file__).resolve().parent
PIPELINE = BASE / "indic_ocr_pipeline3.py"

LANG_DISPLAY = {
    "odia": "Odia",
    "marathi": "Marathi",
    "telugu": "Telugu",
    "tamil": "Tamil",
    "unknown": "Unknown",
}

LANG_PATTERNS = {
    "odia": [r"(?i)odia|oriya|bhougalika|sagyan|prakarana"],
    "marathi": [r"(?i)marathi|baldarshan"],
    "telugu": [r"(?i)telugu|adikaara|basha"],
    "tamil": [r"(?i)tamil|tnla"],
}


def detect_language(fname):
    fname_lower = fname.lower()
    for lang, patterns in LANG_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, fname_lower):
                return lang
    return "unknown"


def print_banner(available_langs):
    langs_str = "\n  " + "\n  ".join(
        f"* {LANG_DISPLAY.get(l, l.capitalize())}" for l in sorted(available_langs)
    )
    banner("OCR PAGE", "RFQ Level 4 Pipeline")
    rule("Supported Languages")
    info(langs_str)
    rule("Features")
    print(
        "  +  OCR (Google Cloud Vision)\n"
        "  +  Level 4 Annotation (Gemini / GLM)\n"
        "  +  Validation & Scoring\n"
        "  +  Visual QA Overlay\n"
        "  +  HTML Quality Report\n"
        "  +  ZIP Export"
    )
    rule()


def choose(prompt, options, multi=False):
    for i, (label, _) in enumerate(options, 1):
        print(f"  [{i}] {label}")
    print(f"  [0] {'Process All' if multi else 'Cancel'}")
    while True:
        try:
            raw = input(f"{prompt}: ").strip()
            if multi:
                if raw == "0":
                    return list(range(len(options)))
                indices = []
                for part in raw.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    if "-" in part:
                        a, b = map(int, part.split("-"))
                        indices.extend(range(a - 1, b))
                    else:
                        indices.append(int(part) - 1)
                return [i for i in indices if 0 <= i < len(options)]
            else:
                idx = int(raw)
                if idx == 0:
                    return None
                if 1 <= idx <= len(options):
                    return idx - 1
        except (ValueError, IndexError):
            pass
        warn("  Invalid choice, try again.")


def ask_int(prompt, default=0):
    raw = input(f"{prompt} [{default}]: ").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def zip_output(lang_key, lang_dir):
    zip_name = lang_dir / f"{lang_key}.zip"
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
        for fpath in lang_dir.rglob("*"):
            if fpath.is_file() and fpath != zip_name:
                zf.write(fpath, fpath.relative_to(lang_dir))
    ok(f"  Created: {zip_name}")


class Dashboard:
    STAGES = ["Rendering", "OCR", "LLM", "Relations", "Validation", "QA", "Report", "ZIP"]

    def __init__(self, total_pages=0):
        self._start = time.time()
        self._pages_done = 0
        self._total_pages = total_pages
        self._pdf_name = ""
        self._current_page = ""
        self._current_stage = ""
        self._stage_status = {s: " " for s in self.STAGES}
        self._api_usage = {}
        self._has_rich = False
        self._first_ascii = True

        try:
            from rich.console import Console as _RC
            from rich.live import Live as _RL
            from rich.progress import Progress as _RP, BarColumn as _RB, TextColumn as _RTC
            from rich.progress import TimeElapsedColumn as _RTE, TimeRemainingColumn as _RTR
            from rich.table import Table as _RT
            from rich.text import Text as _RText
            from rich.console import Group as _RGroup

            self._has_rich = True
            self._RText = _RText
            self._RT = _RT
            self._RGroup = _RGroup
            self._progress = _RP(
                _RTC("{task.completed}/{task.total}"),
                _RB(),
                _RTC("{task.percentage:>3.0f}%"),
                _RTE(),
                _RTR(),
            )
            self._task = self._progress.add_task("", total=max(total_pages, 1))
            self._live = _RL(self._build_rich(), refresh_per_second=4)
            self._live.start()
        except ImportError:
            pass

    def _build_rich(self):
        if self._total_pages:
            self._progress.update(self._task, completed=self._pages_done, total=self._total_pages)

        info = self._RT.grid(padding=(0, 2))
        info.add_column(style="bold cyan")
        info.add_column()
        info.add_row("PDF:", self._pdf_name or "(waiting)")
        info.add_row(
            "Page:",
            self._RText.assemble(
                (self._current_page or "--", "bold"),
                "     ",
                ("Stage:", "dim"),
                " ",
                (self._current_stage or "--", "bold blue"),
            ),
        )

        stages_cells = [self._RText("Stages: ", style="bold")]
        for s in self.STAGES:
            st = self._stage_status.get(s, " ")
            if st == "done":
                stages_cells.append(self._RText(f"[OK] {s}  ", style="green"))
            elif st == "current":
                stages_cells.append(self._RText(f">> {s}  ", style="bold blue"))
            else:
                stages_cells.append(self._RText(f"[ ] {s}  ", style="dim"))
        stages = self._RT.grid()
        stages.add_row(self._RText.assemble(*stages_cells))

        usage_cells = [self._RText("API: ", style="bold")]
        for prov, count in sorted(self._api_usage.items()):
            usage_cells.append(self._RText(f"{prov}:{count}  ", style="yellow"))
        usage = self._RT.grid()
        if self._api_usage:
            usage.add_row(self._RText.assemble(*usage_cells))

        return (
            self._RGroup(info, self._progress, stages, usage)
            if self._api_usage
            else self._RGroup(info, self._progress, stages)
        )

    def _build_ascii(self):
        try:
            cols = shutil.get_terminal_size().columns
        except Exception:
            cols = 80
        bar_w = min(cols - 35, 40)
        bar_w = max(bar_w, 10)
        pct = self._pages_done / self._total_pages if self._total_pages > 0 else 0
        filled = int(bar_w * pct)
        bar = "#" * filled + " " * (bar_w - filled)

        elapsed = time.time() - self._start
        e_min, e_sec = int(elapsed // 60), int(elapsed % 60)
        elapsed_str = f"{e_min:02d}:{e_sec:02d}"
        if self._pages_done > 0 and self._total_pages > 0:
            eta = elapsed / self._pages_done * (self._total_pages - self._pages_done)
            eta_str = f"{int(eta // 60):02d}:{int(eta % 60):02d}"
        else:
            eta_str = "--:--"

        stage_parts = []
        for s in self.STAGES:
            st = self._stage_status.get(s, " ")
            if st == "done":
                stage_parts.append(f"[OK] {s}")
            elif st == "current":
                stage_parts.append(f">> {s}")
            else:
                stage_parts.append(f"[ ] {s}")

        lines = [
            f"  PDF: {self._pdf_name}",
            f"  Page: {self._current_page or '--'}     Stage: {self._current_stage}",
            f"  [{bar}]  {self._pages_done}/{self._total_pages}  {pct*100:.0f}%",
            f"  Elapsed: {elapsed_str}   ETA: {eta_str}",
            "  " + "  ".join(stage_parts),
        ]
        if self._api_usage:
            usage_str = "  API: " + " ".join(
                f"{p}={c}" for p, c in sorted(self._api_usage.items(), key=lambda x: -x[1])
            )
            lines.append(usage_str)
        return "\n".join(lines)

    def update(self, pages_done, total_pages, pdf_name, current_page, current_stage, stage_status):
        self._pages_done = pages_done
        self._total_pages = total_pages
        self._pdf_name = pdf_name
        self._current_page = current_page
        self._current_stage = current_stage
        self._stage_status = stage_status
        self._redraw()

    def update_usage(self, provider: str, count: int):
        self._api_usage[provider] = count
        self._redraw()

    def _redraw(self):
        if self._has_rich:
            self._live.update(self._build_rich())
        else:
            block = self._build_ascii()
            n = block.count("\n") + 1
            if self._first_ascii:
                self._first_ascii = False
                sys.stdout.write("\n" + block)
            else:
                sys.stdout.write("\033[" + str(n) + "A\r" + block)
            sys.stdout.flush()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self._has_rich:
            self._live.stop()
            print()
        else:
            print()


def mode_process_everything(pdfs):
    lang_groups = {}
    for pdf in pdfs:
        lang = detect_language(pdf.name)
        if lang != "unknown":
            lang_groups.setdefault(lang, []).append(pdf.name)
    total = sum(len(v) for v in lang_groups.values())
    print(f"\n  Processing all {total} PDF(s) across {len(lang_groups)} language(s)")
    return lang_groups


def run_for_language(lang_key, files, max_pages, settings=None):
    out_dir = BASE / "output" / lang_key
    stats = {
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
                (settings or {}).get("provider", "gemini"),
                "--level",
                str((settings or {}).get("level", 4)),
                "--max-pages",
                str(max_pages),
            ]
            if (settings or {}).get("preprocess", False):
                cmd.append("--preprocess")
            if (settings or {}).get("validate", True):
                cmd.append("--validate")
            if (settings or {}).get("qa", False):
                cmd.append("--qa")
            if (settings or {}).get("report", True):
                cmd.append("--report")

            dashboard.update(0, total_pages, fname, "", "Rendering", stage_status)

            proc_env = {**os.environ, "PYTHONUNBUFFERED": "1"}
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                env=proc_env,
            )

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
                    pages_done, total_pages, fname, current_page, current_stage, stage_status
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
        dashboard.update(pages_done, total_pages, fname, "", "Complete", stage_status)
        if (settings or {}).get("zip", True):
            zip_output(lang_key, out_dir)
        return stats
    finally:
        dashboard.close()


def get_page_count(pdf_path):
    try:
        import fitz

        doc = fitz.open(pdf_path)
        n = doc.page_count
        doc.close()
        return n
    except Exception:
        return None


def pdf_label(pdf, show_count=True):
    lang = detect_language(pdf.name)
    display = LANG_DISPLAY.get(lang, lang.capitalize())
    label = f"{display} \u2014 {pdf.name}"
    if show_count:
        n = get_page_count(pdf)
        if n is not None:
            label += f"  ({n} page{'s' if n != 1 else ''})"
    return label


def mode_select_by_pdf(pdfs):
    pdf_options = []
    for pdf in pdfs:
        lang = detect_language(pdf.name)
        pdf_options.append((pdf_label(pdf), (lang, pdf.name)))
    print(f"\nSelect by PDF:\n")
    choices = choose("  PDF number(s)", pdf_options, multi=True)
    if not choices:
        return None
    selected = {}
    for ci in choices:
        lang, fname = pdf_options[ci][1]
        selected.setdefault(lang, []).append(fname)
    return selected


def mode_select_by_language(pdfs):
    lang_groups = {}
    for pdf in pdfs:
        lang = detect_language(pdf.name)
        if lang != "unknown":
            lang_groups.setdefault(lang, []).append(pdf.name)

    sorted_langs = sorted(lang_groups.keys())
    n = len(sorted_langs)

    print(f"\nSelect by language:\n")
    for i, k in enumerate(sorted_langs, 1):
        count = len(lang_groups[k])
        label = f"{LANG_DISPLAY.get(k, k.capitalize())} ({count} PDF{'s' if count != 1 else ''})"
        print(f"  [{i}] {label}")
    print(f"  [0] All Languages")

    while True:
        try:
            raw = input("  Language number(s): ").strip()
            if raw == "0":
                return {k: lang_groups[k] for k in sorted_langs}
            indices = []
            for part in raw.split(","):
                part = part.strip()
                if not part:
                    continue
                if "-" in part:
                    a, b = map(int, part.split("-"))
                    indices.extend(range(a - 1, b))
                else:
                    indices.append(int(part) - 1)
            selected = {}
            for idx in indices:
                if 0 <= idx < n:
                    k = sorted_langs[idx]
                    selected.setdefault(k, [])
            if not selected:
                print("  Invalid choice, try again.")
                continue
            for lang_key in selected:
                files = lang_groups[lang_key]
                print(f"\n  {LANG_DISPLAY.get(lang_key, lang_key)} PDFs:")
                for i, fname in enumerate(files, 1):
                    n = get_page_count(BASE / fname)
                    extra = f"  ({n} pages)" if n is not None else ""
                    print(f"    [{i}] {fname}{extra}")
                raw2 = input("  Select PDFs (comma/range, or 0 for all): ").strip()
                if not raw2 or raw2 == "0":
                    selected[lang_key] = files
                else:
                    try:
                        idxs = []
                        for part in raw2.split(","):
                            part = part.strip()
                            if "-" in part:
                                a, b = map(int, part.split("-"))
                                idxs.extend(range(a - 1, b))
                            else:
                                idxs.append(int(part) - 1)
                        selected[lang_key] = [files[i] for i in idxs if 0 <= i < len(files)]
                    except ValueError:
                        selected[lang_key] = files
            return selected
        except (ValueError, IndexError):
            print("  Invalid choice, try again.")


def show_settings(current):
    while True:
        rule("Settings")
        print(f"  1. LLM Provider         : {current['provider']}")
        print(f"  2. Annotation Level     : {current['level']}")
        print(f"  3. Preprocessing        : {'Yes' if current['preprocess'] else 'No'}")
        print(f"  4. Validation           : {'Yes' if current['validate'] else 'No'}")
        print(f"  5. QA Overlay           : {'Yes' if current['qa'] else 'No'}")
        print(f"  6. HTML Report          : {'Yes' if current['report'] else 'No'}")
        print(f"  7. ZIP Export           : {'Yes' if current['zip'] else 'No'}")
        print(f"  8. Max pages per PDF    : {current['max_pages']}  (0 = all)")
        print(f"  {'-' * 40}")
        print(f"  0. Back to main menu")
        print()
        raw = input("  Select setting to change: ").strip()
        if raw == "0":
            return current
        elif raw == "1":
            print("  Providers: [1] gemini  [2] glm")
            c = input("  Choose: ").strip()
            if c == "2":
                current["provider"] = "glm"
            else:
                current["provider"] = "gemini"
        elif raw == "2":
            c = input("  Level (3 or 4) [4]: ").strip()
            if c == "3":
                current["level"] = 3
            else:
                current["level"] = 4
        elif raw == "3":
            current["preprocess"] = not current["preprocess"]
        elif raw == "4":
            current["validate"] = not current["validate"]
        elif raw == "5":
            current["qa"] = not current["qa"]
        elif raw == "6":
            current["report"] = not current["report"]
        elif raw == "7":
            current["zip"] = not current["zip"]
        elif raw == "8":
            v = ask_int("  Pages per PDF", default=current["max_pages"])
            current["max_pages"] = v
        else:
            warn("  Invalid choice.")


def display_summary(stats_list):
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
    out_dir = first.get("output_dir", "")
    base_out = os.path.relpath(out_dir.parent, BASE) if out_dir else "output"
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
    raw(f"  [bold cyan]QA Folder[/bold cyan]            : N/A")
    raw(f"  [bold cyan]HTML Report[/bold cyan]          : {report_rel or 'N/A'}")
    raw(f"  [bold cyan]ZIP File[/bold cyan]             : {zip_rel or 'N/A'}")
    print()


def show_system_status(settings):
    tracker = UsageTracker(QUOTA_STATE_FILE)
    data = tracker.dashboard(settings)

    rule("SYSTEM STATUS", char="=")
    print()
    raw(f"    [bold cyan]Pipeline Version[/bold cyan] : RFQ Level {settings['level']}")
    raw(f"    [bold cyan]Provider[/bold cyan]          : {settings['provider']}")
    raw(
        f"    [bold cyan]Pages Today[/bold cyan]       : {sum(d['today']['pages'] for d in data['providers'].values())}"
    )
    raw(
        f"    [bold cyan]Pages This Month[/bold cyan]   : {sum(d['this_month']['pages'] for d in data['providers'].values())}"
    )
    last_req = data["recent_requests"][0] if data["recent_requests"] else None
    if last_req:
        from datetime import datetime

        ts_str = datetime.fromtimestamp(last_req["t"]).strftime("%Y-%m-%d %H:%M:%S")
        raw(
            f"    [bold cyan]Last Request[/bold cyan]     : {ts_str} | {last_req['p']} | {last_req['pg']}p"
        )
    else:
        raw(f"    [bold cyan]Last Request[/bold cyan]     : [yellow]None yet[/yellow]")
    print()


def _check_api_key(prov):
    from indic_ocr_pipeline.utils.config import (
        GEMINI_API_KEY,
        GOOGLE_VISION_API_KEY,
        GLM_API_KEY,
        GROQ_API_KEY,
        OPENROUTER_API_KEY,
        IAMHC_API_KEY,
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


def show_quota_monitor(settings):
    from indic_ocr_pipeline.utils.config import OPENROUTER_API_KEY

    tracker = UsageTracker(QUOTA_STATE_FILE)
    data = tracker.dashboard(settings)

    rule("USAGE MONITOR", char="=")
    print()

    or_usage = tracker.fetch_openrouter_official_usage(OPENROUTER_API_KEY)

    try:
        from rich.table import Table
        from rich import box

        c = _get_console()
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
                fail = str(t["failures"]) if t["failures"] else "0"
                table.add_row(
                    pd["label"],
                    str(t["requests"]),
                    str(m["requests"]),
                    str(lt["requests"]),
                    fail,
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

        label = pd["label"]
        t = pd["today"]
        y = pd["yesterday"]
        m = pd["this_month"]
        lt = pd["lifetime"]

        has_usage = t["requests"] > 0 or m["requests"] > 0 or lt["requests"] > 0
        if not has_usage:
            continue

        key_ok = _check_api_key(prov)
        key_status = "Loaded" if key_ok else "Not set"

        raw(f"  [bold cyan]{label}[/bold cyan]")
        raw(
            f"    API Key            : [{'green' if key_ok else 'red'}]{key_status}[/{'green' if key_ok else 'red'}]"
        )

        if pd["has_official_usage_api"]:
            if or_usage:
                raw(f"    Official Usage     : [green]Retrieved successfully[/green]")
                if prov == "openrouter":
                    raw(f"    Credits Used       : ${or_usage.get('usage', 0):.2f}")
                    raw(
                        f"    Credits Remaining  : ${or_usage.get('limit_remaining', 0):.2f}"
                        if or_usage.get("limit_remaining") is not None
                        else ""
                    )
                    raw(f"    Reset              : {or_usage.get('limit_reset', 'N/A')}")
            else:
                raw(f"    Official Usage     : [yellow]Not available from provider[/yellow]")
        else:
            raw(f"    Official Usage     : [yellow]Not available from provider[/yellow]")

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

        # Remaining quota - only for OpenRouter via official API
        if pd["has_official_quota_api"] and or_usage:
            pass  # shown above as credits remaining
        elif pd["has_official_quota_api"] and not or_usage:
            raw(f"    Remaining Quota    : [yellow]Not available from provider[/yellow]")

        print()

    if not data["providers"]:
        info("  (No usage data yet. Run the pipeline first.)")
        print()

    rule(char="=")
    input("  Press Enter to return to menu...")
    print()


def _check_result(pass_type, message, fix=None):
    if pass_type == "pass":
        ok(f"  [OK] {message}")
    elif pass_type == "warn":
        warn(f"  [!!] {message}")
        if fix:
            warn(f"        Fix: {fix}")
    else:
        err(f"  [XX] {message}")
        if fix:
            err(f"        Fix: {fix}")


def run_checks():
    critical = False

    rule("System Checks")
    print()

    # 1. Python version
    v = sys.version_info
    if v >= (3, 10):
        _check_result("pass", f"Python {v.major}.{v.minor}.{v.micro}")
    elif v >= (3, 8):
        _check_result("warn", f"Python {v.major}.{v.minor}.{v.micro} (3.10+ recommended)")
    else:
        _check_result(
            "fail",
            f"Python {v.major}.{v.minor}.{v.micro} (3.8+ required)",
            "Upgrade to Python 3.10+ from https://python.org",
        )
        critical = True

    # 2. Required packages
    packages = {
        "requests": "pip install requests",
        "PyMuPDF": "pip install PyMuPDF",
    }
    optional = {"rich": "pip install rich"}
    all_present = True

    for pkg, fix_cmd in packages.items():
        try:
            if pkg == "PyMuPDF":
                import fitz
            else:
                __import__(pkg)
            _check_result("pass", f"Package: {pkg}")
        except ImportError:
            _check_result("fail", f"Package: {pkg} not found", fix_cmd)
            all_present = False
            critical = True

    for pkg, fix_cmd in optional.items():
        try:
            __import__(pkg)
            _check_result("pass", f"Package: {pkg}")
        except ImportError:
            _check_result("warn", f"Package: {pkg} not found", fix_cmd)

    # 3. API Keys
    from indic_ocr_pipeline.utils.config import GEMINI_API_KEY, GOOGLE_VISION_API_KEY, GLM_API_KEY

    keys = [
        ("Google Cloud Vision", GOOGLE_VISION_API_KEY, "GOOGLE_VISION_API_KEY"),
        ("Gemini", GEMINI_API_KEY, "GEMINI_API_KEY"),
        ("GLM-4V", GLM_API_KEY, "GLM_API_KEY"),
    ]
    for name, val, env_var in keys:
        if val:
            _check_result("pass", f"API Key: {name}")
        else:
            _check_result(
                "warn", f"API Key: {name} not set", f"Add {env_var}=your_key to .env file"
            )

    # 4. Output folder & write permissions
    test_dir = BASE / "output"
    try:
        test_dir.mkdir(parents=True, exist_ok=True)
        test_file = test_dir / ".write_test"
        test_file.write_text("")
        test_file.unlink()
        _check_result("pass", "Output folder writable")
    except Exception:
        _check_result(
            "fail",
            "Cannot write to output/ folder",
            "Check folder permissions or run as different user",
        )
        critical = True

    # 5. Internet connectivity
    try:
        import urllib.request

        urllib.request.urlopen("https://www.google.com", timeout=5)
        _check_result("pass", "Internet connectivity")
    except Exception:
        _check_result(
            "warn",
            "Internet connectivity failed",
            "Check network connection (required for OCR + LLM)",
        )

    rule()
    print()

    if critical:
        err("  Critical failures detected. Pipeline cannot run.")
        print()
        sys.exit(1)


def main():
    run_checks()
    os.chdir(BASE)

    pdfs = sorted(BASE.glob("*.pdf"))
    if not pdfs:
        err("\n  No PDF files found in this folder.")
        sys.exit(1)

    available = set()
    for pdf in pdfs:
        lang = detect_language(pdf.name)
        if lang != "unknown":
            available.add(lang)

    print_banner(available)

    # Session settings
    settings = {
        "max_pages": 0,
        "provider": "gemini",
        "level": 4,
        "preprocess": False,
        "validate": True,
        "qa": False,
        "report": True,
        "zip": True,
    }

    while True:
        # Build language groups sorted by most PDFs first
        lang_groups = {}
        for pdf in pdfs:
            lang = detect_language(pdf.name)
            if lang != "unknown":
                lang_groups.setdefault(lang, []).append(pdf.name)
        sorted_langs = sorted(lang_groups.keys(), key=lambda k: -len(lang_groups[k]))

        bold(f"\n  Found {len(pdfs)} PDF(s)")

        rule("Select Language")
        for i, k in enumerate(sorted_langs, 1):
            count = len(lang_groups[k])
            print(
                f"  [{i}] {LANG_DISPLAY.get(k, k.capitalize())} ({count} PDF{'s' if count != 1 else ''})"
            )
        rule()
        print("  [S]ettings  [Q]uota  [E]xit")
        print()
        raw = input("  Choice: ").strip().upper()

        if raw == "E":
            info("  Exiting.")
            sys.exit(0)
        if raw == "Q":
            show_quota_monitor(settings)
            continue
        if raw == "S":
            settings = show_settings(settings)
            continue

        try:
            lang_idx = int(raw) - 1
            if lang_idx < 0 or lang_idx >= len(sorted_langs):
                warn("  Invalid choice.")
                continue
        except ValueError:
            warn("  Invalid choice.")
            continue

        lang_key = sorted_langs[lang_idx]
        files = lang_groups[lang_key]

        # --- PDF selection within language ---
        bold(f"\n  {LANG_DISPLAY.get(lang_key, lang_key)} PDFs")
        rule()
        for i, fname in enumerate(files, 1):
            n = get_page_count(BASE / fname)
            extra = f"  ({n} pages)" if n is not None else ""
            print(f"  [{i}] {fname}{extra}")
        print(f"  [0] Process All")
        print(f"  [B] Back to languages")
        print()
        raw2 = input("  Select PDFs (comma/range, or 0 for all): ").strip()

        if raw2.upper() == "B":
            continue
        if not raw2 or raw2 == "0":
            selected_files = files
        else:
            try:
                idxs = []
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
            continue

        selected = {lang_key: selected_files}

        mp = ask_int("  Pages per PDF (0 = all)", default=0)

        # --- Processing Summary ---
        total_est = 0
        for fname in selected_files:
            n = get_page_count(BASE / fname)
            if n is not None:
                total_est += min(n, mp) if mp > 0 else n
            else:
                total_est += mp if mp > 0 else 0

        rule("Processing Summary")
        print(f"  Language           : {LANG_DISPLAY.get(lang_key, lang_key)}")
        print(f"  PDF Count          : {len(selected_files)}")
        print(f"  Provider           : {settings['provider']}")
        print(f"  RFQ Level          : {settings['level']}")
        print(f"  Preprocessing      : {'Yes' if settings['preprocess'] else 'No'}")
        print(f"  Validation         : {'Yes' if settings['validate'] else 'No'}")
        print(f"  QA Overlay         : {'Yes' if settings['qa'] else 'No'}")
        print(f"  HTML Report        : {'Yes' if settings['report'] else 'No'}")
        print(f"  ZIP Export         : {'Yes' if settings['zip'] else 'No'}")
        print(f"  Estimated Pages    : {total_est}")
        rule()
        proceed = input("  Start Processing? (Y/N): ").strip().upper()
        if proceed != "Y":
            info("  Returned to menu.")
            continue

        all_stats = []
        for lk, flist in selected.items():
            stats = run_for_language(lk, flist, mp, settings)
            all_stats.append(stats)

        display_summary(all_stats)
        rule()


if __name__ == "__main__":
    main()
