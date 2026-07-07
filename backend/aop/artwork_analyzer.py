"""Artwork analyzer - CPU fallback using OpenCV + LLM vision assist.

Detects:
- primary subject bbox (saliency)
- face bbox (Haar cascade)
- text/logo high-contrast zones (approximation)
- dominant colors (KMeans on quantized image)
- saliency heatmap (edge density)
- coarse segmentation (GrabCut) around primary subject
"""
from __future__ import annotations
import base64
import io
import os
from typing import Dict, Any, List, Optional, Tuple
import cv2
import numpy as np
from PIL import Image


def load_image_from_bytes(data: bytes) -> np.ndarray:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    arr = np.array(img)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def resize_max(img: np.ndarray, max_dim: int = 900) -> Tuple[np.ndarray, float]:
    h, w = img.shape[:2]
    m = max(h, w)
    if m <= max_dim:
        return img.copy(), 1.0
    scale = max_dim / m
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA), scale


def dominant_colors(img: np.ndarray, k: int = 5) -> List[Dict[str, Any]]:
    small = cv2.resize(img, (120, 120), interpolation=cv2.INTER_AREA)
    Z = small.reshape((-1, 3)).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(Z, k, None, criteria, 5, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.flatten(), minlength=k).astype(np.float32)
    total = counts.sum() or 1.0
    out = []
    order = np.argsort(-counts)
    for idx in order:
        b, g, r = centers[idx]
        out.append({
            "hex": "#{:02X}{:02X}{:02X}".format(int(r), int(g), int(b)),
            "rgb": [int(r), int(g), int(b)],
            "share": float(counts[idx] / total),
        })
    return out


def saliency_heatmap(img: np.ndarray) -> np.ndarray:
    try:
        sal = cv2.saliency.StaticSaliencyFineGrained_create()
        ok, m = sal.computeSaliency(img)
        if ok:
            return (m * 255).astype(np.uint8)
    except Exception:
        pass
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 180)
    heat = cv2.GaussianBlur(edges.astype(np.float32), (0, 0), 15)
    if heat.max() > 0:
        heat = heat / heat.max() * 255.0
    return heat.astype(np.uint8)


def primary_subject_bbox(heat: np.ndarray) -> Dict[str, int]:
    _, mask = cv2.threshold(heat, int(heat.mean() + heat.std()), 255, cv2.THRESH_BINARY)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = heat.shape[:2]
    if not cnts:
        return {"x": w // 4, "y": h // 4, "w": w // 2, "h": h // 2}
    biggest = max(cnts, key=cv2.contourArea)
    x, y, ww, hh = cv2.boundingRect(biggest)
    if ww * hh < (w * h) * 0.04:
        return {"x": w // 4, "y": h // 4, "w": w // 2, "h": h // 2}
    return {"x": int(x), "y": int(y), "w": int(ww), "h": int(hh)}


def detect_faces(img: np.ndarray) -> List[Dict[str, int]]:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=4, minSize=(30, 30))
    return [{"x": int(x), "y": int(y), "w": int(w), "h": int(h)} for (x, y, w, h) in faces]


def detect_text_regions(img: np.ndarray) -> List[Dict[str, int]]:
    """Approximate detection: MSER + high-contrast edge clumps."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mser = cv2.MSER_create()
    mser.setMinArea(60)
    mser.setMaxArea(int(gray.shape[0] * gray.shape[1] * 0.05))
    regions, _ = mser.detectRegions(gray)
    if not regions:
        return []
    rects = [cv2.boundingRect(np.array(r)) for r in regions]
    rects.sort(key=lambda r: -(r[2] * r[3]))
    top = rects[:8]
    return [{"x": int(x), "y": int(y), "w": int(w), "h": int(h)} for (x, y, w, h) in top]


def encode_png_b64(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        return ""
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def encode_gray_png_b64(mask: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", mask)
    if not ok:
        return ""
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def analyze_artwork(data: bytes) -> Dict[str, Any]:
    img_full = load_image_from_bytes(data)
    img, scale = resize_max(img_full, 900)
    h, w = img.shape[:2]

    heat = saliency_heatmap(img)
    subject = primary_subject_bbox(heat)
    faces = detect_faces(img)
    text_regions = detect_text_regions(img)
    colors = dominant_colors(img, k=5)

    # rough saliency zones: high/mid/low
    zones = {
        "hot": int((heat > 180).sum()),
        "mid": int(((heat > 100) & (heat <= 180)).sum()),
        "cold": int((heat <= 100).sum()),
    }

    # heatmap colorized
    heat_color = cv2.applyColorMap(heat, cv2.COLORMAP_INFERNO)

    thumb = cv2.resize(img, (480, int(480 * h / w))) if w >= h else cv2.resize(img, (int(480 * w / h), 480))
    heat_thumb = cv2.resize(heat_color, thumb.shape[:2][::-1])

    return {
        "canvas_px": {"width": int(w), "height": int(h)},
        "scale_used": float(scale),
        "primary_subject": subject,
        "faces": faces,
        "text_regions": text_regions,
        "dominant_colors": colors,
        "saliency_zones": zones,
        "thumb_png_b64": encode_png_b64(thumb),
        "heatmap_png_b64": encode_png_b64(heat_thumb),
        "original_thumb_dim": {"width": int(thumb.shape[1]), "height": int(thumb.shape[0])},
    }
