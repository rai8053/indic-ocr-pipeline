import time

import requests

from core.terminal import warn as _term_warn
from core.config import (OPENROUTER_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, GLM_API_KEY, IAMHC_API_KEY,
                         OPENROUTER_MODEL, GEMINI_MODEL, GEMINI_ENDPOINT_TMPL,
                         GLM_ENDPOINT, GLM_MODEL,
                         OPENROUTER_ENDPOINT, GROQ_MODEL, GROQ_ENDPOINT,
                         IAMHC_ENDPOINT, IAMHC_MODEL,
                         RETRY_ATTEMPTS, RETRY_BACKOFF_SECONDS)
from pipeline.tracker import _usg
from pipeline.prompts import build_vision_batch_prompt, build_batch_prompt
from pipeline.annotator import _parse_batch_response
from pipeline.ocr import image_to_base64


def _post_with_retry(url, json_body, headers, timeout):
    resp = None
    retries = 0
    t0 = time.time()
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = requests.post(url, json=json_body, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                latency = (time.time() - t0) * 1000
                return resp, retries, latency
            retries += 1
            wait = int(resp.headers.get("Retry-After", RETRY_BACKOFF_SECONDS * (attempt + 1) * 4))
            if wait > 60: wait = 60
            time.sleep(wait)
        except Exception as e:
            retries += 1
            if attempt == RETRY_ATTEMPTS - 1:
                raise RuntimeError(f"Request failed after {retries} attempts: {e}")
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    latency = (time.time() - t0) * 1000
    raise RuntimeError(f"Request failed after {RETRY_ATTEMPTS} attempts")


def run_openrouter_proofread_batch(image_paths, pages_blocks, level=3):
    if not OPENROUTER_API_KEY: raise RuntimeError("OPENROUTER_API_KEY not set")
    prompt = build_batch_prompt(pages_blocks, level=level)
    payload = {"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 16384}
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    n_pages = len(image_paths)
    in_tok = max(1, len(prompt) // 4)
    try:
        resp, retries, lat = _post_with_retry(OPENROUTER_ENDPOINT, payload, headers, timeout=180)
        raw_text = resp.json()["choices"][0]["message"]["content"]
        out_tok = max(1, len(raw_text) // 4)
        if _usg:
            _usg.record_request("openrouter", success=True, latency_ms=lat,
                retry_count=retries, pages=n_pages, images=n_pages,
                input_tokens=in_tok, output_tokens=out_tok)
        pages_out = _parse_batch_response(raw_text, n_pages, pages_blocks, level)
        if level >= 4:
            for page in pages_out:
                page["annotation_quality"] = "degraded_text_only_fallback"
        return pages_out
    except Exception as e:
        if _usg:
            _usg.record_request("openrouter", success=False, latency_ms=0,
                retry_count=0, error=str(e), pages=n_pages, images=n_pages)
        raise


def run_gemini_proofread_batch(image_paths, pages_blocks, level=3):
    if not GEMINI_API_KEY: raise RuntimeError("GEMINI_API_KEY not set")
    prompt = build_vision_batch_prompt(pages_blocks, level=level)
    parts = [{"text": prompt}]
    for img_path in image_paths:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": image_to_base64(img_path)}})
    url = GEMINI_ENDPOINT_TMPL.format(model=GEMINI_MODEL)
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload = {"contents": [{"parts": parts}], "generationConfig": {"response_mime_type": "application/json"}}
    n_pages = len(image_paths)
    in_tok = max(1, len(prompt) // 4)
    try:
        resp, retries, lat = _post_with_retry(url, payload, headers, timeout=180)
        raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        out_tok = max(1, len(raw_text) // 4)
        if _usg:
            _usg.record_request("gemini", success=True, latency_ms=lat,
                retry_count=retries, pages=n_pages, images=n_pages,
                input_tokens=in_tok, output_tokens=out_tok)
        pages_out = _parse_batch_response(raw_text, n_pages, pages_blocks, level)
        if level >= 4:
            for page in pages_out:
                page["annotation_quality"] = "full_level4"
        return pages_out
    except Exception as e:
        if _usg:
            _usg.record_request("gemini", success=False, latency_ms=0,
                retry_count=0, error=str(e), pages=n_pages, images=n_pages)
        raise


def run_groq_proofread_batch(image_paths, pages_blocks, level=3):
    if not GROQ_API_KEY: raise RuntimeError("GROQ_API_KEY not set")
    prompt = build_batch_prompt(pages_blocks, level=level)
    payload = {"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 8192}
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    n_pages = len(image_paths)
    in_tok = max(1, len(prompt) // 4)
    try:
        resp, retries, lat = _post_with_retry(GROQ_ENDPOINT, payload, headers, timeout=180)
        raw_text = resp.json()["choices"][0]["message"]["content"]
        out_tok = max(1, len(raw_text) // 4)
        if _usg:
            _usg.record_request("groq", success=True, latency_ms=lat,
                retry_count=retries, pages=n_pages, images=n_pages,
                input_tokens=in_tok, output_tokens=out_tok)
        pages_out = _parse_batch_response(raw_text, n_pages, pages_blocks, level)
        if level >= 4:
            for page in pages_out:
                page["annotation_quality"] = "degraded_text_only_fallback"
        return pages_out
    except Exception as e:
        if _usg:
            _usg.record_request("groq", success=False, latency_ms=0,
                retry_count=0, error=str(e), pages=n_pages, images=n_pages)
        raise


def run_glm_proofread_batch(image_paths, pages_blocks, level=3):
    if not GLM_API_KEY: raise RuntimeError("GLM_API_KEY not set")
    prompt = build_vision_batch_prompt(pages_blocks, level=level)
    content = [{"type": "text", "text": prompt}]
    for img_path in image_paths:
        b64 = image_to_base64(img_path)
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

    payload = {"model": GLM_MODEL, "messages": [{"role": "user", "content": content}], "max_tokens": 16384}
    headers = {"Authorization": f"Bearer {GLM_API_KEY}", "Content-Type": "application/json"}
    n_pages = len(image_paths)
    in_tok = max(1, len(prompt) // 4)
    try:
        resp, retries, lat = _post_with_retry(GLM_ENDPOINT, payload, headers, timeout=180)
        raw_text = resp.json()["choices"][0]["message"].get("content", "")
        out_tok = max(1, len(raw_text) // 4)
        if _usg:
            _usg.record_request("glm", success=True, latency_ms=lat,
                retry_count=retries, pages=n_pages, images=n_pages,
                input_tokens=in_tok, output_tokens=out_tok)
        pages_out = _parse_batch_response(raw_text, n_pages, pages_blocks, level)
        if level >= 4:
            for page in pages_out:
                page["annotation_quality"] = "full_level4"
        return pages_out
    except Exception as e:
        if _usg:
            _usg.record_request("glm", success=False, latency_ms=0,
                retry_count=0, error=str(e), pages=n_pages, images=n_pages)
        raise


def run_iamhc_proofread_batch(image_paths, pages_blocks, level=3):
    if not IAMHC_API_KEY:
        raise RuntimeError("IAMHC_API_KEY not set")
    prompt = build_vision_batch_prompt(pages_blocks, level=level)
    content = [{"type": "text", "text": prompt}]
    for img_path in image_paths:
        b64 = image_to_base64(img_path)
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    payload = {"model": IAMHC_MODEL, "messages": [{"role": "user", "content": content}], "max_tokens": 16384}
    headers = {"Authorization": f"Bearer {IAMHC_API_KEY}", "Content-Type": "application/json"}
    n_pages = len(image_paths)
    in_tok = max(1, len(prompt) // 4)
    try:
        resp, retries, lat = _post_with_retry(IAMHC_ENDPOINT, payload, headers, timeout=180)
        raw_text = resp.json()["choices"][0]["message"]["content"]
        out_tok = max(1, len(raw_text) // 4)
        if _usg:
            _usg.record_request("iamhc", success=True, latency_ms=lat,
                retry_count=retries, pages=n_pages, images=n_pages,
                input_tokens=in_tok, output_tokens=out_tok)
        pages_out = _parse_batch_response(raw_text, n_pages, pages_blocks, level)
        if level >= 4:
            for page in pages_out:
                page["annotation_quality"] = "full_level4"
        return pages_out
    except Exception as e:
        try:
            text_prompt = build_batch_prompt(pages_blocks, level=level)
            text_payload = {"model": IAMHC_MODEL, "messages": [{"role": "user", "content": text_prompt}], "max_tokens": 16384}
            resp, retries, lat = _post_with_retry(IAMHC_ENDPOINT, text_payload, headers, timeout=180)
            raw_text = resp.json()["choices"][0]["message"]["content"]
            out_tok = max(1, len(raw_text) // 4)
            if _usg:
                _usg.record_request("iamhc", success=True, latency_ms=lat,
                    retry_count=retries, pages=n_pages, images=n_pages,
                    input_tokens=in_tok, output_tokens=out_tok)
            pages_out = _parse_batch_response(raw_text, n_pages, pages_blocks, level)
            if level >= 4:
                for page in pages_out:
                    page["annotation_quality"] = "degraded_text_only_fallback"
            return pages_out
        except Exception as e2:
            if _usg:
                _usg.record_request("iamhc", success=False, latency_ms=0,
                    retry_count=0, error=str(e2), pages=n_pages, images=n_pages)
            raise RuntimeError(f"iamhc vision+text both failed: {e} / {e2}")


def run_proofread_batch(provider: str, image_paths, pages_blocks, level=3):
    providers = {
        "openrouter": run_openrouter_proofread_batch,
        "gemini": run_gemini_proofread_batch,
        "groq": run_groq_proofread_batch,
        "glm": run_glm_proofread_batch,
        "iamhc": run_iamhc_proofread_batch,
    }
    chain = [provider]
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

    first_error = None
    for p in chain:
        if p not in providers:
            continue
        try:
            return providers[p](image_paths, pages_blocks, level)
        except Exception as e:
            if first_error is None:
                first_error = e
            _term_warn(f"      [Warning] {p} failed, trying next provider... ({e})")
            continue
    raise RuntimeError(f"All providers failed. First error: {first_error}")
