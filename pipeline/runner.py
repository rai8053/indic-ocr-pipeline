import argparse
import json
import os
import time
from pathlib import Path

import fitz

from core.config import (LANGUAGE_HINTS, NO_TEXT_IN_PICTURE_MARKER,
                         QUOTA_STATE_FILE, VISION_MONTHLY_LIMIT, LLM_DAILY_LIMIT)
from utils.usage import UsageTracker
from utils.logging import PipelineLogger
from pipeline.tracker import set_tracker, get_tracker
from pipeline.pictures import detect_embedded_pictures, detect_picture_regions_cv
from pipeline.ocr import run_vision_ocr


def pdf_to_images(pdf_path: Path, out_dir: Path, dpi: int = 150, jpeg_quality: int = 60) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    image_paths = []
    for i, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=matrix)
        img_path = out_dir / f"page_{i:04d}.jpg"
        pix.save(img_path, jpg_quality=jpeg_quality)
        image_paths.append(img_path)
    doc.close()
    return image_paths


def process_pdf(pdf_path: Path, lang: str, out_dir: Path, dpi: int = 150, jpeg_quality: int = 60,
                 provider: str = "gemini", batch_size: int = 1,
                 create_zip: bool = False, max_samples: int = 0, validate: bool = False,
                 level: int = 3, preprocess: bool = False, qa: bool = False,
                 create_report: bool = False, max_pages: int = 0):

    lang = lang.lower()
    hints = LANGUAGE_HINTS.get(lang)
    images_dir, json_dir = out_dir / "images", out_dir / "annotations"
    qa_dir = out_dir / "qa" if qa else None
    report_dir = out_dir / "report" if create_report else None
    logs_dir = out_dir / "logs"
    json_dir.mkdir(parents=True, exist_ok=True)

    plog = PipelineLogger(logs_dir)
    plog.start_stage("total")

    set_tracker(UsageTracker(QUOTA_STATE_FILE))
    _usg = get_tracker()
    plog.log(f"      Usage tracker initialized at {QUOTA_STATE_FILE}")

    plog.start_stage("pdf_to_images")
    plog.log(f"[1/5] Splitting {pdf_path.name} into page images...")
    image_paths = pdf_to_images(pdf_path, images_dir, dpi=dpi, jpeg_quality=jpeg_quality)
    if max_pages > 0 and len(image_paths) > max_pages:
        plog.log(f"      Limiting to first {max_pages} of {len(image_paths)} pages")
        image_paths = image_paths[:max_pages]
    plog.end_stage("pdf_to_images")

    picture_blocks_by_page = {}
    try:
        pic_doc = fitz.open(pdf_path)
        for i, img_path in enumerate(image_paths):
            if i < len(pic_doc):
                blocks = detect_embedded_pictures(pic_doc[i], dpi)
                if blocks:
                    picture_blocks_by_page[img_path.name] = blocks
                    plog.log(f"      {img_path.name}: {len(blocks)} embedded picture(s)")
        pic_doc.close()
    except Exception as e:
        plog.log(f"      Embedded picture detection skipped: {e}")

    if preprocess:
        plog.start_stage("preprocessing")
        plog.log(f"      Preprocessing {len(image_paths)} pages...")
        preproc_dir = out_dir / "preprocessed"
        preproc_dir.mkdir(parents=True, exist_ok=True)
        from preprocessing.image import preprocess_image
        preprocessed = []
        for img_path in image_paths:
            out_pre = preproc_dir / img_path.name
            try:
                preprocess_image(img_path, out_pre)
                preprocessed.append(out_pre)
            except Exception as e:
                plog.error(f"Preprocessing failed for {img_path.name}: {e}")
                preprocessed.append(img_path)
        image_paths = preprocessed
        images_dir = preproc_dir
        plog.end_stage("preprocessing")

    pending = [p for p in image_paths if not (json_dir / f"{p.stem}.json").exists()]
    plog.log(f"      -> {len(pending)} pages to process")

    ocr_cache = {}
    for img_path in pending:
        plog.start_stage("vision_ocr")
        if not _usg.available("vision", VISION_MONTHLY_LIMIT):
            plog.log(f"[!] Vision OCR monthly limit ({VISION_MONTHLY_LIMIT}) reached, stopping.")
            plog.end_stage("vision_ocr"); break
        plog.log(f"[2/5] OCR: {img_path.name}")
        try:
            vision_result = run_vision_ocr(img_path, language_hints=hints)
        except Exception as e:
            plog.error(f"Vision failed: {e}"); plog.end_stage("vision_ocr"); continue
        plog.end_stage("vision_ocr")
        if not vision_result["blocks"]:
            plog.log("      No text -- excluding page"); img_path.unlink(missing_ok=True); continue

        text_boxes = [b["box"] for b in vision_result["blocks"]]
        picture_blocks = picture_blocks_by_page.get(img_path.name, [])
        if not picture_blocks:
            try:
                picture_blocks = detect_picture_regions_cv(img_path, text_boxes)
            except Exception as e:
                plog.log(f"      CV picture detection skipped for {img_path.name}: {e}")
                picture_blocks = []

        if picture_blocks:
            plog.log(f"      {img_path.name}: {len(picture_blocks)} picture region(s) detected")
            vision_result["blocks"] = vision_result["blocks"] + [
                {**pb, "text": NO_TEXT_IN_PICTURE_MARKER} for pb in picture_blocks
            ]

        ocr_cache[img_path] = vision_result

    from pipeline.providers import run_proofread_batch

    ocr_items = list(ocr_cache.items())
    for i in range(0, len(ocr_items), batch_size):
        chunk = ocr_items[i:i + batch_size]

        chunk_paths = [p for p, _ in chunk]
        chunk_blocks = [r["blocks"] for _, r in chunk]

        if not _usg.available(provider, LLM_DAILY_LIMIT):
            plog.log(f"[!] {provider} daily limit ({LLM_DAILY_LIMIT}) reached, stopping.")
            break

        plog.log(f"[3/5] Proofread ({provider}, batch {len(chunk)}): {', '.join(p.name for p in chunk_paths)}")

        plog.start_stage("llm_proofread")
        try:
            pages_out = run_proofread_batch(provider, chunk_paths, chunk_blocks, level=level)
            plog.log(f"      [OK] {provider} proofread completed")
            for img_path, page_result in zip(chunk_paths, pages_out):
                page_result["image"] = img_path.name
                ro_source = page_result.pop("_ro_source", "llm")
                plog.log(f"      {img_path.stem}: reading_order source={ro_source}")
                if page_result.get("annotation_quality") == "degraded_text_only_fallback":
                    plog.log(f"      [WARN] {img_path.stem}: Level 4 requested but fell back to "
                             f"a text-only provider -- no table/formula LaTeX generated for this page.")
                out_path = json_dir / f"{img_path.stem}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(page_result, f, ensure_ascii=False, indent=2)
        except Exception as e:
            plog.error(f"LLM proofread failed: {e} -- Falling back to raw Vision output (Level 2)")
            for img_path, vision_result in chunk:
                fallback = {
                    "image": img_path.name,
                    "block_boxes": [b["box"] for b in vision_result["blocks"]],
                    "block_classes": ["Text"] * len(vision_result["blocks"]),
                    "block_text": [b["text"] for b in vision_result["blocks"]],
                }
                with open(json_dir / f"{img_path.stem}.json", "w", encoding="utf-8") as f:
                    json.dump(fallback, f, ensure_ascii=False, indent=2)
        plog.end_stage("llm_proofread")

    if level >= 4:
        jsons = sorted(json_dir.glob("*.json"))
        plog.start_stage("auto_relations")
        from layout.relations import auto_relations
        for j in jsons:
            data = json.load(open(j, encoding="utf-8"))
            if not data.get("block_relations"):
                wrapped_blocks = [{"box": b} for b in data["block_boxes"]]
                relations = auto_relations(wrapped_blocks, data["block_classes"])
                if relations:
                    data["block_relations"] = relations
                    with open(j, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    plog.log(f"      {j.name}: auto relations added ({len(relations)})")
        plog.end_stage("auto_relations")

    jsons = sorted(json_dir.glob("*.json"))
    all_validations = []
    all_overlays = []

    if validate or qa or create_report:
        plog.start_stage("validation")
        plog.log("[4/5] Analyzing annotations...")
        from validation.schema import validate_page as advanced_validate
        from validation.scoring import score_page
        for j in jsons:
            r = advanced_validate(j)
            s = score_page(j)
            all_validations.append((j, r, s))
            status = "PASS" if r["valid"] else "FAIL"
            detail = f" ({len(r['errors'])} errors)" if not r["valid"] else ""
            plog.log(f"      {j.name}: {status}{detail} | Scores: OCR={s['ocr']}% RO={s['reading_order']}% Overall={s['overall']}%")

            if qa:
                from qa.overlay import draw_overlay
                img_name = json.load(open(j, encoding="utf-8")).get("image", "")
                src_img = images_dir / img_name
                if src_img.exists():
                    overlay_path = qa_dir / f"{j.stem}_overlay.jpg" if qa_dir else out_dir / "qa" / f"{j.stem}_overlay.jpg"
                    overlay_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        draw_overlay(src_img, j, overlay_path)
                        all_overlays.append(overlay_path)
                    except Exception as e:
                        plog.error(f"QA overlay failed for {j.name}: {e}")

        passed = sum(1 for _, r, _ in all_validations if r["valid"])
        plog.log(f"      {passed}/{len(jsons)} pages valid")
        plog.end_stage("validation")

    if create_report and jsons:
        plog.start_stage("report")
        plog.log("[5/5] Generating HTML report...")
        from report.html_report import generate_report
        report_pages = []
        for j, r, s in all_validations:
            data = json.load(open(j, encoding="utf-8"))
            overlay_rel = ""
            if qa:
                overlay_path = (qa_dir if qa_dir else out_dir / "qa") / f"{j.stem}_overlay.jpg"
                if overlay_path.exists():
                    overlay_rel = str(os.path.relpath(overlay_path, report_dir)) if report_dir else str(overlay_path.relative_to(out_dir))
            report_pages.append({
                "name": j.name,
                "validation": r,
                "scores": s,
                "overlay": overlay_rel,
            })
        report_path = report_dir / "report.html" if report_dir else out_dir / "report" / "report.html"
        _r_usage = {"date": time.strftime("%Y-%m-%d"), "total": 0, "providers": {}}
        if _usg:
            _rd = _usg.dashboard()
            _r_usage["providers"] = {p: d["today"]["requests"] for p, d in _rd.get("providers", {}).items()}
            _r_usage["total"] = sum(_r_usage["providers"].values())
        generate_report(report_pages, report_path, usage=_r_usage)
        plog.log(f"      -> {report_path}")
        plog.end_stage("report")

    if validate and not any(all_validations):
        plog.log("\n[Validation] Checking annotations...")
        passed = 0
        for j in jsons:
            r = advanced_validate(j)
            status = "PASS" if r["valid"] else "FAIL"
            detail = f" ({len(r['errors'])} errors)" if not r["valid"] else ""
            plog.log(f"      {j.name}: {status}{detail}")
            if r["valid"]: passed += 1
        plog.log(f"      {passed}/{len(jsons)} pages valid")

    if create_zip:
        import zipfile
        plog.log("\n[ZIP] Creating submission...")
        zip_path = out_dir / f"{lang}_submission.zip"
        if max_samples > 0 and len(jsons) > max_samples:
            from validation.schema import validate_page as advanced_validate
            scored = [(j, advanced_validate(j)) for j in jsons]
            scored.sort(key=lambda x: (x[1].get("diverse", False), x[1].get("class_count", 0)), reverse=True)
            jsons = [s[0] for s in scored[:max_samples]]
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for j in jsons:
                data = json.load(open(j, encoding="utf-8"))
                zf.writestr(f"{lang}/{j.stem}.json", json.dumps(data, ensure_ascii=False, indent=2))
                img_path = images_dir / data.get("image", "")
                if img_path.exists(): zf.write(img_path, f"{lang}/{img_path.name}")
        plog.log(f"      -> {zip_path}")

    if _usg:
        _d = _usg.dashboard()
        plog.log("\n--- Free-tier headroom ---")
        for prov, pd in _d.get("providers", {}).items():
            t = pd["today"]
            m = pd["this_month"]
            lt = pd["lifetime"]
            plog.log(f"  {pd['label']:20s}: {t['requests']:3d} today, "
                     f"{m['requests']:3d} month, {lt['requests']:4d} lifetime, "
                     f"retries={lt['retries']}, failures={lt['failures']}")
        plog.log("--------------------------")

    plog.end_stage("total")
    plog.log(f"\nDone. Images: {images_dir}, Annotations: {json_dir}")
    summary = plog.summary()
    if summary:
        plog.log("Timing summary:")
        for stage, secs in summary.items():
            plog.log(f"  {stage}: {secs:.1f}s")
    plog.log("Usage tracking: recorded via per-request instrumentation")


def main():
    parser = argparse.ArgumentParser(description="Indic OCR/parse dataset pipeline (Upgraded)")
    parser.add_argument("--pdf", required=True, help="Path to source PDF")
    parser.add_argument("--lang", default="", help="Target language, e.g. tamil (auto-detected if omitted)")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--dpi", type=int, default=150, help="Render DPI (default 150)")
    parser.add_argument("--jpeg-quality", type=int, default=60, help="JPEG quality 1-100 (default 60)")
    parser.add_argument("--provider", choices=["openrouter", "gemini", "groq", "glm", "iamhc"], default="gemini",
                         help="Primary LLM provider. Failover: gemini->glm->openrouter, glm->openrouter")
    parser.add_argument("--level", type=int, choices=[3, 4], default=4, help="Annotation level (3 or 4)")
    parser.add_argument("--batch-size", type=int, default=1, help="Pages per request (default 1)")
    parser.add_argument("--validate", action="store_true", help="Validate output JSONs")
    parser.add_argument("--zip", action="store_true", help="Create submission ZIP")
    parser.add_argument("--max-pages", type=int, default=0, help="Process only first N pages (0=all)")
    parser.add_argument("--samples", type=int, default=0, help="Max samples in ZIP (0=all)")
    parser.add_argument("--preprocess", action="store_true", help="Enable OpenCV preprocessing (deskew, denoise, contrast)")
    parser.add_argument("--qa", action="store_true", help="Generate visual QA overlays (boxes, classes, reading order arrows)")
    parser.add_argument("--report", action="store_true", help="Generate HTML quality report with RFQ scores")
    args = parser.parse_args()

    process_pdf(Path(args.pdf), args.lang, Path(args.out), dpi=args.dpi,
                jpeg_quality=args.jpeg_quality, provider=args.provider,
                batch_size=args.batch_size,
                create_zip=args.zip, max_samples=args.samples,
                validate=args.validate, level=args.level,
                preprocess=args.preprocess, qa=args.qa, create_report=args.report,
                max_pages=args.max_pages)


if __name__ == "__main__":
    main()
