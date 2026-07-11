import os
from pathlib import Path

# Load .env file from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _k, _v = _k.strip(), _v.strip().strip("\"'")
                if _k not in os.environ:
                    os.environ[_k] = _v

GOOGLE_VISION_API_KEY = os.environ.get("GOOGLE_VISION_API_KEY", os.environ.get("GOOGLE_VISION_KEY", ""))
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GLM_API_KEY = os.environ.get("GLM_API_KEY", "")

OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_ENDPOINT_TMPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GLM_ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
GLM_MODEL = "glm-4v-flash"
VISION_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 5

QUOTA_STATE_FILE = Path(os.environ.get("QUOTA_STATE_FILE", str(Path(__file__).resolve().parent.parent / ".pipeline_quota_state.json")))

# Free-tier safety limits (far below provider hard limits)
VISION_MONTHLY_LIMIT = 1000   # Google Cloud Vision: 1000 units/month free
LLM_DAILY_LIMIT = 1500        # Per-provider LLM requests/day (Gemini: ~1500 free)

IAMHC_ENDPOINT = os.environ.get("IAMHC_ENDPOINT", "https://api.iamhc.cn/v1/chat/completions")
IAMHC_MODEL = os.environ.get("IAMHC_MODEL", "auto")
IAMHC_API_KEY = os.environ.get("IAMHC_API_KEY", "")

NO_TEXT_IN_PICTURE_MARKER = "[NO_TEXT_IN_PICTURE]"

VALID_CLASSES = [
    "Text", "Title", "Section-header", "List-item", "TOC", "Bibliography",
    "Footnote", "Page-header", "Page-footer", "Picture", "Formula",
    "Table", "Caption",
]
VALID_CLASSES_SET = set(VALID_CLASSES)

VALID_RELATIONS = [
    "caption_of_table", "table_has_caption",
    "caption_of_figure", "figure_has_caption",
    "footnote_refers_to",
]

LANGUAGE_HINTS = {
    "hindi": ["hi"], "bengali": ["bn"], "gujarati": ["gu"], "odia": ["or"],
    "assamese": ["as"], "punjabi": ["pa"], "marathi": ["mr"], "urdu": ["ur"],
    "tamil": ["ta"], "telugu": ["te"], "malayalam": ["ml"], "kannada": ["kn"],
}

CLASS_COLORS = {
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
