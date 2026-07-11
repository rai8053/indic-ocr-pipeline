"""Tests for quality scoring module."""

import json

from indic_ocr_pipeline.layout.validator import score_page


class TestScoring:
    def test_perfect_page(self, sample_page_path):
        scores = score_page(sample_page_path)
        assert scores["ocr"] == 100
        assert scores["reading_order"] == 100
        assert scores["overall"] >= 90
        assert scores["boxes"] == 100

    def test_missing_fields(self, tmp_path):
        data = {
            "image": "test.jpg",
            "block_boxes": [[0, 0, 100, 100]],
            "block_classes": ["Text"],
            "block_text": ["Hello"],
        }
        path = tmp_path / "minimal.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        scores = score_page(path)
        assert scores["ocr"] >= 0
        assert scores["overall"] >= 0
