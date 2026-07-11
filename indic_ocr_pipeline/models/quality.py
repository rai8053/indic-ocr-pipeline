"""Quality assessment data structures for annotation validation and scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class AnnotationQuality(str, Enum):
    """Tag indicating the quality path used during annotation."""

    FULL_LEVEL4 = "full_level4"
    DEGRADED_TEXT_ONLY = "degraded_text_only_fallback"


@dataclass
class QualityScores:
    """RFQ quality scores for a single page.

    Attributes:
        ocr: OCR completeness score (0-100).
        layout: Layout diversity score (0-100).
        reading_order: Reading order correctness score (0-100).
        boxes: Bounding box validity score (0-100).
        relations: Relation validity score (0-100).
        overall: Weighted average of all scores (0-100).
    """

    ocr: float = 0.0
    layout: float = 0.0
    reading_order: float = 0.0
    boxes: float = 0.0
    relations: float = 0.0
    overall: float = 0.0

    def to_dict(self) -> dict[str, float]:
        """Serialize to the standard dict format."""
        return {
            "ocr": self.ocr,
            "layout": self.layout,
            "reading_order": self.reading_order,
            "boxes": self.boxes,
            "relations": self.relations,
            "overall": self.overall,
        }


@dataclass
class ValidationResult:
    """Validation outcome for a single page annotation.

    Attributes:
        valid: Whether the page passed all validation checks.
        errors: List of error messages.
        warnings: List of warning messages.
        class_count: Number of blocks on the page.
        level: Annotation level (3 or 4).
        diverse: Whether multiple distinct classes are present.
        checks: Per-check results dict.
    """

    valid: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    class_count: int = 0
    level: int = 3
    diverse: bool = False
    checks: Optional[dict[str, Any]] = None
