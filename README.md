# Soul Threading · Smart AI IMG2Garment Mapper

Deterministic AOP garment mapper with an optional smart AI analysis layer.

## What's included

- **Backend (FastAPI, port 8001)** — `/app/backend/server.py`
  - `/api/health`, `/api/model-status`, `/api/rules`
  - `/api/garments`, `/api/garments/{id}`, `/api/garments/{id}/template/{filename}`
  - `/api/upload-artwork`, `/api/analyze`, `/api/map`
  - `/api/jobs/{id}`, `/api/jobs/{id}/panel/{panel_key}?kind=composed|guides`, `/api/jobs/{id}/download`
- **AOP pipeline modules** — `/app/backend/aop/*`
  - `database_loader`, `artwork_analyzer`, `model_manager`
  - `archetype_classifier`, `garment_fit_scorer`
  - `exclusion_zones` (hero comfort box + adjacency graph)
  - `master_composer` (deterministic Pillow composition + pocket underlay from exact front sample)
  - `validator`, `retry_controller` (in `validator.py`)
  - `output_packager` (ZIP with print PNGs, guides, contact sheet, manifest, quality report, process log)
  - `process_logger`
  - `pipeline` (orchestrator: analyze → classify → score → compose → validate → retry → package)
  - `vision_assist` (Emergent LLM Gemini vision smart hint)
- **Garment database (19 templates)** — `/app/backend/aop_data/`
- **Frontend (React)** — dark technical control-room dashboard at `/app/frontend/src/App.js`

## Smart AI required note

For best production-quality mapping on Hugging Face Spaces / GPU:
- OWLv2 or GroundingDINO for object/subject detection
- SAM2, SAM, or CLIPSeg for segmentation
- RetinaFace / InsightFace / MediaPipe for face detection
- OCR (EasyOCR/PaddleOCR) for text/logo
- Deterministic Pillow/OpenCV/NumPy composition for final PNGs

CPU fallback (used on Emergent preview):
- OpenCV Haar face, saliency FineGrained, MSER text regions, GrabCut segmentation, KMeans colors
- Optional: Emergent LLM key (`EMERGENT_LLM_KEY`) — Gemini 3 Flash for smart archetype hint

Install the GPU stack via `requirements-ai.txt` (packaged in the smart_ai host-ready zip).
