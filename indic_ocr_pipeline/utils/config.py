"""Shared pipeline constants, API keys, and configuration."""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# .env loader — load environment variables from project root .env
# ---------------------------------------------------------------------------
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _k, _v = _k.strip(), _v.strip().strip("\"'")
                if _k not in os.environ:
                    os.environ[_k] = _v

# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------
GOOGLE_VISION_API_KEY: str = os.environ.get(
    "GOOGLE_VISION_API_KEY", os.environ.get("GOOGLE_VISION_KEY", "")
)
OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
GLM_API_KEY: str = os.environ.get("GLM_API_KEY", "")
IAMHC_API_KEY: str = os.environ.get("IAMHC_API_KEY", "")

# ---------------------------------------------------------------------------
# Endpoints & Models
# ---------------------------------------------------------------------------
OPENROUTER_MODEL: str = "meta-llama/llama-3.3-70b-instruct:free"
GEMINI_MODEL: str = "gemini-2.5-flash-lite"
GEMINI_ENDPOINT_TMPL: str = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
GLM_ENDPOINT: str = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
GLM_MODEL: str = "glm-4v-flash"
VISION_ENDPOINT: str = "https://vision.googleapis.com/v1/images:annotate"
OPENROUTER_ENDPOINT: str = "https://openrouter.ai/api/v1/chat/completions"
GROQ_MODEL: str = "llama-3.3-70b-versatile"
GROQ_ENDPOINT: str = "https://api.groq.com/openai/v1/chat/completions"
IAMHC_ENDPOINT: str = os.environ.get("IAMHC_ENDPOINT", "https://api.iamhc.cn/v1/chat/completions")
IAMHC_MODEL: str = os.environ.get("IAMHC_MODEL", "auto")

# ---------------------------------------------------------------------------
# Retry / Backoff
# ---------------------------------------------------------------------------
RETRY_ATTEMPTS: int = 3
RETRY_BACKOFF_SECONDS: int = 5

# ---------------------------------------------------------------------------
# Quota / Rate Limits
# ---------------------------------------------------------------------------
QUOTA_STATE_FILE: Path = Path(
    os.environ.get(
        "QUOTA_STATE_FILE",
        str(Path(__file__).resolve().parent.parent.parent / ".pipeline_quota_state.json"),
    )
)
VISION_MONTHLY_LIMIT: int = 1000  # Google Cloud Vision free tier
LLM_DAILY_LIMIT: int = 1500  # Per-provider daily safety limit

# ---------------------------------------------------------------------------
# Picture Detection
# ---------------------------------------------------------------------------
NO_TEXT_IN_PICTURE_MARKER: str = "[NO_TEXT_IN_PICTURE]"

# ---------------------------------------------------------------------------
# RFQ Class Taxonomy
# ---------------------------------------------------------------------------
VALID_CLASSES: list[str] = [
    "Text",
    "Title",
    "Section-header",
    "List-item",
    "TOC",
    "Bibliography",
    "Footnote",
    "Page-header",
    "Page-footer",
    "Picture",
    "Formula",
    "Table",
    "Caption",
]
VALID_CLASSES_SET: set[str] = set(VALID_CLASSES)

# ---------------------------------------------------------------------------
# Relations
# ---------------------------------------------------------------------------
VALID_RELATIONS: list[str] = [
    "caption_of_table",
    "table_has_caption",
    "caption_of_figure",
    "figure_has_caption",
    "footnote_refers_to",
]

# ---------------------------------------------------------------------------
# Language Hints
# ---------------------------------------------------------------------------
LANGUAGE_HINTS: dict[str, list[str]] = {
    "hindi": ["hi"],
    "bengali": ["bn"],
    "gujarati": ["gu"],
    "odia": ["or"],
    "assamese": ["as"],
    "punjabi": ["pa"],
    "marathi": ["mr"],
    "urdu": ["ur"],
    "tamil": ["ta"],
    "telugu": ["te"],
    "malayalam": ["ml"],
    "kannada": ["kn"],
}

# ---------------------------------------------------------------------------
# Overlay Colors
# ---------------------------------------------------------------------------
CLASS_COLORS: dict[str, tuple[int, int, int]] = {
    "Text": (0, 255, 0),
    "Title": (255, 0, 0),
    "Section-header": (0, 0, 255),
    "List-item": (255, 165, 0),
    "TOC": (128, 0, 128),
    "Bibliography": (139, 69, 19),
    "Footnote": (0, 128, 128),
    "Page-header": (255, 192, 203),
    "Page-footer": (173, 216, 230),
    "Picture": (0, 0, 139),
    "Formula": (255, 0, 255),
    "Table": (0, 255, 255),
    "Caption": (128, 128, 0),
}
