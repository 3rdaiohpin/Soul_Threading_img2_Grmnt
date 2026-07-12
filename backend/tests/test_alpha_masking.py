"""Test suite for alpha masking, piece ordering, and validation functions.

Tests the new features from the gpt-edits/masking branch:
  - Alpha mask handling (transparent backgrounds)
  - Cargo loose shorts piece normalization & reordering
  - Validation helpers for transparency and clipped PNG outputs
"""
from __future__ import annotations
import io
import tempfile
from pathlib import Path
from typing import Dict, Any

import pytest
from PIL import Image

from aop.validator import validate_alpha_clipped_png, validate_composed_images
from aop.database_loader import (
    normalize_key,
    reorder_piece_list,
    reorder_piece_dict,
    STANDARD_CARGO_LOOSE_SHORTS_ORDER,
)


# ============================================================================
# Unit Tests: normalize_key
# ============================================================================
class TestNormalizeKey:
    """Test the normalize_key function for piece ID standardization."""

    def test_lowercase_conversion(self):
        """Key is converted to lowercase."""
        assert normalize_key("CargoLooseSHORTS") == "cargolooseshorts"

    def test_hyphen_to_underscore(self):
        """Hyphens are replaced with underscores."""
        assert normalize_key("cargo-loose-shorts") == "cargo_loose_shorts"

    def test_space_to_underscore(self):
        """Spaces are replaced with underscores."""
        assert normalize_key("cargo loose shorts") == "cargo_loose_shorts"

    def test_double_underscore_shape_normalization(self):
        """Double underscores before shape are collapsed to single."""
        result = normalize_key("cargo_loose_shorts_design_template__left_leg__shape_01")
        assert "_shape_" in result
        assert "__shape_" not in result

    def test_mixed_normalizations(self):
        """All normalizations applied together."""
        result = normalize_key("Cargo-Loose-Shorts__Left Leg__Shape_01")
        assert result == "cargo_loose_shorts_left_leg_shape_01"

    def test_strip_underscores(self):
        """Leading/trailing underscores are stripped."""
        assert normalize_key("_cargo_loose_shorts_") == "cargo_loose_shorts"


# ============================================================================
# Integration Tests: reorder_piece_list
# ============================================================================
class TestReorderPieceList:
    """Test reordering piece lists to standard cargo shorts order."""

    def _make_piece(self, piece_id: str) -> Dict[str, Any]:
        """Helper to create a minimal piece dict."""
        return {
            "piece_id": piece_id,
            "label": piece_id.replace("_", " "),
            "canvas_px": {"width": 900, "height": 900},
        }

    def test_reorder_correct_order_already(self):
        """If pieces are already in order, they stay in order."""
        pieces = [self._make_piece(pid) for pid in STANDARD_CARGO_LOOSE_SHORTS_ORDER]
        result = reorder_piece_list(pieces)
        assert len(result) == len(pieces)
        for i, piece in enumerate(result):
            assert piece["piece_id"] == STANDARD_CARGO_LOOSE_SHORTS_ORDER[i]

    def test_reorder_reverse_order(self):
        """Pieces in reverse order are reordered correctly."""
        pieces = [self._make_piece(pid) for pid in reversed(STANDARD_CARGO_LOOSE_SHORTS_ORDER)]
        result = reorder_piece_list(pieces)
        for i, piece in enumerate(result):
            assert piece["piece_id"] == STANDARD_CARGO_LOOSE_SHORTS_ORDER[i]

    def test_reorder_missing_pieces_raises(self):
        """Missing pieces cause ValueError."""
        pieces = [self._make_piece(STANDARD_CARGO_LOOSE_SHORTS_ORDER[0])]
        with pytest.raises(ValueError, match="Missing composer pieces"):
            reorder_piece_list(pieces)

    def test_reorder_sets_composer_key(self):
        """Reordering sets piece_id and composer_key to standard."""
        pieces = [
            self._make_piece("custom_id_1"),
            self._make_piece("custom_id_2"),
        ]
        # Add all required pieces with custom IDs
        for standard_id in STANDARD_CARGO_LOOSE_SHORTS_ORDER[2:]:
            pieces.append(self._make_piece("custom_" + standard_id))

        result = reorder_piece_list(pieces)
        for piece, standard_id in zip(result, STANDARD_CARGO_LOOSE_SHORTS_ORDER):
            assert piece["piece_id"] == standard_id
            assert piece["composer_key"] == standard_id


# ============================================================================
# Integration Tests: reorder_piece_dict
# ============================================================================
class TestReorderPieceDict:
    """Test reordering piece dicts with normalized key matching."""

    def _make_piece(self, piece_id: str) -> Dict[str, Any]:
        """Helper to create a minimal piece dict."""
        return {
            "piece_id": piece_id,
            "label": piece_id.replace("_", " "),
            "canvas_px": {"width": 900, "height": 900},
        }

    def test_reorder_dict_with_normalized_keys(self):
        """Piece dicts with normalized keys are matched and reordered."""
        pieces_dict = {}
        for standard_id in STANDARD_CARGO_LOOSE_SHORTS_ORDER:
            # Store with a variant key (uppercase, hyphens, etc.)
            variant_key = standard_id.upper().replace("_", "-")
            pieces_dict[variant_key] = self._make_piece(standard_id)

        result = reorder_piece_dict(pieces_dict)
        assert len(result) == len(STANDARD_CARGO_LOOSE_SHORTS_ORDER)
        for i, (key, piece) in enumerate(result.items()):
            assert key == STANDARD_CARGO_LOOSE_SHORTS_ORDER[i]
            assert piece["piece_id"] == STANDARD_CARGO_LOOSE_SHORTS_ORDER[i]

    def test_reorder_dict_missing_pieces_raises(self):
        """Missing pieces in dict cause ValueError."""
        pieces_dict = {"some_piece": self._make_piece("some_piece")}
        with pytest.raises(ValueError, match="Missing composer pieces"):
            reorder_piece_dict(pieces_dict)

    def test_reorder_dict_extra_pieces_warning(self):
        """Extra pieces are allowed but logged."""
        pieces_dict = {}
        for standard_id in STANDARD_CARGO_LOOSE_SHORTS_ORDER:
            pieces_dict[standard_id] = self._make_piece(standard_id)
        # Add an extra piece
        pieces_dict["extra_piece"] = self._make_piece("extra_piece")

        result = reorder_piece_dict(pieces_dict)
        # Extra piece should not be in ordered result
        assert "extra_piece" not in result
        assert len(result) == len(STANDARD_CARGO_LOOSE_SHORTS_ORDER)


# ============================================================================
# Alpha Channel Validation Tests
# ============================================================================
class TestAlphaClippedPngValidation:
    """Test validate_alpha_clipped_png function."""

    def _make_png_with_alpha(
        self, width: int = 100, height: int = 100, opaque_ratio: float = 0.5
    ) -> bytes:
        """Create a PNG with specified opaque pixel ratio."""
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))  # transparent bg
        pixels = img.load()
        opaque_count = int(width * height * opaque_ratio)
        for i in range(opaque_count):
            x = i % width
            y = i // width
            pixels[x, y] = (255, 0, 0, 255)  # red opaque
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    def test_valid_clipped_png(self, tmp_path):
        """PNG with opaque and transparent pixels passes."""
        img_bytes = self._make_png_with_alpha(opaque_ratio=0.5)
        img_path = tmp_path / "test.png"
        img_path.write_bytes(img_bytes)
        # Should not raise
        validate_alpha_clipped_png(str(img_path))

    def test_all_transparent_png_fails(self, tmp_path):
        """PNG with no opaque pixels fails."""
        img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        img_path = tmp_path / "transparent.png"
        img.save(img_path, "PNG")
        with pytest.raises(ValueError, match="no visible pixels"):
            validate_alpha_clipped_png(str(img_path))

    def test_fully_opaque_rectangular_png_fails(self, tmp_path):
        """PNG that is fully rectangular (no transparency) fails."""
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))  # all opaque red
        img_path = tmp_path / "rectangular.png"
        img.save(img_path, "PNG")
        with pytest.raises(ValueError, match="rectangular.*mask not applied"):
            validate_alpha_clipped_png(str(img_path))

    def test_sparse_opaque_pixels(self, tmp_path):
        """PNG with few opaque pixels passes."""
        img_bytes = self._make_png_with_alpha(opaque_ratio=0.01)
        img_path = tmp_path / "sparse.png"
        img_path.write_bytes(img_bytes)
        validate_alpha_clipped_png(str(img_path))


# ============================================================================
# Composed Images Validation Tests
# ============================================================================
class TestComposedImagesValidation:
    """Test validate_composed_images function."""

    def _make_image_with_alpha(
        self, opaque_ratio: float = 0.5
    ) -> Image.Image:
        """Create an in-memory RGBA image."""
        img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        pixels = img.load()
        opaque_count = int(10000 * opaque_ratio)
        for i in range(opaque_count):
            x = i % 100
            y = i // 100
            pixels[x, y] = (255, 0, 0, 255)
        return img

    def test_valid_composed_images(self):
        """Valid composed images pass."""
        composed = {
            "front_body": self._make_image_with_alpha(0.5),
            "back_body": self._make_image_with_alpha(0.6),
        }
        # Should not raise
        validate_composed_images(composed)

    def test_all_transparent_image_fails(self):
        """Image with no opaque pixels fails."""
        composed = {
            "front_body": Image.new("RGBA", (100, 100), (0, 0, 0, 0)),
        }
        with pytest.raises(ValueError, match="no visible pixels"):
            validate_composed_images(composed)

    def test_fully_opaque_rectangular_image_fails(self):
        """Image that is fully opaque fails."""
        composed = {
            "front_body": Image.new("RGBA", (100, 100), (255, 0, 0, 255)),
        }
        with pytest.raises(ValueError, match="rectangular.*no transparency"):
            validate_composed_images(composed)

    def test_mixed_valid_invalid_images(self):
        """One valid and one invalid image raises."""
        composed = {
            "front_body": self._make_image_with_alpha(0.5),
            "back_body": Image.new("RGBA", (100, 100), (0, 0, 0, 0)),  # transparent
        }
        with pytest.raises(ValueError, match="no visible pixels"):
            validate_composed_images(composed)


# ============================================================================
# Mask-Based Composition Tests
# ============================================================================
class TestMaskBasedComposition:
    """Test composition with transparent backgrounds and alpha masks."""

    def _make_test_image_with_visible_content(self) -> Image.Image:
        """Create a test image with recognizable features."""
        img = Image.new("RGB", (200, 200), (200, 200, 200))
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        d.ellipse((50, 50, 150, 150), fill=(255, 0, 0))  # red circle
        return img.convert("RGBA")

    def _make_circular_mask(self) -> Image.Image:
        """Create a circular alpha mask."""
        mask = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        from PIL import ImageDraw
        d = ImageDraw.Draw(mask)
        d.ellipse((50, 50, 150, 150), fill=(255, 255, 255, 255))
        return mask.convert("RGBA")

    def test_transparent_bg_paste_with_alpha(self):
        """Pasting with alpha mask onto transparent background."""
        art = self._make_test_image_with_visible_content()
        mask = self._make_circular_mask()

        # Compose on transparent background
        canvas = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        alpha = mask.getchannel("A")
        canvas.paste(art, (0, 0), alpha)

        # Verify result has both opaque and transparent pixels
        pixels = list(canvas.getdata())
        opaque = sum(1 for p in pixels if p[3] > 200)
        transparent = sum(1 for p in pixels if p[3] < 50)
        assert opaque > 100, "Should have opaque pixels"
        assert transparent > 100, "Should have transparent pixels"

    def test_mask_alpha_extraction(self):
        """Alpha channel is correctly extracted from mask."""
        mask = self._make_circular_mask()
        alpha = mask.getchannel("A")
        assert alpha.mode == "L"
        pixels = list(alpha.getdata())
        opaque = sum(1 for p in pixels if p > 200)
        transparent = sum(1 for p in pixels if p < 50)
        assert opaque > 100
        assert transparent > 100


# ============================================================================
# Integration: Alpha Mask + Cargo Shorts Ordering
# ============================================================================
class TestAlphaMaskCargoIntegration:
    """Integration tests combining alpha masking and cargo shorts ordering."""

    def _make_cargo_piece(self, standard_id: str) -> Dict[str, Any]:
        """Create a cargo piece with canvas_px."""
        return {
            "piece_id": standard_id,
            "label": standard_id.replace("_", " "),
            "canvas_px": {"width": 900, "height": 900},
            "piece_px": {"width": 200, "height": 300},
        }

    def test_ordered_cargo_pieces_with_alpha_masks(self):
        """Cargo pieces reordered and can be composed with alpha masks."""
        # Create pieces in random order
        import random
        piece_ids = list(STANDARD_CARGO_LOOSE_SHORTS_ORDER)
        random.shuffle(piece_ids)
        pieces = [self._make_cargo_piece(pid) for pid in piece_ids]

        # Reorder
        ordered = reorder_piece_list(pieces)

        # Verify order
        for i, piece in enumerate(ordered):
            assert piece["piece_id"] == STANDARD_CARGO_LOOSE_SHORTS_ORDER[i]

        # Simulate composition with transparent canvases
        from PIL import Image as _Image
        composed = {}
        for piece in ordered:
            # Each piece gets a small transparent canvas with opaque center
            canvas = _Image.new("RGBA", (200, 300), (0, 0, 0, 0))
            pixels = canvas.load()
            for y in range(100, 200):
                for x in range(50, 150):
                    pixels[x, y] = (100, 150, 200, 255)
            composed[piece["piece_id"]] = canvas

        # Validate all composed images
        validate_composed_images(composed)
        assert len(composed) == len(STANDARD_CARGO_LOOSE_SHORTS_ORDER)
