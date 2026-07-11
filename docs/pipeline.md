# Pipeline

The pipeline processes PDFs through 5 stages.

## Stage 1: PDF to Images

Splits the PDF into individual page images using PyMuPDF at configurable DPI (default 150).

## Stage 2: Vision OCR

Each page is sent to Google Cloud Vision OCR for DOCUMENT_TEXT_DETECTION. Returns paragraph-level bounding boxes with transcribed text.

## Stage 3: LLM Proofreading

Blocks are batched and sent to the LLM provider chain for:
- Class assignment (Text, Title, Picture, Table, etc.)
- Reading order determination
- Block relations (caption linking)
- LaTeX generation (Level 4)

## Stage 4: Validation + Scoring

Validates the annotation JSON against the RFQ schema. Computes per-page quality scores.

## Stage 5: Export

Generates QA overlays and an HTML quality report.
