"""
Actions Routes.
POST /api/actions/sync-link/{link_id}
POST /api/actions/simulate-lapse/{id}
POST /api/actions/already-paid-hold/{id}
POST /api/actions/test-time-block
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from app.config import IST
from app.core.queue_engine import queue_engine
from app.core.cashfree import cashfree_client
import app.routes.queue as queue_routes

router = APIRouter(prefix="/api/actions", tags=["Actions"])

class TimeBlockPayload(BaseModel):
    fake_now: Optional[str] = None  # e.g. "19:15" or None to reset

@router.post("/sync-link/{link_id}")
def sync_link(link_id: str):
    """
    Polls real live status from Cashfree Sandbox.
    If PAID or PARTIALLY_PAID, immediately re-forms queue with rank deltas (↑/↓).
    """
    res = cashfree_client.get_payment_link_status(link_id)
    if not res.get("success"):
        return res

    status = res.get("link_status", "").upper()
    amount_paid = float(res.get("link_amount_paid", 0.0))

    target_lid = None
    for lid, b in queue_engine.borrowers.items():
        if b.get("last_link_id") == link_id or link_id.startswith(f"link_{lid.replace('-', '_')}"):
            target_lid = lid
            break

    if target_lid and status in ["PAID", "PARTIALLY_PAID"]:
        is_full = (status == "PAID")
        paid_val = amount_paid if amount_paid > 0 else float(queue_engine.borrowers[target_lid].get("amount_due", 100))
        queue_engine.handle_payment_event(target_lid, amount_paid=paid_val, is_full=is_full)
        res["queue_reformed"] = True
        res["target_loan_id"] = target_lid

    return res

@router.post("/simulate-lapse/{id}")
def simulate_lapse(id: str):
    """Simulates broken payment commitment, penalizing score and shifting rank down."""
    if id not in queue_engine.borrowers:
        raise HTTPException(status_code=404, detail="Loan ID not found")
    return queue_engine.handle_promise_lapse(id)

@router.post("/already-paid-hold/{id}")
def already_paid_hold(id: str):
    """Triggers Already-Paid reconciliation hold ('branch mein de diya')."""
    if id not in queue_engine.borrowers:
        raise HTTPException(status_code=404, detail="Loan ID not found")
    return queue_engine.handle_reconciliation_claim(id)

@router.post("/test-time-block")
def test_time_block(payload: TimeBlockPayload):
    """
    Simulates calling hours check. Passing fake_now='19:15' triggers the
    RBI Jan 2027 hard block on non-opted-in accounts.
    """
    if payload.fake_now:
        try:
            parts = [int(p) for p in payload.fake_now.split(":")]
            h, m = parts[0], parts[1]
            queue_routes.CURRENT_FAKE_TIME = datetime(2026, 11, 21, h, m, tzinfo=IST)
            msg = f"Simulating {payload.fake_now} IST. Hard block active for non-opted-in borrowers."
        except Exception:
            queue_routes.CURRENT_FAKE_TIME = datetime(2026, 11, 21, 19, 15, tzinfo=IST)
            msg = "Simulating 19:15 IST (After-hours window block active)."
    else:
        queue_routes.CURRENT_FAKE_TIME = None
        msg = "Restored live IST calling hours."

    return {
        "fake_now": payload.fake_now,
        "is_override_active": bool(queue_routes.CURRENT_FAKE_TIME),
        "message": msg
    }
