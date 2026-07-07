"""Master composer.

Composes artwork onto each template's individual PIECE shapes using the
`analysis_masks/{template}__shape_XX/full_bleed.png` masks (the deterministic
printable regions). Each piece is output as its own PNG cropped to its tight
bbox — no template line-art / no labels / no red guides on the final print.

Pocket piece is deterministically sampled from the EXACT underlying composed
front so its interior continues the front artwork.
"""
from __future__ import annotations
import io
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional
import cv2
import numpy as np
from PIL import Image, ImageDraw


# Human labels for the visible pieces per template kind.
# shape_01 in each template is the main/largest silhouette in this DB.
PIECE_LABELS = {
    "front_side": ["front body", "front trim upper", "front trim lower", "front collar", "front misc"],
    "back_side": ["back body", "back trim upper", "back trim lower", "back misc"],
    "sleeves": ["right sleeve", "left sleeve", "sleeve trim", "sleeve trim 2", "sleeve misc", "sleeve misc 2"],
    "hood": ["hood outer", "hood inner", "hood binding", "hood strip", "hood misc"],
    "kangaroo_pocket": ["kangaroo pocket", "pocket binding", "pocket misc"],
    "inside_label": ["inside label"],
}


def _fill_mask(mask: Image.Image) -> Image.Image:
    """Fill an outline mask so the interior becomes solid.

    Some DB masks (front_side, back_side, sleeves) store the piece as a thin
    1-2px OUTLINE only with occasional micro-gaps that defeat naive flood-fill.
    Strategy: for sparse masks (<15% coverage) compute the CONVEX HULL of the
    outline pixel cloud and fill it. This preserves the general piece
    silhouette (front/back body, sleeve, etc.) while ignoring tiny outline
    discontinuities. Dense masks (hood, pocket) are returned unchanged.
    """
    arr = np.array(mask.convert("L"))
    h, w = arr.shape
    binary = (arr > 40).astype(np.uint8) * 255
    coverage = binary.sum() / max(1, (h * w * 255))
    if coverage > 0.15:
        return mask

    ys, xs = np.where(binary > 0)
    if len(xs) < 6:
        return mask
    pts = np.stack([xs, ys], axis=1).astype(np.int32)
    hull = cv2.convexHull(pts)
    solid = np.zeros_like(binary)
    cv2.fillPoly(solid, [hull], 255)
    return Image.fromarray(solid, mode="L")

# Which shape indices produce the actual print pieces the user cares about
# (vs. tiny trim / binding strips). Only "main" shapes are exported by default.
MAIN_SHAPES = {
    "front_side": [1],
    "back_side": [1],
    "sleeves": [1, 2],
    "hood": [1, 2],
    "kangaroo_pocket": [1],
}


def _load_template(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def _fit_cover(art: Image.Image, target_w: int, target_h: int) -> Image.Image:
    aw, ah = art.size
    ratio = max(target_w / aw, target_h / ah)
    new_w = max(1, int(aw * ratio))
    new_h = max(1, int(ah * ratio))
    resized = art.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def _fit_contain(art: Image.Image, target_w: int, target_h: int) -> Image.Image:
    aw, ah = art.size
    ratio = min(target_w / aw, target_h / ah)
    new_w = max(1, int(aw * ratio))
    new_h = max(1, int(ah * ratio))
    resized = art.resize((new_w, new_h), Image.LANCZOS)
    bg = Image.new("RGBA", (target_w, target_h), (255, 255, 255, 255))
    bg.paste(resized, ((target_w - new_w) // 2, (target_h - new_h) // 2))
    return bg


def _archetype_placement(archetype: str, side: str) -> Dict[str, Any]:
    if archetype == "portrait_hero":
        if side == "front":
            return {"mode": "contain", "y_shift": -0.05}
        if side == "back":
            return {"mode": "cover", "y_shift": 0.0}
    if archetype == "logo_text_layout" and side == "front":
        return {"mode": "contain", "y_shift": -0.08}
    return {"mode": "cover", "y_shift": 0.0}


def _template_key_from_path(rel_path: str) -> str:
    """`source_templates/oversized_hoodie/Front side.png` -> `front_side`."""
    return Path(rel_path).stem.lower().replace(" ", "_").replace("-", "_")


def _load_shape_masks(db_root: Path, product_id: str, template_key: str) -> List[Tuple[int, Image.Image]]:
    """Load all shape masks for a given template. Returns [(shape_idx, mask_L), ...]."""
    result: List[Tuple[int, Image.Image]] = []
    mask_root = db_root / "analysis_masks"
    prefix = f"{product_id}__{template_key}__shape_"
    if not mask_root.exists():
        return result
    for d in sorted(mask_root.iterdir()):
        if not d.is_dir() or not d.name.startswith(prefix):
            continue
        try:
            idx = int(d.name[len(prefix):])
        except ValueError:
            continue
        fb = d / "full_bleed.png"
        if fb.exists():
            m = Image.open(fb).convert("L")
            m = _fill_mask(m)
            result.append((idx, m))
    return result


def _extract_piece(composed_art: Image.Image, mask: Image.Image, pad: int = 8) -> Optional[Image.Image]:
    """Cut composed_art with the shape mask and crop to the mask's tight bbox."""
    if composed_art.size != mask.size:
        mask = mask.resize(composed_art.size, Image.LANCZOS)
    arr = np.array(mask)
    ys, xs = np.where(arr > 40)
    if len(xs) == 0:
        return None
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    # pad
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(composed_art.size[0], x1 + pad)
    y1 = min(composed_art.size[1], y1 + pad)
    # Apply mask to art (RGBA output on transparent bg)
    cut = Image.new("RGBA", composed_art.size, (0, 0, 0, 0))
    cut.paste(composed_art.convert("RGBA"), (0, 0), mask)
    return cut.crop((x0, y0, x1, y1))


def _piece_label(template_key: str, shape_idx: int) -> str:
    labels = PIECE_LABELS.get(template_key, [])
    if 1 <= shape_idx <= len(labels):
        return labels[shape_idx - 1]
    return f"{template_key.replace('_', ' ')} shape {shape_idx}"


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s.lower()).strip("_")


def compose_master(
    art_bytes: bytes,
    product: Dict[str, Any],
    db_root: Path,
    archetype: str,
    downscale_max_dim: int = 900,  # match analysis-mask resolution
) -> Dict[str, Any]:
    """Compose per-piece prints. Returns { 'composed': {piece_key: Image}, 'plan': [...] }.

    Composition strategy:
      1. For each template file (front_side, back_side, sleeves, hood, kangaroo_pocket)
         load its shape masks from analysis_masks/.
      2. Resize the artwork to the mask canvas using archetype-appropriate placement.
      3. For each MAIN shape in that template, cut the composed artwork with the
         shape's full_bleed mask and crop tight. This is the piece print PNG.
      4. Pocket main shape is deterministically sampled from the composed FRONT
         so its interior continues the front artwork (UR-005 exact-underlay rule).
    """
    art = Image.open(io.BytesIO(art_bytes)).convert("RGBA")
    plan: List[Dict[str, Any]] = []
    composed: Dict[str, Image.Image] = {}

    tf_by_key: Dict[str, Dict[str, Any]] = {}
    for t in product.get("template_files", []):
        key = _template_key_from_path(t["source_relative_path"])
        tf_by_key[key] = t

    # We build composed art per template at the analysis mask canvas size.
    # (shapes and full_bleed masks share this canvas.)
    front_composed_full: Optional[Image.Image] = None

    order = ["hood", "front_side", "back_side", "sleeves", "kangaroo_pocket"]
    for key in order:
        tf = tf_by_key.get(key)
        if not tf:
            continue
        analysis_px = tf.get("analysis_px") or tf.get("canvas_px")
        target_w = int(analysis_px["width"])
        target_h = int(analysis_px["height"])

        side = "front" if key == "front_side" else ("back" if key == "back_side" else key)
        placement = _archetype_placement(archetype, side)

        if placement["mode"] == "contain":
            art_layer = _fit_contain(art, target_w, target_h)
        else:
            art_layer = _fit_cover(art, target_w, target_h)

        if placement.get("y_shift"):
            shift_px = int(target_h * placement["y_shift"])
            shifted = Image.new("RGBA", (target_w, target_h), (255, 255, 255, 0))
            shifted.paste(art_layer, (0, shift_px))
            art_layer = shifted

        if key == "front_side":
            front_composed_full = art_layer.copy()

        # Extract each MAIN shape as its own piece
        shape_masks = _load_shape_masks(db_root, product["product_id"], key)
        main_indices = MAIN_SHAPES.get(key, [1])
        for idx, mask in shape_masks:
            if idx not in main_indices:
                continue
            piece = _extract_piece(art_layer, mask)
            if piece is None:
                continue
            label = _piece_label(key, idx)
            piece_key = _slug(label)
            composed[piece_key] = piece
            plan.append({
                "piece_key": piece_key,
                "label": label,
                "template_key": key,
                "shape_index": idx,
                "mode": placement["mode"],
                "y_shift": placement.get("y_shift", 0.0),
                "canvas_px": {"width": target_w, "height": target_h},
                "piece_px": {"width": piece.size[0], "height": piece.size[1]},
            })

    # Pocket underlay: sample from the composed FRONT at the pocket zone,
    # then apply the pocket's own shape mask + crop.
    pocket_tf = tf_by_key.get("kangaroo_pocket")
    if pocket_tf and front_composed_full is not None:
        pocket_masks = _load_shape_masks(db_root, product["product_id"], "kangaroo_pocket")
        pocket_main_idx = MAIN_SHAPES.get("kangaroo_pocket", [1])[0]
        pmask = next((m for i, m in pocket_masks if i == pocket_main_idx), None)
        if pmask is not None:
            pw, ph = pmask.size
            fw, fh = front_composed_full.size
            sw = int(fw * 0.6)
            sh = int(fh * 0.28)
            sx = (fw - sw) // 2
            sy = int(fh * 0.55)
            sampled = front_composed_full.crop((sx, sy, sx + sw, sy + sh))
            sampled = sampled.resize((pw, ph), Image.LANCZOS)
            piece = _extract_piece(sampled, pmask)
            if piece is not None:
                # Override the naive pocket produced in the main loop with the
                # deterministic underlay sample (UR-005 exact-underlay rule).
                composed["kangaroo_pocket"] = piece
                plan.append({
                    "piece_key": "kangaroo_pocket",
                    "label": "kangaroo pocket (underlay)",
                    "template_key": "kangaroo_pocket_underlay",
                    "shape_index": pocket_main_idx,
                    "sample_on_front_bbox": {"x": sx, "y": sy, "w": sw, "h": sh},
                    "canvas_px": {"width": pw, "height": ph},
                    "piece_px": {"width": piece.size[0], "height": piece.size[1]},
                })

    return {"composed": composed, "plan": plan}


def draw_guides(base: Image.Image, exclusion: List[Dict[str, Any]], hero_box: Optional[Dict[str, int]] = None) -> Image.Image:
    out = base.convert("RGBA").copy()
    draw = ImageDraw.Draw(out, "RGBA")
    for z in exclusion:
        b = z["bbox"]
        color_map = {
            "collar_band": (255, 200, 0, 90),
            "hem_band": (255, 200, 0, 90),
            "seam_left": (255, 90, 90, 90),
            "seam_right": (255, 90, 90, 90),
            "shoulder_seam": (255, 90, 90, 90),
            "cuff": (255, 200, 0, 90),
            "hood_seam": (255, 90, 90, 90),
            "pocket_edge": (0, 200, 255, 90),
            "generic_bleed": (255, 200, 0, 60),
        }
        c = color_map.get(z["kind"], (255, 255, 255, 60))
        draw.rectangle([b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]], fill=c)
    if hero_box:
        b = hero_box
        draw.rectangle([b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]], outline=(6, 182, 212, 220), width=3)
    return out


def to_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()
