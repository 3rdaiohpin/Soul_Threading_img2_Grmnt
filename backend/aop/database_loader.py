"""Load and index the AOP deterministic garment database."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Any, Optional


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
