# Installation

## Requirements

- Python 3.10+
- [Poppler](https://github.com/oschwartz10612/poppler-windows/releases/) (pdfinfo / pdftoppm)
- [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) (GitHub release, not Windows Store)

## Setup

```bash
git clone https://github.com/rai8053/indic-ocr-pipeline.git
cd indic-ocr-pipeline

python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

pip install -r requirements.txt

# Development dependencies
pip install -r requirements-dev.txt
pip install -e .

# API keys
cp .env.example .env
# Edit .env with your keys
```

## Verify

```bash
python -m pytest tests/
```
