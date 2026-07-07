# Soul Threading · Smart AI IMG2Garment Mapper — PRD

## Original problem statement
Upload artwork → detect subject/face/text/saliency → classify archetype
(portrait_hero / scene_wrap / abstract_wrap / logo_text_layout /
product_object_layout) → score 19 garment templates → compose master
front/back/sleeves/hood/pockets with **exact pocket underlay from front sample**
→ validate → retry → package a print-ready ZIP (print PNGs, guide overlays,
mockup contact sheet, manifest, quality report, process log). Deploy to
Hugging Face Spaces AND Emergent. Full React UI required.

## Deployments live (Jan 2026)
- **Emergent preview** — https://42fc6f0c-4bc4-4ff7-9160-1463a0778587.preview.emergentagent.com
- **Hugging Face Space (private)** — https://huggingface.co/spaces/3rdaiOhpinFully/3rdaiOhpinFully
  - Backend URL: https://3rdaiohpinfully-3rdaiohpinfully.hf.space (requires HF auth)

## Architecture

### Backend (`/app/backend/`, FastAPI, ports 8001 dev / 7860 HF)
- `server.py` — 15 REST routes under `/api/*`
- `aop/` — 15 pipeline modules:
  - `database_loader`, `artwork_analyzer`, `model_manager`
  - `archetype_classifier`, `garment_fit_scorer`, `exclusion_zones`
  - `master_composer` (deterministic Pillow + exact pocket underlay from front sample)
  - `validator`, `retry_controller` (in `validator.py`)
  - `output_packager`, `process_logger`, `pipeline` (orchestrator)
  - `vision_assist` (Emergent LLM Gemini 3 Flash smart hint, non-blocking)
  - `pod_printful` (Printful V2 draft/confirm order submission)

### Frontend (`/app/frontend/src/App.js`, React)
Dark technical control-room dashboard, six panels + Model Manager sidebar +
Printful modal.

### Data (`/app/backend/aop_data/`, 95 MB)
19 garment templates × master front/back/sleeves/hood/pockets, per-piece
analysis masks, universal deterministic ruleset.

## Endpoints
- `GET /api/health`, `/api/model-status`, `/api/rules`
- `GET /api/garments`, `/api/garments/{id}`, `/api/garments/{id}/template/{file}`
- `POST /api/upload-artwork`, `POST /api/analyze`, `POST /api/map`
- `GET /api/jobs/{id}`, `/api/jobs/{id}/panel/{key}?kind=composed|guides`, `/api/jobs/{id}/download`
- **`GET /api/pod/status`** — configured / not configured
- **`POST /api/pod/submit`** — Printful draft/confirm order
- **`GET /api/pod/orders/{id}/status`** — poll fulfillment status

## Implemented — Jan 2026
- End-to-end pipeline validated on all 19 garments
- **Iteration 2**: 24/24 backend tests + full frontend E2E; ActionBar/badge
  overlap fixed
- **Iteration 3**: Printful POD integration + garment library scroll fix +
  code-review cleanups
- 27/27 backend tests passing (100%)
- Emergent LLM vision assist (Gemini 3 Flash) wired with graceful fallback
- **Live on Hugging Face Spaces** (Docker SDK, port 7860) + Emergent preview

## Runtime env
- `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS` (backend/.env)
- `EMERGENT_LLM_KEY` (optional; smart hint)
- `PRINTFUL_API_TOKEN` (optional; POD fulfillment)
- `PUBLIC_BASE_URL` (required for POD — Printful must reach panel URLs)

## Backlog
- P1: MongoDB job persistence (currently in-memory, 1h TTL)
- P1: Live SSE process-log streaming
- P1: `/api/pod/variants` — pull live Printful catalog to reduce hardcoded map drift
- P2: True GPU smart layer on HF (OWLv2 / SAM2 / RetinaFace)
- P2: Left/right sleeve mirroring for directional artwork
- P2: Batch mode — one artwork across multiple garments
- P3: Auth + team workspaces

## Test credentials
None. No auth.
