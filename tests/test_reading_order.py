"""Tests for reading order detection."""

import json


class TestReadingOrder:
    def test_geometry_order_simple(self):
        from indic_ocr_pipeline.layout.reading_order import geometry_order

        boxes = [
            [100, 100, 500, 150],  # Title (top)
            [100, 200, 500, 400],  # Text body
            [100, 450, 500, 600],  # Another paragraph
        ]
        order = geometry_order(boxes)
        assert len(order) == 3
        assert order[0] == 0  # Title first
        assert order[1] == 1  # Then first paragraph
        assert order[2] == 2  # Then second paragraph

    def test_geometry_order_two_column(self):
        from indic_ocr_pipeline.layout.reading_order import geometry_order

        boxes = [
            [100, 100, 400, 200],  # Left column top
            [100, 250, 400, 500],  # Left column bottom
            [450, 100, 800, 300],  # Right column top
            [450, 350, 800, 500],  # Right column bottom
        ]
        order = geometry_order(boxes)
        assert len(order) == 4

    def test_geometry_order_rejects_empty(self):
        from indic_ocr_pipeline.layout.reading_order import geometry_order

        order = geometry_order([])
        assert order == []

    def test_geometry_order_no_overlap(self):
        from indic_ocr_pipeline.layout.reading_order import geometry_order

        boxes = [
            [0, 0, 100, 50],
            [200, 0, 300, 50],
            [0, 100, 100, 150],
        ]
        order = geometry_order(boxes)
        assert len(order) == 3
        assert order[0] == 0  # Top-left
        assert order[-1] == 2  # Bottom-left last
