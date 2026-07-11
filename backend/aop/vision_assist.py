"""Optional LLM vision assist for smart archetype/subject hints.

Primary: Ollama LLaVA-7B (free, local, ZeroGPU-compatible)
Fallback: Emergent LLM (if EMERGENT_LLM_KEY is set, but not needed)
"""
from __future__ import annotations
import base64
import json
import os
from typing import Optional, Dict, Any
import httpx

# Try Emergent as optional fallback
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
    _HAS_EI = True
except Exception:
    _HAS_EI = False

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
OLLAMA_MODEL = "llava:7b"

SYS_PROMPT = (
    "You are an expert print-on-demand garment mapping assistant. "
    "Analyze the provided artwork image and return STRICT JSON with keys: "
    '{"archetype": one of ["portrait_hero","scene_wrap","abstract_wrap","logo_text_layout","product_object_layout"], '
    '"has_face": boolean, "has_text_or_logo": boolean, '
    '"primary_subject": short lowercase noun phrase, '
    '"dominant_mood": short adjective phrase, '
    '"back_side_treatment": one of ["abstract_environment","texture_continuation","supporting_motif"]}. '
    "Return ONLY the JSON object, no prose."
)


async def smart_hint_ollama(image_bytes: bytes) -> Optional[Dict[str, Any]]:
    """Use local Ollama LLaVA for vision analysis (100% free, ZeroGPU-compatible)."""
    try:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"http://{OLLAMA_HOST}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": (
                        "Analyze this design for garment printing. "
                        "Is it: portrait_hero, scene_wrap, abstract_wrap, logo_text_layout, or product_object_layout? "
                        "Respond ONLY with JSON: "
                        '{"archetype": "...", "has_face": bool, "has_text_or_logo": bool, '
                        '"primary_subject": "...", "dominant_mood": "...", "back_side_treatment": "..."}'
                    ),
                    "images": [b64],
                    "stream": False,
                    "temperature": 0.3
                }
            )
        
        if response.status_code == 200:
            data = response.json()
            text = data.get("response", "")
            
            # Extract JSON
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    return {"raw": text}
        
        return None
    except Exception as e:
        print(f"Ollama error: {e}")
        return None


async def smart_hint_emergent(image_bytes: bytes) -> Optional[Dict[str, Any]]:
    """Fallback: Emergent LLM (requires EMERGENT_LLM_KEY, not needed with Ollama)."""
    if not _HAS_EI:
        return None
    
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    
    try:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        chat = LlmChat(
            api_key=key,
            session_id=f"aop-vision-{os.urandom(4).hex()}",
            system_message=SYS_PROMPT,
        ).with_model("gemini", "gemini-3-flash-preview")
        img = ImageContent(image_base64=b64)
        msg = UserMessage(
            text="Analyze this artwork and return the JSON.",
            file_contents=[img],
        )
        text = await chat.send_message(msg)
        
        # Extract JSON substring
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                return {"raw": text}
        return {"raw": text}
    except Exception as e:
        return {"error": str(e)}


async def smart_hint(image_bytes: bytes) -> Optional[Dict[str, Any]]:
    """
    Unified smart hint: try Ollama first (free, local), fallback to Emergent (optional, paid).
    """
    # Try Ollama first (100% free, ZeroGPU-compatible)
    result = await smart_hint_ollama(image_bytes)
    if result and "error" not in result:
        return result
    
    # Fallback to Emergent if configured
    result = await smart_hint_emergent(image_bytes)
    if result and "error" not in result:
        return result
    
    # No LLM available - pipeline falls back to CPU analysis
    return None
