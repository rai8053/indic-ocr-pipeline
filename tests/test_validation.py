"""Tests for RFQ schema validation."""
import json


class TestValidation:
    def test_valid_page_passes(self, sample_page_path):
        from indic_ocr_pipeline.layout.validator import validate_page

        result = validate_page(sample_page_path)
        assert result["valid"] is True
        assert len(result.get("errors", [])) == 0

    def test_duplicate_boxes_warn(self, tmp_path):
        from indic_ocr_pipeline.layout.validator import validate_page

        data = {
            "image": "test.jpg",
            "block_boxes": [[100, 100, 200, 200], [100, 100, 200, 200]],
            "block_classes": ["Text", "Text"],
            "block_text": ["A", "B"],
        }
        path = tmp_path / "dup.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        result = validate_page(path)
        assert result["checks"]["duplicate_boxes"] == "WARN"

    def test_empty_invalid(self, tmp_path):
        from indic_ocr_pipeline.layout.validator import validate_page

        data = {"image": "test.jpg", "block_boxes": [], "block_classes": [], "block_text": []}
        path = tmp_path / "empty.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        result = validate_page(path)
        assert not result["valid"]

    def test_missing_required_field(self, tmp_path):
        from indic_ocr_pipeline.layout.validator import validate_page

        data = {"block_boxes": [], "block_classes": [], "block_text": []}
        path = tmp_path / "nofield.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        result = validate_page(path)
        assert not result["valid"]
        assert any("Missing fields" in e for e in result.get("errors", []))

    def test_class_count_in_output(self, sample_page_path):
        from indic_ocr_pipeline.layout.validator import validate_page

        result = validate_page(sample_page_path)
        assert result["class_count"] > 0
