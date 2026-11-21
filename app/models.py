"""
Pydantic Schemas & Domain Models.
Includes: Account, CallLog, PaymentLink, FairnessReport, SignalExtraction
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class Account(BaseModel):
    loan_id: str
    borrower_name: str
    phone: str
    gender: Optional[str] = "Unknown"
    religion: Optional[str] = "Unknown"
    caste: Optional[str] = "Unknown"
    city: Optional[str] = "Unknown"
    pincode: Optional[str] = "000000"
    preferred_language: str = "hi-IN"
    due_date: str = ""
    dpd: float = 0.0
    amount_due: float = 0.0
    past_promises_kept_ratio: float = 0.5
    historical_pay_rate: float = 0.5
    inbound_recency_days: float = 15.0
    broken_promises_count: int = 0
    notes: str = ""
    borrower_opted_in: bool = False
    actually_paid: Optional[int] = None
    
    # Computed Ranker Fields
    priority_score: Optional[float] = 0.0
    status_badge: Optional[str] = "ELIGIBLE"
    manager_reason: Optional[str] = ""
    is_exploration: Optional[bool] = False
    rank: Optional[int] = 0
    rank_delta: Optional[int] = 0
    rbi_compliance: Optional[Dict[str, Any]] = None

class SignalExtraction(BaseModel):
    intent: str
    intent_score: float
    promise_day: Optional[int] = None
    recommended_action: str
    summary: str
    raw_transcript: Optional[str] = None

class PaymentLink(BaseModel):
    link_id: str
    loan_id: str
    link_url: str
    link_amount: float
    link_status: str
    is_partial: bool = False
    min_partial_amount: Optional[float] = None
    created_at: Optional[str] = None

class CallLog(BaseModel):
    log_id: str
    timestamp_ist: str
    loan_id: str
    phone_masked: str
    language: str
    channel: str
    status: str
    allowed: bool
    block_reason: Optional[str] = ""
    disclosure_played: bool
    disclosure_text: str
    gro_included: bool
    agent_id: str = "AUTO_AGENT_V1"
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

class FairnessReport(BaseModel):
    disparate_impact: Dict[str, Any]
    proxy_correlations: Dict[str, float]
    excluded_proxy_features: List[str]
    allowed_scoring_features: List[str]
    pass_all_fairness_checks: bool
