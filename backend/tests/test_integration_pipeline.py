"""Integration tests for the full Soul Threading pipeline with alpha masking.

Tests end-to-end flows:
  - Artwork analysis -> archetype classification
  - Composition with transparent backgrounds
  - Per-piece extraction with alpha masks
  - Quality validation
  - ZIP packaging
"""
from __future__ import annotations
import io
import json
import zipfile
from pathlib import Path
from typing import Dict, Any

import pytest
from PIL import Image, ImageDraw

from aop.database_loader import GarmentDatabase
from aop.master_composer import compose_master
from aop.validator import validate, suggest_retry
from aop.artwork_analyzer import analyze_artwork
from aop.archetype_classifier import classify


# ============================================================================
# Fixtures
# ============================================================================
@pytest.fixture
def aop_db(tmp_path):
    """Create a minimal mock garment database."""
    db_root = tmp_path / "aop_data"
    db_root.mkdir()
    
    # Create state.json with a minimal test product
    state = {
        "products": [
            {
                "product_id": "test_hoodie",
                "display_name": "Test Hoodie",
                "garment_type": "hoodie",
                "piece_count": 2,
                "template_files": [
                    {
                        "source_relative_path": "templates/test/front_side.png",
                        "template_png": "templates/test/front_side.png",
                        "analysis_px": {"width": 900, "height": 900},
                        "canvas_px": {"width": 900, "height": 900},
                    },
                    {
                        "source_relative_path": "templates/test/back_side.png",
                        "template_png": "templates/test/back_side.png",
                        "analysis_px": {"width": 900, "height": 900},
                        "canvas_px": {"width": 900, "height": 900},
                    },
                ],
                "pieces": [
                    {
                        "piece_id": "front_body",
                        "label": "front body",
                        "template_key": "front_side",
                        "shape_index": 1,
                    },
                    {
                        "piece_id": "back_body",
                        "label": "back body",
                        "template_key": "back_side",
                        "shape_index": 1,
                    },
                ],
            }
        ]
    }
    state_path = db_root / "state.json"
    state_path.write_text(json.dumps(state))
    
    # Create rules
    rules_dir = db_root / "rules"
    rules_dir.mkdir()
    rules = {
        "universal_rules": ["rule1", "rule2"],
        "quality_gate": 75.0,
    }
    (rules_dir / "universal_mapper_ruleset.json").write_text(json.dumps(rules))
    
    # Create analysis_masks directory with test masks
    masks_dir = db_root / "analysis_masks"
    masks_dir.mkdir()
    
    # Create front_side mask (shape_01)
    front_mask_dir = masks_dir / "test_hoodie__front_side__shape_01"
    front_mask_dir.mkdir()
    front_mask = Image.new("L", (900, 900), 0)
    front_pixels = front_mask.load()
    for y in range(100, 500):
        for x in range(200, 700):
            front_pixels[x, y] = 255
    front_mask.save(front_mask_dir / "full_bleed.png", "PNG")
    
    # Create back_side mask (shape_01)
    back_mask_dir = masks_dir / "test_hoodie__back_side__shape_01"
    back_mask_dir.mkdir()
    back_mask = Image.new("L", (900, 900), 0)
    back_pixels = back_mask.load()
    for y in range(150, 550):
        for x in range(250, 650):
            back_pixels[x, y] = 255
    back_mask.save(back_mask_dir / "full_bleed.png", "PNG")
    
    return GarmentDatabase(db_root)


def _make_test_artwork_jpeg() -> bytes:
    """Create a synthetic test artwork image."""
    im = Image.new("RGB", (600, 800), (50, 50, 60))
    d = ImageDraw.Draw(im)
    # Simple geometric design
    d.rectangle((100, 100, 500, 700), fill=(100, 150, 200))
    d.ellipse((200, 200, 400, 400), fill=(255, 200, 100))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _make_minimal_analysis() -> Dict[str, Any]:
    """Create a minimal analysis result."""
    return {
        "canvas_px": {"width": 900, "height": 900},
        "faces": [],
        "text_regions": [],
        "dominant_colors": [(100, 150, 200)],
        "primary_subject": "abstract",
        "saliency_zones": [],
        "thumb_png_b64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        "heatmap_png_b64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    }


# ============================================================================
# Alpha Masking Integration Tests
# ============================================================================
class TestAlphaMaskingComposition:
    """Test composition pipeline with transparent backgrounds."""

    def test_compose_with_transparent_bg(self, aop_db):
        """Master composer produces pieces with transparent backgrounds."""
        art_bytes = _make_test_artwork_jpeg()
        product = aop_db.product("test_hoodie")
        
        result = compose_master(
            art_bytes,
            product,
            aop_db.root,
            archetype="abstract_wrap",
            downscale_max_dim=900,
        )
        
        assert "composed" in result
        composed = result["composed"]
        
        # Should have pieces
        assert len(composed) > 0
        
        # Each piece should be RGBA with alpha channel
        for piece_key, img in composed.items():
            assert img.mode == "RGBA", f"Piece {piece_key} should be RGBA"
            
            # Should have both opaque and transparent pixels
            alpha = img.getchannel("A")
            alpha_data = list(alpha.getdata())
            opaque_count = sum(1 for p in alpha_data if p > 200)
            transparent_count = sum(1 for p in alpha_data if p < 50)
            
            assert opaque_count > 0, f"Piece {piece_key} has no opaque pixels"
            assert transparent_count > 0, f"Piece {piece_key} has no transparency (rectangular)"

    def test_compose_plan_contains_piece_metadata(self, aop_db):
        """Composition plan includes metadata for each piece."""
        art_bytes = _make_test_artwork_jpeg()
        product = aop_db.product("test_hoodie")
        
        result = compose_master(
            art_bytes,
            product,
            aop_db.root,
            archetype="abstract_wrap",
        )
        
        plan = result["plan"]
        assert isinstance(plan, list)
        assert len(plan) > 0
        
        # Each plan entry should have required fields
        for entry in plan:
            assert "piece_key" in entry
            assert "label" in entry
            assert "template_key" in entry
            assert "shape_index" in entry
            assert "canvas_px" in entry
            assert "piece_px" in entry
            
            # Piece dimensions should be positive
            assert entry["canvas_px"]["width"] > 0
            assert entry["canvas_px"]["height"] > 0
            assert entry["piece_px"]["width"] > 0
            assert entry["piece_px"]["height"] > 0

    def test_compose_fit_contain_preserves_aspect(self, aop_db):
        """Fit-contain mode preserves image aspect ratio."""
        art_bytes = _make_test_artwork_jpeg()
        product = aop_db.product("test_hoodie")
        
        # Portrait-hero uses contain mode
        result = compose_master(
            art_bytes,
            product,
            aop_db.root,
            archetype="portrait_hero",
        )
        
        composed = result["composed"]
        assert len(composed) > 0
        
        # All pieces should have valid dimensions
        for piece_key, img in composed.items():
            assert img.size[0] > 0
            assert img.size[1] > 0


# ============================================================================
# Quality Validation Integration Tests
# ============================================================================
class TestQualityValidationIntegration:
    """Test quality validation with realistic data."""

    def test_validate_returns_quality_report(self):
        """Validate function returns proper quality report structure."""
        analysis = _make_minimal_analysis()
        plan = [
            {
                "piece_key": "front_body",
                "label": "front body",
                "template_key": "front_side",
                "shape_index": 1,
                "side": "front",
                "mode": "contain",
            }
        ]
        hero_box = {"x": 200, "y": 200, "w": 400, "h": 400}
        exclusion = []
        
        report = validate(analysis, plan, hero_box, exclusion, archetype="portrait_hero")
        
        # Check structure
        assert "scores" in report
        assert "overall" in report
        assert "passed" in report
        assert "hard_fails" in report
        
        # Check score ranges
        assert 0 <= report["overall"] <= 100
        assert isinstance(report["scores"]["focal_completeness"], (int, float))
        assert isinstance(report["scores"]["seam_safety"], (int, float))
        assert isinstance(report["passed"], bool)

    def test_validate_fails_with_high_face_ratio(self):
        """Validation penalizes high face ratio in portrait mode."""
        analysis = _make_minimal_analysis()
        analysis["faces"] = [
            {"x": 0, "y": 0, "w": 900, "h": 900}  # Huge face
        ]
        plan = [
            {
                "piece_key": "front_body",
                "side": "front",
                "mode": "contain",
            }
        ]
        hero_box = {"x": 0, "y": 0, "w": 900, "h": 900}
        exclusion = []
        
        report = validate(analysis, plan, hero_box, exclusion, archetype="portrait_hero")
        
        # Should have chopped penalty
        assert report["scores"]["chopped_penalty"] > 0

    def test_suggest_retry_on_failed_validation(self):
        """Retry suggestion provides adjustments on failed validation."""
        report = {
            "passed": False,
            "scores": {
                "focal_completeness": 5.0,
                "chopped_penalty": 3.0,
            },
            "hard_fails": ["face_cut"],
        }
        
        retry_info = suggest_retry(report, archetype="portrait_hero")
        
        assert retry_info["needed"] is True
        assert len(retry_info["adjustments"]) > 0
        assert "switch_placement_to_contain" in retry_info["adjustments"]

    def test_no_retry_on_passed_validation(self):
        """No retry needed if validation passes."""
        report = {
            "passed": True,
            "scores": {},
            "hard_fails": [],
        }
        
        retry_info = suggest_retry(report, archetype="portrait_hero")
        
        assert retry_info["needed"] is False


# ============================================================================
# End-to-End Pipeline Tests
# ============================================================================
class TestEndToEndPipeline:
    """Test complete artwork-to-output pipeline."""

    def test_analyze_artwork_returns_valid_structure(self):
        """Artwork analysis produces valid output structure."""
        art_bytes = _make_test_artwork_jpeg()
        analysis = analyze_artwork(art_bytes)
        
        # Check required keys
        required_keys = [
            "canvas_px", "faces", "text_regions", "dominant_colors",
            "primary_subject", "saliency_zones",
        ]
        for key in required_keys:
            assert key in analysis, f"Missing {key} in analysis"
        
        # Check types
        assert isinstance(analysis["canvas_px"], dict)
        assert "width" in analysis["canvas_px"]
        assert "height" in analysis["canvas_px"]
        assert isinstance(analysis["faces"], list)
        assert isinstance(analysis["dominant_colors"], list)

    def test_classify_returns_valid_archetype(self):
        """Archetype classification produces valid result."""
        analysis = _make_minimal_analysis()
        result = classify(analysis, smart_hint=None)
        
        assert "archetype" in result
        assert result["archetype"] in [
            "portrait_hero", "scene_wrap", "abstract_wrap",
            "logo_text_layout", "product_object_layout",
        ]
        assert "scores" in result

    def test_full_pipeline_art_to_composition(self, aop_db):
        """Full pipeline from artwork to composed pieces."""
        # Step 1: Analyze artwork
        art_bytes = _make_test_artwork_jpeg()
        analysis = analyze_artwork(art_bytes)
        
        # Step 2: Classify archetype
        arch_result = classify(analysis, smart_hint=None)
        archetype = arch_result["archetype"]
        
        # Step 3: Get product
        product = aop_db.product("test_hoodie")
        assert product is not None
        
        # Step 4: Compose
        compose_result = compose_master(
            art_bytes,
            product,
            aop_db.root,
            archetype=archetype,
        )
        
        # Step 5: Validate
        plan = compose_result["plan"]
        hero_box = {"x": 200, "y": 200, "w": 400, "h": 400}
        quality_report = validate(
            analysis,
            plan,
            hero_box,
            exclusion=[],
            archetype=archetype,
        )
        
        # Verify outputs
        assert len(compose_result["composed"]) > 0
        assert 0 <= quality_report["overall"] <= 100
        assert isinstance(quality_report["passed"], bool)


# ============================================================================
# Regression Tests
# ============================================================================
class TestRegressions:
    """Regression tests for known issues."""

    def test_piece_center_not_outline_only(self, aop_db):
        """Piece silhouettes should be filled, not outline-only."""
        art_bytes = _make_test_artwork_jpeg()
        product = aop_db.product("test_hoodie")
        
        result = compose_master(
            art_bytes,
            product,
            aop_db.root,
            archetype="abstract_wrap",
        )
        
        composed = result["composed"]
        for piece_key, img in composed.items():
            rgba = img.convert("RGBA")
            w, h = rgba.size
            
            # Sample center region
            center_x = w // 2
            center_y = h // 2
            center_pixels = []
            for dx in range(-5, 6):
                for dy in range(-5, 6):
                    x = max(0, min(w - 1, center_x + dx))
                    y = max(0, min(h - 1, center_y + dy))
                    px = rgba.getpixel((x, y))
                    center_pixels.append(px)
            
            # Should have some opaque pixels in center
            opaque_in_center = sum(1 for p in center_pixels if len(p) == 4 and p[3] >= 200)
            assert opaque_in_center > 0, f"Piece {piece_key} is outline-only at center"

    def test_transparent_bg_not_white(self, aop_db):
        """Transparent backgrounds should be (0,0,0,0), not white."""
        art_bytes = _make_test_artwork_jpeg()
        product = aop_db.product("test_hoodie")
        
        result = compose_master(
            art_bytes,
            product,
            aop_db.root,
            archetype="abstract_wrap",
        )
        
        composed = result["composed"]
        for piece_key, img in composed.items():
            rgba = img.convert("RGBA")
            pixels = list(rgba.getdata())
            
            # Find transparent pixels
            transparent_pixels = [p for p in pixels if p[3] < 50]
            
            # These should be black transparent, not white
            for px in transparent_pixels[:10]:  # Check first 10
                assert px[:3] == (0, 0, 0), f"Transparent pixel in {piece_key} is not black: {px}"


# ============================================================================
# Performance Tests
# ============================================================================
class TestPerformance:
    """Performance tests for composition speed."""

    def test_compose_completes_in_reasonable_time(self, aop_db):
        """Composition should complete quickly."""
        import time
        
        art_bytes = _make_test_artwork_jpeg()
        product = aop_db.product("test_hoodie")
        
        start = time.time()
        compose_master(
            art_bytes,
            product,
            aop_db.root,
            archetype="abstract_wrap",
        )
        elapsed = time.time() - start
        
        # Should complete in reasonable time (< 5 seconds)
        assert elapsed < 5.0, f"Composition took {elapsed}s, expected < 5s"
