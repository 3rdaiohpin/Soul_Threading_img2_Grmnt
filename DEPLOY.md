# Deploy · Soul Threading Smart AI IMG2Garment Mapper

Two supported deploy paths.

---

## A. Hugging Face Spaces (Docker SDK) — one-shot deploy

The repo is Space-ready. It builds the React frontend, boots FastAPI on port
`7860`, and serves both the API and the SPA from a single process.

### Files that make this work

| File | Purpose |
| --- | --- |
| `Dockerfile` | Multi-stage build: `node:18` builds the React SPA, `python:3.11-slim` runs FastAPI |
| `hf_serve.py` | Mounts the built SPA on the FastAPI app; API stays on `/api/*` |
| `space_README.md` | Contains the HF Space YAML metadata (rename to `README.md` in the Space repo) |
| `backend/` | FastAPI + AOP pipeline modules |
| `backend/aop_data/` | 19-template deterministic garment database (95 MB) |
| `frontend/` | React source; built inside the Docker image |

### Steps

1. Create a new **Space** on huggingface.co with **SDK = Docker**.
2. Clone the Space repo locally.
3. Copy this repo's contents into the Space repo root.
4. Rename `space_README.md` → `README.md` (the YAML frontmatter is what tells HF
   to serve on port 7860 with the Docker SDK).
5. (Optional) On the Space **Settings → Variables and secrets** add
   `EMERGENT_LLM_KEY` if you want the smart archetype hint. Everything works
   without it (CPU fallback).
6. `git add -A && git commit -m "init" && git push`.
7. HF builds the image and starts the Space. First build takes ~5–8 min.

### Verifying the deploy

- `GET /api/health` returns `{"ok": true, "db_products": 19, ...}`
- Root `/` returns the SPA.

### Optional GPU / smart-model layer

For the best-result AI stack (OWLv2, SAM2, CLIPSeg, RetinaFace, OCR), attach
GPU hardware and add `requirements-ai.txt` (included in the smart-ai host-ready
zip) to the Docker build.

---

## B. GitHub push (any Docker/Node host)

The same repo is a clean GitHub-friendly layout:

```
/app
├── backend/           # FastAPI + aop/ pipeline modules + aop_data/
├── frontend/          # React SPA (CRA + Tailwind + shadcn primitives)
├── hf_serve.py        # single-process combined entrypoint
├── Dockerfile         # HF Spaces / any container host
├── space_README.md    # HF metadata (rename to README.md on HF)
├── README.md          # project overview
└── DEPLOY.md          # this file
```

### Push to GitHub

Use the **"Save to GitHub"** feature in the Emergent chat input — that's the
supported path from this environment. It will initialize the remote, push the
current codebase, and keep it in sync.

After pushing, you can deploy the same Dockerfile to:

- **Hugging Face Spaces** (Docker SDK) — see path A
- **Railway / Render / Fly.io** — point at the Dockerfile, expose port 7860
- **Any VPS with docker**:
  ```bash
  docker build -t soul-threading .
  docker run -p 7860:7860 --env EMERGENT_LLM_KEY=... soul-threading
  ```

---

## Runtime env vars

| Variable | Purpose | Default |
| --- | --- | --- |
| `MONGO_URL` | Optional; kept for future job history persistence | `mongodb://localhost:27017` |
| `DB_NAME` | Mongo db name | `soul_threading` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `*` |
| `EMERGENT_LLM_KEY` | Enables Gemini 3 Flash smart hint | unset (falls back to CPU) |
| `PORT` | Server port | `7860` |

The pipeline works fully without Mongo or `EMERGENT_LLM_KEY` — Mongo is only
touched when future job history features are enabled, and the smart hint is a
non-blocking augment on top of the deterministic CPU analysis.
