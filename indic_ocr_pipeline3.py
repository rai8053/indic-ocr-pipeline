#!/usr/bin/env python3
"""
Indic OCR/Parse Dataset Pipeline (Upgraded) — refactored into indic_ocr_pipeline package.

This module re-exports all public functions for backward compatibility.
New code should import directly from the indic_ocr_pipeline package:
    from indic_ocr_pipeline.pipeline.runner import process_pdf, main
    from indic_ocr_pipeline.ocr.google_vision import run_vision_ocr
    from indic_ocr_pipeline.utils.helpers import image_to_base64
    from indic_ocr_pipeline.pipeline.orchestrator import _parse_batch_response
    from indic_ocr_pipeline.pipeline.orchestrator import build_vision_batch_prompt, build_batch_prompt
    from indic_ocr_pipeline.layout.detector import detect_embedded_pictures, detect_picture_regions_cv
    from indic_ocr_pipeline.providers.manager import run_proofread_batch
"""

from indic_ocr_pipeline.pipeline.runner import process_pdf, main
from indic_ocr_pipeline.ocr.rendering import pdf_to_images
from indic_ocr_pipeline.ocr.google_vision import run_vision_ocr
from indic_ocr_pipeline.utils.helpers import image_to_base64
from indic_ocr_pipeline.pipeline.orchestrator import _parse_batch_response, _extract_json_object
from indic_ocr_pipeline.pipeline.orchestrator import build_vision_batch_prompt, build_batch_prompt
from indic_ocr_pipeline.layout.detector import detect_embedded_pictures, detect_picture_regions_cv
from indic_ocr_pipeline.providers.manager import run_proofread_batch, _post_with_retry
from indic_ocr_pipeline.providers.manager import (
    _run_iamhc_proofread_batch as run_iamhc_proofread_batch,
)
from indic_ocr_pipeline.providers.gemini import run_gemini_proofread_batch
from indic_ocr_pipeline.providers.groq import run_groq_proofread_batch
from indic_ocr_pipeline.providers.glm import run_glm_proofread_batch
from indic_ocr_pipeline.providers.openrouter import run_openrouter_proofread_batch

if __name__ == "__main__":
    main()
