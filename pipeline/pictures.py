def detect_embedded_pictures(pdf_page, dpi: int) -> list[dict]:
    zoom = dpi / 72
    page_w, page_h = pdf_page.rect.width * zoom, pdf_page.rect.height * zoom
    results = []
    for img_info in pdf_page.get_image_info():
        bbox = img_info.get("bbox")
        if not bbox:
            continue
        x1, y1, x2, y2 = bbox
        scaled = [x1 * zoom, y1 * zoom, x2 * zoom, y2 * zoom]
        w, h = scaled[2] - scaled[0], scaled[3] - scaled[1]
        if w < 40 or h < 40:
            continue
        if w * h > 0.5 * page_w * page_h:
            continue
        results.append({"box": [round(v) for v in scaled], "text": "", "is_picture": True})
    return results


def detect_picture_regions_cv(image_path, text_boxes: list[list[int]],
                                min_area: int = 3000) -> list[dict]:
    import cv2
    import numpy as np

    img = cv2.imread(str(image_path))
    if img is None:
        return []
    h, w = img.shape[:2]

    mask = np.ones((h, w), dtype=np.uint8) * 255
    for box in text_boxes:
        x1, y1, x2, y2 = [max(0, min(v, [w, h, w, h][i])) for i, v in enumerate(box)]
        mask[y1:y2, x1:x2] = 0

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
    thresh = cv2.bitwise_and(thresh, thresh, mask=mask)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    results = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = cw * ch
        if area < min_area:
            continue
        if area > 0.5 * w * h:
            continue
        if cw > 0.9 * w and ch > 0.9 * h:
            continue
        results.append({"box": [x, y, x + cw, y + ch], "text": "", "is_picture": True})
    return results
