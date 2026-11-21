"""
Queue & Audit Logs Routes.
GET /api/queue
GET /api/audit-logs
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Query

from app.config import IST
from app.core.queue_engine import queue_engine, sanitize_record
from app.core.compliance import audit_logger, evaluate_borrower_call_compliance

router = APIRouter(prefix="/api", tags=["Queue"])

# State for fake_now evening simulation
CURRENT_FAKE_TIME: Optional[datetime] = None

@router.get("/queue")
def get_queue(limit: int = 360):
    """Returns top 360 prioritized call queue, hold lanes, and stats."""
    queue = queue_engine.get_top_queue(limit)
    test_dt = CURRENT_FAKE_TIME or datetime.now(IST)
    
    augmented = []
    for item in queue:
        comp = evaluate_borrower_call_compliance(item, check_time=test_dt)
        entry = dict(item)
        entry["rbi_compliance"] = comp
        augmented.append(sanitize_record(entry))

    hold_lanes = queue_engine.get_hold_lanes()
    # Sanitize hold lane entries
    sanitized_lanes = {
        k: [sanitize_record(x) for x in v] for k, v in hold_lanes.items()
    }
    stats = queue_engine.get_summary_metrics()

    return {
        "queue": augmented,
        "count": len(augmented),
        "hold_lanes": sanitized_lanes,
        "stats": stats,
        "is_evening_override_active": bool(CURRENT_FAKE_TIME)
    }

@router.get("/audit-logs")
def get_audit_logs(limit: int = 100, filter_loan: Optional[str] = None):
    """Returns searchable 6-month call and regulatory compliance logs."""
    return {"logs": audit_logger.get_logs(limit=limit, filter_loan=filter_loan)}

