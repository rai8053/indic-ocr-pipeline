"""Relation types and data structures for block-to-block relationships."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RelationType(str, Enum):
    """Valid block relation types for RFQ Level 4 annotations."""

    CAPTION_OF_TABLE = "caption_of_table"
    TABLE_HAS_CAPTION = "table_has_caption"
    CAPTION_OF_FIGURE = "caption_of_figure"
    FIGURE_HAS_CAPTION = "figure_has_caption"
    FOOTNOTE_REFERS_TO = "footnote_refers_to"


@dataclass
class Relation:
    """A directed relation between two blocks on a page.

    Attributes:
        source: Index of the source block.
        target: Index of the target block.
        relation: The relation type label.
    """

    source: int
    target: int
    relation: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the standard pipeline dict format."""
        return {"source": self.source, "target": self.target, "relation": self.relation}
