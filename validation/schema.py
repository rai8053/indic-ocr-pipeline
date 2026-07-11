import json
from pathlib import Path
from core.config import VALID_CLASSES_SET, VALID_CLASSES, VALID_RELATIONS

AREA_THRESHOLD = 500


def validate_page(json_path: Path) -> dict:
    errors = []
    warnings = []
    try:
        with open(json_path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        return {"valid": False, "errors": [f"Can't read JSON: {e}"], "warnings": [],
                "class_count": 0, "level": 0, "checks": {}}

    checks = {}

    # Required fields
    missing_fields = [f for f in ("image", "block_boxes", "block_classes", "block_text") if f not in d]
    if missing_fields:
        errors.append(f"Missing fields: {missing_fields}")
        return {"valid": False, "errors": errors, "warnings": [],
                "class_count": 0, "level": 0, "checks": {"required_fields": "FAIL"}}

    checks["required_fields"] = "PASS"

    n = len(d["block_boxes"])

    # Array length consistency
    checks["array_lengths"] = "PASS"
    if len(d["block_classes"]) != n:
        errors.append(f"block_classes length {len(d['block_classes'])} != block_boxes {n}")
        checks["array_lengths"] = "FAIL"
    if len(d["block_text"]) != n:
        errors.append(f"block_text length {len(d['block_text'])} != block_boxes {n}")
        checks["array_lengths"] = "FAIL"

    if n == 0:
        errors.append("No blocks found on page")
        checks["non_empty"] = "FAIL"
        return {"valid": False, "errors": errors, "warnings": warnings,
                "class_count": 0, "level": 0, "checks": checks}

    checks["non_empty"] = "PASS"

    # Box validation
    checks["boxes"] = {"valid": 0, "invalid": 0}
    for i, box in enumerate(d["block_boxes"]):
        if len(box) != 4:
            errors.append(f"block_boxes[{i}] has {len(box)} values (expected 4)")
            checks["boxes"]["invalid"] += 1
            continue
        x1, y1, x2, y2 = box
        if not (x2 > x1 and y2 > y1):
            errors.append(f"block_boxes[{i}] {box} has x2<=x1 or y2<=y1")
            checks["boxes"]["invalid"] += 1
        elif max(box) <= 1.0:
            errors.append(f"block_boxes[{i}] {box} appears normalized (all values <= 1)")
            checks["boxes"]["invalid"] += 1
        elif (x2 - x1) * (y2 - y1) < AREA_THRESHOLD:
            warnings.append(f"block_boxes[{i}] area {(x2-x1)*(y2-y1)} is very small")
            checks["boxes"]["invalid"] += 1
        else:
            checks["boxes"]["valid"] += 1

    # Class validation
    checks["classes"] = {"valid": 0, "invalid": 0}
    for i, cls in enumerate(d["block_classes"]):
        if cls not in VALID_CLASSES_SET:
            errors.append(f"block_classes[{i}] invalid: '{cls}'")
            checks["classes"]["invalid"] += 1
        else:
            checks["classes"]["valid"] += 1

    # Duplicate box detection
    checks["duplicate_boxes"] = "PASS"
    seen_boxes = set()
    for i, box in enumerate(d["block_boxes"]):
        key = tuple(int(v) for v in box)
        if key in seen_boxes:
            warnings.append(f"block_boxes[{i}] is a duplicate of another box")
            checks["duplicate_boxes"] = "WARN"
        seen_boxes.add(key)

    # Overlapping box detection
    checks["overlapping_boxes"] = "PASS"
    for i in range(n):
        for j in range(i + 1, n):
            b1 = d["block_boxes"][i]
            b2 = d["block_boxes"][j]
            overlap_x = max(0, min(b1[2], b2[2]) - max(b1[0], b2[0]))
            overlap_y = max(0, min(b1[3], b2[3]) - max(b1[1], b2[1]))
            if overlap_x > 0 and overlap_y > 0:
                area_i = (b1[2] - b1[0]) * (b1[3] - b1[1])
                area_j = (b2[2] - b2[0]) * (b2[3] - b2[1])
                overlap_area = overlap_x * overlap_y
                if overlap_area > 0.5 * min(area_i, area_j):
                    warnings.append(f"block_boxes[{i}] and [{j}] overlap significantly ({overlap_area} px)")
                    checks["overlapping_boxes"] = "WARN"

    # Duplicate text detection
    checks["duplicate_text"] = "PASS"
    seen_texts = {}
    for i, txt in enumerate(d["block_text"]):
        t = txt.strip().lower()
        if t and len(t) > 10:
            if t in seen_texts:
                warnings.append(f"block_text[{i}] duplicates block_text[{seen_texts[t]}]")
                checks["duplicate_text"] = "WARN"
            seen_texts[t] = i

    # Empty OCR text
    checks["empty_text"] = "PASS"
    empty_count = sum(1 for t in d["block_text"] if not t.strip())
    if empty_count == n:
        errors.append(f"All {n} blocks have empty text")
        checks["empty_text"] = "FAIL"
    elif empty_count > n * 0.5:
        warnings.append(f"{empty_count}/{n} blocks have empty text")
        checks["empty_text"] = "WARN"

    # Level 4 checks
    has_l4 = all(k in d for k in ("reading_order", "block_relations"))
    level = 4 if has_l4 else 3

    if level >= 4:
        ro = d.get("reading_order", [])
        if len(ro) != n:
            errors.append(f"reading_order length {len(ro)} != blocks {n}")
            checks["reading_order"] = "FAIL"
        else:
            checks["reading_order"] = "PASS"
            seen_ro = set()
            for idx, ro_val in enumerate(ro):
                if ro_val < 0 or ro_val >= n:
                    errors.append(f"reading_order[{idx}]={ro_val} out of range [0,{n-1}]")
                    checks["reading_order"] = "FAIL"
                elif ro_val in seen_ro:
                    warnings.append(f"reading_order has duplicate index {ro_val}")
                    checks["reading_order"] = "WARN"
                seen_ro.add(ro_val)

            rels = d.get("block_relations", [])
            checks["relations"] = {"valid": 0, "invalid": 0}
            for ri, rel in enumerate(rels):
                if not all(k in rel for k in ("source", "target", "relation")):
                    errors.append(f"block_relations[{ri}] missing source/target/relation")
                    checks["relations"]["invalid"] += 1
                    continue
                s = rel.get("source", -1)
                t = rel.get("target", -1)
                rtype = rel.get("relation", "")
                if s < 0 or s >= n or t < 0 or t >= n:
                    errors.append(f"block_relations[{ri}] has out-of-range source/target")
                    checks["relations"]["invalid"] += 1
                elif s == t:
                    errors.append(f"block_relations[{ri}] source == target ({s})")
                    checks["relations"]["invalid"] += 1
                elif rtype not in VALID_RELATIONS:
                    warnings.append(f"block_relations[{ri}] unknown relation type: '{rtype}'")
                    checks["relations"]["invalid"] += 1
                else:
                    checks["relations"]["valid"] += 1

            # Missing caption checks
            checks["missing_captions"] = {"table": "PASS", "figure": "PASS"}
            table_indices = [i for i, c in enumerate(d["block_classes"]) if c == "Table"]
            figure_indices = [i for i, c in enumerate(d["block_classes"]) if c == "Picture"]
            caption_indices = [i for i, c in enumerate(d["block_classes"]) if c == "Caption"]
            rel_sources = set(r["source"] for r in rels)
            rel_targets = set(r["target"] for r in rels)

            for ti in table_indices:
                if ti not in rel_sources and ti not in rel_targets:
                    warnings.append(f"Table at index {ti} has no caption relation")
                    checks["missing_captions"]["table"] = "WARN"
            for fi in figure_indices:
                if fi not in rel_sources and fi not in rel_targets:
                    warnings.append(f"Picture at index {fi} has no caption relation")
                    checks["missing_captions"]["figure"] = "WARN"
    else:
        checks["reading_order"] = "N/A"
        checks["relations"] = {}
        checks["missing_captions"] = {}

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "class_count": n,
        "diverse": len(set(d["block_classes"])) > 1,
        "level": level,
        "checks": checks,
    }
