# OCR PAGE

Indic OCR Dataset Pipeline — extracts text + RFQ Level 4 layout annotations from scanned Indic-language PDFs using Google Cloud Vision OCR and a multi-provider LLM failover chain.

## Requirements

- Python 3.10+
- [Poppler](https://github.com/oschwartz10612/poppler-windows/releases/) (for `pdfinfo`/`pdftoppm`)
- [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) (GitHub release, not Windows Store)
- API keys for all providers you want to use

## Setup

```bash
git clone <repo>
cd ocr-page

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

## Providers

All are **free-tier** capable:

| Provider | Role | Limits |
|---|---|---|
| Google Cloud Vision | OCR (text extraction) | 1,000 units/month |
| Gemini 2.5 Flash Lite | Vision LLM (primary) | ~1,500 req/day |
| GLM-4V Flash | Vision LLM (fallback) | Rate-limited |
| IAMHC (relay) | Vision LLM (fallback) | No known limits |
| OpenRouter (Llama 3.3 70B) | Text-only LLM (fallback) | Free model, rate-limited |
| Groq (Llama 3.3 70B) | Text-only LLM (last resort) | 30 RPM, 12K TPM, 1K RPD |

**Failover chain**: `gemini → glm → iamhc → openrouter → groq`

## Usage

```bash
# Interactive CLI (recommended)
python run.py

# Direct pipeline
python indic_ocr_pipeline3.py \
    --pdf path/to/document.pdf \
    --lang odia \
    --out ./output \
    --level 4 \
    --validate \
    --report \
    --batch-size 2 \
    --provider iamhc

# With preprocessing, QA overlays, and HTML report
python indic_ocr_pipeline3.py \
    --pdf path/to/document.pdf \
    --lang odia \
    --out ./output \
    --level 4 \
    --preprocess \
    --qa \
    --report \
    --validate \
    --batch-size 2
```

### Options

| Flag | Description |
|---|---|
| `--pdf` | Input PDF file |
| `--lang` | Language code (`odia`, `telugu`, `marathi`, `tamil`, etc.) |
| `--out` | Output directory |
| `--level` | Annotation level (3 = classes + order, 4 = + LaTeX + relations) |
| `--provider` | LLM provider (`gemini`, `glm`, `iamhc`, `openrouter`, `groq`) |
| `--batch-size` | Pages per LLM call (1 or 2) |
| `--preprocess` | Apply OpenCV deskew/denoise/contrast |
| `--qa` | Generate visual QA overlay images |
| `--report` | Generate HTML quality report |
| `--validate` | Run RFQ schema validation |
| `--max-pages` | Limit number of pages to process |

## Output Structure

```
output/
├── images/          # Page images (JPEG)
├── annotations/     # JSON per page (classes, boxes, text, relations)
├── qa/              # Visual QA overlays (optional)
├── logs/            # Pipeline logs
└── report/          # HTML report (optional)
```

### Annotation JSON Schema

```json
{
  "image": "page_0001.jpg",
  "block_boxes": [[x1, y1, x2, y2], ...],
  "block_classes": ["Text", "Title", "Section-header", ...],
  "block_text": ["...", ...],
  "reading_order": [0, 3, 1, 2, ...],
  "block_relations": [
    {"from": 0, "to": 1, "relation": "caption_of_figure"},
    ...
  ],
  "annotation_quality": "full_level4",
  "validation_results": { "valid": true, ... }
}
```

### Classes

Text, Title, Section-header, List-item, TOC, Bibliography, Footnote, Page-header, Page-footer, Picture, Formula, Table, Caption

## Features

- **Multi-provider failover** — automatic fallback through the chain if a provider fails
- **Picture detection** — embedded PDF images + OpenCV contour detection
- **Reading order** — LLM-driven with geometry-based fallback
- **Block relations** — caption↔table/figure, footnote references
- **Formula/table LaTeX** — Level 4 generates LaTeX markup for formulas and tables
- **Validation** — duplicate/overlap detection, missing captions, schema enforcement
- **Scoring** — per-page OCR accuracy, reading order correctness, overall RFQ score
- **QA overlays** — visual bounding box + class + order arrow overlays
- **Usage tracking** — per-request recording with free-tier headroom summary
- **Quota enforcement** — pre-flight checks against provider limits

## Project Structure

```
├── indic_ocr_pipeline3.py    # Main pipeline
├── run.py                    # Interactive CLI
├── core/
│   └── config.py             # API keys, models, constants
├── layout/
│   ├── reading_order.py      # Geometry-based reading order
│   └── relations.py          # Auto relation detection
├── utils/
│   └── usage.py              # Usage tracker + dashboard
├── validation/
│   └── schema.py             # RFQ schema validation
├── preprocessing/
│   └── image.py              # OpenCV image preprocessing
├── qa/
│   └── draw_overlay.py       # Visual QA overlays
└── report/
    └── html_report.py        # HTML report generation
```
