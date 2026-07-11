import base64
import time

import requests

from core.config import GOOGLE_VISION_API_KEY, VISION_ENDPOINT, RETRY_ATTEMPTS, RETRY_BACKOFF_SECONDS
from pipeline.tracker import _usg


def image_to_base64(image_path) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def run_vision_ocr(image_path, language_hints: list[str] | None = None) -> dict:
    if not GOOGLE_VISION_API_KEY:
        raise RuntimeError("GOOGLE_VISION_API_KEY not set")

    b64 = image_to_base64(image_path)
    request_body = {
        "requests": [{
            "image": {"content": b64},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            "imageContext": ({"languageHints": language_hints} if language_hints else {}),
        }]
    }

    url = f"{VISION_ENDPOINT}?key={GOOGLE_VISION_API_KEY}"
    t0 = time.time()
    retries = 0
    last_err = ""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = requests.post(url, json=request_body, timeout=60)
            if resp.status_code == 200:
                latency = (time.time() - t0) * 1000
                if _usg:
                    _usg.record_request("vision", model="DOCUMENT_TEXT_DETECTION",
                        success=True, latency_ms=latency, retry_count=retries,
                        pages=1, images=1)
                break
            retries += 1
            last_err = f"{resp.status_code} {resp.text}"
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
        except Exception as e:
            retries += 1
            last_err = str(e)
            if attempt == RETRY_ATTEMPTS - 1:
                latency = (time.time() - t0) * 1000
                if _usg:
                    _usg.record_request("vision", model="DOCUMENT_TEXT_DETECTION",
                        success=False, latency_ms=latency, retry_count=retries,
                        error=str(e), pages=1, images=1)
                raise RuntimeError(f"Vision API failed after {retries} attempts: {e}")
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    else:
        latency = (time.time() - t0) * 1000
        if _usg:
            _usg.record_request("vision", model="DOCUMENT_TEXT_DETECTION",
                success=False, latency_ms=latency, retry_count=retries,
                error=last_err, pages=1, images=1)
        raise RuntimeError(f"Vision API failed after {RETRY_ATTEMPTS} attempts: {last_err}")

    data = resp.json()
    result = data.get("responses", [{}])[0]

    if "error" in result:
        raise RuntimeError(f"Vision API error: {result['error']}")
    if "fullTextAnnotation" not in result:
        return {"blocks": [], "full_text": ""}

    blocks = []
    for page in result["fullTextAnnotation"].get("pages", []):
        for block in page.get("blocks", []):
            for paragraph in block.get("paragraphs", []):
                p_verts = paragraph["boundingBox"]["vertices"]
                p_xs = [v.get("x", 0) for v in p_verts]
                p_ys = [v.get("y", 0) for v in p_verts]
                para_box = [min(p_xs), min(p_ys), max(p_xs), max(p_ys)]

                para_text = ""
                for word in paragraph.get("words", []):
                    symbols = "".join(s.get("text", "") for s in word.get("symbols", []))
                    para_text += symbols
                    last_symbol = word.get("symbols", [{}])[-1]
                    break_type = last_symbol.get("property", {}).get("detectedBreak", {}).get("type", "")
                    if break_type in ("SPACE", "EOL_SURE_SPACE"): para_text += " "
                    elif break_type == "LINE_BREAK": para_text += "\n"

                if para_text.strip():
                    blocks.append({"box": para_box, "text": para_text.strip()})

    return {"blocks": blocks, "full_text": result["fullTextAnnotation"].get("text", "")}
