"""Exclusion zones + hero comfort box + adjacency graph builder.

Given a garment product and archetype, compute:
- exclusion zones per template (seam/fold/bleed/pocket/collar/cuff bands)
- hero comfort box (safe area for face/focal placement)
- adjacency graph (which template pieces share edges)
"""
from __future__ import annotations
from typing import Dict, Any, List, Tuple


def hero_comfort_box(template_dim: Dict[str, int], garment_type: str) -> Dict[str, int]:
    """Return safe inset box on a template canvas."""
    w = template_dim["width"]
    h = template_dim["height"]
    inset_x = int(w * 0.18)
    inset_y_top = int(h * 0.22)
    inset_y_bot = int(h * 0.28)
    return {"x": inset_x, "y": inset_y_top, "w": w - 2 * inset_x, "h": h - inset_y_top - inset_y_bot}


def exclusion_zones(template_key: str, template_dim: Dict[str, int]) -> List[Dict[str, Any]]:
    """Return list of exclusion bands: seams, folds, pockets, collar/hem/cuff bands."""
    w = template_dim["width"]
    h = template_dim["height"]
    zones: List[Dict[str, Any]] = []
    key = template_key.lower()

    if "front" in key or "back" in key:
        zones.append({"kind": "collar_band", "bbox": {"x": 0, "y": 0, "w": w, "h": int(h * 0.08)}})
        zones.append({"kind": "hem_band", "bbox": {"x": 0, "y": int(h * 0.94), "w": w, "h": int(h * 0.06)}})
        zones.append({"kind": "seam_left", "bbox": {"x": 0, "y": 0, "w": int(w * 0.04), "h": h}})
        zones.append({"kind": "seam_right", "bbox": {"x": int(w * 0.96), "y": 0, "w": int(w * 0.04), "h": h}})
    if "sleeve" in key:
        zones.append({"kind": "shoulder_seam", "bbox": {"x": 0, "y": 0, "w": w, "h": int(h * 0.08)}})
        zones.append({"kind": "cuff", "bbox": {"x": 0, "y": int(h * 0.92), "w": w, "h": int(h * 0.08)}})
    if "hood" in key:
        zones.append({"kind": "hood_seam", "bbox": {"x": 0, "y": int(h * 0.90), "w": w, "h": int(h * 0.10)}})
    if "pocket" in key:
        zones.append({"kind": "pocket_edge", "bbox": {"x": 0, "y": 0, "w": w, "h": int(h * 0.06)}})
        zones.append({"kind": "pocket_edge", "bbox": {"x": 0, "y": int(h * 0.94), "w": w, "h": int(h * 0.06)}})
    if not zones:
        zones.append({"kind": "generic_bleed", "bbox": {"x": 0, "y": 0, "w": w, "h": int(h * 0.05)}})
    return zones


def adjacency_graph(product: Dict[str, Any]) -> Dict[str, Any]:
    tf = product.get("template_files", [])
    names = [t["source_relative_path"].lower().split(".")[0] for t in tf]
    edges: List[Tuple[str, str, str]] = []
    def has(x): return any(x in n for n in names)
    if has("front") and has("back"):
        edges.append(("front side", "back side", "shoulder+side seam"))
    if has("sleeve") and has("front"):
        edges.append(("sleeves", "front side", "armhole seam"))
    if has("sleeve") and has("back"):
        edges.append(("sleeves", "back side", "armhole seam"))
    if has("hood") and has("back"):
        edges.append(("hood", "back side", "neckline seam"))
    if has("pocket") and has("front"):
        edges.append(("kangaroo pocket", "front side", "overlay attachment"))
    return {"nodes": names, "edges": edges}
