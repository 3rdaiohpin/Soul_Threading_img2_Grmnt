"""Printful V2 print-on-demand fulfillment integration.

Reads PRINTFUL_API_TOKEN from env. All endpoints are optional — if the token
is not set they return a 503 with a clear "not_configured" flag so the
frontend can hide the POD UI without any errors.
"""
from __future__ import annotations
import os
from typing import Dict, Any, List, Optional
import httpx


PRINTFUL_API_URL = "https://api.printful.com/v2"


def is_configured() -> bool:
    return bool(os.environ.get("PRINTFUL_API_TOKEN"))


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['PRINTFUL_API_TOKEN']}",
        "Content-Type": "application/json",
    }


# Reasonable defaults mapping our garment_type -> a common Printful AOP variant.
# Users can override per-request. These are typical AOP catalog IDs from Printful
# V2 catalog (subject to change - user should verify in their Printful account).
GARMENT_TO_CATALOG_VARIANT: Dict[str, int] = {
    "oversized_hoodie": 9224,
    "pull_over_hoodie": 9224,
    "dress_hoodie": 9224,
    "snug_hoodie_2": 9224,
    "raglan_hoodie": 9224,
    "adult_jumpsuit": 15719,
    "cargo_loose_shorts": 12036,
    "flare_jogger": 9226,
    "padded_sports_bra": 11549,
    "polo_shirt": 12290,
    "long_sleeve_button_down_shirt": 9227,
    "reversible_baseball_jersey": 13116,
    "tshirt_dress": 12048,
    "cardigan": 12220,
    "hooded_baseball_jacket": 13570,
    "elongated_cloak": 15719,
    "zipper_cloak": 15719,
    "women_long_sleeve_hooded_performance_shirt": 9227,
    "women_s_cut_and_sew_racerback_dress_aop": 12048,
}


# Map our internal panel keys to Printful V2 placement keys.
PANEL_TO_PLACEMENT: Dict[str, str] = {
    "master_front": "front",
    "master_back": "back",
    "sleeves": "left_sleeve",  # single sleeve panel maps to both, but v2 expects specific side
    "hood": "hood",
}


def suggest_variant_for(garment_type: str) -> Optional[int]:
    return GARMENT_TO_CATALOG_VARIANT.get(garment_type)


def build_placements(panels: List[str], base_url: str, job_id: str) -> List[Dict[str, Any]]:
    """Turn our composed panel keys into Printful placement objects with public URLs."""
    result: List[Dict[str, Any]] = []
    seen_placements = set()
    for panel in panels:
        # Pocket panels are already sampled from front; skip separate placement
        # to avoid Printful pocket overlay duplicating.
        if panel.startswith("pocket_"):
            continue
        placement = PANEL_TO_PLACEMENT.get(panel)
        if not placement or placement in seen_placements:
            continue
        seen_placements.add(placement)
        url = f"{base_url.rstrip('/')}/api/jobs/{job_id}/panel/{panel}?kind=composed"
        result.append({
            "placement": placement,
            "layers": [{"type": "file", "url": url}],
        })
        # If we have sleeves and both sides accepted, duplicate for right_sleeve
        if panel == "sleeves" and "right_sleeve" not in seen_placements:
            seen_placements.add("right_sleeve")
            result.append({
                "placement": "right_sleeve",
                "layers": [{"type": "file", "url": url}],
            })
    return result


async def create_and_submit_order(
    catalog_variant_id: int,
    placements: List[Dict[str, Any]],
    recipient: Dict[str, Any],
    confirm: bool = False,
) -> Dict[str, Any]:
    """Create draft order, add item with placements, optionally confirm.

    Returns dict with printful_order_id, status, and (if confirmed) confirm response.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Create draft order
        draft = await client.post(
            f"{PRINTFUL_API_URL}/orders",
            headers=_headers(),
            json={"recipient": recipient},
        )
        if draft.status_code not in (200, 201):
            return {"error": "draft_failed", "status": draft.status_code, "body": draft.text}
        order_id = draft.json()["data"]["id"]

        # 2. Add line item
        item_payload = {
            "catalog_variant_id": catalog_variant_id,
            "placements": placements,
        }
        item = await client.post(
            f"{PRINTFUL_API_URL}/orders/{order_id}/items",
            headers=_headers(),
            json=item_payload,
        )
        if item.status_code not in (200, 201):
            return {
                "printful_order_id": order_id,
                "status": "draft_item_failed",
                "detail": item.text,
            }

        # 3. Confirm (optional — DRAFT stays free)
        confirm_body: Optional[Dict[str, Any]] = None
        if confirm:
            conf = await client.post(
                f"{PRINTFUL_API_URL}/orders/{order_id}/confirm",
                headers=_headers(),
            )
            confirm_body = conf.json() if conf.status_code in (200, 201) else {"error": conf.text}

        return {
            "printful_order_id": order_id,
            "status": "confirmed" if confirm else "draft",
            "dashboard_url": f"https://www.printful.com/dashboard/orders/{order_id}",
            "confirm_response": confirm_body,
        }


async def get_order_status(order_id: int) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.get(
            f"{PRINTFUL_API_URL}/orders/{order_id}",
            headers=_headers(),
        )
        if res.status_code != 200:
            return {"error": "not_found", "status_code": res.status_code, "body": res.text}
        data = res.json().get("data", {})
        shipments = data.get("shipments", []) or []
        tracking_url = shipments[0].get("tracking_url") if shipments else None
        return {
            "printful_order_id": order_id,
            "status": data.get("status"),
            "tracking_url": tracking_url,
            "dashboard_url": f"https://www.printful.com/dashboard/orders/{order_id}",
        }
