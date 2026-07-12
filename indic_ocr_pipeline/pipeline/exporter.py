"""Export utilities — ZIP creation and output management."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path


def create_submission_zip(
    output_dir: Path,
    lang: str,
    json_files: list[Path],
    images_dir: Path,
    max_samples: int = 0,
) -> Path:
    """Create a submission ZIP archive containing annotation JSONs and source images.

    Optionally samples the best N pages based on validation diversity and
    class count when ``max_samples > 0``.

    Args:
        output_dir: Output root directory.
        lang: Language key for folder naming inside the ZIP.
        json_files: Sorted list of annotation JSON paths.
        images_dir: Directory containing source page images.
        max_samples: Maximum number of pages to include (0 = all).

    Returns:
        Path to the created ZIP file.
    """
    lang = lang.lower() if lang else "unknown"
    zip_path = output_dir / f"{lang}_submission.zip"

    if max_samples > 0 and len(json_files) > max_samples:
        from indic_ocr_pipeline.layout.validator import validate_page

        scored = [(j, validate_page(j)) for j in json_files]
        scored.sort(
            key=lambda x: (x[1].get("diverse", False), x[1].get("class_count", 0)), reverse=True
        )
        json_files = [s[0] for s in scored[:max_samples]]

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for j in json_files:
            with open(j, encoding="utf-8") as f:
                data = json.load(f)
            zf.writestr(f"{lang}/{j.stem}.json", json.dumps(data, ensure_ascii=False, indent=2))
            img_name = data.get("image", "")
            if img_name:
                img_path = images_dir / img_name
                if img_path.exists():
                    zf.write(img_path, f"{lang}/{img_path.name}")

    return zip_path
