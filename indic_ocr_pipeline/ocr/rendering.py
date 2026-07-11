"""PDF-to-image rendering using PyMuPDF (fitz)."""

from __future__ import annotations

from pathlib import Path

import fitz


def pdf_to_images(
    pdf_path: Path,
    out_dir: Path,
    dpi: int = 150,
    jpeg_quality: int = 60,
) -> list[Path]:
    """Render every page of a PDF to individual JPEG images.

    Args:
        pdf_path: Path to the source PDF.
        out_dir: Output directory for page images (created if it doesn't exist).
        dpi: Rendering resolution (dots per inch). Default 150.
        jpeg_quality: JPEG save quality 1-100. Default 60.

    Returns:
        Sorted list of paths to the rendered page images (``page_0001.jpg``, …).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    image_paths: list[Path] = []
    for i, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=matrix)
        img_path = out_dir / f"page_{i:04d}.jpg"
        pix.save(img_path, jpg_quality=jpeg_quality)
        image_paths.append(img_path)
    doc.close()
    return image_paths


def get_page_count(pdf_path: Path) -> int:
    """Get the number of pages in a PDF without rendering images.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Number of pages, or 0 if the file cannot be read.
    """
    try:
        doc = fitz.open(pdf_path)
        n = doc.page_count
        doc.close()
        return n
    except Exception:
        return 0
