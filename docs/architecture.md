# Architecture

```
                    ┌─────────────┐
                    │   PDF Input │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  PyMuPDF    │
                    │  Splitter   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Vision OCR │
                    │  (Google)   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Picture    │
                    │  Detection  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  LLM Chain  │
                    │  gemini →   │
                    │  glm →      │
                    │  iamhc →    │
                    │  openrouter │
                    │  → groq     │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Validation │
                    │  + Scoring  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Output    │
                    │  JSON/QA/   │
                    │  Report     │
                    └─────────────┘
```

## Components

- **PDF Splitter**: Renders PDF pages to JPEG at 150 DPI
- **Vision OCR**: Google Cloud Vision DOCUMENT_TEXT_DETECTION
- **Picture Detection**: Embedded images (PyMuPDF) + OpenCV contours
- **LLM Chain**: Multi-provider failover for annotation
- **Validation**: Schema checks, overlap detection, scoring
- **Export**: JSON annotations, QA overlays, HTML reports
