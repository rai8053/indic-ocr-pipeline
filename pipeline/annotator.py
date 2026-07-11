import json
import re

from core.terminal import warn as _term_warn
from core.config import NO_TEXT_IN_PICTURE_MARKER, VALID_CLASSES


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

        orig_blocks = (original_blocks[page_idx]
                       if original_blocks and page_idx < len(original_blocks)
                       else None)
        orig_count = len(orig_blocks) if orig_blocks else 0

        if orig_count > 0 and n != orig_count:
            _term_warn(f"      [Warning] Page {page_idx}: model returned {n} blocks, "
                  f"expected {orig_count}. Padding output.")
            if n < orig_count:
                classes = list(classes) + ["Text"] * (orig_count - n)
                n = orig_count
            else:
                classes = classes[:orig_count]
                n = orig_count

        model_texts = p.get("block_text", None)
        model_boxes = p.get("block_boxes", None)

        if model_texts is not None:
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
            texts = [b["text"] for b in original_blocks[page_idx]]
            boxes = [b["box"] for b in original_blocks[page_idx]]
        else:
            texts = [""] * n
            boxes = [[0, 0, 0, 0]] * n

        if order is not None:
            if len(order) > n:
                order = order[:n]
            if len(order) > 0 and order[0] >= 1 and max(order) >= len(boxes):
                order = [i - 1 for i in order]

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
                if original_blocks and page_idx < len(original_blocks):
                    from layout.reading_order import geometry_order
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
            ro_source = "default"

        if order is not None and len(order) == n:
            classes = [classes[i] for i in order]

        legacy_map = {"Page-number": "Page-header"}
        classes = [legacy_map.get(c, c) for c in classes]

        for i in range(len(final_texts)):
            if final_texts[i] == NO_TEXT_IN_PICTURE_MARKER:
                classes[i] = "Picture"

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

        page_out["_ro_source"] = ro_source

        result.append(page_out)
    return result
