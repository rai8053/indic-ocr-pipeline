"""Tests for configuration module."""

from indic_ocr_pipeline.utils.config import (
    LANGUAGE_HINTS,
    LLM_DAILY_LIMIT,
    NO_TEXT_IN_PICTURE_MARKER,
    VALID_CLASSES,
    VALID_CLASSES_SET,
    VALID_RELATIONS,
    VISION_MONTHLY_LIMIT,
)


class TestConfig:
    def test_valid_classes(self):
        assert "Text" in VALID_CLASSES
        assert "Picture" in VALID_CLASSES
        assert "Table" in VALID_CLASSES
        assert "Caption" in VALID_CLASSES
        assert len(VALID_CLASSES) == 13

    def test_valid_classes_set(self):
        for c in VALID_CLASSES:
            assert c in VALID_CLASSES_SET

    def test_valid_relations(self):
        assert "caption_of_table" in VALID_RELATIONS
        assert "caption_of_figure" in VALID_RELATIONS
        assert "table_has_caption" in VALID_RELATIONS
        assert "figure_has_caption" in VALID_RELATIONS
        assert "footnote_refers_to" in VALID_RELATIONS

    def test_limits_positive(self):
        assert VISION_MONTHLY_LIMIT > 0
        assert LLM_DAILY_LIMIT > 0

    def test_language_hints(self):
        assert "odia" in LANGUAGE_HINTS
        assert LANGUAGE_HINTS["odia"] == ["or"]
        assert "hindi" in LANGUAGE_HINTS
        assert LANGUAGE_HINTS["hindi"] == ["hi"]

    def test_picture_marker(self):
        assert NO_TEXT_IN_PICTURE_MARKER == "[NO_TEXT_IN_PICTURE]"
