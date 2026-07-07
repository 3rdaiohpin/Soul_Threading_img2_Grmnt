"""Output packager - builds ZIP with print PNGs, guides, mockup, manifest."""
from __future__ import annotations
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List
from PIL import Image


def build_contact_sheet(images: Dict[str, Image.Image], tile: int = 380) -> Image.Image:
    keys = list(images.keys())
    if not keys:
        return Image.new("RGBA", (tile, tile), (18, 20, 26, 255))
    cols = min(3, len(keys))
    rows = (len(keys) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * tile, rows * tile), (18, 20, 26, 255))
    for i, k in enumerate(keys):
        im = images[k].copy()
        im.thumbnail((tile - 20, tile - 40), Image.LANCZOS)
        x = (i % cols) * tile + (tile - im.size[0]) // 2
        y = (i // cols) * tile + (tile - im.size[1]) // 2
        sheet.paste(im, (x, y), im if im.mode == "RGBA" else None)
    return sheet


def package_output(
    job_id: str,
    product_id: str,
    archetype: str,
    composed: Dict[str, Image.Image],
    guides: Dict[str, Image.Image],
    plan: List[Dict[str, Any]],
    quality_report: Dict[str, Any],
    process_log_text: str,
) -> bytes:
    """Return ZIP bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        # Print PNGs (no guides)
        for key, img in composed.items():
            b = io.BytesIO()
            img.save(b, "PNG")
            z.writestr(f"print/{key}.png", b.getvalue())
        # Guide previews
        for key, img in guides.items():
            b = io.BytesIO()
            img.save(b, "PNG")
            z.writestr(f"guides/{key}_guide.png", b.getvalue())
        # Contact sheet
        cs = build_contact_sheet(composed)
        b = io.BytesIO()
        cs.save(b, "PNG")
        z.writestr("mockup/contact_sheet.png", b.getvalue())
        # Manifest
        manifest = {
            "job_id": job_id,
            "product_id": product_id,
            "archetype": archetype,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "plan": plan,
            "output_files": {
                "print": [f"print/{k}.png" for k in composed],
                "guides": [f"guides/{k}_guide.png" for k in guides],
                "mockup": ["mockup/contact_sheet.png"],
            },
        }
        z.writestr("mapping_manifest.json", json.dumps(manifest, indent=2))
        z.writestr("quality_report.json", json.dumps(quality_report, indent=2))
        z.writestr("mapping_process_log.txt", process_log_text)
    return buf.getvalue()
