"""
Geometry-based reading order detection.
Used as a fallback or to validate/correct LLM-generated reading order.
"""


def detect_column_layout(boxes: list[list[float]], x_threshold: float = 50) -> str:
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


def geometry_order(boxes: list[list[float]], page_height: float | None = None) -> list[int]:
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

    # Interleave: take next from whichever column is higher on page
    result = []
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
    boxes = [b["box"] for b in blocks]
    return geometry_order(boxes)


def correct_llm_order(llm_order: list[int], geo_order: list[int],
                      boxes: list[list[float]]) -> list[int]:
    n = len(llm_order)
    if n != len(geo_order):
        return geo_order

    diffs = sum(1 for a, b in zip(llm_order, geo_order) if a != b)
    confidence = 1.0 - (diffs / n)

    if confidence >= 0.8:
        return llm_order
    return geo_order
