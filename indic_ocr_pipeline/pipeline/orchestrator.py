"""Pipeline orchestration — prompt building, JSON parsing, and batch annotation."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from indic_ocr_pipeline.utils.config import (
    VALID_CLASSES, NO_TEXT_IN_PICTURE_MARKER, VALID_CLASSES_SET,
)
from indic_ocr_pipeline.utils.helpers import warn as _term_warn


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def build_vision_batch_prompt(
    pages_blocks: list[list[dict]],
    level: int = 3,
) -> str:
    """Build a prompt for vision-capable LLMs (Gemini, GLM, IAMHC).

    Includes page images inline and requests block classes, reading order,
    block_text (LaTeX for tables/formulas), and optionally block_relations.

    Args:
        pages_blocks: Raw OCR blocks per page, each with ``box`` and ``text``.
        level: Annotation level (3 = classes + order, 4 = + relations).

    Returns:
        Complete prompt string ready to send to the LLM.
    """
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


def build_batch_prompt(
    pages_blocks: list[list[dict]],
    max_chars: int = 100,
    level: int = 3,
) -> str:
    """Build a text-only prompt for providers that cannot handle images (OpenRouter, Groq).

    Truncates long block texts to ``max_chars`` to stay within token limits.

    Args:
        pages_blocks: Raw OCR blocks per page.
        max_chars: Maximum characters per block text before truncation.
        level: Annotation level.

    Returns:
        Complete text-only prompt string.
    """
    class_list = ", ".join(VALID_CLASSES)
    truncated: list[list[dict]] = []
    for blocks in pages_blocks:
        page_blocks: list[dict] = []
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
# JSON extraction & repair
# ---------------------------------------------------------------------------

def _find_matching_brace(text: str, start: int) -> int:
    """Find the matching closing brace for an opening brace at ``start``."""
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch == "{":
                depth = 1 if i == start else depth + 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
    return -1


def _repair_json(text: str) -> str:
    """Attempt to repair common JSON formatting issues."""
    original = text
    text = text.replace(",\n]", "\n]").replace(",]", "]")
    text = text.replace(",\n}", "\n}").replace(",}", "}")
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass
    text = re.sub(r'"\s+"', '", "', text)
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass
    return original


def _extract_json_object(raw_text: str) -> dict:
    """Extract and parse the first JSON object from LLM response text.

    Handles markdown fences, emoji reasoning blocks, and common JSON
    formatting issues.
    """
    text = raw_text.strip()

    # Strip emoji reasoning tags
    while "\U0001f4ad" in text and "\u2728" in text:
        start, end = text.index("\U0001f4ad"), text.index("\u2728") + len("\u2728")
        text = (text[:start] + text[end:]).strip()

    # Strip markdown fences
    while "```" in text:
        parts = text.split("```", 1)
        before = parts[0].strip()
        if "{" in before:
            text = before
        else:
            fence_end = parts[1].find("```") if len(parts) > 1 else -1
            fenced = parts[1][:fence_end] if fence_end >= 0 else (
                parts[1] if len(parts) > 1 else ""
            )
            if "{" in fenced:
                text = fenced.strip()
                if text.startswith("json"):
                    text = text[4:]
            else:
                break

    first = text.find("{")
    if first == -1:
        raise ValueError(f"No JSON object found: {raw_text[:200]!r}")
    last = _find_matching_brace(text, first)
    if last == -1:
        raise ValueError(f"Unmatched opening brace: {raw_text[:200]!r}")
    text = text[first:last + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        repaired = _repair_json(text)
        if repaired != text:
            return json.loads(repaired)
        raise


# ---------------------------------------------------------------------------
# Batch response parser
# ---------------------------------------------------------------------------

def _parse_batch_response(
    raw_text: str,
    expected_pages: int,
    original_blocks: Optional[list[list[dict]]] = None,
    level: int = 3,
) -> list[dict]:
    """Parse the JSON response from an LLM proofread call into page annotations.

    Handles:
    - Missing or extra blocks (pad/truncate).
    - Invalid reading orders (geometry fallback).
    - Legacy class name mapping (``Page-number`` -> ``Page-header``).
    - ``[NO_TEXT_IN_PICTURE]`` marker override -> ``Picture`` class.
    - LLM-assigned ``Picture`` reclassification for small text blocks.

    Args:
        raw_text: Raw response text from the provider.
        expected_pages: Number of pages that were sent.
        original_blocks: Original OCR blocks per page for shape validation.
        level: Annotation level.

    Returns:
        List of page annotation dicts, each with ``block_boxes``,
        ``block_classes``, ``block_text``, and optionally ``reading_order``
        and ``block_relations``.
    """
    parsed = _extract_json_object(raw_text)
    pages = parsed["pages"] if "pages" in parsed else (
        [parsed] if "block_classes" in parsed and expected_pages == 1 else []
    )
    if not pages or len(pages) != expected_pages:
        raise ValueError(f"Expected {expected_pages} pages, got {len(pages)}")

    result: list[dict] = []
    for page_idx, p in enumerate(pages):
        classes: list[str] = list(p.get("block_classes", []))
        order: Optional[list[int]] = p.get("page_order", None) or p.get("reading_order", None)
        n = len(classes)
        relations: list[dict] = p.get("block_relations", [])

        orig_blocks = (
            original_blocks[page_idx]
            if original_blocks and page_idx < len(original_blocks)
            else None
        )
        orig_count = len(orig_blocks) if orig_blocks else 0

        # Pad/truncate to match original block count
        if orig_count > 0 and n != orig_count:
            _term_warn(
                f"      [Warning] Page {page_idx}: model returned {n} blocks, "
                f"expected {orig_count}. Padding output."
            )
            if n < orig_count:
                classes = list(classes) + ["Text"] * (orig_count - n)
                n = orig_count
            else:
                classes = classes[:orig_count]
                n = orig_count

        model_texts: Optional[list[str]] = p.get("block_text", None)
        model_boxes: Optional[list[list[int]]] = p.get("block_boxes", None)

        if model_texts is not None:
            if len(model_texts) < n:
                model_texts = list(model_texts) + [""] * (n - len(model_texts))
            texts: list[str] = []
            for i, mt in enumerate(model_texts[:n]):
                if mt and mt.strip():
                    texts.append(mt)
                elif original_blocks and page_idx < len(original_blocks):
                    orig = original_blocks[page_idx]
                    texts.append(orig[i]["text"] if i < len(orig) else "")
                else:
                    texts.append("")
            if model_boxes is not None and len(model_boxes) == n:
                boxes: list[list[int]] = model_boxes
            elif original_blocks and page_idx < len(original_blocks):
                boxes = [b["box"] for b in original_blocks[page_idx]]
            else:
                boxes = [[0, 0, 0, 0]] * n
        elif original_blocks and page_idx < len(original_blocks):
            texts = [b["text"] for b in original_blocks[page_idx]]
            boxes = [b["box"] for b in original_blocks[page_idx]]
        else:
            texts = [""] * n
            boxes = [[0, 0, 0, 0]] * n

        # Reading order resolution
        ro_source = "default"
        if order is not None:
            if len(order) > n:
                order = order[:n]
            if len(order) > 0 and order[0] >= 1 and max(order) >= len(boxes):
                order = [i - 1 for i in order]

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
                if original_blocks and page_idx < len(original_blocks):
                    from indic_ocr_pipeline.layout.reading_order import geometry_order
                    geo_boxes = [b["box"] for b in original_blocks[page_idx]]
                    order = geometry_order(geo_boxes)
                    if len(order) == n and len(set(order)) == n and max(order) < n:
                        ro_source = "geometry"
                    else:
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
                used = set(order)
                missing = sorted(i for i in range(n) if i not in used)
                full_order = list(order) + missing
                final_boxes = [boxes[i] for i in full_order]
                final_texts = [texts[i] for i in full_order]
                order = full_order
        else:
            final_boxes = boxes[:n]
            final_texts = texts[:n]

        # Reorder classes to match reading order permutation
        if order is not None and len(order) == n:
            classes = [classes[i] for i in order]

        # Legacy class name mapping
        legacy_map = {"Page-number": "Page-header"}
        classes = [legacy_map.get(c, c) for c in classes]

        # Marker override: [NO_TEXT_IN_PICTURE] -> Picture
        for i in range(len(final_texts)):
            if final_texts[i] == NO_TEXT_IN_PICTURE_MARKER:
                classes[i] = "Picture"

        # Reclassify small LLM-assigned Picture blocks back to Text
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
                        _term_warn(
                            f"      [Override] Block {i} (orig {orig_idx}): "
                            f"LLM-assigned Picture reclassified to Text - "
                            f"area={area} text={safe_text!r}"
                        )
                        classes[i] = "Text"

        for c in classes:
            if c not in VALID_CLASSES:
                raise ValueError(f"Invalid class label: {c}")

        page_out: dict[str, Any] = {
            "block_boxes": final_boxes,
            "block_classes": classes,
            "block_text": final_texts,
        }

        if level >= 4:
            page_out["reading_order"] = order if order is not None else list(range(n))
            page_out["block_relations"] = relations

        page_out["_ro_source"] = ro_source
        result.append(page_out)

    return result
