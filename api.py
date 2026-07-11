"""
FastAPI wrapper for the Indic OCR Pipeline.

Provides REST API endpoints for annotation, batch processing,
health checks, and provider/metrics queries.

Usage:
    uvicorn api:app --host 0.0.0.0 --port 8000
    # or: python -m uvicorn api:app --reload
"""
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, FileResponse

app = FastAPI(
    title="Indic OCR Pipeline API",
    description="Extract RFQ Level 4 layout annotations from scanned Indic-language PDFs",
    version="0.2.0",
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.2.0"}


@app.get("/providers")
async def providers():
    """List available LLM providers."""
    return {
        "providers": [
            {"name": "gemini", "description": "Gemini 2.5 Flash Lite", "vision": True},
            {"name": "glm", "description": "GLM-4V Flash", "vision": True},
            {"name": "iamhc", "description": "OpenAI-compatible relay", "vision": True},
            {"name": "openrouter", "description": "Llama 3.3 70B (free)", "vision": False},
            {"name": "groq", "description": "Llama 3.3 70B", "vision": False},
        ],
        "default": "gemini",
        "failover_chain": ["gemini", "glm", "iamhc", "openrouter", "groq"],
    }


@app.get("/metrics")
async def metrics():
    """Return usage metrics from quota state."""
    from core.config import QUOTA_STATE_FILE
    from utils.usage import UsageTracker

    tracker = UsageTracker(QUOTA_STATE_FILE)
    data = tracker.dashboard()
    return data


@app.post("/annotate")
async def annotate(
    file: UploadFile = File(...),
    lang: str = Form("odia"),
    level: int = Form(4),
    provider: str = Form("gemini"),
    batch_size: int = Form(5),
):
    """Annotate a single PDF file.

    Returns per-page JSON annotations as a zip archive.
    """
    if level not in (3, 4):
        raise HTTPException(400, "level must be 3 or 4")

    if provider not in ("gemini", "glm", "iamhc", "openrouter", "groq"):
        raise HTTPException(400, f"Unknown provider: {provider}")

    suffix = Path(file.filename).suffix if file.filename else ".pdf"
    if suffix.lower() != ".pdf":
        raise HTTPException(400, "Only PDF files are supported")

    tmp = tempfile.mkdtemp()
    pdf_path = Path(tmp) / f"input{suffix}"
    out_dir = Path(tmp) / "output"

    try:
        content = await file.read()
        pdf_path.write_bytes(content)

        from pipeline.runner import process_pdf

        process_pdf(
            pdf_path=pdf_path,
            lang=lang,
            out_dir=out_dir,
            dpi=150,
            jpeg_quality=60,
            provider=provider,
            batch_size=batch_size,
            level=level,
            validate=True,
            max_pages=0,
        )

        annotations = list(out_dir.glob("annotations/*.json"))
        if not annotations:
            raise HTTPException(500, "No annotations were generated")

        # Return as JSON list
        results = []
        for ann_path in sorted(annotations):
            data = json.loads(ann_path.read_text(encoding="utf-8"))
            data["_file"] = ann_path.name
            results.append(data)

        return JSONResponse(content={"pages": len(results), "annotations": results})

    except Exception as e:
        logger.exception("Annotation failed")
        raise HTTPException(500, str(e))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


@app.post("/batch")
async def batch_annotate(
    files: list[UploadFile] = File(...),
    lang: str = Form("odia"),
    level: int = Form(4),
    provider: str = Form("gemini"),
):
    """Annotate multiple PDF files."""
    results = []
    for f in files:
        try:
            result = await annotate(file=f, lang=lang, level=level, provider=provider)
            results.append({"file": f.filename, "status": "ok", "pages": result.get("pages", 0)})
        except Exception as e:
            results.append({"file": f.filename, "status": "error", "error": str(e)})

    return JSONResponse(content={"results": results})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
