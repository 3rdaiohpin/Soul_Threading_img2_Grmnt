"""Master composer.

Places artwork on garment templates (front/back/sleeves/hood/pocket)
using deterministic Pillow composition. Ensures pockets sample from the
EXACT underlying composed front (no independent crop).

Returns dict of {template_key: PIL.Image or bytes} + placement plan.
"""
from __future__ import annotations
import io
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional
from PIL import Image, ImageDraw, ImageFilter


def _load_template(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def _fit_and_tile(art: Image.Image, target_w: int, target_h: int, mode: str = "cover") -> Image.Image:
    """Return artwork resized to cover a target canvas."""
    aw, ah = art.size
    if mode == "cover":
        ratio = max(target_w / aw, target_h / ah)
        new_w = int(aw * ratio)
        new_h = int(ah * ratio)
        resized = art.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        return resized.crop((left, top, left + target_w, top + target_h))
    elif mode == "contain":
        ratio = min(target_w / aw, target_h / ah)
        new_w = int(aw * ratio)
        new_h = int(ah * ratio)
        resized = art.resize((new_w, new_h), Image.LANCZOS)
        bg = Image.new("RGBA", (target_w, target_h), (255, 255, 255, 255))
        bg.paste(resized, ((target_w - new_w) // 2, (target_h - new_h) // 2))
        return bg
    return art.resize((target_w, target_h), Image.LANCZOS)


def _archetype_placement(archetype: str, side: str) -> Dict[str, Any]:
    """Return placement params: scale, y_shift (fraction), mode."""
    if archetype == "portrait_hero":
        if side == "front":
            return {"mode": "contain", "scale": 0.85, "y_shift": -0.05}
        if side == "back":
            return {"mode": "cover", "scale": 1.0, "y_shift": 0.0, "abstract_only": True}
    if archetype == "logo_text_layout":
        return {"mode": "contain", "scale": 0.7, "y_shift": -0.08}
    return {"mode": "cover", "scale": 1.0, "y_shift": 0.0}


def compose_master(
    art_bytes: bytes,
    product: Dict[str, Any],
    db_root: Path,
    archetype: str,
    downscale_max_dim: int = 1400,
) -> Dict[str, Any]:
    """Compose master views. Returns dict with 'composed' pillow images per template key + plan."""
    art = Image.open(io.BytesIO(art_bytes)).convert("RGBA")
    plan: List[Dict[str, Any]] = []
    composed: Dict[str, Image.Image] = {}

    # Locate front + back templates
    tf = product.get("template_files", [])
    front_tf = next((t for t in tf if "front" in t["source_relative_path"].lower()), None)
    back_tf = next((t for t in tf if "back" in t["source_relative_path"].lower()), None)
    pocket_tfs = [t for t in tf if "pocket" in t["source_relative_path"].lower()]
    sleeve_tf = next((t for t in tf if "sleeve" in t["source_relative_path"].lower()), None)
    hood_tf = next((t for t in tf if "hood" in t["source_relative_path"].lower()), None)

    def compose_side(template_entry: Dict[str, Any], side: str) -> Optional[Image.Image]:
        path = db_root / template_entry["template_png"]
        if not path.exists():
            return None
        template = _load_template(path)
        # Downscale template for compose (real prod would use full res)
        tw, th = template.size
        m = max(tw, th)
        if m > downscale_max_dim:
            scale = downscale_max_dim / m
            template = template.resize((int(tw * scale), int(th * scale)), Image.LANCZOS)
            tw, th = template.size

        placement = _archetype_placement(archetype, side)
        art_layer = _fit_and_tile(art, tw, th, mode=placement["mode"])
        # y-shift
        if placement.get("y_shift"):
            shift_px = int(th * placement["y_shift"])
            shifted = Image.new("RGBA", (tw, th), (255, 255, 255, 0))
            shifted.paste(art_layer, (0, shift_px))
            art_layer = shifted

        # composite: use template alpha as mask so only garment shape is painted
        base = Image.new("RGBA", (tw, th), (255, 255, 255, 0))
        # If template has alpha (transparent bg), use it as mask
        alpha = template.split()[-1]
        base.paste(art_layer, (0, 0), alpha)
        # keep template line-art overlay faint
        base = Image.alpha_composite(base, template)
        plan.append({
            "template": template_entry["template_png"],
            "side": side,
            "mode": placement["mode"],
            "scale": placement["scale"],
            "y_shift": placement.get("y_shift", 0.0),
            "canvas_px": {"width": tw, "height": th},
        })
        return base

    if front_tf:
        img = compose_side(front_tf, "front")
        if img is not None:
            composed["master_front"] = img
    if back_tf:
        img = compose_side(back_tf, "back")
        if img is not None:
            composed["master_back"] = img
    if sleeve_tf:
        img = compose_side(sleeve_tf, "sleeve")
        if img is not None:
            composed["sleeves"] = img
    if hood_tf:
        img = compose_side(hood_tf, "hood")
        if img is not None:
            composed["hood"] = img

    # pocket sampling from front (deterministic underlay)
    for pt in pocket_tfs:
        path = db_root / pt["template_png"]
        if not path.exists():
            continue
        pocket_tpl = _load_template(path)
        pw, ph = pocket_tpl.size
        m = max(pw, ph)
        if m > downscale_max_dim:
            scale = downscale_max_dim / m
            pocket_tpl = pocket_tpl.resize((int(pw * scale), int(ph * scale)), Image.LANCZOS)
            pw, ph = pocket_tpl.size

        if "master_front" in composed:
            front_img = composed["master_front"]
            fw, fh = front_img.size
            # sample center-lower region of front for kangaroo pocket
            sample_w = int(fw * 0.55)
            sample_h = int(fh * 0.28)
            left = (fw - sample_w) // 2
            top = int(fh * 0.55)
            sampled = front_img.crop((left, top, left + sample_w, top + sample_h))
            sampled = sampled.resize((pw, ph), Image.LANCZOS)
            base = Image.new("RGBA", (pw, ph), (255, 255, 255, 0))
            alpha = pocket_tpl.split()[-1]
            base.paste(sampled, (0, 0), alpha)
            base = Image.alpha_composite(base, pocket_tpl)
            key = "pocket_" + Path(pt["template_png"]).stem
            composed[key] = base
            plan.append({
                "template": pt["template_png"],
                "side": "pocket_underlay_sample",
                "sample_bbox_on_front": {"x": left, "y": top, "w": sample_w, "h": sample_h},
                "canvas_px": {"width": pw, "height": ph},
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
        draw.rectangle([b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]], outline=(6, 182, 212, 220), width=4)
    return out


def to_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()
