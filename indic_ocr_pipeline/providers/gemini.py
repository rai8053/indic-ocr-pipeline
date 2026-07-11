"""Gemini LLM provider wrapper (vision-capable, full Level 4)."""

from __future__ import annotations

from typing import Any, Optional

from indic_ocr_pipeline.utils.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_ENDPOINT_TMPL
from indic_ocr_pipeline.utils.helpers import image_to_base64
from indic_ocr_pipeline.providers.manager import _post_with_retry, _parse_provider_result


def run_gemini_proofread_batch(
    image_paths: list[Any],
    pages_blocks: list[list[dict]],
    level: int = 3,
    usage_recorder: Optional[object] = None,
) -> list[dict]:
    """Run a proofreading batch via Gemini (vision + text).

    Sends page images inline for visual context.

    Args:
        image_paths: Page image paths.
        pages_blocks: Raw OCR blocks per page.
        level: Annotation level (3 or 4).
        usage_recorder: Optional UsageTracker for recording.

    Returns:
        Parsed page annotations with ``annotation_quality = "full_level4"`` for level >= 4.

    Raises:
        RuntimeError: If the API key is missing or all retries fail.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")

    from indic_ocr_pipeline.pipeline.orchestrator import build_vision_batch_prompt
    prompt = build_vision_batch_prompt(pages_blocks, level=level)
    parts: list[dict] = [{"text": prompt}]
    for img_path in image_paths:
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": image_to_base64(img_path),
            },
        })

    url = GEMINI_ENDPOINT_TMPL.format(model=GEMINI_MODEL)
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }
    payload: dict = {
        "contents": [{"parts": parts}],
        "generationConfig": {"response_mime_type": "application/json"},
    }
    n_pages = len(image_paths)
    in_tok = max(1, len(prompt) // 4)

    try:
        resp, retries, lat = _post_with_retry(url, payload, headers, timeout=180)
        raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        out_tok = max(1, len(raw_text) // 4)

        if usage_recorder:
            usage_recorder.record_request(
                "gemini", success=True, latency_ms=lat,
                retry_count=retries, pages=n_pages, images=n_pages,
                input_tokens=in_tok, output_tokens=out_tok,
            )

        return _parse_provider_result(raw_text, n_pages, pages_blocks, level, "full_level4")

    except Exception as e:
        if usage_recorder:
            usage_recorder.record_request(
                "gemini", success=False, latency_ms=0,
                retry_count=0, error=str(e), pages=n_pages, images=n_pages,
            )
        raise
