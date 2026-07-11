import json

from core.config import VALID_CLASSES


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
