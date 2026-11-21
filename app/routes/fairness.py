"""
Fairness Audit Route.
GET /api/fairness
Returns live Disparate Impact Ratio + proxy correlation proof.
"""
from fastapi import APIRouter
import pandas as pd

from app.core.queue_engine import queue_engine
from app.core.fairness import audit_fairness_and_proxies

router = APIRouter(prefix="/api/fairness", tags=["Fairness"])

@router.get("")
def get_fairness_report():
    """Returns live Disparate Impact (>= 0.80) & proxy correlation matrix."""
    df = pd.DataFrame(queue_engine.ranked_queue)
    if df.empty:
        return {"status": "NO_DATA", "pass_all_fairness_checks": True}
    report = audit_fairness_and_proxies(df, top_n=360)
    return report

