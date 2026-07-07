"""Archetype classifier for artwork.

Uses deterministic heuristics from artwork analysis output:
- portrait_hero: face(s) detected + face bbox area >= 3% of canvas
- logo_text_layout: text/mser regions dominate + few colors
- product_object_layout: strong single subject bbox with clear background
- scene_wrap: high edge density spread across canvas, medium color diversity
- abstract_wrap: default fallback / no faces / no dominant subject

Optionally accepts a "smart_hint" from Emergent vision LLM to bias.
"""
from __future__ import annotations
from typing import Dict, Any, Optional

ARCHETYPES = [
    "portrait_hero",
    "scene_wrap",
    "abstract_wrap",
    "logo_text_layout",
    "product_object_layout",
]


def classify(analysis: Dict[str, Any], smart_hint: Optional[str] = None) -> Dict[str, Any]:
    canvas = analysis.get("canvas_px", {"width": 900, "height": 900})
    W = max(1, int(canvas.get("width", 900)))
    H = max(1, int(canvas.get("height", 900)))
    area = W * H

    scores = {a: 0.0 for a in ARCHETYPES}

    faces = analysis.get("faces", [])
    face_area = sum(f["w"] * f["h"] for f in faces) if faces else 0
    face_ratio = face_area / area
    scores["portrait_hero"] += 60.0 * min(1.0, face_ratio / 0.03) if faces else 0.0
    if len(faces) >= 1:
        scores["portrait_hero"] += 15.0

    text_regions = analysis.get("text_regions", [])
    text_area = sum(r["w"] * r["h"] for r in text_regions) if text_regions else 0
    text_ratio = text_area / area
    scores["logo_text_layout"] += 55.0 * min(1.0, text_ratio / 0.08)
    if len(text_regions) >= 4:
        scores["logo_text_layout"] += 15.0

    subj = analysis.get("primary_subject", {"w": 0, "h": 0})
    subj_ratio = (subj.get("w", 0) * subj.get("h", 0)) / area
    if 0.15 <= subj_ratio <= 0.55 and not faces:
        scores["product_object_layout"] += 50.0

    zones = analysis.get("saliency_zones", {})
    hot = zones.get("hot", 0)
    mid = zones.get("mid", 0)
    cold = zones.get("cold", 1)
    total = max(1, hot + mid + cold)
    hot_ratio = hot / total
    mid_ratio = mid / total
    if hot_ratio + mid_ratio > 0.4:
        scores["scene_wrap"] += 45.0
    else:
        scores["abstract_wrap"] += 40.0

    colors = analysis.get("dominant_colors", [])
    if colors:
        top_share = colors[0]["share"]
        if top_share > 0.55:
            scores["abstract_wrap"] += 15.0
        if len(colors) >= 4 and colors[0]["share"] < 0.4:
            scores["scene_wrap"] += 10.0

    if smart_hint and smart_hint in ARCHETYPES:
        scores[smart_hint] += 25.0

    scores["abstract_wrap"] += 5.0

    archetype = max(scores.items(), key=lambda kv: kv[1])[0]
    return {
        "archetype": archetype,
        "scores": {k: round(v, 2) for k, v in scores.items()},
        "signals": {
            "face_ratio": round(face_ratio, 4),
            "text_ratio": round(text_ratio, 4),
            "subject_ratio": round(subj_ratio, 4),
            "hot_ratio": round(hot_ratio, 4),
        },
        "smart_hint": smart_hint,
    }
