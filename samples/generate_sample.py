"""
Sample data for testing the Indic OCR Pipeline.

This module provides helper functions to generate sample annotation
data for test runs and demonstrations without needing a real PDF.
"""
import json
from pathlib import Path


def create_sample_annotation(out_path: Path) -> dict:
    """Create a minimal sample annotation JSON.

    Args:
        out_path: Path to write the sample annotation.

    Returns:
        The annotation dict for inspection.
    """
    data = {
        "image": "sample_page.jpg",
        "block_boxes": [
            [100, 100, 500, 150],
            [100, 160, 500, 400],
            [100, 410, 500, 600],
            [600, 100, 900, 300],
        ],
        "block_classes": ["Title", "Text", "Text", "Picture"],
        "block_text": [
            "Chapter 1: Introduction",
            "This is a sample paragraph for testing the pipeline output format. "
            "It demonstrates how annotated text appears in the JSON output.",
            "Another paragraph with additional content that follows in reading order.",
            "[NO_TEXT_IN_PICTURE]",
        ],
        "reading_order": [0, 1, 2, 3],
        "block_relations": [],
        "annotation_quality": "full_level4",
        "validation_results": {"valid": True, "errors": []},
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data


def create_sample_report_data() -> list[dict]:
    """Create sample data suitable for the HTML report generator.

    Returns:
        A list of page dicts matching the report generator's expected format.
    """
    return [
        {
            "name": "page_0001.json",
            "validation": {
                "valid": True,
                "errors": [],
                "warnings": [],
                "class_count": 4,
                "level": 4,
                "checks": {},
            },
            "scores": {
                "ocr": 100,
                "layout": 85,
                "reading_order": 100,
                "boxes": 100,
                "relations": 100,
                "overall": 97,
            },
            "overlay": "",
        }
    ]


if __name__ == "__main__":
    sample = create_sample_annotation(Path("samples/sample_annotation.json"))
    print(f"Created sample annotation with {len(sample['block_boxes'])} blocks")
