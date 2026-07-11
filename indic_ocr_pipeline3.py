#!/usr/bin/env python3
"""
Indic OCR/Parse Dataset Pipeline (Upgraded) — refactored into pipeline/ package.

This module re-exports all public functions for backward compatibility.
New code should import directly from the pipeline package:
    from pipeline.runner import process_pdf, main
    from pipeline.ocr import run_vision_ocr, image_to_base64
    from pipeline.annotator import _parse_batch_response
    from pipeline.prompts import build_vision_batch_prompt, build_batch_prompt
    from pipeline.pictures import detect_embedded_pictures, detect_picture_regions_cv
    from pipeline.providers import run_proofread_batch, run_openrouter_proofread_batch
"""

from pipeline.runner import process_pdf, main, pdf_to_images
from pipeline.ocr import run_vision_ocr, image_to_base64
from pipeline.annotator import _parse_batch_response, _extract_json_object
from pipeline.prompts import build_vision_batch_prompt, build_batch_prompt
from pipeline.pictures import detect_embedded_pictures, detect_picture_regions_cv
from pipeline.providers import (run_proofread_batch, run_openrouter_proofread_batch,
                                run_gemini_proofread_batch, run_groq_proofread_batch,
                                run_glm_proofread_batch, run_iamhc_proofread_batch,
                                _post_with_retry)

if __name__ == "__main__":
    main()
