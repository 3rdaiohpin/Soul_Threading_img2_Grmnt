"""Optional Emergent LLM vision assist for smart archetype/subject hints."""
from __future__ import annotations
import base64
import json
import os
from typing import Optional, Dict, Any

try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
    _HAS_EI = True
except Exception:
    _HAS_EI = False


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


async def smart_hint(image_bytes: bytes) -> Optional[Dict[str, Any]]:
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
