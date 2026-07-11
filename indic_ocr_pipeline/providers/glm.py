"""GLM-4V Flash provider wrapper (vision-capable, full Level 4)."""

from __future__ import annotations

from typing import Any

from indic_ocr_pipeline.providers.manager import _parse_provider_result, _post_with_retry
from indic_ocr_pipeline.utils.config import GLM_API_KEY, GLM_ENDPOINT, GLM_MODEL
from indic_ocr_pipeline.utils.helpers import image_to_base64


def run_glm_proofread_batch(
    image_paths: list[Any],
    pages_blocks: list[list[dict]],
    level: int = 3,
    usage_recorder: Any | None = None,
) -> list[dict]:
    """Run a proofreading batch via GLM-4V Flash (vision-capable).

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
    if not GLM_API_KEY:
        raise RuntimeError("GLM_API_KEY not set")

    from indic_ocr_pipeline.pipeline.orchestrator import build_vision_batch_prompt

    prompt = build_vision_batch_prompt(pages_blocks, level=level)
    content: list[dict] = [{"type": "text", "text": prompt}]
    for img_path in image_paths:
        b64 = image_to_base64(img_path)
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
        )

    payload: dict = {
        "model": GLM_MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 16384,
    }
    headers = {
        "Authorization": f"Bearer {GLM_API_KEY}",
        "Content-Type": "application/json",
    }
    n_pages = len(image_paths)
    in_tok = max(1, len(prompt) // 4)

    try:
        resp, retries, lat = _post_with_retry(GLM_ENDPOINT, payload, headers, timeout=180)
        raw_text = resp.json()["choices"][0]["message"].get("content", "")
        out_tok = max(1, len(raw_text) // 4)

        if usage_recorder:
            usage_recorder.record_request(
                "glm",
                success=True,
                latency_ms=lat,
                retry_count=retries,
                pages=n_pages,
                images=n_pages,
                input_tokens=in_tok,
                output_tokens=out_tok,
            )

        return _parse_provider_result(raw_text, n_pages, pages_blocks, level, "full_level4")

    except Exception as e:
        if usage_recorder:
            usage_recorder.record_request(
                "glm",
                success=False,
                latency_ms=0,
                retry_count=0,
                error=str(e),
                pages=n_pages,
                images=n_pages,
            )
        raise
