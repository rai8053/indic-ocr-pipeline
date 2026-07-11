"""Provider types and metadata for all supported OCR/LLM backends."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ProviderType(str, Enum):
    """Supported API provider identifiers."""

    VISION = "vision"
    GEMINI = "gemini"
    GLM = "glm"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    IAMHC = "iamhc"


@dataclass
class ProviderInfo:
    """Metadata about an API provider.

    Attributes:
        label: Human-readable display name.
        description: Model or service description.
        has_official_usage_api: Whether provider exposes usage via API.
        has_official_quota_api: Whether provider exposes quota via API.
        local_tracking: Whether we track usage locally.
    """

    label: str
    description: str
    has_official_usage_api: bool = False
    has_official_quota_api: bool = False
    local_tracking: bool = True


@dataclass
class ProviderResult:
    """Result from an LLM proofreading call.

    Attributes:
        pages: Parsed page annotations.
        raw_text: Raw response text from the provider.
        latency_ms: Total request latency in milliseconds.
        retries: Number of retries needed.
        input_tokens: Estimated input token count.
        output_tokens: Estimated output token count.
    """

    pages: list[dict[str, Any]]
    raw_text: str = ""
    latency_ms: float = 0.0
    retries: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
