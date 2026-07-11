"""OpenRouter LLM provider wrapper (text-only fallback)."""

from __future__ import annotations

from typing import Any, Optional

from indic_ocr_pipeline.utils.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_ENDPOINT,
)
from indic_ocr_pipeline.providers.manager import _post_with_retry, _parse_provider_result


def run_openrouter_proofread_batch(
    image_paths: list[Any],
    pages_blocks: list[list[dict]],
    level: int = 3,
    usage_recorder: Optional[Any] = None,
) -> list[dict]:
    """Run a proofreading batch via OpenRouter (text-only).

    Args:
        image_paths: Page image paths (used for count only — images not sent).
        pages_blocks: Raw OCR blocks per page.
        level: Annotation level (3 or 4).
        usage_recorder: Optional UsageTracker for recording.

    Returns:
        Parsed page annotations with ``annotation_quality`` set to
        ``"degraded_text_only_fallback"`` for level >= 4.

    Raises:
        RuntimeError: If the API key is missing or all retries fail.
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    from indic_ocr_pipeline.pipeline.orchestrator import build_batch_prompt

    prompt = build_batch_prompt(pages_blocks, level=level)
    payload: dict = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 16384,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    n_pages = len(image_paths)
    in_tok = max(1, len(prompt) // 4)

    try:
        resp, retries, lat = _post_with_retry(OPENROUTER_ENDPOINT, payload, headers, timeout=180)
        raw_text = resp.json()["choices"][0]["message"]["content"]
        out_tok = max(1, len(raw_text) // 4)

        if usage_recorder:
            usage_recorder.record_request(
                "openrouter",
                success=True,
                latency_ms=lat,
                retry_count=retries,
                pages=n_pages,
                images=n_pages,
                input_tokens=in_tok,
                output_tokens=out_tok,
            )

        return _parse_provider_result(
            raw_text, n_pages, pages_blocks, level, "degraded_text_only_fallback"
        )

    except Exception as e:
        if usage_recorder:
            usage_recorder.record_request(
                "openrouter",
                success=False,
                latency_ms=0,
                retry_count=0,
                error=str(e),
                pages=n_pages,
                images=n_pages,
            )
        raise
