"""Provider manager — shared retry logic, result parsing, and failover orchestration."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import requests

from indic_ocr_pipeline.utils.config import (
    IAMHC_API_KEY,
    IAMHC_ENDPOINT,
    IAMHC_MODEL,
    RETRY_ATTEMPTS,
    RETRY_BACKOFF_SECONDS,
)
from indic_ocr_pipeline.utils.helpers import image_to_base64
from indic_ocr_pipeline.utils.helpers import warn as _term_warn

# ---------------------------------------------------------------------------
# Shared HTTP retry
# ---------------------------------------------------------------------------


def _post_with_retry(
    url: str,
    json_body: dict,
    headers: dict[str, str],
    timeout: int,
) -> tuple[requests.Response, int, float]:
    """POST JSON to a URL with exponential backoff retry.

    Args:
        url: Endpoint URL.
        json_body: JSON-serializable request payload.
        headers: HTTP headers.
        timeout: Request timeout in seconds.

    Returns:
        Tuple of ``(response, retry_count, latency_ms)``.

    Raises:
        RuntimeError: If all retry attempts fail.
    """
    resp: requests.Response | None = None
    retries = 0
    t0 = time.time()
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = requests.post(url, json=json_body, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                latency = (time.time() - t0) * 1000
                return resp, retries, latency
            retries += 1
            wait = int(
                resp.headers.get(
                    "Retry-After",
                    RETRY_BACKOFF_SECONDS * (attempt + 1) * 4,
                )
            )
            if wait > 60:
                wait = 60
            time.sleep(wait)
        except Exception as e:
            retries += 1
            if attempt == RETRY_ATTEMPTS - 1:
                raise RuntimeError(f"Request failed after {retries} attempts: {e}") from e
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    latency = (time.time() - t0) * 1000
    raise RuntimeError(f"Request failed after {RETRY_ATTEMPTS} attempts")


# ---------------------------------------------------------------------------
# Shared result parsing
# ---------------------------------------------------------------------------


def _parse_provider_result(
    raw_text: str,
    n_pages: int,
    pages_blocks: list[list[dict]],
    level: int,
    quality_tag: str,
) -> list[dict]:
    """Parse raw LLM response and tag annotation quality.

    Args:
        raw_text: Raw response text from the LLM.
        n_pages: Expected number of pages.
        pages_blocks: Original OCR blocks per page.
        level: Annotation level.
        quality_tag: Value for ``annotation_quality`` field.

    Returns:
        Parsed page annotation dicts.
    """
    from indic_ocr_pipeline.pipeline.orchestrator import _parse_batch_response

    pages_out = _parse_batch_response(raw_text, n_pages, pages_blocks, level)
    if level >= 4:
        for page in pages_out:
            page["annotation_quality"] = quality_tag
    return pages_out


# ---------------------------------------------------------------------------
# IAMHC provider (relay with vision + text fallback)
# ---------------------------------------------------------------------------


def _run_iamhc_proofread_batch(
    image_paths: list[Any],
    pages_blocks: list[list[dict]],
    level: int = 3,
    usage_recorder: Any | None = None,
) -> list[dict]:
    """Run proofreading via IAMHC relay (vision-first, text-only fallback).

    Tries vision-capable request first; if that fails, falls back to a
    text-only prompt (same endpoint, different payload).

    Args:
        image_paths: Page image paths.
        pages_blocks: Raw OCR blocks per page.
        level: Annotation level.
        usage_recorder: Optional UsageTracker.

    Returns:
        Parsed page annotations.

    Raises:
        RuntimeError: If both vision and text attempts fail.
    """
    if not IAMHC_API_KEY:
        raise RuntimeError("IAMHC_API_KEY not set")

    from indic_ocr_pipeline.pipeline.orchestrator import (
        build_batch_prompt,
        build_vision_batch_prompt,
    )

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
        "model": IAMHC_MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 16384,
    }
    headers = {
        "Authorization": f"Bearer {IAMHC_API_KEY}",
        "Content-Type": "application/json",
    }
    n_pages = len(image_paths)
    in_tok = max(1, len(prompt) // 4)

    try:
        resp, retries, lat = _post_with_retry(IAMHC_ENDPOINT, payload, headers, timeout=180)
        raw_text = resp.json()["choices"][0]["message"]["content"]
        out_tok = max(1, len(raw_text) // 4)
        if usage_recorder:
            usage_recorder.record_request(
                "iamhc",
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
        # Fallback to text-only
        try:
            text_prompt = build_batch_prompt(pages_blocks, level=level)
            text_payload: dict = {
                "model": IAMHC_MODEL,
                "messages": [{"role": "user", "content": text_prompt}],
                "max_tokens": 16384,
            }
            resp, retries, lat = _post_with_retry(
                IAMHC_ENDPOINT, text_payload, headers, timeout=180
            )
            raw_text = resp.json()["choices"][0]["message"]["content"]
            out_tok = max(1, len(raw_text) // 4)
            if usage_recorder:
                usage_recorder.record_request(
                    "iamhc",
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
        except Exception as e2:
            if usage_recorder:
                usage_recorder.record_request(
                    "iamhc",
                    success=False,
                    latency_ms=0,
                    retry_count=0,
                    error=str(e2),
                    pages=n_pages,
                    images=n_pages,
                )
            raise RuntimeError(f"iamhc vision+text both failed: {e} / {e2}") from e


# ---------------------------------------------------------------------------
# Failover orchestration
# ---------------------------------------------------------------------------


def run_proofread_batch(
    provider: str,
    image_paths: list[Any],
    pages_blocks: list[list[dict]],
    level: int = 3,
    usage_recorder: Any | None = None,
) -> list[dict]:
    """Run a proofreading batch with automatic failover between providers.

    The failover chain (for each primary provider) is:
    - ``gemini`` → ``glm`` → ``iamhc`` → ``openrouter`` → ``groq``
    - ``glm`` → ``iamhc`` → ``openrouter`` → ``groq``
    - ``iamhc`` → ``openrouter`` → ``groq``
    - ``openrouter`` → ``groq``
    - ``groq`` — no fallback

    Args:
        provider: Primary provider name.
        image_paths: Page image paths.
        pages_blocks: Raw OCR blocks per page.
        level: Annotation level.
        usage_recorder: Optional UsageTracker instance.

    Returns:
        Parsed page annotations from the first successful provider.

    Raises:
        RuntimeError: If all providers in the chain fail.
    """
    from indic_ocr_pipeline.providers.gemini import run_gemini_proofread_batch
    from indic_ocr_pipeline.providers.glm import run_glm_proofread_batch
    from indic_ocr_pipeline.providers.groq import run_groq_proofread_batch
    from indic_ocr_pipeline.providers.openrouter import run_openrouter_proofread_batch

    _providers: dict[str, Callable] = {
        "openrouter": run_openrouter_proofread_batch,
        "gemini": run_gemini_proofread_batch,
        "groq": run_groq_proofread_batch,
        "glm": run_glm_proofread_batch,
        "iamhc": _run_iamhc_proofread_batch,
    }

    chain: list[str] = [provider]
    if provider == "gemini":
        chain.extend(["glm", "iamhc", "openrouter", "groq"])
    elif provider == "glm":
        chain.extend(["iamhc", "openrouter", "groq"])
    elif provider == "iamhc":
        chain.extend(["openrouter", "groq"])
    elif provider == "openrouter":
        chain.extend(["groq"])
    elif provider == "groq":
        pass

    first_error: Exception | None = None
    for p in chain:
        if p not in _providers:
            continue
        try:
            return _providers[p](image_paths, pages_blocks, level, usage_recorder)
        except Exception as e:
            if first_error is None:
                first_error = e
            _term_warn(f"      [Warning] {p} failed, trying next provider... ({e})")
            continue

    raise RuntimeError(f"All providers failed. First error: {first_error}")
