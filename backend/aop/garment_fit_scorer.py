"""Garment fit scoring against artwork analysis + archetype."""
from __future__ import annotations
from typing import Dict, Any, List


ARCHETYPE_PREFERENCE = {
    "portrait_hero": {
        "prefer_types": ["tshirt_dress", "long_sleeve_button_down_shirt", "blade_collar_polo_shirt",
                         "adult_jumpsuit", "reversible_baseball_jersey"],
        "avoid_features": {"has_pocket": 15, "has_hood": 10},
    },
    "scene_wrap": {
        "prefer_types": ["dress_hoodie", "oversized_hoodie", "pull_over_hoodie", "snug_hoodie_2",
                         "adult_jumpsuit", "elongated_cloak", "zipper_cloak"],
        "avoid_features": {},
    },
    "abstract_wrap": {
        "prefer_types": ["padded_sports_bra", "cardigan", "flare_jogger", "cargo_loose_shorts",
                         "women_s_cut_and_sew_racerback_dress_aop"],
        "avoid_features": {},
    },
    "logo_text_layout": {
        "prefer_types": ["blade_collar_polo_shirt", "reversible_baseball_jersey",
                         "long_sleeve_button_down_shirt", "hooded_baseball_jacket"],
        "avoid_features": {"has_pocket": 20, "has_hood": 10},
    },
    "product_object_layout": {
        "prefer_types": ["blade_collar_polo_shirt", "oversized_hoodie", "reversible_baseball_jersey",
                         "long_sleeve_button_down_shirt"],
        "avoid_features": {"has_pocket": 10},
    },
}


def score_garment(product_summary: Dict[str, Any], archetype: str) -> Dict[str, Any]:
    prefs = ARCHETYPE_PREFERENCE.get(archetype, {})
    gtype = product_summary.get("garment_type", "")
    preferred = gtype in prefs.get("prefer_types", [])

    focal_preservation = 8.0
    panel_fit = 7.0
    seam_risk = 3.0
    pocket_risk = 5.0 if product_summary.get("has_pocket") else 1.0
    wrap_continuity = 7.0
    aesthetic_match = 8.0 if preferred else 6.0

    if archetype == "portrait_hero" and product_summary.get("has_pocket"):
        focal_preservation -= 2.0
        pocket_risk += 2.0
    if archetype in ("scene_wrap", "abstract_wrap"):
        wrap_continuity += 1.0
    if product_summary.get("has_sleeves"):
        wrap_continuity += 0.5
    if product_summary.get("has_hood") and archetype == "portrait_hero":
        panel_fit -= 1.0

    # composite score (0-100)
    composite = (
        focal_preservation * 4
        + panel_fit * 3
        + (10 - seam_risk) * 2
        + (10 - pocket_risk) * 2
        + wrap_continuity * 2
        + aesthetic_match * 3
    ) / 1.6

    hero_panels = ["front_side"]
    if product_summary.get("has_back"):
        hero_panels.append("back_side")

    risky_panels = []
    if product_summary.get("has_pocket"):
        risky_panels.append("kangaroo_pocket / pockets")

    return {
        "product_id": product_summary["product_id"],
        "display_name": product_summary["display_name"],
        "preferred_for_archetype": preferred,
        "components": {
            "focal_preservation": round(focal_preservation, 2),
            "panel_fit": round(panel_fit, 2),
            "seam_risk": round(seam_risk, 2),
            "pocket_risk": round(pocket_risk, 2),
            "wrap_continuity": round(wrap_continuity, 2),
            "aesthetic_match": round(aesthetic_match, 2),
        },
        "hero_panels": hero_panels,
        "risky_panels": risky_panels,
        "composite_score": round(min(100.0, max(0.0, composite)), 2),
    }


def score_all(product_summaries: List[Dict[str, Any]], archetype: str) -> List[Dict[str, Any]]:
    scored = [score_garment(p, archetype) for p in product_summaries]
    scored.sort(key=lambda s: -s["composite_score"])
    return scored
