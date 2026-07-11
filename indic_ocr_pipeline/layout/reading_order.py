"""Geometry-based reading order detection and correction."""

from __future__ import annotations


def detect_column_layout(
    boxes: list[list[float]],
    x_threshold: float = 50,
) -> str:
    """Detect the column layout of a page based on block center x-coordinates.

    Args:
        boxes: List of ``[x1, y1, x2, y2]`` bounding boxes.
        x_threshold: Minimum horizontal gap between columns (pixels).

    Returns:
        ``"single"``, ``"double"``, or ``"multi"`` column layout.
    """
    if len(boxes) < 3:
        return "single"

    centers = [(b[0] + b[2]) / 2 for b in boxes]
    sorted_centers = sorted(centers)
    gaps = [sorted_centers[i + 1] - sorted_centers[i] for i in range(len(sorted_centers) - 1)]
    large_gaps = [g for g in gaps if g > x_threshold]

    if len(large_gaps) >= 2:
        return "multi"
    elif len(large_gaps) == 1:
        return "double"
    return "single"


def geometry_order(
    boxes: list[list[float]],
    page_height: float | None = None,
) -> list[int]:
    """Determine reading order using geometric layout analysis.

    Single-column: sort top-to-bottom, left-to-right.
    Multi-column: split into left/right columns, then interleave by y-position.

    Args:
        boxes: List of ``[x1, y1, x2, y2]`` bounding boxes.
        page_height: Optional page height (not currently used, kept for API compat).

    Returns:
        List of block indices in reading order.
    """
    layout = detect_column_layout(boxes)
    indices = list(range(len(boxes)))

    if layout == "single":
        indices.sort(key=lambda i: (boxes[i][1], boxes[i][0]))
        return indices

    mid_x = max(b[2] for b in boxes) / 2
    left = [i for i in indices if (boxes[i][0] + boxes[i][2]) / 2 < mid_x]
    right = [i for i in indices if (boxes[i][0] + boxes[i][2]) / 2 >= mid_x]

    left.sort(key=lambda i: boxes[i][1])
    right.sort(key=lambda i: boxes[i][1])

    result: list[int] = []
    li, ri = 0, 0
    while li < len(left) and ri < len(right):
        if boxes[left[li]][1] <= boxes[right[ri]][1]:
            result.append(left[li])
            li += 1
        else:
            result.append(right[ri])
            ri += 1
    result.extend(left[li:])
    result.extend(right[ri:])
    return result


def geometry_reading_order(blocks: list[dict]) -> list[int]:
    """Determine reading order from a list of block dicts with ``box`` keys.

    Args:
        blocks: List of block dicts, each containing ``{"box": [x1,y1,x2,y2]}``.

    Returns:
        List of block indices in reading order.
    """
    boxes = [b["box"] for b in blocks]
    return geometry_order(boxes)


def correct_llm_order(
    llm_order: list[int],
    geo_order: list[int],
    boxes: list[list[float]],
) -> list[int]:
    """Compare LLM reading order against geometry-based order.

    If confidence (fraction of matching indices) >= 0.8, trust the LLM order;
    otherwise fall back to geometry order.

    Args:
        llm_order: Reading order returned by the LLM.
        geo_order: Reading order computed by geometry.
        boxes: Bounding boxes (used for compatibility, not currently scored).

    Returns:
        The more confident reading order.
    """
    n = len(llm_order)
    if n != len(geo_order):
        return geo_order

    diffs = sum(1 for a, b in zip(llm_order, geo_order, strict=False) if a != b)
    confidence = 1.0 - (diffs / n)

    if confidence >= 0.8:
        return llm_order
    return geo_order
