"""Image preprocessing (deskew, denoise, contrast, threshold) via OpenCV."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np


def deskew(image: np.ndarray) -> np.ndarray:
    """Correct skew in a scanned page image.

    Uses ``cv2.minAreaRect`` to detect the dominant text angle and rotates
    the image to compensate.

    Args:
        image: BGR image array.

    Returns:
        Deskewed image (same dimensions as input if angle < 0.5°).
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    coords = np.column_stack(np.where(gray > 0))
    if len(coords) == 0:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    if abs(angle) < 0.5:
        return image
    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        image,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def denoise(image: np.ndarray, strength: int = 10) -> np.ndarray:
    """Apply fast non-local means denoising.

    Args:
        image: BGR image array.
        strength: Filter strength (higher = more aggressive).

    Returns:
        Denoised BGR image.
    """
    return cv2.fastNlMeansDenoisingColored(image, None, strength, strength, 7, 21)


def enhance_contrast(image: np.ndarray) -> np.ndarray:
    """Apply CLAHE contrast enhancement on the L channel in LAB space.

    Args:
        image: BGR image array.

    Returns:
        Contrast-enhanced BGR image.
    """
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    enhanced = cv2.merge([l, a, b])
    return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)


def adaptive_threshold(image: np.ndarray) -> np.ndarray:
    """Apply adaptive Gaussian thresholding.

    Args:
        image: BGR image array.

    Returns:
        Binary BGR image (thresholded).
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        2,
    )
    return cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)


def preprocess_image(
    image_path: Path,
    output_path: Path,
    ops: Optional[list[str]] = None,
) -> Path:
    """Run a configurable sequence of preprocessing operations on an image.

    Supported operations (in order): ``denoise``, ``enhance``, ``deskew``,
    ``threshold``.

    Args:
        image_path: Source image path.
        output_path: Destination path for the processed image.
        ops: Ordered list of operation names. Defaults to
            ``["denoise", "enhance", "deskew"]``.

    Returns:
        ``output_path`` for chaining.

    Raises:
        ValueError: If the source image cannot be read.
    """
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Cannot read image: {image_path}")

    if ops is None:
        ops = ["denoise", "enhance", "deskew"]

    for op in ops:
        if op == "deskew":
            image = deskew(image)
        elif op == "denoise":
            image = denoise(image)
        elif op == "enhance":
            image = enhance_contrast(image)
        elif op == "threshold":
            image = adaptive_threshold(image)

    cv2.imwrite(str(output_path), image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    return output_path
