"""End-to-end mapping pipeline orchestrator."""
from __future__ import annotations
import io
import uuid
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image

from .database_loader import GarmentDatabase
from .artwork_analyzer import analyze_artwork
from .archetype_classifier import classify
from .garment_fit_scorer import score_all
from .exclusion_zones import exclusion_zones, hero_comfort_box, adjacency_graph
from .master_composer import compose_master, draw_guides, to_bytes
from .validator import validate, suggest_retry
from .output_packager import package_output
from .process_logger import ProcessLogger
from .model_manager import ModelManager


class MapJob:
    def __init__(self, db: GarmentDatabase, art_bytes: bytes, product_id: str, smart_hint_data: Optional[Dict[str, Any]] = None):
        self.db = db
        self.art_bytes = art_bytes
        self.product_id = product_id
        self.smart_hint_data = smart_hint_data or {}
        self.job_id = uuid.uuid4().hex[:12]
        self.logger = ProcessLogger()
        self.result: Dict[str, Any] = {"job_id": self.job_id}
        self.composed_images: Dict[str, Image.Image] = {}
        self.guides_images: Dict[str, Image.Image] = {}
        self.zip_bytes: bytes = b""

    def run(self, allow_retry: bool = True) -> Dict[str, Any]:
        self.logger.info("boot", f"Job {self.job_id} started")
        product = self.db.product(self.product_id)
        if product is None:
            self.logger.error("db", f"Unknown product_id={self.product_id}")
            self.result["error"] = "unknown_product"
            return self.result
        self.logger.ok("db", f"Loaded product {product['display_name']} pieces={product.get('piece_count')}")

        # 1. Analyze
        self.logger.info("analyze", "Analyzing artwork (CPU fallback stack)")
        analysis = analyze_artwork(self.art_bytes)
        self.logger.ok(
            "analyze",
            f"faces={len(analysis['faces'])} text_regions={len(analysis['text_regions'])} "
            f"colors={len(analysis['dominant_colors'])}",
        )

        # 2. Archetype (with optional smart hint)
        smart_arch = None
        if isinstance(self.smart_hint_data, dict):
            smart_arch = self.smart_hint_data.get("archetype")
            if smart_arch:
                self.logger.ok("smart_hint", f"vision assist hint = {smart_arch}")
        arch = classify(analysis, smart_hint=smart_arch)
        self.logger.ok("archetype", f"chosen = {arch['archetype']}")

        # 3. Score garments
        scored = score_all(self.db.summary(), arch["archetype"])
        chosen_score = next((s for s in scored if s["product_id"] == self.product_id), None)
        self.logger.ok("fit_score", f"composite={chosen_score['composite_score'] if chosen_score else 'n/a'}")

        # 4. Composition
        self.logger.info("compose", "Composing master front/back/sleeves/hood/pockets")
        comp_result = compose_master(self.art_bytes, product, self.db.root, arch["archetype"])
        composed = comp_result["composed"]
        plan = comp_result["plan"]
        self.composed_images = composed
        self.logger.ok("compose", f"produced {len(composed)} composed panels")

        # 5. Exclusion zones + hero box + guides
        for key, im in composed.items():
            w, h = im.size
            zones = exclusion_zones(key, {"width": w, "height": h})
            hbox = hero_comfort_box({"width": w, "height": h}, product.get("garment_type", ""))
            self.guides_images[key] = draw_guides(im, zones, hbox)
        adj = adjacency_graph(product)
        self.logger.ok("exclusion", f"zones+guides for {len(composed)} panels; adjacency edges={len(adj['edges'])}")

        # 6. Validate
        # use first front/back plan for hero box report
        first_plan = plan[0] if plan else {"canvas_px": {"width": 900, "height": 900}}
        hbox = hero_comfort_box(first_plan["canvas_px"], product.get("garment_type", ""))
        excl = exclusion_zones("front_side", first_plan["canvas_px"])
        report = validate(analysis, plan, hbox, excl, arch["archetype"])
        self.logger.ok("validate", f"overall={report['overall']} passed={report['passed']}")

        # 7. Retry if needed (single-shot)
        retry_info = suggest_retry(report, arch["archetype"])
        if retry_info["needed"] and allow_retry:
            self.logger.warn("retry", f"attempting adjustments: {retry_info['adjustments']}")
            # Simple retry: force archetype-appropriate placement by rerunning as portrait_hero if possible
            comp_result2 = compose_master(
                self.art_bytes, product, self.db.root,
                "portrait_hero" if "switch_placement_to_contain" in retry_info["adjustments"] else arch["archetype"],
            )
            composed = comp_result2["composed"]
            plan = comp_result2["plan"]
            self.composed_images = composed
            self.guides_images = {}
            for key, im in composed.items():
                w, h = im.size
                zones = exclusion_zones(key, {"width": w, "height": h})
                hbox = hero_comfort_box({"width": w, "height": h}, product.get("garment_type", ""))
                self.guides_images[key] = draw_guides(im, zones, hbox)
            report = validate(analysis, plan, hbox, excl, arch["archetype"])
            self.logger.ok("retry", f"post-retry overall={report['overall']}")

        # 8. Package
        log_text = self.logger.to_text()
        self.zip_bytes = package_output(
            job_id=self.job_id,
            product_id=self.product_id,
            archetype=arch["archetype"],
            composed=self.composed_images,
            guides=self.guides_images,
            plan=plan,
            quality_report=report,
            process_log_text=log_text,
        )
        self.logger.ok("package", f"output_package.zip size_bytes={len(self.zip_bytes)}")

        self.result.update({
            "product_id": self.product_id,
            "product_name": product["display_name"],
            "archetype": arch,
            "analysis_summary": {
                "faces": len(analysis["faces"]),
                "text_regions": len(analysis["text_regions"]),
                "dominant_colors": analysis["dominant_colors"],
                "canvas_px": analysis["canvas_px"],
                "primary_subject": analysis["primary_subject"],
                "thumb_png_b64": analysis["thumb_png_b64"],
                "heatmap_png_b64": analysis["heatmap_png_b64"],
            },
            "fit_score": chosen_score,
            "top_alternatives": scored[:5],
            "plan": plan,
            "adjacency_graph": adj,
            "quality_report": report,
            "retry": retry_info,
            "process_log": self.logger.events,
            "process_log_text": log_text,
            "output_zip_bytes_len": len(self.zip_bytes),
            "composed_panels": list(self.composed_images.keys()),
        })
        return self.result
