# Soul Threading · Smart AI IMG2Garment Mapper — PRD

## Original Problem
Build a Smart AI IMG2Garment Mapper: upload artwork, analyze subject/face/logos, classify archetype (portrait_hero / scene_wrap / abstract_wrap / logo_text_layout / product_object_layout), score 19 garment templates for fit, compose master front/back/sleeves/hood/pockets deterministically (Pillow, pocket underlay samples EXACT front region), validate quality gate, retry on failure, package ZIP with print PNGs, guides, mockup contact sheet, manifest, quality report, and process log.

## User Choices
- Deployment: Hugging Face Spaces (GPU) + Emergent preview (CPU)
- AI layer: CPU-safe fallback + Emergent LLM vision assist (Gemini 3 Flash) — deterministic Pillow/OpenCV compositor
- Frontend: Full React dashboard
- Scope: Full end-to-end MVP

## Architecture
- FastAPI backend (port 8001) — /app/backend/server.py + /app/backend/aop/*
- 15 pipeline modules: database_loader, artwork_analyzer, model_manager, archetype_classifier, garment_fit_scorer, master_composer, hero_comfort_box + exclusion_zones + adjacency_graph, piece_deriver (in master_composer), pocket_underlay (in master_composer), validator, retry_controller (in validator), output_packager, process_logger, pipeline, vision_assist
- 19-garment deterministic DB at /app/backend/aop_data (95 MB): garment_database.json, source_templates PNGs, analysis_masks, rules
- React frontend — dark technical control-room dashboard, IBM Plex Sans + JetBrains Mono, industrial-amber accent

## Implemented (2026-01-07)
- All 15 core AOP modules with deterministic Pillow composition + pocket underlay sampling from exact front crop
- CPU fallback stack: OpenCV Haar face, saliency FineGrained, MSER text, KMeans dominant colors
- Emergent LLM vision assist for smart archetype hint (Gemini 3 Flash via emergentintegrations) — degrades gracefully when key budget exhausted
- FastAPI endpoints: health, model-status, rules, garments, garments/{id}, template PNG serve, upload-artwork, analyze, map, jobs/{id}, jobs/{id}/panel/{key}, jobs/{id}/download
- Full ZIP output: print/*.png, guides/*.png, mockup/contact_sheet.png, mapping_manifest.json, quality_report.json, mapping_process_log.txt
- React UI: Upload dropzone, Analyze panel (heatmap + detections + colors + archetype scores), Garment Library grid with fit scores, Master Composition preview (composed/guides toggle), Quality Gauge with hard-fails, Process Log terminal, Model Manager sidebar, action bar with download
- Backend testing: 22/22 pytest cases passed (deterministic pipeline + zip contents validated)

## Backlog (P1)
- Multi-garment batch mapping in one job
- Save/browse previous jobs (MongoDB persistence)
- Custom exclusion-zone editor per template
- HF Spaces deployment package (requirements-ai.txt already staged in /tmp/artifacts/smart_ai)

## Backlog (P2)
- Real OWLv2/SAM2/CLIPSeg pipeline for HF GPU
- Adjust retry controller with per-strategy scoring
- Preset styles per archetype (contain vs cover, y-shift)

## Enhancement Idea
Add a "share preview" that generates a public link with the mockup contact sheet + top 3 recommended garments — great for POD sellers to socialize designs before committing to production.
