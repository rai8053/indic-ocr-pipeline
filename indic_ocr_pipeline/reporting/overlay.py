"""Visual QA overlay generation with OpenCV."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from indic_ocr_pipeline.utils.config import CLASS_COLORS, VALID_CLASSES


def draw_overlay(
    image_path: Path,
    annotation_path: Path,
    output_path: Path,
    show_reading_order: bool = True,
    show_relations: bool = True,
) -> Path:
    """Draw a visual QA overlay on a page image showing block boxes, classes,
    reading order arrows, and relation arrows.

    Args:
        image_path: Path to the source page image.
        annotation_path: Path to the annotation JSON file.
        output_path: Destination path for the overlay image.
        show_reading_order: Draw white arrowed lines for reading order.
        show_relations: Draw cyan arrowed lines for block relations.

    Returns:
        ``output_path`` for chaining.
    """
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Cannot read image: {image_path}")

    with open(annotation_path, encoding="utf-8") as f:
        data = json.load(f)

    h, w = image.shape[:2]
    boxes = data.get("block_boxes", [])
    classes = data.get("block_classes", [])
    reading_order = data.get("reading_order", None)
    relations = data.get("block_relations", [])

    overlay = image.copy()

    for i, box in enumerate(boxes):
        x1, y1, x2, y2 = [int(v) for v in box]
        cls = classes[i] if i < len(classes) else "Text"
        color = CLASS_COLORS.get(cls, (200, 200, 200))

        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)

        label = f"[{i}] {cls}"
        if reading_order and i < len(reading_order):
            label += f" RO:{reading_order[i]}"

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
        cv2.rectangle(overlay, (x1, y1 - th - 4), (x1 + tw + 4, y1), color, -1)
        cv2.putText(
            overlay, label, (x1 + 2, y1 - 2),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1, cv2.LINE_AA,
        )

    if show_reading_order and reading_order and len(reading_order) > 1:
        for k in range(len(reading_order) - 1):
            src_idx = reading_order[k]
            dst_idx = reading_order[k + 1]
            if src_idx >= len(boxes) or dst_idx >= len(boxes):
                continue
            sx = int((boxes[src_idx][0] + boxes[src_idx][2]) / 2)
            sy = int((boxes[src_idx][1] + boxes[src_idx][3]) / 2)
            dx = int((boxes[dst_idx][0] + boxes[dst_idx][2]) / 2)
            dy = int((boxes[dst_idx][1] + boxes[dst_idx][3]) / 2)
            cv2.arrowedLine(overlay, (sx, sy), (dx, dy), (255, 255, 255), 2, tipLength=0.15)
            mid_x, mid_y = (sx + dx) // 2, (sy + dy) // 2
            cv2.putText(
                overlay, str(k + 1), (mid_x, mid_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA,
            )

    if show_relations and relations:
        for rel in relations:
            s = rel.get("source", -1)
            t = rel.get("target", -1)
            rtype = rel.get("relation", "")
            if s >= len(boxes) or t >= len(boxes):
                continue
            sx = int((boxes[s][0] + boxes[s][2]) / 2)
            sy = int((boxes[s][1] + boxes[s][3]) / 2)
            tx = int((boxes[t][0] + boxes[t][2]) / 2)
            ty = int((boxes[t][1] + boxes[t][3]) / 2)
            cv2.arrowedLine(overlay, (sx, sy), (tx, ty), (0, 255, 255), 1, tipLength=0.1)
            cv2.putText(
                overlay, rtype, ((sx + tx) // 2, (sy + ty) // 2 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1, cv2.LINE_AA,
            )

    legend_x = 10
    legend_y = h - 30 * len(VALID_CLASSES) - 10
    cv2.rectangle(
        overlay,
        (legend_x - 5, legend_y - 5),
        (legend_x + 160, legend_y + 30 * len(VALID_CLASSES) + 5),
        (0, 0, 0), -1,
    )
    cv2.putText(
        overlay, "Legend:", (legend_x, legend_y + 15),
        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA,
    )
    for idx, cls in enumerate(VALID_CLASSES):
        color = CLASS_COLORS.get(cls, (200, 200, 200))
        ly = legend_y + 30 * (idx + 1)
        cv2.rectangle(overlay, (legend_x, ly - 10), (legend_x + 15, ly + 5), color, -1)
        cv2.putText(
            overlay, cls, (legend_x + 20, ly),
            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1, cv2.LINE_AA,
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), overlay)
    return output_path
