"""
Cashfree & Relay Webhook Route.
POST /api/webhook/cashfree
Handles PAYMENT_LINK_EVENT (PAID, PARTIALLY_PAID, EXPIRED) & Relay calls.
"""
from fastapi import APIRouter, Request
from typing import Dict, Any

from app.core.queue_engine import queue_engine
from app.core.cashfree import cashfree_client

router = APIRouter(prefix="/api/webhook", tags=["Webhook"])

@router.post("/cashfree")
async def cashfree_webhook(request: Request):
    """
    Handles Cashfree Webhook & Relay events.
    When a borrower pays, immediately updates borrower status and re-forms queue.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    parsed = cashfree_client.parse_webhook_payload(body)
    link_id = parsed["link_id"]
    link_status = parsed["link_status"]
    amount_paid = parsed["amount_paid"]

    target_lid = None
    for lid, b in queue_engine.borrowers.items():
        if b.get("last_link_id") == link_id or link_id.startswith(f"link_{lid.replace('-', '_')}"):
            target_lid = lid
            break

    if target_lid and (parsed["is_paid"] or parsed["is_partial"]):
        is_full = parsed["is_paid"]
        queue_engine.handle_payment_event(target_lid, amount_paid=amount_paid, is_full=is_full)
        return {
            "status": "SUCCESS",
            "message": f"Queue updated for loan {target_lid}",
            "link_status": link_status,
            "rank_delta_reformed": True
        }

    return {"status": "ACK", "message": "Webhook received", "link_status": link_status}

