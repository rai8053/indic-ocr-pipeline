"""Test fixtures shared across test modules."""
from pathlib import Path
import json
import pytest


@pytest.fixture
def sample_blocks():
    return {
        "block_boxes": [
            [100, 100, 500, 150],
            [100, 160, 500, 400],
            [100, 410, 500, 600],
            [600, 100, 900, 300],
            [600, 310, 900, 350],
        ],
        "block_classes": ["Title", "Text", "Text", "Picture", "Caption"],
        "block_text": [
            "Chapter 1",
            "This is a paragraph of text with some content for testing.",
            "Another paragraph with more content that follows the first one.",
            "[NO_TEXT_IN_PICTURE]",
            "Figure 1: A sample illustration",
        ],
    }


@pytest.fixture
def sample_relations():
    return [
        {"source": 3, "target": 4, "relation": "figure_has_caption"},
        {"source": 4, "target": 3, "relation": "caption_of_figure"},
    ]


@pytest.fixture
def sample_annotation(sample_blocks, sample_relations):
    data = dict(sample_blocks)
    data["image"] = "page_0001.jpg"
    data["reading_order"] = [0, 1, 2, 3, 4]
    data["block_relations"] = sample_relations
    data["annotation_quality"] = "full_level4"
    return data


@pytest.fixture
def sample_page_path(tmp_path, sample_annotation):
    path = tmp_path / "page_0001.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sample_annotation, f)
    return path


@pytest.fixture
def overlapping_blocks():
    return {
        "image": "page_0001.jpg",
        "block_boxes": [
            [100, 100, 500, 300],
            [200, 150, 400, 250],  # overlaps with block 0
            [100, 400, 500, 600],
        ],
        "block_classes": ["Text", "Text", "Text"],
        "block_text": ["Content A", "Content B", "Content C"],
    }
