---
title: Soul Threading Smart AI IMG2Garment Mapper
emoji: 🧵
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: "Smart AI mapper: artwork to production AOP garments."
---

# Soul Threading · Smart AI IMG2Garment Mapper

Upload artwork → deterministic pipeline detects subject / face / text / saliency, classifies archetype
(portrait_hero, scene_wrap, abstract_wrap, logo_text_layout, product_object_layout), scores 19 garment
templates for fit, composes master front/back/sleeves/hood/pockets with **exact pocket underlay**,
validates against a quality gate, retries when needed, and packages a print-ready ZIP.

## Model layer

- **CPU fallback (always available):** OpenCV Haar face, FineGrained saliency, MSER text regions,
  GrabCut segmentation, KMeans dominant colors.
- **Smart assist (optional):** set `EMERGENT_LLM_KEY` — routes archetype/subject reasoning through
  Gemini 3 Flash via `emergentintegrations`.
- **Best-result stack (HF GPU):** OWLv2 / GroundingDINO / SAM2 / SAM / CLIPSeg / RetinaFace / OCR —
  installable via `requirements-ai.txt` when running on GPU hardware.

## Endpoints

- `GET /api/health`
- `GET /api/model-status`
- `GET /api/garments` and `GET /api/garments/{product_id}`
- `POST /api/upload-artwork` (multipart file)
- `POST /api/analyze` (form: artwork_id, use_smart_hint)
- `POST /api/map` (json: artwork_id, product_id, use_smart_hint)
- `GET /api/jobs/{job_id}` / `.../panel/{panel_key}?kind=composed|guides` / `.../download`
