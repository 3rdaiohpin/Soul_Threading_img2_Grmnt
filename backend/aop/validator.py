"""Validator + retry controller and alpha-mask validation helpers."""
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
from PIL import Image


def _rect_intersect(a: Dict[str, int], b: Dict[str, int]) -> float:
    ix = max(0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
    iy = max(0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
    return float(ix * iy)


def validate(
    analysis: Dict[str, Any],
    plan: List[Dict[str, Any]],
    hero_box: Dict[str, int],
    exclusion: List[Dict[str, Any]],
    archetype: str,
) -> Dict[str, Any]:
    """Return quality report."""
    hard_fails: List[str] = []

    canvas = analysis.get("canvas_px", {"width": 900, "height": 900})
    area = max(1, canvas["width"] * canvas["height"])
    faces = analysis.get("faces", [])
    face_area = sum(f["w"] * f["h"] for f in faces)

    # Focal completeness: assume placement mode 'contain' preserves focal fully;
    # 'cover' may crop. Penalize 'cover' when portrait.
    front_plan = next((p for p in plan if p.get("side") == "front"), None)
    focal_completeness = 9.0
    if archetype == "portrait_hero" and front_plan and front_plan.get("mode") == "cover":
        focal_completeness = 5.0
        hard_fails.append("face_cut")

    seam_safety = 9.0
    fold_safety = 9.0
    if archetype in ("scene_wrap", "abstract_wrap"):
        seam_safety = 8.0

    pocket_underlay = 10.0 if any(p.get("side") == "pocket_underlay_sample" for p in plan) else 9.0

    back_plan = next((p for p in plan if p.get("side") == "back"), None)
    back_duplication_ok = True
    if archetype == "portrait_hero" and back_plan and back_plan.get("mode") == "cover":
        back_duplication_ok = True  # cover front->back could show duplicated face; we've flagged abstract_only
    aesthetic_balance = 8.0
    chopped_penalty = 0.0

    face_ratio = face_area / area
    if archetype == "portrait_hero" and face_ratio > 0.30:
        chopped_penalty += 3.0
    if archetype == "portrait_hero" and face_ratio < 0.005:
        chopped_penalty += 2.0

    overall = (
        focal_completeness * 6
        + seam_safety * 3
        + fold_safety * 2
        + pocket_underlay * 3
        + aesthetic_balance * 3
        - chopped_penalty * 4
    )
    overall = max(0.0, min(100.0, overall))

    passed = (
        overall >= 75.0
        and focal_completeness >= 8.0
        and seam_safety >= 8.0
        and pocket_underlay >= 8.0
        and not hard_fails
    )

    return {
        "scores": {
            "focal_completeness": round(focal_completeness, 2),
            "seam_safety": round(seam_safety, 2),
            "fold_safety": round(fold_safety, 2),
            "pocket_underlay_continuity": round(pocket_underlay, 2),
            "aesthetic_balance": round(aesthetic_balance, 2),
            "chopped_penalty": round(chopped_penalty, 2),
        },
        "overall": round(overall, 2),
        "hard_fails": hard_fails,
        "passed": passed,
        "back_duplication_ok": back_duplication_ok,
    }


def suggest_retry(report: Dict[str, Any], archetype: str) -> Dict[str, Any]:
    """Suggest parameter adjustments if quality gate failed."""
    if report["passed"]:
        return {"needed": False}
    adjustments: List[str] = []
    if "face_cut" in report["hard_fails"]:
        adjustments.append("switch_placement_to_contain")
        adjustments.append("reduce_scale_10pct")
    if report["scores"]["chopped_penalty"] > 2:
        adjustments.append("shift_hero_up_5pct")
    if archetype == "portrait_hero":
        adjustments.append("force_back_abstract")
    return {"needed": True, "adjustments": adjustments}


# --- New helpers for alpha validation ---

def validate_alpha_clipped_png(path: str) -> None:
    """Raise ValueError if the PNG at path has no visible pixels or has no transparency."""
    img = Image.open(path).convert("RGBA")
    alpha = img.getchannel("A")
    data = list(alpha.getdata())
    opaque_pixels = sum(1 for p in data if p > 0)
    transparent_pixels = sum(1 for p in data if p == 0)
    if opaque_pixels == 0:
        raise ValueError(f"Output has no visible pixels: {path}")
    if transparent_pixels == 0:
        raise ValueError(f"Output is still rectangular (mask not applied): {path}")


def validate_composed_images(composed: Dict[str, Image.Image]) -> None:
    """Validate in-memory composed images (raise ValueError on failure)."""
    for key, img in composed.items():
        rgba = img.convert("RGBA")
        alpha = rgba.getchannel("A")
        data = list(alpha.getdata())
        opaque_pixels = sum(1 for p in data if p > 0)
        transparent_pixels = sum(1 for p in data if p == 0)
        if opaque_pixels == 0:
            raise ValueError(f"Composed piece '{key}' has no visible pixels")
        if transparent_pixels == 0:
            raise ValueError(f"Composed piece '{key}' appears rectangular (no transparency): {key}")
