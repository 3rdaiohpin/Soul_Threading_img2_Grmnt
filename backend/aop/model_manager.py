"""Model manager. Reports available analysis backends.

Primary (GPU / HF Spaces): OWLv2, GroundingDINO, SAM2, SAM, CLIPSeg, RetinaFace, OCR.
Emergent vision assist: Claude/Gemini via emergentintegrations (image chat).
CPU fallback: OpenCV Haar, saliency, MSER, KMeans.
"""
from __future__ import annotations
import os
from typing import Dict, Any, List


def detect_backends() -> Dict[str, Any]:
    active = "cpu_fallback"
    smart_available = False
    emergent_key = os.environ.get("EMERGENT_LLM_KEY", "")
    if emergent_key:
        active = "emergent_vision_assist"
        smart_available = True

    torch_ok = False
    try:
        import torch  # type: ignore
        torch_ok = True
    except Exception:
        torch_ok = False

    return {
        "active_backend": active,
        "smart_available": smart_available,
        "detectors": [
            {"name": "OWLv2", "type": "object_detection", "available": False, "note": "GPU only (HF Spaces)"},
            {"name": "GroundingDINO", "type": "object_detection", "available": False, "note": "GPU only (HF Spaces)"},
            {"name": "SAM2", "type": "segmentation", "available": False, "note": "GPU only (HF Spaces)"},
            {"name": "SAM", "type": "segmentation", "available": False, "note": "GPU only (HF Spaces)"},
            {"name": "CLIPSeg", "type": "segmentation", "available": False, "note": "GPU only (HF Spaces)"},
            {"name": "RetinaFace / InsightFace / MediaPipe", "type": "face", "available": False,
             "note": "GPU/large model (HF Spaces)"},
            {"name": "OCR (EasyOCR/PaddleOCR)", "type": "text_logo", "available": False, "note": "HF Spaces"},
            {"name": "OpenCV Haar Face", "type": "face", "available": True, "note": "CPU fallback"},
            {"name": "OpenCV Saliency (FineGrained)", "type": "saliency", "available": True, "note": "CPU fallback"},
            {"name": "OpenCV MSER text regions", "type": "text_logo", "available": True, "note": "CPU fallback"},
            {"name": "OpenCV GrabCut", "type": "segmentation", "available": True, "note": "CPU fallback"},
            {"name": "KMeans dominant colors", "type": "colors", "available": True, "note": "CPU"},
            {"name": "Emergent Vision (Claude/Gemini)", "type": "smart_assist", "available": smart_available,
             "note": "Multimodal LLM archetype + subject reasoning" if smart_available else "Set EMERGENT_LLM_KEY"},
        ],
        "torch_installed": torch_ok,
    }


class ModelManager:
    def __init__(self):
        self._status = detect_backends()

    @property
    def status(self) -> Dict[str, Any]:
        return self._status

    def refresh(self) -> Dict[str, Any]:
        self._status = detect_backends()
        return self._status
