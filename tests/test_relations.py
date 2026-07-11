"""Tests for automatic relation detection."""
from indic_ocr_pipeline.layout.relations import auto_relations


class TestRelations:
    def test_figure_caption_detected(self):
        blocks = [
            {"box": [100, 100, 500, 300]},
            {"box": [100, 310, 500, 350]},
        ]
        classes = ["Picture", "Caption"]
        relations = auto_relations(blocks, classes)
        assert len(relations) > 0
        rel_types = {r["relation"] for r in relations}
        assert "figure_has_caption" in rel_types
        assert "caption_of_figure" in rel_types

    def test_table_caption_detected(self):
        blocks = [
            {"box": [100, 100, 500, 300]},
            {"box": [100, 310, 500, 350]},
        ]
        classes = ["Table", "Caption"]
        relations = auto_relations(blocks, classes)
        rel_types = {r["relation"] for r in relations}
        assert "table_has_caption" in rel_types

    def test_empty_blocks(self):
        relations = auto_relations([], [])
        assert relations == []

    def test_no_caption_blocks(self):
        blocks = [
            {"box": [100, 100, 500, 300]},
            {"box": [100, 350, 500, 600]},
        ]
        classes = ["Picture", "Text"]
        relations = auto_relations(blocks, classes)
        assert relations == []
