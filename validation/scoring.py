import json
from pathlib import Path
from core.config import VALID_CLASSES_SET, VALID_RELATIONS


def score_page(json_path: Path) -> dict:
    with open(json_path, encoding="utf-8") as f:
        d = json.load(f)

    n = len(d["block_boxes"])

    # OCR Score
    empty_texts = sum(1 for t in d["block_text"] if not t.strip())
    ocr_score = max(0, 100 - int((empty_texts / max(n, 1)) * 100))

    # Layout Score
    unique_classes = len(set(d["block_classes"]))
    layout_score = min(100, int((unique_classes / max(len(VALID_CLASSES_SET), 1)) * 100)) + 50
    layout_score = min(100, layout_score)

    # Reading Order Score
    has_l4 = all(k in d for k in ("reading_order", "block_relations"))
    if has_l4:
        ro = d["reading_order"]
        ro_errors = 0
        if len(ro) != n:
            ro_errors += 5
        seen = set()
        for v in ro:
            if v < 0 or v >= n:
                ro_errors += 2
            if v in seen:
                ro_errors += 1
            seen.add(v)
        ro_score = max(0, 100 - ro_errors * 10)
    else:
        ro_score = 0

    # Bounding Box Score
    box_score = 100
    bad_boxes = 0
    for box in d["block_boxes"]:
        if len(box) != 4:
            bad_boxes += 1
            continue
        x1, y1, x2, y2 = box
        if not (x2 > x1 and y2 > y1):
            bad_boxes += 1
        elif max(box) <= 1.0:
            bad_boxes += 1
    if n > 0:
        box_score = max(0, 100 - int((bad_boxes / n) * 100))

    # Relation Score
    rels = d.get("block_relations", [])
    if n > 0 and rels:
        valid_rels = sum(
            1 for r in rels
            if 0 <= r.get("source", -1) < n
            and 0 <= r.get("target", -1) < n
            and r.get("relation", "") in VALID_RELATIONS
        )
        rel_score = int((valid_rels / len(rels)) * 100)
    elif n > 0 and has_l4:
        rel_score = 100
    else:
        rel_score = 0

    # Overall
    overall = int((ocr_score + layout_score + ro_score + box_score + rel_score) / 5)

    return {
        "ocr": ocr_score,
        "layout": layout_score,
        "reading_order": ro_score,
        "boxes": box_score,
        "relations": rel_score,
        "overall": overall,
    }
