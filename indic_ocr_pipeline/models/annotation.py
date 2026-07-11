"""Domain models for document layout annotations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BoundingBox:
    """An axis-aligned bounding box on a page.

    Attributes:
        x1: Left edge coordinate (pixels).
        y1: Top edge coordinate (pixels).
        x2: Right edge coordinate (pixels).
        y2: Bottom edge coordinate (pixels).
    """

    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        """Horizontal span of the box."""
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        """Vertical span of the box."""
        return max(0, self.y2 - self.y1)

    @property
    def area(self) -> int:
        """Area of the box in square pixels."""
        return self.width * self.height

    @classmethod
    def from_list(cls, coords: list[int]) -> BoundingBox:
        """Create from a 4-element list [x1, y1, x2, y2]."""
        return cls(x1=coords[0], y1=coords[1], x2=coords[2], y2=coords[3])

    def to_list(self) -> list[int]:
        """Return as a 4-element list [x1, y1, x2, y2]."""
        return [self.x1, self.y1, self.x2, self.y2]


@dataclass
class Block:
    """A single OCR-detected paragraph or picture region on a page.

    Attributes:
        box: Bounding box in pixel coordinates.
        text: Raw OCR text or picture marker.
        class_label: RFQ class label (Text, Title, Table, Picture, …).
        block_text: Optional modified text (LaTeX for tables/formulas).
        is_picture: Whether this block was detected as a non-text region.
        reading_order_index: Position in the page reading order.
    """

    box: BoundingBox
    text: str
    class_label: str = "Text"
    block_text: str = ""
    is_picture: bool = False
    reading_order_index: int | None = None


@dataclass
class PageAnnotation:
    """Annotation result for a single page.

    Attributes:
        image: Filename of the source page image.
        block_boxes: Bounding boxes for each block.
        block_classes: RFQ class label per block.
        block_text: Modified text (LaTeX) per block.
        reading_order: Indices mapping blocks to reading sequence.
        block_relations: Relation objects between blocks.
        annotation_quality: Quality tag set during processing.
    """

    image: str = ""
    block_boxes: list[list[int]] = field(default_factory=list)
    block_classes: list[str] = field(default_factory=list)
    block_text: list[str] = field(default_factory=list)
    reading_order: list[int] | None = None
    block_relations: list[dict[str, Any]] | None = None
    annotation_quality: str | None = None


@dataclass
class VisionResult:
    """Result from Google Cloud Vision OCR for one page.

    Attributes:
        blocks: List of raw block dicts with 'box' and 'text' keys.
        full_text: Concatenated raw OCR text for the page.
    """

    blocks: list[dict[str, Any]] = field(default_factory=list)
    full_text: str = ""
