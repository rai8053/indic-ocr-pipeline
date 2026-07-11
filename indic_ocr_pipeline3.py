#!/usr/bin/env python3
"""
Indic OCR/Parse Dataset Pipeline (Upgraded)
=============================================
Splits PDFs into page images, runs Google Vision OCR to get paragraph-level 
bounding boxes + raw text, then sends each page to a free Vision LLM (Gemini or GLM)
to assign RFQ class labels, fix reading order, and generate Level 4 annotations 
(table/formula LaTeX in block_text, block relations, reading order).

New features:
- --preprocess: OpenCV deskew/denoise/contrast/threshold
- --qa: Visual QA overlays (boxes, classes, reading order arrows, relations)
- --report: HTML quality report with RFQ scores
- Geometry-based reading order as fallback
- Automatic relation detection (table→caption, figure→caption, footnote→ref)
- Advanced validator (duplicate/overlapping boxes, missing captions, etc.)
- RFQ scoring per page
- Pipeline logging with timing metrics
"""

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
import fitz  # PyMuPDF

from core.terminal import warn as _term_warn
from core.config import (VALID_CLASSES, VALID_CLASSES_SET, CLASS_COLORS,
                         LANGUAGE_HINTS, VALID_RELATIONS, NO_TEXT_IN_PICTURE_MARKER,
                         GOOGLE_VISION_API_KEY, OPENROUTER_API_KEY,
                          GEMINI_API_KEY, GROQ_API_KEY, GLM_API_KEY, IAMHC_API_KEY,
                          OPENROUTER_MODEL, GEMINI_MODEL, GEMINI_ENDPOINT_TMPL,
                          GLM_ENDPOINT, GLM_MODEL, VISION_ENDPOINT,
                          OPENROUTER_ENDPOINT, GROQ_MODEL, GROQ_ENDPOINT,
                          IAMHC_ENDPOINT, IAMHC_MODEL,
                          QUOTA_STATE_FILE, VISION_MONTHLY_LIMIT, LLM_DAILY_LIMIT,
                         RETRY_ATTEMPTS, RETRY_BACKOFF_SECONDS)
from utils.usage import UsageTracker
from validation.schema import validate_page as advanced_validate
from validation.scoring import score_page
from qa.overlay import draw_overlay

# Module-level usage tracker (set in process_pdf)
_usg = None

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Constants imported from core.config:
#   VALID_CLASSES, VALID_CLASSES_SET, LANGUAGE_HINTS, CLASS_COLORS, VALID_RELATIONS
#   GOOGLE_VISION_API_KEY, OPENROUTER_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, GLM_API_KEY
#   OPENROUTER_MODEL, GEMINI_MODEL, GEMINI_ENDPOINT_TMPL, GLM_ENDPOINT, GLM_MODEL
#   VISION_ENDPOINT, OPENROUTER_ENDPOINT, GROQ_MODEL, GROQ_ENDPOINT
#   QUOTA_STATE_FILE, RETRY_ATTEMPTS, RETRY_BACKOFF_SECONDS


# ---------------------------------------------------------------------------
# Step 1: PDF -> page images
# ---------------------------------------------------------------------------

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


def detect_embedded_pictures(pdf_page, dpi: int) -> list[dict]:
    zoom = dpi / 72
    page_w, page_h = pdf_page.rect.width * zoom, pdf_page.rect.height * zoom
    results = []
    for img_info in pdf_page.get_image_info():
        bbox = img_info.get("bbox")
        if not bbox:
            continue
        x1, y1, x2, y2 = bbox
        scaled = [x1 * zoom, y1 * zoom, x2 * zoom, y2 * zoom]
        w, h = scaled[2] - scaled[0], scaled[3] - scaled[1]
        if w < 40 or h < 40:
            continue
        if w * h > 0.5 * page_w * page_h:
            continue
        results.append({"box": [round(v) for v in scaled], "text": "", "is_picture": True})
    return results


def detect_picture_regions_cv(image_path: Path, text_boxes: list[list[int]],
                                min_area: int = 3000) -> list[dict]:
    import cv2
    import numpy as np

    img = cv2.imread(str(image_path))
    if img is None:
        return []
    h, w = img.shape[:2]

    mask = np.ones((h, w), dtype=np.uint8) * 255
    for box in text_boxes:
        x1, y1, x2, y2 = [max(0, min(v, [w, h, w, h][i])) for i, v in enumerate(box)]
        mask[y1:y2, x1:x2] = 0

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
    thresh = cv2.bitwise_and(thresh, thresh, mask=mask)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    results = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = cw * ch
        if area < min_area:
            continue
        if area > 0.5 * w * h:
            continue
        if cw > 0.9 * w and ch > 0.9 * h:
            continue
        results.append({"box": [x, y, x + cw, y + ch], "text": "", "is_picture": True})
    return results


# ---------------------------------------------------------------------------
# Step 2: Google Vision OCR (Extracting PARAGRAPHS for tighter boxes)
# ---------------------------------------------------------------------------

def image_to_base64(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def run_vision_ocr(image_path: Path, language_hints: list[str] | None = None) -> dict:
    if not GOOGLE_VISION_API_KEY:
        raise RuntimeError("GOOGLE_VISION_API_KEY not set")

    b64 = image_to_base64(image_path)
    request_body = {
        "requests": [{
            "image": {"content": b64},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            "imageContext": ({"languageHints": language_hints} if language_hints else {}),
        }]
    }

    url = f"{VISION_ENDPOINT}?key={GOOGLE_VISION_API_KEY}"
    t0 = time.time()
    retries = 0
    last_err = ""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = requests.post(url, json=request_body, timeout=60)
            if resp.status_code == 200:
                latency = (time.time() - t0) * 1000
                if _usg:
                    _usg.record_request("vision", model="DOCUMENT_TEXT_DETECTION",
                        success=True, latency_ms=latency, retry_count=retries,
                        pages=1, images=1)
                break
            retries += 1
            last_err = f"{resp.status_code} {resp.text}"
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
        except Exception as e:
            retries += 1
            last_err = str(e)
            if attempt == RETRY_ATTEMPTS - 1:
                latency = (time.time() - t0) * 1000
                if _usg:
                    _usg.record_request("vision", model="DOCUMENT_TEXT_DETECTION",
                        success=False, latency_ms=latency, retry_count=retries,
                        error=str(e), pages=1, images=1)
                raise RuntimeError(f"Vision API failed after {retries} attempts: {e}")
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    else:
        latency = (time.time() - t0) * 1000
        if _usg:
            _usg.record_request("vision", model="DOCUMENT_TEXT_DETECTION",
                success=False, latency_ms=latency, retry_count=retries,
                error=last_err, pages=1, images=1)
        raise RuntimeError(f"Vision API failed after {RETRY_ATTEMPTS} attempts: {last_err}")

    data = resp.json()
    result = data.get("responses", [{}])[0]

    if "error" in result:
        raise RuntimeError(f"Vision API error: {result['error']}")
    if "fullTextAnnotation" not in result:
        return {"blocks": [], "full_text": ""}

    blocks = []
    for page in result["fullTextAnnotation"].get("pages", []):
        for block in page.get("blocks", []):
            for paragraph in block.get("paragraphs", []):
                p_verts = paragraph["boundingBox"]["vertices"]
                p_xs = [v.get("x", 0) for v in p_verts]
                p_ys = [v.get("y", 0) for v in p_verts]
                para_box = [min(p_xs), min(p_ys), max(p_xs), max(p_ys)]

                para_text = ""
                for word in paragraph.get("words", []):
                    symbols = "".join(s.get("text", "") for s in word.get("symbols", []))
                    para_text += symbols
                    last_symbol = word.get("symbols", [{}])[-1]
                    break_type = last_symbol.get("property", {}).get("detectedBreak", {}).get("type", "")
                    if break_type in ("SPACE", "EOL_SURE_SPACE"): para_text += " "
                    elif break_type == "LINE_BREAK": para_text += "\n"

                if para_text.strip():
                    blocks.append({"box": para_box, "text": para_text.strip()})

    return {"blocks": blocks, "full_text": result["fullTextAnnotation"].get("text", "")}


# ---------------------------------------------------------------------------
# Step 3: Prompts
# ---------------------------------------------------------------------------

def build_vision_batch_prompt(pages_blocks: list[list[dict]], level: int = 3) -> str:
    class_list = ", ".join(VALID_CLASSES)
    pages_json = json.dumps(
        [{"page_index": i, "raw_blocks": b} for i, b in enumerate(pages_blocks)],
        ensure_ascii=False, indent=2,
    )
    n_pages = len(pages_blocks)

    base = (
        "You are preparing OCR training data for a document layout model.\n\n"
        f"You will see {n_pages} page image(s), in order, each with its own "
        "list of raw OCR blocks (box + text) detected by Google Vision, "
        "grouped by page_index matching image order. For EACH page:\n\n"
        "1. Assign exactly one class per block from this fixed list: {class_list}\n"
        "2. If a block is a table, output its LaTeX (\\begin{{tabular}}{{...}}\\end{{tabular}}) "
        "in the corresponding block_text element. For ALL other blocks, set block_text to empty string \"\".\n"
        "3. If a block is a display formula, replace its text with LaTeX in block_text.\n"
        "4. Reorder blocks into natural reading order.\n"
        "5. CRITICAL: The output MUST have exactly the SAME number of blocks as the input. "
        "Every input block must have one matching output block. Do not skip any block.\n"
        "6. CRITICAL: block_text must be empty string \"\" for any block where text did not change.\n"
        "7. Inline formulas that appear within a paragraph should remain inline as part of "
        "the Text block's text -- only assign the Formula class to formulas that appear as "
        "their own separate, visually distinct block on the page.\n"
        "8. Any block whose text is exactly \"[NO_TEXT_IN_PICTURE]\" is a non-text visual region "
        "(photo, illustration, diagram, stamp, seal) -- assign it the class \"Picture\" and "
        "leave the block_text unchanged.\n"
    ).format(class_list=class_list)

    if level >= 4:
        extra = (
            "9. Return reading_order array of indices in reading sequence.\n"
            "10. Return block_relations: an array of objects linking related "
            'blocks. Each: {"source": i, "target": j, "relation": "<type>"}. '
            "Types: caption_of_table, table_has_caption, caption_of_figure, "
            "figure_has_caption, footnote_refers_to.\n"
        )
        out_shape = (
            '{"pages": [{"block_classes": ["Text"], '
            '"block_text": ["..."], "reading_order": [0], '
            '"block_relations": []}]}'
        )
    else:
        extra = ""
        out_shape = (
            '{"pages": [{"block_boxes": [[0,0,0,0]], "block_classes": ["Text"], '
            '"block_text": ["..."]}]}'
        )

    return (
        base + extra +
        f"\nRaw Vision OCR blocks per page:\n{pages_json}\n\n"
        "Respond with ONLY a JSON object, no markdown fences, no commentary, "
        "in exactly this shape (one entry per page, SAME ORDER as the images):\n"
        f"{out_shape}\n"
    )


def build_batch_prompt(pages_blocks: list[list[dict]], max_chars: int = 100, level: int = 3) -> str:
    """Text-only prompt for Groq/Openrouter (cannot do Level 4 accurately)."""
    class_list = ", ".join(VALID_CLASSES)
    truncated = []
    for blocks in pages_blocks:
        page_blocks = []
        for b in blocks:
            text = b.get("text", "")
            if len(text) > max_chars:
                text = text[:max_chars] + "..."
            page_blocks.append({"box": b["box"], "text": text})
        truncated.append(page_blocks)

    pages_json = json.dumps(
        [{"page_index": i, "raw_blocks": b} for i, b in enumerate(truncated)],
        ensure_ascii=False, indent=None,
    )
    n_pages = len(pages_blocks)

    base = (
        "You are preparing OCR training data for a document layout model.\n\n"
        f"You will receive raw OCR blocks for {n_pages} page(s). "
        "DO NOT split or merge blocks.\n"
        f"1. Assign exactly one class per block from: {class_list}\n"
        "2. Determine reading order using box coordinates.\n"
        "3. Return page_order as an array of indices in reading order.\n"
        "4. DO NOT return block_text or block_boxes.\n"
    )

    out_shape = '{"pages": [{"page_order": [0,1,2], "block_classes": ["Text",...]}]}'
    return (
        base + f"\nRaw Vision OCR blocks per page:\n{pages_json}\n\n"
        "Respond with ONLY a JSON object, no markdown fences, no commentary, "
        f"in exactly this shape:\n{out_shape}\n"
    )


# ---------------------------------------------------------------------------
# JSON Repair & Parsing
# ---------------------------------------------------------------------------

def _find_matching_brace(text: str, start: int) -> int:
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape: escape = False; continue
        if ch == "\\" and in_string: escape = True; continue
        if ch == '"': in_string = not in_string; continue
        if not in_string:
            if ch == "{": depth = 1 if i == start else depth + 1
            elif ch == "}":
                depth -= 1
                if depth == 0: return i
    return -1


def _repair_json(text: str) -> str:
    original = text
    text = text.replace(",\n]", "\n]").replace(",]", "]").replace(",\n}", "\n}").replace(",}", "}")
    try: json.loads(text); return text
    except json.JSONDecodeError: pass
    text = re.sub(r'"\s+"', '", "', text)
    try: json.loads(text); return text
    except json.JSONDecodeError: pass
    return original


def _extract_json_object(raw_text: str) -> dict:
    text = raw_text.strip()
    # Strip emoji reasoning tags some models emit
    while "💭" in text and "✨" in text:
        start, end = text.index("💭"), text.index("✨") + len("✨")
        text = (text[:start] + text[end:]).strip()
    while "```" in text:
        parts = text.split("```", 1)
        before = parts[0].strip()
        if "{" in before:
            text = before
        else:
            fence_end = parts[1].find("```") if len(parts) > 1 else -1
            fenced = parts[1][:fence_end] if fence_end >= 0 else (parts[1] if len(parts) > 1 else "")
            if "{" in fenced:
                text = fenced.strip()
                if text.startswith("json"): text = text[4:]
            else:
                break
    first = text.find("{")
    if first == -1: raise ValueError(f"No JSON object found: {raw_text[:200]!r}")
    last = _find_matching_brace(text, first)
    if last == -1: raise ValueError(f"Unmatched opening brace: {raw_text[:200]!r}")
    text = text[first:last + 1]
    try: return json.loads(text)
    except json.JSONDecodeError:
        repaired = _repair_json(text)
        if repaired != text: return json.loads(repaired)
        raise


def _parse_batch_response(raw_text: str, expected_pages: int,
                          original_blocks: list[list[dict]] | None = None,
                          level: int = 3) -> list[dict]:
    parsed = _extract_json_object(raw_text)
    pages = parsed["pages"] if "pages" in parsed else (
        [parsed] if "block_classes" in parsed and expected_pages == 1 else []
    )
    if not pages or len(pages) != expected_pages:
        raise ValueError(f"Expected {expected_pages} pages, got {len(pages)}")

    result = []
    for page_idx, p in enumerate(pages):
        classes = p.get("block_classes", [])
        order = p.get("page_order", None) or p.get("reading_order", None)
        n = len(classes)
        relations = p.get("block_relations", [])

        # Get original Vision blocks for this page
        orig_blocks = (original_blocks[page_idx]
                       if original_blocks and page_idx < len(original_blocks)
                       else None)
        orig_count = len(orig_blocks) if orig_blocks else 0

        # Safety: if model returned wrong block count, pad/truncate to match original
        if orig_count > 0 and n != orig_count:
            _term_warn(f"      [Warning] Page {page_idx}: model returned {n} blocks, "
                  f"expected {orig_count}. Padding output.")
            if n < orig_count:
                # Model dropped blocks: pad classes with "Text", pad texts with ""
                classes = list(classes) + ["Text"] * (orig_count - n)
                n = orig_count
            else:
                # Model added extra blocks: truncate
                classes = classes[:orig_count]
                n = orig_count

        # Use model's block_text if provided; fill empty strings with original Vision text
        model_texts = p.get("block_text", None)
        model_boxes = p.get("block_boxes", None)

        if model_texts is not None:
            # Pad model_texts if it's shorter than n (after padding)
            if len(model_texts) < n:
                model_texts = list(model_texts) + [""] * (n - len(model_texts))
            texts = []
            for i, mt in enumerate(model_texts[:n]):
                if mt and mt.strip():
                    texts.append(mt)
                elif original_blocks and page_idx < len(original_blocks):
                    orig = original_blocks[page_idx]
                    texts.append(orig[i]["text"] if i < len(orig) else "")
                else:
                    texts.append("")
            if model_boxes is not None and len(model_boxes) == n:
                boxes = model_boxes
            elif original_blocks and page_idx < len(original_blocks):
                boxes = [b["box"] for b in original_blocks[page_idx]]
            else:
                boxes = [[0, 0, 0, 0]] * n
        elif original_blocks and page_idx < len(original_blocks):
            # Text-only provider path: keep original Vision boxes/text
            texts = [b["text"] for b in original_blocks[page_idx]]
            boxes = [b["box"] for b in original_blocks[page_idx]]
        else:
            texts = [""] * n
            boxes = [[0, 0, 0, 0]] * n

        if order is not None:
            # Truncate order if it exceeds n (e.g. model returned fewer blocks)
            if len(order) > n:
                order = order[:n]
            # Handle 1-based indexing (some models number blocks starting from 1)
            if len(order) > 0 and order[0] >= 1 and max(order) >= len(boxes):
                order = [i - 1 for i in order]

            # ------------------------------------------------------------------
            # Validate LLM reading order — fallback to geometry if invalid
            # ------------------------------------------------------------------
            ro_source = "llm"
            order_valid = True
            if len(order) != n:
                order_valid = False
            else:
                seen = set()
                for idx in order:
                    if idx < 0 or idx >= n or idx in seen:
                        order_valid = False
                        break
                    seen.add(idx)

            if not order_valid:
                # Fallback 1: geometry-based reading order from existing module
                if original_blocks and page_idx < len(original_blocks):
                    from layout.reading_order import geometry_order
                    geo_boxes = [b["box"] for b in original_blocks[page_idx]]
                    order = geometry_order(geo_boxes)
                    if len(order) == n and len(set(order)) == n and max(order) < n:
                        ro_source = "geometry"
                    else:
                        # Fallback 2: sequential order
                        order = list(range(n))
                        ro_source = "default"
                else:
                    order = list(range(n))
                    ro_source = "default"

            if len(order) == n and max(order) < len(boxes):
                final_boxes = [boxes[i] for i in order]
                final_texts = [texts[i] for i in order]
            elif len(order) == n:
                raise ValueError(f"page_order {order} incompatible with {len(boxes)} blocks")
            else:
                # order shorter than n (padded blocks): fill in missing indices
                used = set(order)
                missing = sorted(i for i in range(n) if i not in used)
                full_order = list(order) + missing
                final_boxes = [boxes[i] for i in full_order]
                final_texts = [texts[i] for i in full_order]
                order = full_order
        else:
            final_boxes = boxes[:n]
            final_texts = texts[:n]
            ro_source = "default"

        # Reorder classes to match reading order permutation
        if order is not None and len(order) == n:
            classes = [classes[i] for i in order]

        # Remap legacy class names to RFQ-approved equivalents
        legacy_map = {"Page-number": "Page-header"}
        classes = [legacy_map.get(c, c) for c in classes]

        # Override: any output position whose text is the picture marker gets Picture class
        for i in range(len(final_texts)):
            if final_texts[i] == NO_TEXT_IN_PICTURE_MARKER:
                classes[i] = "Picture"

        # Override: LLM-assigned Picture blocks that were originally text
        if orig_blocks is not None:
            for i in range(len(final_texts)):
                if classes[i] != "Picture":
                    continue
                orig_idx = order[i] if (order is not None and i < len(order)) else i
                if orig_idx < len(orig_blocks) and orig_blocks[orig_idx].get("is_picture"):
                    continue
                t = final_texts[i]
                if t and t.strip() and t != NO_TEXT_IN_PICTURE_MARKER:
                    b = final_boxes[i]
                    area = (b[2] - b[0]) * (b[3] - b[1])
                    if area < 1000:
                        safe_text = t[:60].encode("ascii", errors="backslashreplace").decode("ascii")
                        _term_warn(f"      [Override] Block {i} (orig {orig_idx}): "
                            f"LLM-assigned Picture reclassified to Text — "
                            f"area={area} text={safe_text!r}")
                        classes[i] = "Text"

        for c in classes:
            if c not in VALID_CLASSES:
                raise ValueError(f"Invalid class label: {c}")

        page_out = {
            "block_boxes": final_boxes,
            "block_classes": classes,
            "block_text": final_texts,
        }

        if level >= 4:
            page_out["reading_order"] = order if order is not None else list(range(n))
            page_out["block_relations"] = relations

        # Track source for pipeline logging (stripped before JSON serialization)
        page_out["_ro_source"] = ro_source

        result.append(page_out)
    return result


# ---------------------------------------------------------------------------
# API Execution Wrappers
# ---------------------------------------------------------------------------

def _post_with_retry(url, json_body, headers, timeout):
    resp = None
    retries = 0
    t0 = time.time()
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = requests.post(url, json=json_body, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                latency = (time.time() - t0) * 1000
                return resp, retries, latency
            retries += 1
            wait = int(resp.headers.get("Retry-After", RETRY_BACKOFF_SECONDS * (attempt + 1) * 4))
            if wait > 60: wait = 60
            time.sleep(wait)
        except Exception as e:
            retries += 1
            if attempt == RETRY_ATTEMPTS - 1:
                raise RuntimeError(f"Request failed after {retries} attempts: {e}")
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    latency = (time.time() - t0) * 1000
    raise RuntimeError(f"Request failed after {RETRY_ATTEMPTS} attempts")


def run_openrouter_proofread_batch(image_paths, pages_blocks, level=3):
    if not OPENROUTER_API_KEY: raise RuntimeError("OPENROUTER_API_KEY not set")
    prompt = build_batch_prompt(pages_blocks, level=level)
    payload = {"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 16384}
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    n_pages = len(image_paths)
    in_tok = max(1, len(prompt) // 4)
    try:
        resp, retries, lat = _post_with_retry(OPENROUTER_ENDPOINT, payload, headers, timeout=180)
        raw_text = resp.json()["choices"][0]["message"]["content"]
        out_tok = max(1, len(raw_text) // 4)
        if _usg:
            _usg.record_request("openrouter", success=True, latency_ms=lat,
                retry_count=retries, pages=n_pages, images=n_pages,
                input_tokens=in_tok, output_tokens=out_tok)
        pages_out = _parse_batch_response(raw_text, n_pages, pages_blocks, level)
        if level >= 4:
            for page in pages_out:
                page["annotation_quality"] = "degraded_text_only_fallback"
        return pages_out
    except Exception as e:
        if _usg:
            _usg.record_request("openrouter", success=False, latency_ms=0,
                retry_count=0, error=str(e), pages=n_pages, images=n_pages)
        raise


def run_gemini_proofread_batch(image_paths, pages_blocks, level=3):
    if not GEMINI_API_KEY: raise RuntimeError("GEMINI_API_KEY not set")
    prompt = build_vision_batch_prompt(pages_blocks, level=level)
    parts = [{"text": prompt}]
    for img_path in image_paths:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": image_to_base64(img_path)}})
    url = GEMINI_ENDPOINT_TMPL.format(model=GEMINI_MODEL)
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload = {"contents": [{"parts": parts}], "generationConfig": {"response_mime_type": "application/json"}}
    n_pages = len(image_paths)
    in_tok = max(1, len(prompt) // 4)
    try:
        resp, retries, lat = _post_with_retry(url, payload, headers, timeout=180)
        raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        out_tok = max(1, len(raw_text) // 4)
        if _usg:
            _usg.record_request("gemini", success=True, latency_ms=lat,
                retry_count=retries, pages=n_pages, images=n_pages,
                input_tokens=in_tok, output_tokens=out_tok)
        pages_out = _parse_batch_response(raw_text, n_pages, pages_blocks, level)
        if level >= 4:
            for page in pages_out:
                page["annotation_quality"] = "full_level4"
        return pages_out
    except Exception as e:
        if _usg:
            _usg.record_request("gemini", success=False, latency_ms=0,
                retry_count=0, error=str(e), pages=n_pages, images=n_pages)
        raise


def run_groq_proofread_batch(image_paths, pages_blocks, level=3):
    if not GROQ_API_KEY: raise RuntimeError("GROQ_API_KEY not set")
    prompt = build_batch_prompt(pages_blocks, level=level)
    payload = {"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 8192}
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    n_pages = len(image_paths)
    in_tok = max(1, len(prompt) // 4)
    try:
        resp, retries, lat = _post_with_retry(GROQ_ENDPOINT, payload, headers, timeout=180)
        raw_text = resp.json()["choices"][0]["message"]["content"]
        out_tok = max(1, len(raw_text) // 4)
        if _usg:
            _usg.record_request("groq", success=True, latency_ms=lat,
                retry_count=retries, pages=n_pages, images=n_pages,
                input_tokens=in_tok, output_tokens=out_tok)
        pages_out = _parse_batch_response(raw_text, n_pages, pages_blocks, level)
        if level >= 4:
            for page in pages_out:
                page["annotation_quality"] = "degraded_text_only_fallback"
        return pages_out
    except Exception as e:
        if _usg:
            _usg.record_request("groq", success=False, latency_ms=0,
                retry_count=0, error=str(e), pages=n_pages, images=n_pages)
        raise


def run_glm_proofread_batch(image_paths, pages_blocks, level=3):
    if not GLM_API_KEY: raise RuntimeError("GLM_API_KEY not set")
    prompt = build_vision_batch_prompt(pages_blocks, level=level)
    content = [{"type": "text", "text": prompt}]
    for img_path in image_paths:
        b64 = image_to_base64(img_path)
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

    payload = {"model": GLM_MODEL, "messages": [{"role": "user", "content": content}], "max_tokens": 16384}
    headers = {"Authorization": f"Bearer {GLM_API_KEY}", "Content-Type": "application/json"}
    n_pages = len(image_paths)
    in_tok = max(1, len(prompt) // 4)
    try:
        resp, retries, lat = _post_with_retry(GLM_ENDPOINT, payload, headers, timeout=180)
        raw_text = resp.json()["choices"][0]["message"].get("content", "")
        out_tok = max(1, len(raw_text) // 4)
        if _usg:
            _usg.record_request("glm", success=True, latency_ms=lat,
                retry_count=retries, pages=n_pages, images=n_pages,
                input_tokens=in_tok, output_tokens=out_tok)
        pages_out = _parse_batch_response(raw_text, n_pages, pages_blocks, level)
        if level >= 4:
            for page in pages_out:
                page["annotation_quality"] = "full_level4"
        return pages_out
    except Exception as e:
        if _usg:
            _usg.record_request("glm", success=False, latency_ms=0,
                retry_count=0, error=str(e), pages=n_pages, images=n_pages)
        raise



def run_iamhc_proofread_batch(image_paths, pages_blocks, level=3):
    """OpenAI-compatible relay (supports vision models)."""
    if not IAMHC_API_KEY:
        raise RuntimeError("IAMHC_API_KEY not set")
    prompt = build_vision_batch_prompt(pages_blocks, level=level)
    content = [{"type": "text", "text": prompt}]
    for img_path in image_paths:
        b64 = image_to_base64(img_path)
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    payload = {"model": IAMHC_MODEL, "messages": [{"role": "user", "content": content}], "max_tokens": 16384}
    headers = {"Authorization": f"Bearer {IAMHC_API_KEY}", "Content-Type": "application/json"}
    n_pages = len(image_paths)
    in_tok = max(1, len(prompt) // 4)
    try:
        resp, retries, lat = _post_with_retry(IAMHC_ENDPOINT, payload, headers, timeout=180)
        raw_text = resp.json()["choices"][0]["message"]["content"]
        out_tok = max(1, len(raw_text) // 4)
        if _usg:
            _usg.record_request("iamhc", success=True, latency_ms=lat,
                retry_count=retries, pages=n_pages, images=n_pages,
                input_tokens=in_tok, output_tokens=out_tok)
        pages_out = _parse_batch_response(raw_text, n_pages, pages_blocks, level)
        if level >= 4:
            for page in pages_out:
                page["annotation_quality"] = "full_level4"
        return pages_out
    except Exception as e:
        try:
            text_prompt = build_batch_prompt(pages_blocks, level=level)
            text_payload = {"model": IAMHC_MODEL, "messages": [{"role": "user", "content": text_prompt}], "max_tokens": 16384}
            resp, retries, lat = _post_with_retry(IAMHC_ENDPOINT, text_payload, headers, timeout=180)
            raw_text = resp.json()["choices"][0]["message"]["content"]
            out_tok = max(1, len(raw_text) // 4)
            if _usg:
                _usg.record_request("iamhc", success=True, latency_ms=lat,
                    retry_count=retries, pages=n_pages, images=n_pages,
                    input_tokens=in_tok, output_tokens=out_tok)
            pages_out = _parse_batch_response(raw_text, n_pages, pages_blocks, level)
            if level >= 4:
                for page in pages_out:
                    page["annotation_quality"] = "degraded_text_only_fallback"
            return pages_out
        except Exception as e2:
            if _usg:
                _usg.record_request("iamhc", success=False, latency_ms=0,
                    retry_count=0, error=str(e2), pages=n_pages, images=n_pages)
            raise RuntimeError(f"iamhc vision+text both failed: {e} / {e2}")


def run_proofread_batch(provider: str, image_paths, pages_blocks, level=3):
    providers = {
        "openrouter": run_openrouter_proofread_batch,
        "gemini": run_gemini_proofread_batch,
        "groq": run_groq_proofread_batch,
        "glm": run_glm_proofread_batch,
        "iamhc": run_iamhc_proofread_batch,
    }
    # Build failover chain: requested provider first, then fallbacks
    chain = [provider]
    if provider == "gemini":
        chain.extend(["glm", "iamhc", "openrouter", "groq"])
    elif provider == "glm":
        chain.extend(["iamhc", "openrouter", "groq"])
    elif provider == "iamhc":
        chain.extend(["openrouter", "groq"])
    elif provider == "openrouter":
        chain.extend(["groq"])
    elif provider == "groq":
        pass

    first_error = None
    for p in chain:
        if p not in providers:
            continue
        try:
            return providers[p](image_paths, pages_blocks, level)
        except Exception as e:
            if first_error is None:
                first_error = e
            _term_warn(f"      [Warning] {p} failed, trying next provider... ({e})")
            continue
    raise RuntimeError(f"All providers failed. First error: {first_error}")


# ---------------------------------------------------------------------------
# Orchestration & Validation
# ---------------------------------------------------------------------------

# LANGUAGE_HINTS and VALID_CLASSES_SET imported from core.config


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

    # Logging
    from utils.logging import PipelineLogger
    plog = PipelineLogger(logs_dir)
    plog.start_stage("total")

    # Usage tracker
    global _usg
    _usg = UsageTracker(QUOTA_STATE_FILE)
    plog.log(f"      Usage tracker initialized at {QUOTA_STATE_FILE}")

    # Step 1: PDF -> Images
    plog.start_stage("pdf_to_images")
    plog.log(f"[1/5] Splitting {pdf_path.name} into page images...")
    image_paths = pdf_to_images(pdf_path, images_dir, dpi=dpi, jpeg_quality=jpeg_quality)
    if max_pages > 0 and len(image_paths) > max_pages:
        plog.log(f"      Limiting to first {max_pages} of {len(image_paths)} pages")
        image_paths = image_paths[:max_pages]
    plog.end_stage("pdf_to_images")

    # Detect embedded raster images from PDF (no API call)
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

    # Optional: Preprocessing
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

    # Step 2: Google Vision OCR
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
            plog.log(f"      No text -- excluding page"); img_path.unlink(missing_ok=True); continue

        # Picture region detection: try embedded images first, fall back to CV
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

    # Step 3: LLM Proofreading
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

    # Auto relations fallback (Level 4 only): when LLM returns empty relations
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

    # Step 4: Validation + Scoring + QA Overlays
    jsons = sorted(json_dir.glob("*.json"))
    all_scores = []
    all_validations = []
    all_overlays = []

    if validate or qa or create_report:
        plog.start_stage("validation")
        plog.log(f"[4/5] Analyzing annotations...")
        for j in jsons:
            r = advanced_validate(j)
            s = score_page(j)
            all_validations.append((j, r, s))
            status = "PASS" if r["valid"] else "FAIL"
            detail = f" ({len(r['errors'])} errors)" if not r["valid"] else ""
            plog.log(f"      {j.name}: {status}{detail} | Scores: OCR={s['ocr']}% RO={s['reading_order']}% Overall={s['overall']}%")

            if qa:
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

    # Step 5: HTML Report
    if create_report and jsons:
        plog.start_stage("report")
        plog.log(f"[5/5] Generating HTML report...")
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
        from report.html_report import generate_report
        report_path = report_dir / "report.html" if report_dir else out_dir / "report" / "report.html"
        _r_usage = {"date": time.strftime("%Y-%m-%d"), "total": 0, "providers": {}}
        if _usg:
            _rd = _usg.dashboard()
            _r_usage["providers"] = {p: d["today"]["requests"] for p, d in _rd.get("providers", {}).items()}
            _r_usage["total"] = sum(_r_usage["providers"].values())
        generate_report(report_pages, report_path, usage=_r_usage)
        plog.log(f"      -> {report_path}")
        plog.end_stage("report")

    # Original simple validate (kept for backward compatibility)
    if validate and not any(all_validations):
        plog.log(f"\n[Validation] Checking annotations...")
        passed = 0
        for j in jsons:
            r = advanced_validate(j)
            status = "PASS" if r["valid"] else "FAIL"
            detail = f" ({len(r['errors'])} errors)" if not r["valid"] else ""
            plog.log(f"      {j.name}: {status}{detail}")
            if r["valid"]: passed += 1
        plog.log(f"      {passed}/{len(jsons)} pages valid")

    # ZIP creation
    if create_zip:
        plog.log(f"\n[ZIP] Creating submission...")
        import zipfile
        zip_path = out_dir / f"{lang}_submission.zip"
        if max_samples > 0 and len(jsons) > max_samples:
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

    # Free-tier headroom summary
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
