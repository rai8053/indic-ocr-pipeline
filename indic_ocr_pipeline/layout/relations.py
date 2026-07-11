"""Automatic block relation detection (table-caption, figure-caption, footnote-ref)."""

from __future__ import annotations


def auto_relations(
    blocks: list[dict],
    classes: list[str],
) -> list[dict]:
    """Auto-detect caption and footnote relations between blocks.

    Uses vertical proximity and horizontal overlap to match:
    - ``Table`` blocks with ``Caption`` blocks.
    - ``Picture`` blocks with ``Caption`` blocks.
    - ``Footnote`` blocks with preceding ``Text`` blocks.

    Args:
        blocks: List of block dicts, each with a ``"box"`` key containing
            ``[x1, y1, x2, y2]``.
        classes: RFQ class label per block.

    Returns:
        List of relation dicts ``{"source": int, "target": int, "relation": str}``.
    """
    relations: list[dict] = []

    table_indices = [i for i, c in enumerate(classes) if c == "Table"]
    figure_indices = [i for i, c in enumerate(classes) if c == "Picture"]
    footnote_indices = [i for i, c in enumerate(classes) if c == "Footnote"]
    caption_indices = [i for i, c in enumerate(classes) if c == "Caption"]

    # Caption for each table
    for ti in table_indices:
        tb = blocks[ti]["box"]
        t_center_y = (tb[1] + tb[3]) / 2
        best_caption: int | None = None
        best_dist = float("inf")

        for ci in caption_indices:
            cb = blocks[ci]["box"]
            c_center_y = (cb[1] + cb[3]) / 2
            dist = abs(c_center_y - t_center_y)
            h_overlap = max(0, min(tb[2], cb[2]) - max(tb[0], cb[0]))
            if h_overlap > 0 and dist < best_dist:
                best_dist = dist
                best_caption = ci

        if best_caption is not None:
            if blocks[best_caption]["box"][1] > tb[1]:
                relations.append(
                    {"source": ti, "target": best_caption, "relation": "table_has_caption"}
                )
                relations.append(
                    {"source": best_caption, "target": ti, "relation": "caption_of_table"}
                )
            else:
                relations.append(
                    {"source": best_caption, "target": ti, "relation": "caption_of_table"}
                )
                relations.append(
                    {"source": ti, "target": best_caption, "relation": "table_has_caption"}
                )

    # Caption for each figure
    for fi in figure_indices:
        fb = blocks[fi]["box"]
        f_center_y = (fb[1] + fb[3]) / 2
        best_caption = None
        best_dist = float("inf")

        for ci in caption_indices:
            cb = blocks[ci]["box"]
            c_center_y = (cb[1] + cb[3]) / 2
            dist = abs(c_center_y - f_center_y)
            h_overlap = max(0, min(fb[2], cb[2]) - max(fb[0], cb[0]))
            if h_overlap > 0 and dist < best_dist:
                best_dist = dist
                best_caption = ci

        if best_caption is not None:
            if blocks[best_caption]["box"][1] > fb[1]:
                relations.append(
                    {"source": fi, "target": best_caption, "relation": "figure_has_caption"}
                )
                relations.append(
                    {"source": best_caption, "target": fi, "relation": "caption_of_figure"}
                )
            else:
                relations.append(
                    {"source": best_caption, "target": fi, "relation": "caption_of_figure"}
                )
                relations.append(
                    {"source": fi, "target": best_caption, "relation": "figure_has_caption"}
                )

    # Footnote references
    done: set[int] = set()
    for fi in footnote_indices:
        fb = blocks[fi]["box"]
        for ti, tb in [(i, b["box"]) for i, b in enumerate(blocks) if i not in footnote_indices]:
            if tb[1] < fb[1] and abs(((tb[1] + tb[3]) / 2) - (fb[1] - tb[3])) < 200:
                h_overlap = max(0, min(fb[2], tb[2]) - max(fb[0], tb[0]))
                if h_overlap > 0 and fi not in done:
                    relations.append({"source": ti, "target": fi, "relation": "footnote_refers_to"})
                    done.add(fi)
                    break

    return relations
