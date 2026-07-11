<div align="center">

# Indic OCR Pipeline

**RFQ Level 4 layout annotation for Indic-language scanned PDFs — free tier only.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://github.com/rai8053/indic-ocr-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/rai8053/indic-ocr-pipeline/actions)
[![code style: black](https://img.shields.io/badge/code%20style-black-000000)](https://github.com/psf/black)
[![lint: ruff](https://img.shields.io/badge/lint-ruff-informational)](https://github.com/astral-sh/ruff)
[![typing: mypy](https://img.shields.io/badge/typing-mypy-yellow)](http://mypy-lang.org)
[![tests: 21 passing](https://img.shields.io/badge/tests-21%20passing-brightgreen)](https://github.com/rai8053/indic-ocr-pipeline/actions)
[![PRs: welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](CONTRIBUTING.md)
[![stars](https://img.shields.io/github/stars/rai8053/indic-ocr-pipeline?style=social)](https://github.com/rai8053/indic-ocr-pipeline)

</div>

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Annotation Levels](#annotation-levels)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Usage](#usage)
- [Providers](#providers)
- [Output Format](#output-format)
- [Project Structure](#project-structure)
- [Performance Benchmarks](#performance-benchmarks)
- [Limitations](#limitations)
- [Roadmap](#roadmap)
- [FAQ](#faq)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Citation](#citation)
- [License](#license)

---

## Overview

### The Problem

Existing OCR tools extract raw text but lose document structure. Given a scanned PDF page, they return paragraphs of text but cannot tell you which paragraph is a **title**, a **footnote**, a **table caption**, or a **figure**. This makes the output unsuitable for training document-layout AI models.

### Why Indic OCR Is Difficult

Indic scripts (Odia, Telugu, Tamil, Marathi, Bengali, etc.) are under-served by commercial document-layout tools. Most layout datasets and pre-trained models focus on English or Chinese. The scripts are cursive, have complex conjuncts, and use non-Latin Unicode ranges that many OCR engines handle poorly.

### What This Project Does

This pipeline converts scanned Indic-language PDFs into **RFQ Level 4 annotations** — a structured dataset with:

- Per-block class labels from a 13-class taxonomy
- Natural reading order
- Caption-to-figure/table relations
- LaTeX markup for tables and display formulas

It combines **Google Cloud Vision OCR** with a **5-provider LLM failover chain** — all within free-tier API limits.

### What Makes It Unique

- **Entirely free-tier** — no API costs; quota-checked before every call
- **5-provider failover** — `gemini → glm → iamhc → openrouter → groq`; if one hits quota, the next takes over
- **Indic-first** — 12 major Indic languages supported, with more addable via config
- **RFQ Level 4 output** — full document-layout annotations ready for model training
- **Schema-validated** — every output JSON is checked for consistency and correctness
- **Docker + FastAPI** — run as a CLI tool, a container, or a REST API

---

## Features

### Core

| Feature | Description |
|---|---|
| **Google Cloud Vision OCR** | Paragraph-level bounding boxes with text transcription for all Indic scripts |
| **13-class RFQ classification** | Labels: Text, Title, Section-header, List-item, TOC, Bibliography, Footnote, Page-header, Page-footer, Picture, Formula, Table, Caption |
| **Reading order** | LLM-driven ordering with geometry-based fallback (`indic_ocr_pipeline/layout/reading_order.py`) |
| **Block relations** | Automatic caption↔figure, caption↔table, and footnote reference linking (`indic_ocr_pipeline/layout/relations.py`) |
| **LaTeX generation** | Tables and display formulas encoded as LaTeX at Level 4 |

### Provider Failover

| Feature | Description |
|---|---|
| **5-provider chain** | `gemini → glm → iamhc → openrouter → groq` (`indic_ocr_pipeline/providers/manager.py`) |
| **Vision + text-only** | Gemini/GLM/IAMHC are vision-capable; OpenRouter/Groq are text-only fallbacks |
| **Graceful degradation** | Degraded pages tagged `"degraded_text_only_fallback"` |
| **Quota pre-checks** | Per-provider limit checking before every API call |

### Quality Assurance

| Feature | Description |
|---|---|
| **Schema validation** | Array-length consistency, duplicate boxes, overlapping boxes, missing captions, relation integrity (`indic_ocr_pipeline/layout/validator.py`) |
| **Per-page scoring** | 0-100 scores for OCR quality, layout diversity, reading order, box validity, and relations |
| **QA overlay images** | Bounding boxes with class labels and reading-order arrows (`indic_ocr_pipeline/reporting/overlay.py`) |
| **HTML report** | Aggregate quality report with per-page breakdowns (`indic_ocr_pipeline/reporting/html.py`) |

### Preprocessing & Export

| Feature | Description |
|---|---|
| **OpenCV preprocessing** | Deskew, denoise, and contrast enhancement (`indic_ocr_pipeline/ocr/preprocessing.py`) |
| **Usage tracking** | Per-provider request/token logging with quota headroom dashboard (`indic_ocr_pipeline/utils/usage.py`) |
| **ZIP export** | Compress output to `{lang}_submission.zip` |
| **Docker** | Containerized CLI and API via Dockerfile + docker-compose |
| **FastAPI** | REST API with `/annotate`, `/batch`, `/health`, `/providers`, `/metrics` endpoints |

### Supported Languages

| Language | Code | Script | Language | Code | Script |
|---|---|---|---|---|---|
| Assamese | `assamese` | Bengali | Marathi | `marathi` | Devanagari |
| Bengali | `bengali` | Bengali | Odia | `odia` | Odia |
| Gujarati | `gujarati` | Gujarati | Punjabi | `punjabi` | Gurmukhi |
| Hindi | `hindi` | Devanagari | Tamil | `tamil` | Tamil |
| Kannada | `kannada` | Kannada | Telugu | `telugu` | Telugu |
| Malayalam | `malayalam` | Malayalam | Urdu | `urdu` | Perso-Arabic |

Languages are configured in `indic_ocr_pipeline/utils/config.py` (the `LANGUAGE_HINTS` dict). Adding a new language is a one-line change.

---

## Architecture

```mermaid
graph TD
    A["PDF Input"] --> B["PyMuPDF Render<br/>150 DPI → JPEG"]
    B --> C["Google Cloud Vision<br/>DOCUMENT_TEXT_DETECTION"]
    C --> D["Raw OCR Blocks<br/>boxes + text"]
    D --> E{"Picture Detection"}
    E --> F["Embedded PDF Images<br/>PyMuPDF extraction"]
    E --> G["OpenCV Contours<br/>threshold=240, min_area=3000"]
    F --> H["Augmented Blocks"]
    G --> H
    H --> I["LLM Proofread Chain"]
    I --> J{"Provider<br/>Available?"}
    J -->|"Yes"| K["Vision LLM<br/>Gemini / GLM / IAMHC"]
    J -->|"No"| L["Text-only LLM<br/>OpenRouter / Groq"]
    K --> M["Full Level 4<br/>classes + order + relations + LaTeX"]
    L --> N["Level 3 (degraded)<br/>classes + order only"]
    M --> O["JSON Annotation<br/>per page"]
    N --> O
    O --> P["Validation + Scoring"]
    P --> Q["QA Overlay Images<br/>boxes + labels + arrows"]
    P --> R["HTML Quality Report<br/>per-page breakdown"]
    P --> S["Usage Log<br/>+ Quota Dashboard"]
```

### Data Flow

```mermaid
sequenceDiagram
    participant PDF
    participant Render
    participant OCR
    participant Detect
    participant LLM
    participant Export

    PDF->>Render: Input PDF
    Render->>Render: Render pages at 150 DPI
    Render->>OCR: Page JPEGs
    OCR->>OCR: Google Cloud Vision OCR
    OCR->>Detect: Paragraph blocks [boxes + text]
    Detect->>Detect: Embedded images + CV contours
    Detect->>LLM: Augmented blocks
    LLM->>LLM: Try primary → failover chain
    LLM->>LLM: Classify, order, relate, LaTeX
    LLM->>Export: Per-page JSON
    Export->>Export: Validate, score, overlay, report
```

### Provider Failover

```mermaid
graph LR
    A["Primary Provider"] --> B{"Success?"}
    B -->|"Yes"| C["✓ Annotated JSON"]
    B -->|"No"| D["Next Provider in Chain"]
    D --> E{"Success?"}
    E -->|"Yes"| C
    E -->|"No"| F["... continues chain"]
    F --> G["Level 2 fallback<br/>if all providers fail"]
```

---

## Annotation Levels

| Level | Name | LLM Required | Content | Trigger |
|---|---|---|---|---|
| 1 | Raw OCR | No | `block_boxes`, `block_text` | Internal (always produced) |
| 2 | Fallback | No | Level 1 + all classes = `"Text"` | All providers failed |
| 3 | Classified | Yes | Level 2 + `block_classes`, `reading_order` | `--level 3` or degraded fallback |
| 4 | Full RFQ | Yes | Level 3 + `block_relations`, LaTeX in `block_text` | `--level 4` with vision provider |

CLI accepts `--level 3` or `--level 4` (default `4`). Levels 1–2 are internal fallback states.

Vision-capable providers (Gemini, GLM, IAMHC) produce full Level 4 output with `"annotation_quality": "full_level4"`. Text-only fallbacks (OpenRouter, Groq) produce Level 3 output tagged `"annotation_quality": "degraded_text_only_fallback"`.

---

## Installation

### Prerequisites

- **Python 3.10+**
- **API keys** — at least Google Cloud Vision + one LLM provider (see [Configuration](#configuration))

### From source

```bash
git clone https://github.com/rai8053/indic-ocr-pipeline.git
cd indic-ocr-pipeline

python -m venv .venv
source .venv/bin/activate       # Linux/macOS
# .venv\Scripts\activate        # Windows

pip install -r requirements.txt
```

### With uv (faster)

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### Development install

```bash
pip install -r requirements-dev.txt
pip install -e .
pre-commit install
```

### Docker

```bash
docker compose build

# Run CLI
docker compose run --rm pipeline \
    --pdf /app/input/document.pdf \
    --lang odia \
    --out /app/output

# Run API
docker compose --profile api up -d
curl http://localhost:8000/health
```

---

## Quick Start

```bash
# 1. Configure your API keys
cp .env.example .env
# Edit .env with your keys

# 2. Process a PDF
python indic_ocr_pipeline3.py \
    --pdf path/to/document.pdf \
    --lang odia \
    --out ./output \
    --level 4

# 3. Use the interactive CLI
python run.py
```

---

## Configuration

### Environment variables (`.env`)

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_VISION_KEY` | **Yes** | Google Cloud Vision API key |
| `GEMINI_API_KEY` | Recommended | Gemini 2.5 Flash Lite |
| `GLM_API_KEY` | Optional | GLM-4V Flash |
| `IAMHC_API_KEY` | Optional | IAMHC relay |
| `OPENROUTER_API_KEY` | Optional | OpenRouter (free tier) |
| `GROQ_API_KEY` | Optional | Groq (free tier) |

The `.env` file is auto-loaded from the project root. Fallback variable names are accepted (e.g., `GOOGLE_VISION_API_KEY` also works for Vision).

### Configuration file

All tunable constants are in `indic_ocr_pipeline/utils/config.py`:

| Constant | Default | Description |
|---|---|---|
| `GEMINI_MODEL` | `gemini-2.5-flash-lite` | Gemini model name |
| `GLM_MODEL` | `glm-4v-flash` | GLM model name |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model name |
| `OPENROUTER_MODEL` | `meta-llama/llama-3.3-70b-instruct:free` | OpenRouter model |
| `IAMHC_MODEL` | `auto` | IAMHC relay model |
| `IAMHC_ENDPOINT` | `https://api.iamhc.cn/v1/chat/completions` | IAMHC endpoint |
| `RETRY_ATTEMPTS` | `3` | API retry count |
| `RETRY_BACKOFF_SECONDS` | `5` | Seconds between retries |
| `VISION_MONTHLY_LIMIT` | `1000` | Google Vision free tier monthly limit |
| `LLM_DAILY_LIMIT` | `1500` | Per-provider daily safety limit |
| `QUOTA_STATE_FILE` | `.pipeline_quota_state.json` | Quota persistence file |

---

## Usage

### CLI

```bash
# Process with default settings
python indic_ocr_pipeline3.py \
    --pdf document.pdf \
    --lang odia \
    --out ./output

# Specify provider and level
python indic_ocr_pipeline3.py \
    --pdf document.pdf \
    --lang tamil \
    --out ./output \
    --provider gemini \
    --level 4 \
    --batch-size 5

# Full featured run
python indic_ocr_pipeline3.py \
    --pdf document.pdf \
    --lang odia \
    --out ./output \
    --level 4 \
    --provider gemini \
    --batch-size 3 \
    --preprocess \
    --qa \
    --report \
    --validate \
    --zip \
    --max-pages 10
```

### Arguments

| Argument | Type | Default | Description |
|---|---|---|---|
| `--pdf` | `str` | **(required)** | Path to source PDF |
| `--lang` | `str` | `""` | Language code (`odia`, `tamil`, etc.) |
| `--out` | `str` | **(required)** | Output directory |
| `--dpi` | `int` | `150` | Page rendering DPI |
| `--jpeg-quality` | `int` | `60` | JPEG quality 1–100 |
| `--provider` | `str` | `"gemini"` | Primary provider: `gemini`, `glm`, `iamhc`, `openrouter`, `groq` |
| `--level` | `int` | `4` | Annotation level: `3` or `4` |
| `--batch-size` | `int` | `1` | Pages per LLM request |
| `--max-pages` | `int` | `0` | Process only first N pages (`0` = all) |
| `--samples` | `int` | `0` | Max samples in ZIP (`0` = all) |
| `--preprocess` | flag | — | Enable OpenCV deskew/denoise/contrast |
| `--qa` | flag | — | Generate QA overlay images |
| `--report` | flag | — | Generate HTML quality report |
| `--validate` | flag | — | Validate output JSON schemas |
| `--zip` | flag | — | Create submission ZIP archive |

> **Note on batch size:** Larger batches reduce total API calls but increase per-request tokens. If you see truncated JSON responses, reduce `--batch-size`.

### Interactive CLI

```bash
python run.py
```

Launches a Rich-powered interactive menu for step-by-step configuration.

### REST API (FastAPI)

```bash
pip install uvicorn
uvicorn api:app --host 0.0.0.0 --port 8000

# Health check
curl http://localhost:8000/health

# List providers
curl http://localhost:8000/providers

# Annotate a single PDF
curl -X POST http://localhost:8000/annotate \
    -F "file=@document.pdf" \
    -F "lang=odia" \
    -F "level=4"

# Batch annotate multiple PDFs
curl -X POST http://localhost:8000/batch \
    -F "files=@doc1.pdf" \
    -F "files=@doc2.pdf" \
    -F "lang=tamil"

# View usage metrics
curl http://localhost:8000/metrics
```

### Docker

```bash
# Process a PDF via Docker CLI
docker compose run --rm pipeline \
    --pdf /app/input/document.pdf \
    --lang odia \
    --out /app/output \
    --level 4 \
    --validate \
    --report

# Start the API
docker compose --profile api up -d
```

---

## Providers

### OCR

| Provider | Type | Endpoint | Free Tier |
|---|---|---|---|
| **Google Cloud Vision** | `DOCUMENT_TEXT_DETECTION` | `vision.googleapis.com` | 1,000 units/month |

The pipeline uses Google Cloud Vision for paragraph-level OCR. Each page returns bounding boxes and transcribed text. No other OCR backend is currently supported.

### LLM Proofreading

The pipeline chains five LLM providers. If the primary fails (quota exceeded, timeout, rate limit), the next is tried automatically.

| Provider | Vision? | Model | Free Tier Limits |
|---|---|---|---|
| **Gemini** | ✅ Yes | `gemini-2.5-flash-lite` | ~1,500 req/day |
| **GLM-4V** | ✅ Yes | `glm-4v-flash` | Rate-limited |
| **IAMHC** | ✅ Yes | `auto` (relay) | Varies |
| **OpenRouter** | ❌ No | `meta-llama/llama-3.3-70b-instruct:free` | Rate-limited |
| **Groq** | ❌ No | `llama-3.3-70b-versatile` | 30 RPM / 6k TPM / 1k RPD |

**Failover chains by primary provider:**

| Primary | Chain |
|---|---|
| `gemini` | `gemini → glm → iamhc → openrouter → groq` |
| `glm` | `glm → iamhc → openrouter → groq` |
| `iamhc` | `iamhc → openrouter → groq` |
| `openrouter` | `openrouter → groq` |
| `groq` | `groq` (no fallback) |

Pages processed by text-only providers (OpenRouter, Groq) are tagged `"annotation_quality": "degraded_text_only_fallback"` — they have class labels and reading order but no LaTeX or relations.

---

## Output Format

### Directory structure

```
output/
├── images/             # Page JPEG images
├── annotations/        # One JSON per page
│   ├── page_0001.json
│   ├── page_0002.json
│   └── ...
├── qa/                 # QA overlay images (--qa)
├── logs/               # Pipeline logs + metrics.jsonl
└── report/             # HTML quality report (--report)
```

### Annotation JSON schema

Each annotation JSON file contains these fields:

```json
{
  "image": "page_0001.jpg",
  "block_boxes": [
    [72, 98, 540, 142],
    [72, 155, 540, 482],
    [72, 495, 260, 540]
  ],
  "block_classes": [
    "Page-header",
    "Text",
    "Picture"
  ],
  "block_text": [
    "Chapter 3: ଓଡ଼ିଆ ସାହିତ୍ୟ",
    "ଓଡ଼ିଆ ସାହିତ୍ୟର ଇତିହାସ ବହୁ ପୁରାତନ...",
    ""
  ],
  "reading_order": [0, 2, 1],
  "block_relations": [
    {"source": 0, "target": 1, "relation": "caption_of_figure"}
  ],
  "annotation_quality": "full_level4"
}
```

### Field reference

| Field | Level | Type | Description |
|---|---|---|---|
| `image` | 1+ | `string` | Page image filename (e.g., `page_0001.jpg`) |
| `block_boxes` | 1+ | `[[x1,y1,x2,y2], ...]` | Bounding boxes in pixel coordinates — one per block, same order as OCR output |
| `block_classes` | 3+ | `[string, ...]` | RFQ class label per block (see taxonomy below) |
| `block_text` | 1+ | `[string, ...]` | Transcribed text per block; empty string for pictures; LaTeX for tables/formulas at level 4 |
| `reading_order` | 3+ | `[int, ...]` | Permutation reordering the arrays into natural reading sequence |
| `block_relations` | 4 | `[{source, target, relation}]` | Directed relation edges between blocks |
| `annotation_quality` | 4 | `string` | `"full_level4"` or `"degraded_text_only_fallback"` |
| `_ro_source` | 3 | `string` | Source of reading order: `"llm"`, `"geometry"`, or `"default"` |

All arrays have the same length — enforced by validation.

### Class taxonomy (13 classes)

```
Text, Title, Section-header, List-item, TOC, Bibliography,
Footnote, Page-header, Page-footer, Picture, Formula, Table, Caption
```

### Relation types

| Relation | Meaning |
|---|---|
| `caption_of_table` | Block A is the caption for a Table block |
| `table_has_caption` | Block A (Table) has a caption |
| `caption_of_figure` | Block A is the caption for a Picture block |
| `figure_has_caption` | Block A (Picture) has a caption |
| `footnote_refers_to` | Block A is a footnote referencing block B |

---

## Project Structure

```
indic-ocr-pipeline/
│
├── indic_ocr_pipeline3.py       # CLI entry point
├── run.py                        # Interactive CLI (Rich)
├── api.py                        # FastAPI REST wrapper
│
├── indic_ocr_pipeline/           # Main package
│   ├── pipeline/
│   │   ├── runner.py             # process_pdf() orchestrator
│   │   ├── orchestrator.py       # LLM prompt builders, JSON extraction
│   │   ├── exporter.py           # JSON & ZIP export
│   │   └── metrics.py            # Aggregate scoring
│   │
│   ├── providers/
│   │   ├── manager.py            # Failover chain, retry, IAMHC relay
│   │   ├── gemini.py             # Gemini 2.5 Flash Lite
│   │   ├── glm.py                # GLM-4V Flash
│   │   ├── groq.py               # Groq (Llama 3.3 70B)
│   │   └── openrouter.py         # OpenRouter (Llama 3.3 70B)
│   │
│   ├── layout/
│   │   ├── detector.py           # Picture region detection
│   │   ├── reading_order.py      # Geometry-based order fallback
│   │   ├── relations.py          # Auto relation detection
│   │   └── validator.py          # Schema validation + scoring
│   │
│   ├── ocr/
│   │   ├── google_vision.py      # Google Cloud Vision client
│   │   ├── preprocessing.py      # OpenCV deskew/denoise/contrast
│   │   └── rendering.py          # PyMuPDF page rendering
│   │
│   ├── reporting/
│   │   ├── html.py               # HTML quality report
│   │   ├── overlay.py            # QA overlay images
│   │   └── benchmark.py          # Timer utilities
│   │
│   ├── models/                   # Data classes
│   │   ├── annotation.py
│   │   ├── provider.py
│   │   ├── quality.py
│   │   └── relation.py
│   │
│   └── utils/
│       ├── config.py             # API keys, constants, limits
│       ├── usage.py              # Usage tracker + quota dashboard
│       ├── logging.py            # Pipeline logger
│       └── helpers.py            # Terminal I/O utilities
│
├── tests/                        # 21 tests (pytest)
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_reading_order.py
│   ├── test_relations.py
│   ├── test_scoring.py
│   └── test_validation.py
│
├── docs/                         # Documentation (mkdocs)
├── samples/                      # Sample PDF generator
├── .github/workflows/ci.yml      # CI pipeline
│
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── CHANGELOG.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── LICENSE
└── CITATION.cff
```

---

## Performance Benchmarks

> ⚠️ **No pre-computed benchmarks exist.** Performance data is collected per-run from live provider calls and logged to `metrics.jsonl`. The section below describes what is measured, not fixed results.

### Metrics collected per run

- **OCR latency** — time per page for Google Cloud Vision
- **LLM latency** — time per batch per provider (with retries)
- **Token counts** — input and output tokens per provider call
- **Success rates** — per-provider pass/fail counts
- **Stage timing** — render → OCR → detect → proofread → export

### How to view your results

```bash
# After a run, check the CLI summary output
python indic_ocr_pipeline3.py --pdf doc.pdf --lang odia --out ./output

# View the HTML report (--report flag)
open output/report/index.html

# Inspect raw timing data
cat output/logs/metrics.jsonl

# Query metrics via API
curl http://localhost:8000/metrics
```

Results vary by:
- **Provider** — vision providers are 2–3× slower than text-only
- **Batch size** — larger batches reduce per-page overhead but risk truncation
- **Document complexity** — dense layouts with many blocks increase token usage
- **Network latency** — varies by provider endpoint and geographic region

Benchmarking with standardized test PDFs across all providers is planned. See [Roadmap](#roadmap).

---

## Limitations

- **Single OCR backend** — only Google Cloud Vision is supported; Tesseract, Azure OCR, and others are not integrated
- **Text-only fallback quality** — OpenRouter and Groq produce no LaTeX or relations (tagged as degraded)
- **Picture detection thresholds** — OpenCV defaults (`threshold=240`, `min_area=3000`) may need tuning for different scan qualities; adjust in `indic_ocr_pipeline/layout/detector.py`
- **Token limits** — pages with many blocks or complex layouts may produce truncated LLM responses; reduce `--batch-size`
- **Sequential processing** — pages are processed sequentially per batch; no parallelism
- **Windows Unicode** — terminal logging on cp437-encoded Windows terminals may crash with Indic text (handled via ASCII-safe fallback)
- **Mkdocs navigation** — the site config (`mkdocs.yml`) references 4 pages that do not yet exist in `docs/`: `providers.md`, `annotation-levels.md`, `validation.md`, `developer-guide.md`
- **No shell scripts** — no `.sh` or `.bat` launcher scripts provided

---

## Roadmap

### Completed

- [x] Multi-provider LLM failover chain (5 providers)
- [x] Picture region detection (embedded PDF images + OpenCV contours)
- [x] Schema validation and quality scoring
- [x] QA overlay images with bounding boxes, class labels, reading order arrows
- [x] HTML quality report with per-page breakdown
- [x] Module refactoring into `pipeline/`, `providers/`, `reporting/` structure
- [x] FastAPI REST wrapper (`/annotate`, `/batch`, `/health`, `/providers`, `/metrics`)
- [x] Docker support (Dockerfile + docker-compose with pipeline and api services)
- [x] 21 tests covering config, reading order, relations, scoring, validation

### Future

- [ ] Export to COCO / DocLayNet / HuggingFace Dataset formats
- [ ] Parallel page processing (multi-threaded or async)
- [ ] Web UI for upload, review, and annotation editing
- [ ] Documentation site (mkdocs) — complete missing pages
- [ ] Pre-computed benchmarks across all providers with standardized test PDFs
- [ ] Support for additional OCR backends (Tesseract, Azure AI Document Intelligence)
- [ ] Pre-built models for common Indic scripts
- [ ] Shell launcher scripts (`.sh` / `.bat`) for common workflows
- [ ] `uv`-based project configuration for faster installs

---

## FAQ

### How much does it cost to run?

**Nothing.** All providers have free tiers. The pipeline pre-checks quota before each call and stops gracefully when limits are reached.

### Which provider should I use?

Start with **Gemini** — it has the most generous free tier (~1,500 req/day) and reliable vision support. The pipeline auto-fallbacks if a provider is unavailable.

### Do I need all six API keys?

No. You need **Google Cloud Vision** (OCR) and at least **one LLM provider**. Gemini is recommended. The pipeline will skip providers with missing or empty keys.

### Can I run this on macOS/Linux?

Yes. The pipeline is pure Python with PyMuPDF for PDF rendering (no Poppler or Tesseract dependency). All system dependencies are Python packages.

### What happens if all providers fail?

The page is saved at **Level 2** (raw OCR output) with all classes set to `"Text"`. A warning is logged and the pipeline continues to the next page.

### How do I add a new language?

Add the language code to `LANGUAGE_HINTS` in `indic_ocr_pipeline/utils/config.py`. Google Cloud Vision supports all major Indic scripts.

### Can I use my own LLM API?

Yes. Any OpenAI-compatible endpoint can be added as a provider. Follow the pattern in `indic_ocr_pipeline/providers/` and register it in `manager.py`. See [CONTRIBUTING.md](CONTRIBUTING.md).

### How is this different from regular OCR?

Standard OCR returns raw text. This pipeline returns **structured annotations**: each text block has a class label (Title, Footnote, Table, etc.), a position in the reading order, relations to other blocks (caption-of, refers-to), and LaTeX for tables/formulas.

### What is RFQ Level 4?

A document-layout annotation standard that includes block-level class labels, natural reading order, caption relations, and LaTeX markup. This is the format used to train document-layout AI models.

---

## Troubleshooting

| Symptom | Cause | Solution |
|---|---|---|
| **JSON parse errors / truncated responses** | LLM hit token limit | Reduce `--batch-size`; check `max_tokens` in `indic_ocr_pipeline/utils/config.py` |
| **`"annotation_quality": "degraded_text_only_fallback"`** | All vision providers failed; text-only fallback used | Wait for vision provider quota to reset, or set a different primary provider via `--provider` |
| **Low reading-order or relations scores** | Provider fallback or missing fields | Check `annotation_quality` first — degraded mode has no relations |
| **Gemini returns 429** | Daily quota exceeded | Reset is midnight America/Los_Angeles; use `--provider glm` or `--provider iamhc` in the meantime |
| **GLM times out** | Image payloads cause latency | Switch to `--provider gemini` or `--provider iamhc` |
| **OpenRouter 429** | Free model rate-limited | Wait or use a different provider |
| **Windows terminal shows garbage / crashes** | cp437 can't render Indic Unicode | Update to latest version (includes ASCII-safe logging fallback) |
| **`ModuleNotFoundError: No module named 'indic_ocr_pipeline'`** | Package not installed | Run `pip install -e .` from the project root |
| **`key GOOGLE_VISION_API_KEY` not found** | `.env` missing or incomplete | Copy `.env.example` to `.env` and fill in your keys |
| **OCR returns empty blocks** | Google Vision API key error or page is blank | Check your Vision API key and that the PDF renders correctly |

---

## Contributing

We welcome contributions. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for the full guidelines.

### Quick start for developers

```bash
# Install dev dependencies
pip install -r requirements-dev.txt
pip install -e .
pre-commit install

# Run checks before submitting a PR
pytest                    # 21 tests
black .                   # Format code
ruff check .              # Lint
mypy .                    # Type check
```

### How to add a new provider

1. Create a provider module in `indic_ocr_pipeline/providers/` following the existing pattern
2. Add the API key constant in `indic_ocr_pipeline/utils/config.py`
3. Register the provider function in `indic_ocr_pipeline/providers/manager.py` (add to `_providers` dict and `run_proofread_batch` chain)
4. Add to `PROVIDER_INFO` in `indic_ocr_pipeline/utils/usage.py`
5. Add to CLI choices in `indic_ocr_pipeline/pipeline/runner.py`
6. Add to `.env.example`
7. Add to `/providers` endpoint in `api.py`
8. Test with a sample page

---

## Citation

```bibtex
@software{hazra_indic_ocr_2026,
  author = {Hazra, Raihan},
  title = {Indic OCR Dataset Pipeline},
  year = {2026},
  url = {https://github.com/rai8053/indic-ocr-pipeline}
}
```

---

## License

This project is licensed under the [MIT License](LICENSE).

---

<div align="center">
  <sub>Built with PyMuPDF, OpenCV, Google Cloud Vision, and free-tier LLM APIs.</sub>
</div>
