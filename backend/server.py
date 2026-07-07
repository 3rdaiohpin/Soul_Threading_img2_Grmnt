"""Soul Threading Smart AI IMG2Garment Mapper - FastAPI backend."""
from __future__ import annotations
import base64
import io
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse, Response
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, ConfigDict
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# Domain modules
from aop.database_loader import GarmentDatabase
from aop.model_manager import ModelManager
from aop.artwork_analyzer import analyze_artwork
from aop.archetype_classifier import classify
from aop.garment_fit_scorer import score_all
from aop.pipeline import MapJob
from aop.vision_assist import smart_hint as vision_smart_hint

# Mongo
mongo_url = os.environ["MONGO_URL"]
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ["DB_NAME"]]

AOP_DATA = ROOT_DIR / "aop_data"
garment_db = GarmentDatabase(AOP_DATA)
model_manager = ModelManager()

# In-memory job store (jobs are large; TTL cleanup)
JOB_STORE: Dict[str, Dict[str, Any]] = {}
JOB_TTL_SEC = 60 * 60


def _prune_jobs():
    now = time.time()
    for k in list(JOB_STORE.keys()):
        if now - JOB_STORE[k].get("_ts", now) > JOB_TTL_SEC:
            JOB_STORE.pop(k, None)


app = FastAPI(title="Soul Threading Smart AI IMG2Garment Mapper", version="1.0.0")
api_router = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("aop_mapper")


class MapRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    artwork_id: str
    product_id: str
    use_smart_hint: bool = True


@api_router.get("/")
async def root():
    return {
        "app": "Soul Threading Smart AI IMG2Garment Mapper",
        "version": "1.0.0",
        "status": "ok",
    }


@api_router.get("/health")
async def health():
    return {
        "ok": True,
        "db_products": len(garment_db.products),
        "mongo": "up",
        "time_utc": datetime.now(timezone.utc).isoformat(),
    }


@api_router.get("/model-status")
async def model_status():
    return model_manager.refresh()


@api_router.get("/rules")
async def rules():
    return garment_db.rules


@api_router.get("/garments")
async def garments():
    return {"count": len(garment_db.products), "items": garment_db.summary()}


@api_router.get("/garments/{product_id}")
async def garment_detail(product_id: str):
    p = garment_db.product(product_id)
    if not p:
        raise HTTPException(404, "product not found")
    return {
        "product_id": p["product_id"],
        "display_name": p["display_name"],
        "garment_type": p["garment_type"],
        "template_files": p.get("template_files", []),
        "piece_count": p.get("piece_count", 0),
    }


@api_router.get("/garments/{product_id}/template/{filename}")
async def garment_template_png(product_id: str, filename: str):
    p = garment_db.product(product_id)
    if not p:
        raise HTTPException(404, "product not found")
    # find matching template
    for t in p.get("template_files", []):
        if Path(t["template_png"]).name == filename:
            path = garment_db.resolve_path(t["template_png"])
            if not path.exists():
                raise HTTPException(404, "template file missing")
            return Response(content=path.read_bytes(), media_type="image/png")
    raise HTTPException(404, "template not found")


ARTWORK_STORE: Dict[str, bytes] = {}


@api_router.post("/upload-artwork")
async def upload_artwork(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, "file too large (max 20MB)")
    ct = (file.content_type or "").lower()
    if ct not in ("image/jpeg", "image/jpg", "image/png", "image/webp"):
        # sniff header
        header = data[:12]
        if not (header.startswith(b"\x89PNG") or header[:3] == b"\xff\xd8\xff" or header[:4] == b"RIFF"):
            raise HTTPException(400, f"unsupported content_type={ct}")
    art_id = uuid.uuid4().hex[:12]
    ARTWORK_STORE[art_id] = data
    return {"artwork_id": art_id, "bytes": len(data), "content_type": ct}


@api_router.post("/analyze")
async def analyze(artwork_id: str = Form(...), use_smart_hint: bool = Form(True)):
    data = ARTWORK_STORE.get(artwork_id)
    if not data:
        raise HTTPException(404, "artwork_id not found")
    analysis = analyze_artwork(data)
    hint = None
    if use_smart_hint:
        try:
            hint = await vision_smart_hint(data)
        except Exception as e:
            hint = {"error": str(e)}
    arch = classify(analysis, smart_hint=(hint or {}).get("archetype") if isinstance(hint, dict) else None)
    scored = score_all(garment_db.summary(), arch["archetype"])
    # store analysis so /map can reuse
    return {
        "artwork_id": artwork_id,
        "analysis": analysis,
        "smart_hint": hint,
        "archetype": arch,
        "recommended_garments": scored[:8],
        "all_scored": scored,
    }


@api_router.post("/map")
async def map_artwork(req: MapRequest):
    _prune_jobs()
    data = ARTWORK_STORE.get(req.artwork_id)
    if not data:
        raise HTTPException(404, "artwork_id not found")
    product = garment_db.product(req.product_id)
    if not product:
        raise HTTPException(404, "product_id not found")
    hint = None
    if req.use_smart_hint:
        try:
            hint = await vision_smart_hint(data)
        except Exception as e:
            hint = {"error": str(e)}

    job = MapJob(garment_db, data, req.product_id, smart_hint_data=hint if isinstance(hint, dict) else None)
    result = job.run(allow_retry=True)
    # store job artifacts for download / preview
    JOB_STORE[job.job_id] = {
        "_ts": time.time(),
        "result": result,
        "zip_bytes": job.zip_bytes,
        "composed_png": {k: _pil_to_png_bytes(v) for k, v in job.composed_images.items()},
        "guides_png": {k: _pil_to_png_bytes(v) for k, v in job.guides_images.items()},
    }
    # trim large fields from response for network
    resp = dict(result)
    return resp


def _pil_to_png_bytes(im) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


@api_router.get("/jobs/{job_id}")
async def job_status(job_id: str):
    entry = JOB_STORE.get(job_id)
    if not entry:
        raise HTTPException(404, "job not found")
    return entry["result"]


@api_router.get("/jobs/{job_id}/panel/{panel_key}")
async def job_panel(job_id: str, panel_key: str, kind: str = "composed"):
    entry = JOB_STORE.get(job_id)
    if not entry:
        raise HTTPException(404, "job not found")
    pool = entry["composed_png"] if kind == "composed" else entry["guides_png"]
    if panel_key not in pool:
        raise HTTPException(404, f"panel {panel_key} not in {kind}")
    return Response(content=pool[panel_key], media_type="image/png")


@api_router.get("/jobs/{job_id}/download")
async def job_download(job_id: str):
    entry = JOB_STORE.get(job_id)
    if not entry:
        raise HTTPException(404, "job not found")
    return StreamingResponse(
        io.BytesIO(entry["zip_bytes"]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="soul_threading_map_{job_id}.zip"'},
    )


app.include_router(api_router)


@app.on_event("shutdown")
async def _shutdown():
    mongo_client.close()
