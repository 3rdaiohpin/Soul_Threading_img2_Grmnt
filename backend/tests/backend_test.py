"""Backend tests for Soul Threading Smart AI IMG2Garment Mapper.

Covers health, model status, rules, garment catalog, artwork upload/analyze,
map (job) end-to-end for a portrait-style and a scene-style image, panels
retrieval, ZIP download & structure. Uses the public REACT_APP_BACKEND_URL.
"""
from __future__ import annotations
import io
import json
import os
import zipfile
from pathlib import Path

import pytest
import requests
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Base URL & session
# ---------------------------------------------------------------------------
FRONTEND_ENV = Path("/app/frontend/.env")
BASE_URL = None
for line in FRONTEND_ENV.read_text().splitlines():
    if line.startswith("REACT_APP_BACKEND_URL="):
        BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
        break
assert BASE_URL, "REACT_APP_BACKEND_URL not found in /app/frontend/.env"

TIMEOUT_SHORT = 30
TIMEOUT_LONG = 180  # map job may take 10-30s


@pytest.fixture(scope="session")
def session() -> requests.Session:
    s = requests.Session()
    return s


# ---------------------------------------------------------------------------
# Test images: build synthetic portrait-like and scene-like JPEGs so we don't
# depend on network fetches. They are sufficient to exercise the pipeline.
# ---------------------------------------------------------------------------
def _make_portrait_jpeg() -> bytes:
    """Portrait-hero style image: single central figure/face-like ellipse."""
    im = Image.new("RGB", (800, 1000), (30, 30, 40))
    d = ImageDraw.Draw(im)
    # face
    d.ellipse((300, 200, 500, 460), fill=(220, 180, 150))
    # eyes
    d.ellipse((345, 300, 385, 330), fill=(20, 20, 20))
    d.ellipse((415, 300, 455, 330), fill=(20, 20, 20))
    # mouth
    d.rectangle((360, 400, 440, 420), fill=(160, 40, 40))
    # torso
    d.rectangle((250, 460, 550, 900), fill=(180, 60, 60))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _make_scene_jpeg() -> bytes:
    """Scene-wrap style image: horizontally varied landscape."""
    im = Image.new("RGB", (1200, 800), (135, 206, 235))
    d = ImageDraw.Draw(im)
    # sky gradient bands
    for y in range(0, 400, 20):
        c = 200 - y // 4
        d.rectangle((0, y, 1200, y + 20), fill=(c, c + 20, 235))
    # ground
    d.rectangle((0, 400, 1200, 800), fill=(60, 120, 50))
    # mountains
    d.polygon([(0, 400), (200, 200), (400, 400)], fill=(90, 90, 110))
    d.polygon([(300, 400), (600, 150), (900, 400)], fill=(70, 70, 90))
    d.polygon([(800, 400), (1050, 220), (1200, 400)], fill=(80, 80, 100))
    # trees
    for x in (150, 350, 750, 1000):
        d.ellipse((x, 500, x + 80, 620), fill=(30, 90, 40))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Basic connectivity endpoints
# ---------------------------------------------------------------------------
class TestBasicEndpoints:
    def test_health(self, session):
        r = session.get(f"{BASE_URL}/api/health", timeout=TIMEOUT_SHORT)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["db_products"] == 19
        assert d["mongo"] == "up"

    def test_model_status(self, session):
        r = session.get(f"{BASE_URL}/api/model-status", timeout=TIMEOUT_SHORT)
        assert r.status_code == 200
        d = r.json()
        assert "active_backend" in d
        detectors = d.get("detectors") or d.get("available_detectors") or []
        # detectors can be list of dicts or strings
        text_dump = json.dumps(d).lower()
        assert len(detectors) > 0 or "opencv" in text_dump
        assert "opencv" in text_dump
        assert "emergent" in text_dump

    def test_rules(self, session):
        r = session.get(f"{BASE_URL}/api/rules", timeout=TIMEOUT_SHORT)
        assert r.status_code == 200
        d = r.json()
        assert "universal_rules" in d
        assert "quality_gate" in d


# ---------------------------------------------------------------------------
# Garment catalog
# ---------------------------------------------------------------------------
class TestGarments:
    def test_list_19(self, session):
        r = session.get(f"{BASE_URL}/api/garments", timeout=TIMEOUT_SHORT)
        assert r.status_code == 200
        d = r.json()
        assert d["count"] == 19
        assert len(d["items"]) == 19
        item = d["items"][0]
        for key in [
            "product_id", "display_name", "garment_type", "piece_count",
            "has_front", "has_back", "has_pocket", "has_hood", "has_sleeves",
        ]:
            assert key in item, f"missing key {key} in garment item"
        # boolean flags
        for k in ("has_front", "has_back", "has_pocket", "has_hood", "has_sleeves"):
            assert isinstance(item[k], bool)

    def test_get_hoodie_detail(self, session):
        pid = "oversized_hoodie_design_template"
        r = session.get(f"{BASE_URL}/api/garments/{pid}", timeout=TIMEOUT_SHORT)
        assert r.status_code == 200
        d = r.json()
        assert d["product_id"] == pid
        assert "template_files" in d and isinstance(d["template_files"], list)
        assert len(d["template_files"]) > 0

    def test_get_template_png(self, session):
        pid = "oversized_hoodie_design_template"
        r = session.get(f"{BASE_URL}/api/garments/{pid}", timeout=TIMEOUT_SHORT)
        assert r.status_code == 200
        tfiles = r.json()["template_files"]
        fname = Path(tfiles[0]["template_png"]).name
        r2 = session.get(
            f"{BASE_URL}/api/garments/{pid}/template/{fname}", timeout=TIMEOUT_SHORT
        )
        assert r2.status_code == 200
        assert r2.headers.get("content-type", "").startswith("image/png")
        assert r2.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_get_unknown_product(self, session):
        r = session.get(f"{BASE_URL}/api/garments/does_not_exist", timeout=TIMEOUT_SHORT)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Upload artwork
# ---------------------------------------------------------------------------
class TestUpload:
    def test_upload_valid_jpeg(self, session):
        data = _make_portrait_jpeg()
        files = {"file": ("portrait.jpg", data, "image/jpeg")}
        r = session.post(
            f"{BASE_URL}/api/upload-artwork", files=files, timeout=TIMEOUT_SHORT
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert "artwork_id" in d and isinstance(d["artwork_id"], str)
        assert d["bytes"] == len(data)

    def test_upload_empty_rejected(self, session):
        files = {"file": ("empty.jpg", b"", "image/jpeg")}
        r = session.post(
            f"{BASE_URL}/api/upload-artwork", files=files, timeout=TIMEOUT_SHORT
        )
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Shared upload fixtures (session-scoped): upload once, reuse.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def portrait_art_id(session):
    data = _make_portrait_jpeg()
    r = session.post(
        f"{BASE_URL}/api/upload-artwork",
        files={"file": ("portrait.jpg", data, "image/jpeg")},
        timeout=TIMEOUT_SHORT,
    )
    assert r.status_code == 200, r.text
    return r.json()["artwork_id"]


@pytest.fixture(scope="session")
def scene_art_id(session):
    data = _make_scene_jpeg()
    r = session.post(
        f"{BASE_URL}/api/upload-artwork",
        files={"file": ("scene.jpg", data, "image/jpeg")},
        timeout=TIMEOUT_SHORT,
    )
    assert r.status_code == 200, r.text
    return r.json()["artwork_id"]


# ---------------------------------------------------------------------------
# Analyze
# ---------------------------------------------------------------------------
ALLOWED_ARCHETYPES = {
    "portrait_hero", "scene_wrap", "abstract_wrap", "logo_text_layout",
    "product_object_layout",
}


class TestAnalyze:
    def test_analyze_no_smart_hint(self, session, portrait_art_id):
        r = session.post(
            f"{BASE_URL}/api/analyze",
            data={"artwork_id": portrait_art_id, "use_smart_hint": "false"},
            timeout=TIMEOUT_LONG,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        analysis = d["analysis"]
        for k in [
            "canvas_px", "faces", "text_regions", "dominant_colors",
            "primary_subject", "saliency_zones", "thumb_png_b64", "heatmap_png_b64",
        ]:
            assert k in analysis, f"analysis missing {k}"
        assert isinstance(analysis["faces"], list)
        assert isinstance(analysis["text_regions"], list)
        assert isinstance(analysis["dominant_colors"], list) and len(analysis["dominant_colors"]) > 0
        arch = d["archetype"]
        assert arch["archetype"] in ALLOWED_ARCHETYPES
        assert "scores" in arch
        rec = d["recommended_garments"]
        assert isinstance(rec, list) and len(rec) > 0
        assert "composite_score" in rec[0]

    def test_analyze_smart_hint_graceful(self, session, portrait_art_id):
        """Even with exhausted LLM budget, must still return 200."""
        r = session.post(
            f"{BASE_URL}/api/analyze",
            data={"artwork_id": portrait_art_id, "use_smart_hint": "true"},
            timeout=TIMEOUT_LONG,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # smart_hint may contain error but pipeline should still yield archetype
        assert d["archetype"]["archetype"] in ALLOWED_ARCHETYPES

    def test_analyze_unknown_artwork(self, session):
        r = session.post(
            f"{BASE_URL}/api/analyze",
            data={"artwork_id": "nonexistent_id_xyz", "use_smart_hint": "false"},
            timeout=TIMEOUT_SHORT,
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Map (end-to-end)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def hoodie_map_result(session, portrait_art_id):
    r = session.post(
        f"{BASE_URL}/api/map",
        json={
            "artwork_id": portrait_art_id,
            "product_id": "oversized_hoodie_design_template",
            "use_smart_hint": False,
        },
        timeout=TIMEOUT_LONG,
    )
    assert r.status_code == 200, r.text
    return r.json()


class TestMap:
    def test_map_hoodie_success(self, hoodie_map_result):
        d = hoodie_map_result
        assert "job_id" in d
        panels = d["composed_panels"]
        # composed_panels may be a dict (keyed by panel) or a list of panel keys
        keys = list(panels.keys()) if isinstance(panels, dict) else list(panels)
        assert "master_front" in keys
        assert "master_back" in keys
        assert "sleeves" in keys or any(k.startswith("sleeve") for k in keys)
        assert "hood" in keys or any(k.startswith("hood") for k in keys)
        assert any(k.startswith("pocket") for k in keys), f"no pocket_* key in {keys}"
        qr = d["quality_report"]
        assert "overall" in qr and 0 <= qr["overall"] <= 100
        assert "passed" in qr
        assert "retry" in d or "retry_info" in d
        assert "process_log" in d and isinstance(d["process_log"], list)
        assert d.get("output_zip_bytes_len", 0) > 0

    def test_map_unknown_product(self, session, portrait_art_id):
        r = session.post(
            f"{BASE_URL}/api/map",
            json={
                "artwork_id": portrait_art_id,
                "product_id": "no_such_product",
                "use_smart_hint": False,
            },
            timeout=TIMEOUT_SHORT,
        )
        assert r.status_code == 404

    def test_map_unknown_artwork(self, session):
        r = session.post(
            f"{BASE_URL}/api/map",
            json={
                "artwork_id": "no_such_artwork",
                "product_id": "oversized_hoodie_design_template",
                "use_smart_hint": False,
            },
            timeout=TIMEOUT_SHORT,
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Jobs / panels / download
# ---------------------------------------------------------------------------
class TestJobs:
    def test_job_status(self, session, hoodie_map_result):
        job_id = hoodie_map_result["job_id"]
        r = session.get(f"{BASE_URL}/api/jobs/{job_id}", timeout=TIMEOUT_SHORT)
        assert r.status_code == 200
        d = r.json()
        assert d["job_id"] == job_id
        assert "composed_panels" in d
        assert "quality_report" in d

    def test_panel_composed(self, session, hoodie_map_result):
        job_id = hoodie_map_result["job_id"]
        r = session.get(
            f"{BASE_URL}/api/jobs/{job_id}/panel/master_front",
            params={"kind": "composed"},
            timeout=TIMEOUT_SHORT,
        )
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/png")
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_panel_guides(self, session, hoodie_map_result):
        job_id = hoodie_map_result["job_id"]
        r = session.get(
            f"{BASE_URL}/api/jobs/{job_id}/panel/master_front",
            params={"kind": "guides"},
            timeout=TIMEOUT_SHORT,
        )
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/png")

    def test_download_zip_structure(self, session, hoodie_map_result):
        job_id = hoodie_map_result["job_id"]
        r = session.get(f"{BASE_URL}/api/jobs/{job_id}/download", timeout=TIMEOUT_LONG)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/zip")
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        has_print = any(n.startswith("print/") and n.endswith(".png") for n in names)
        has_guides = any(n.startswith("guides/") and n.endswith(".png") for n in names)
        assert has_print, f"no print/*.png in zip: {names[:10]}"
        assert has_guides, f"no guides/*.png in zip: {names[:10]}"
        assert "mockup/contact_sheet.png" in names
        assert "mapping_manifest.json" in names
        assert "quality_report.json" in names
        assert "mapping_process_log.txt" in names

    def test_job_not_found(self, session):
        r = session.get(f"{BASE_URL}/api/jobs/nonexistent_job/", timeout=TIMEOUT_SHORT)
        # trailing slash or not both should 404
        assert r.status_code in (404, 307, 308)


# ---------------------------------------------------------------------------
# Determinism of archetype classification on distinct inputs
# ---------------------------------------------------------------------------
class TestArchetypeDeterminism:
    def test_two_runs_same_result(self, session, portrait_art_id, scene_art_id):
        results = []
        for aid in (portrait_art_id, scene_art_id):
            r = session.post(
                f"{BASE_URL}/api/analyze",
                data={"artwork_id": aid, "use_smart_hint": "false"},
                timeout=TIMEOUT_LONG,
            )
            assert r.status_code == 200
            results.append(r.json()["archetype"]["archetype"])
        # Run portrait again -> should match first portrait classification
        r2 = session.post(
            f"{BASE_URL}/api/analyze",
            data={"artwork_id": portrait_art_id, "use_smart_hint": "false"},
            timeout=TIMEOUT_LONG,
        )
        assert r2.status_code == 200
        assert r2.json()["archetype"]["archetype"] == results[0]

    def test_scene_map_pipeline(self, session, scene_art_id):
        r = session.post(
            f"{BASE_URL}/api/map",
            json={
                "artwork_id": scene_art_id,
                "product_id": "oversized_hoodie_design_template",
                "use_smart_hint": False,
            },
            timeout=TIMEOUT_LONG,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert 0 <= d["quality_report"]["overall"] <= 100
        panels = d["composed_panels"]
        keys = list(panels.keys()) if isinstance(panels, dict) else list(panels)
        assert "master_front" in keys
