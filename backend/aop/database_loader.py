"""Load and index the AOP deterministic garment database."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Any, Optional


STANDARD_CARGO_LOOSE_SHORTS_ORDER = [
    "cargo_loose_shorts_design_template__left_leg_pocket__shape_01",
    "cargo_loose_shorts_design_template__left_leg_pocket__shape_02",
    "cargo_loose_shorts_design_template__left_leg_pocket__shape_03",

    "cargo_loose_shorts_design_template__left_leg__shape_01",
    "cargo_loose_shorts_design_template__left_leg__shape_02",
    "cargo_loose_shorts_design_template__left_leg__shape_03",
    "cargo_loose_shorts_design_template__left_leg__shape_04",
    "cargo_loose_shorts_design_template__left_leg__shape_05",
    "cargo_loose_shorts_design_template__left_leg__shape_06",

    "cargo_loose_shorts_design_template__pockets__shape_01",
    "cargo_loose_shorts_design_template__pockets__shape_02",
    "cargo_loose_shorts_design_template__pockets__shape_03",
    "cargo_loose_shorts_design_template__pockets__shape_04",

    "cargo_loose_shorts_design_template__right_back_pocket__shape_01",
    "cargo_loose_shorts_design_template__right_back_pocket__shape_02",
    "cargo_loose_shorts_design_template__right_back_pocket__shape_03",
    "cargo_loose_shorts_design_template__right_back_pocket__shape_04",

    "cargo_loose_shorts_design_template__right_leg_pocket__shape_01",
    "cargo_loose_shorts_design_template__right_leg_pocket__shape_02",
    "cargo_loose_shorts_design_template__right_leg_pocket__shape_03",

    "cargo_loose_shorts_design_template__right_leg__shape_01",
    "cargo_loose_shorts_design_template__right_leg__shape_02",
    "cargo_loose_shorts_design_template__right_leg__shape_03",
    "cargo_loose_shorts_design_template__right_leg__shape_04",
    "cargo_loose_shorts_design_template__right_leg__shape_05",
    "cargo_loose_shorts_design_template__right_leg__shape_06",
]


def normalize_key(value: str) -> str:
    return (
        value.lower()
        .replace("-", "_")
        .replace(" ", "_")
        .replace("__shape_", "_shape_")
        .strip("_")
    )


def reorder_piece_list(pieces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_piece_id = {piece["piece_id"]: piece for piece in pieces}

    missing = [key for key in STANDARD_CARGO_LOOSE_SHORTS_ORDER if key not in by_piece_id]
    extra = [key for key in by_piece_id if key not in STANDARD_CARGO_LOOSE_SHORTS_ORDER]

    if missing:
        raise ValueError(f"Missing composer pieces: {missing}")

    ordered = []
    for key in STANDARD_CARGO_LOOSE_SHORTS_ORDER:
        piece = by_piece_id[key]
        piece["piece_id"] = key
        piece["composer_key"] = key
        ordered.append(piece)

    return ordered


def reorder_piece_dict(pieces: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    normalized_lookup = {normalize_key(key): key for key in pieces.keys()}

    ordered: Dict[str, Dict[str, Any]] = {}
    missing = []

    for standard_key in STANDARD_CARGO_LOOSE_SHORTS_ORDER:
        normalized_standard = normalize_key(standard_key)

        old_key = normalized_lookup.get(normalized_standard)

        if old_key is None:
            missing.append(standard_key)
            continue

        piece = pieces[old_key]
        piece["piece_id"] = standard_key
        piece["composer_key"] = standard_key

        ordered[standard_key] = piece

    extra = [
        old_key
        for old_key in pieces.keys()
        if normalize_key(old_key) not in {normalize_key(key) for key in STANDARD_CARGO_LOOSE_SHORTS_ORDER}
    ]

    if missing:
        raise ValueError(f"Missing composer pieces: {missing}")

    if extra:
        # keep extras but log via a simple print; loader callers may replace with proper logging
        print(f"Warning: extra pieces not in composer order: {extra}")

    return ordered


class GarmentDatabase:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.state_path = self.root / "state.json"
        self.rules_json = self.root / "rules" / "universal_mapper_ruleset.json"
        self.state: Dict[str, Any] = {}
        self.rules: Dict[str, Any] = {}
        self._by_id: Dict[str, Dict[str, Any]] = {}
        self._pieces_by_id: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        with open(self.state_path, "r", encoding="utf-8") as f:
            self.state = json.load(f)
        with open(self.rules_json, "r", encoding="utf-8") as f:
            self.rules = json.load(f)
        for product in self.state.get("products", []):
            # Non-destructive normalization for known cargo loose shorts template
            pid = product.get("product_id", "") or ""
            gtype = product.get("garment_type", "") or ""
            try:
                if "cargo_loose_shorts" in pid or gtype == "cargo_loose_shorts":
                    pieces = product.get("pieces", [])
                    if isinstance(pieces, list):
                        product["pieces"] = reorder_piece_list(pieces)
                    elif isinstance(pieces, dict):
                        product["pieces"] = list(reorder_piece_dict(pieces).values())
            except Exception as exc:
                # Don't fail load entirely for normalization issues; surface as warning
                print(f"Cargo normalization warning for {pid}: {exc}")

            self._by_id[product["product_id"]] = product
            for piece in product.get("pieces", []):
                self._pieces_by_id[piece["piece_id"]] = piece

    @property
    def products(self) -> List[Dict[str, Any]]:
        return list(self._by_id.values())

    def product(self, product_id: str) -> Optional[Dict[str, Any]]:
        return self._by_id.get(product_id)

    def piece(self, piece_id: str) -> Optional[Dict[str, Any]]:
        return self._pieces_by_id.get(piece_id)

    def summary(self) -> List[Dict[str, Any]]:
        out = []
        for p in self.products:
            pieces = p.get("pieces", [])
            template_files = p.get("template_files", [])
            has_front = any("front" in (t.get("source_relative_path", "").lower()) for t in template_files)
            has_back = any("back" in (t.get("source_relative_path", "").lower()) for t in template_files)
            has_pocket = any("pocket" in (t.get("source_relative_path", "").lower()) for t in template_files)
            has_hood = any("hood" in (t.get("source_relative_path", "").lower()) for t in template_files)
            has_sleeves = any("sleeve" in (t.get("source_relative_path", "").lower()) for t in template_files)
            out.append({
                "product_id": p["product_id"],
                "display_name": p["display_name"],
                "garment_type": p["garment_type"],
                "piece_count": p.get("piece_count", len(pieces)),
                "template_count": len(template_files),
                "has_front": has_front,
                "has_back": has_back,
                "has_pocket": has_pocket,
                "has_hood": has_hood,
                "has_sleeves": has_sleeves,
            })
        return out

    def resolve_path(self, rel: str) -> Path:
        return self.root / rel
