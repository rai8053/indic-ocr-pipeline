# Indic OCR Dataset Pipeline

Extracts text and RFQ Level 4 layout annotations from scanned Indic-language PDFs, using Google Cloud Vision OCR and a multi-provider LLM failover chain — built to run entirely within free-tier API limits.

Produces training data in the format required for document-layout / OCR-parse model fine-tuning: per-page bounding boxes, class labels, transcribed text, reading order, and inter-block relations (e.g. caption ↔ table/figure).

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Setup](#setup)
- [Providers](#providers)
- [Usage](#usage)
- [Output](#output)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)

---

## Features

- **Multi-provider LLM failover** — automatically falls through a configured provider chain if one fails or hits quota
- **Picture region detection** — combines embedded-PDF-image extraction (PyMuPDF) with OpenCV contour detection for scanned pages, so non-text visual regions (photos, diagrams, stamps) get annotated as `Picture` blocks
- **Reading order** — LLM-driven, with a geometry-based fallback when the LLM doesn't return one
- **Block relations** — automatic caption↔table/figure linking, footnote references
- **Formula/table LaTeX** — Level 4 output includes LaTeX markup for tables and formulas
- **Schema validation** — checks array-length consistency, duplicate/overlapping boxes, missing captions, relation integrity (in-bounds indices, valid relation types)
- **Quality scoring** — per-page OCR/layout/reading-order/relations scores plus an overall RFQ compliance score
- **QA overlays** — visual bounding-box + class + reading-order-arrow images for manual review
- **Usage tracking** — per-provider request/token logging with free-tier headroom reporting
- **Quota-aware** — pre-flight checks against configured per-provider limits before spending a call

---

## Requirements

- Python 3.10+
- [Poppler](https://github.com/oschwartz10612/poppler-windows/releases/) (for `pdfinfo` / `pdftoppm`)
- [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) — GitHub release build, **not** the Windows Store version
- API keys for whichever providers you enable (see [Providers](#providers))

---

## Setup

```bash
git clone https://github.com/rai8053/indic-ocr-pipeline.git
cd indic-ocr-pipeline

python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
```

Copy the example env file and fill in your own keys — **never commit `.env`**:

```bash
cp .env.example .env
```

---

## Providers

All providers below are usable on free tiers. Limits shown are the provider's *published* free-tier caps — your pipeline's own safety limits (`VISION_MONTHLY_LIMIT`, `LLM_DAILY_LIMIT` in `core/config.py`) are typically set below these as a buffer.

| Provider | Role | Free-tier limit |
|---|---|---|
| Google Cloud Vision | OCR (text extraction) | 1,000 units/month |
| Gemini 2.5 Flash Lite | Vision LLM (primary) | ~1,500 req/day |
| GLM-4V Flash | Vision LLM (fallback) | Rate-limited (provider-side) |
| OpenRouter (Llama 3.3 70B, free) | Text-only LLM (fallback) | Rate-limited (provider-side) |
| Groq (Llama 3.3 70B) | Text-only LLM (last resort) | 30 RPM · 6,000 TPM · 1,000 RPD |

**Failover chain:** `gemini → glm → openrouter → groq`

> **Note on Level 4 fidelity across providers:** Gemini and GLM can produce full Level 4 output (table/formula LaTeX, LLM-derived reading order and relations). OpenRouter and Groq's text-only prompt path cannot generate LaTeX or reliable relations — pages processed through this fallback are tagged `"annotation_quality": "degraded_text_only_fallback"` in the output JSON, and a `[WARN]` is logged, so degraded pages can be identified and reprocessed once quota resets.

---

## Usage

```bash
# Interactive CLI (recommended)
python run.py
```

```bash
# Direct pipeline invocation
python indic_ocr_pipeline3.py \
    --pdf path/to/document.pdf \
    --lang odia \
    --out ./output \
    --level 4 \
    --validate \
    --report \
    --batch-size 5 \
    --provider gemini
```

```bash
# Full run: preprocessing, QA overlays, HTML report, validation
python indic_ocr_pipeline3.py \
    --pdf path/to/document.pdf \
    --lang odia \
    --out ./output \
    --level 4 \
    --preprocess \
    --qa \
    --report \
    --validate \
    --batch-size 5
```

### Options

| Flag | Description |
|---|---|
| `--pdf` | Input PDF file |
| `--lang` | Language code — `hindi`, `bengali`, `gujarati`, `odia`, `assamese`, `punjabi`, `marathi`, `urdu`, `tamil`, `telugu`, `malayalam`, `kannada` |
| `--out` | Output directory |
| `--level` | Annotation level — see [Annotation Levels](#annotation-levels) below |
| `--provider` | LLM provider override — `gemini`, `glm`, `openrouter`, `groq` |
| `--batch-size` | Pages per LLM call. Tune based on provider token limits — see note below |
| `--preprocess` | Apply OpenCV deskew / denoise / contrast correction before OCR |
| `--qa` | Generate visual QA overlay images |
| `--report` | Generate an HTML quality report |
| `--validate` | Run RFQ schema validation |
| `--max-pages` | Limit number of pages processed (useful for test runs) |

> **Batch size vs. token limits:** larger batches mean fewer API calls but higher per-request token usage. If you hit truncated/malformed JSON responses on a given provider, reduce `--batch-size` for that provider — each provider's practical ceiling depends on its max output tokens (check `core/config.py` for the per-provider `max_tokens` values currently in use).

---

## Annotation Levels

| Level | What it produces | How |
|---|---|---|
| **1** | Raw OCR only — bounding boxes + transcribed text per paragraph | Google Cloud Vision `DOCUMENT_TEXT_DETECTION`. No LLM involved. |
| **2** | Raw OCR with LLM fallback — same as Level 1, produced when all LLM providers fail mid-run | Vision OCR output dumped directly to JSON with all classes set to `"Text"`. No reading order, no relations. Logged as a fallback. |
| **3** | Class labels + reading order (recommended minimum for training data) | LLM assigns one of 13 RFQ classes (`Text`, `Title`, `Picture`, `Formula`, etc.) to each block and returns a `reading_order` permutation. |
| **4** | Full RFQ annotation — classes + reading order + block relations + LaTeX markup | LLM additionally returns `block_relations` (caption↔table/figure links, footnote references) and LaTeX for tables (`\begin{tabular}...`) and display formulas. |

> **Level 4 fidelity depends on the provider.** Vision-capable LLMs (Gemini, GLM, IAMHC) can produce full Level 4 output. Text-only fallback providers (OpenRouter, Groq) are tagged `"degraded_text_only_fallback"` — they return classes and reading order but cannot generate LaTeX or accurate relations.

The CLI only accepts `--level 3` or `--level 4`. Levels 1 and 2 are internal concepts (raw OCR output and crash-fallback path).

```
output/
├── images/          # Rendered page images (JPEG)
├── annotations/     # One JSON per page: boxes, classes, text, relations
├── qa/              # Visual QA overlays (--qa)
├── logs/            # Pipeline run logs
└── report/          # HTML quality report (--report)
```

### Annotation JSON schema

```json
{
  "image": "page_0001.jpg",
  "block_boxes": [[x1, y1, x2, y2], ...],
  "block_classes": ["Text", "Title", "Section-header", ...],
  "block_text": ["...", ...],
  "reading_order": [0, 3, 1, 2],
  "block_relations": [
    {"source": 0, "target": 1, "relation": "caption_of_figure"}
  ],
  "annotation_quality": "full_level4",
  "validation_results": { "valid": true }
}
```

**Classes:** `Text`, `Title`, `Section-header`, `List-item`, `TOC`, `Bibliography`, `Footnote`, `Page-header`, `Page-footer`, `Picture`, `Formula`, `Table`, `Caption`

---

## Project Structure

```
├── indic_ocr_pipeline3.py    # Main pipeline
├── run.py                    # Interactive CLI
├── core/
│   └── config.py             # API keys, model IDs, limits, constants
├── layout/
│   ├── reading_order.py      # Geometry-based reading order fallback
│   └── relations.py          # Automatic relation detection
├── utils/
│   └── usage.py              # Usage tracker + dashboard
├── validation/
│   └── schema.py             # RFQ schema validation
├── preprocessing/
│   └── image.py              # OpenCV image preprocessing
├── qa/
│   └── overlay.py            # Visual QA overlay rendering
└── report/
    └── html_report.py        # HTML report generation
```

---

## Troubleshooting

**JSON parse errors / truncated LLM responses** — usually means a batch's output exceeded the provider's `max_tokens`. Reduce `--batch-size` for that provider, or check `core/config.py` for the configured limit.

**A page's `annotation_quality` is `"degraded_text_only_fallback"`** — the pipeline fell through to a text-only provider (OpenRouter/Groq) for that page, so it won't have LaTeX tables/formulas or LLM-derived relations. Reprocess that page once a higher-tier provider (Gemini/GLM) has quota available.

**Low reading-order/relations scores in the HTML report on some pages but not others** — check the `annotation_quality` field on the affected pages first; a missing `reading_order` / `block_relations` field (rather than a low-quality one) usually means a provider fallback occurred mid-run, not a scoring bug.

---

## Contributing

Issues and PRs welcome. Please don't include real document content, output JSONs, or API keys in any PR — see `.gitignore`.
