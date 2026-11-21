"""
AWS Lambda Handler for samarthdmahajan-collections-agent (Python 3.12, ap-south-1).
Serves:
1. Cashfree Relay Inbound Webhooks (PAYMENT_LINK_EVENT)
2. Live HTTP API proxy events and raw JSON test events
3. Fair scoring, RBI Jan 2027 compliance gates, and script generation

CRITICAL: 100% Python Standard Library (zero external dependencies: no pydantic, httpx, pandas, sarvamai).
Never returns binary images (Cashfree Relay does not support images).
Always returns standard JSON response: {statusCode, headers, body}.
"""
import json
import os
import re
import math
import random
from datetime import datetime, timezone, timedelta, time
from typing import Dict, Any, List, Optional

# IST Timezone (UTC + 05:30)
IST = timezone(timedelta(hours=5, minutes=30))
RBI_CALLING_WINDOW_START = time(8, 0)
RBI_CALLING_WINDOW_END = time(19, 0)

GRO_FOOTER = (
    "Principal Nodal Officer: nodalofficer@nbfe-recovery.in | "
    "Tel: 1800-XXX-XXXX | RBI CMS Portal: https://cms.rbi.org.in (Toll-Free 14448)"
)

MANDATORY_DISCLOSURES = {
    "hi-IN": "यह कॉल गुणवत्ता, प्रशिक्षण और विनियामक अनुपालन के लिए रिकॉर्ड की जा रही है।",
    "kn-IN": "ಈ ಕರೆಯನ್ನು ಗುಣಮಟ್ಟ, ತರಬೇತಿ ಮತ್ತು ನಿಯಂತ್ರಕ ಅನುಸರಣೆಗಾಗಿ ರೆಕಾರ್ಡ್ ಮಾಡಲಾಗುತ್ತಿದೆ.",
    "en-IN": "This call is being recorded for quality assurance, training, and regulatory compliance."
}

ALLOWED_SCORING_FEATURES = [
    "past_promises_kept_ratio",
    "historical_pay_rate",
    "inbound_recency_days",
    "dpd",
    "broken_promises_count"
]

def check_calling_hours(check_time: Optional[datetime] = None, borrower_opted_in: bool = False) -> Dict[str, Any]:
    now = check_time or datetime.now(IST)
    current_time = now.timetz()
    current_naive_time = time(current_time.hour, current_time.minute, current_time.second)
    
    in_window = (RBI_CALLING_WINDOW_START <= current_naive_time <= RBI_CALLING_WINDOW_END)
    if in_window:
        return {
            "allowed": True,
            "code": "WINDOW_PERMITTED",
            "reason": f"Current IST time ({now.strftime('%I:%M %p')}) is within permissible calling hours (08:00 AM - 07:00 PM IST)."
        }
    if borrower_opted_in:
        return {
            "allowed": True,
            "code": "WINDOW_OVERRIDE_OPT_IN",
            "reason": f"Outside standard window ({now.strftime('%I:%M %p')}), but call permitted due to verified borrower explicit opt-in."
        }
    return {
        "allowed": False,
        "code": "BLOCKED_CALL_WINDOW_HOURS",
        "reason": f"Call blocked: Current time ({now.strftime('%I:%M %p')} IST) is outside RBI permissible calling window (08:00 AM - 07:00 PM). Explicit borrower opt-in required."
    }

def check_compassionate_hold(notes: str) -> Dict[str, Any]:
    text = (notes or "").lower()
    medical_patterns = ["hospital", "admit", "icu", "surgery", "operation", "accident", "medical emergency", "doctor", "bimari", "ilaj", "dawa"]
    bereavement_patterns = ["death", "died", "passed away", "funeral", "rip", "cremation", "shok"]
    wedding_patterns = ["wedding", "shaadi", "marriage", "vivah", "maduve"]

    for p in medical_patterns:
        if p in text:
            return {"is_hold": True, "category": "MEDICAL_EMERGENCY", "hold_days": 30, "reason": f"Compassionate Hold active: Medical distress/hospitalization reported ('{p}'). All calls suspended for 30 days."}
    for p in bereavement_patterns:
        if p in text:
            return {"is_hold": True, "category": "BEREAVEMENT", "hold_days": 30, "reason": f"Compassionate Hold active: Bereavement reported ('{p}'). Collections suspended for 30 days."}
    for p in wedding_patterns:
        if p in text:
            return {"is_hold": True, "category": "WEDDING_HARDSHIP", "hold_days": 15, "reason": "Grace period active: Wedding event in family reported. Outbound calls delayed by 15 days."}
    return {"is_hold": False, "category": None, "hold_days": 0, "reason": ""}

def check_reconciliation_hold(notes: str) -> Dict[str, Any]:
    text = (notes or "").lower()
    branch_patterns = [
        "branch mein de diya", "branch me pay kiya", "branch me jama kiya",
        "already paid at branch", "counter pe diya", "counter par jama",
        "cash deposited", "paid cash", "paise de diye", "already paid", "receipt hai"
    ]
    for p in branch_patterns:
        if p in text:
            return {"is_hold": True, "category": "ALREADY_PAID_RECONCILIATION", "hold_days": 7, "reason": f"Reconciliation Hold active: Borrower stated payment made ('{p}'). Halted outbound calls pending branch transaction verification."}
    return {"is_hold": False, "category": None, "hold_days": 0, "reason": ""}

def evaluate_borrower_call_compliance(borrower: Dict[str, Any], check_time: Optional[datetime] = None) -> Dict[str, Any]:
    opted_in = bool(borrower.get("borrower_opted_in", False))
    window_eval = check_calling_hours(check_time=check_time, borrower_opted_in=opted_in)
    if not window_eval["allowed"]:
        return {"allowed": False, "stage": "TIME_WINDOW_GATE", "code": window_eval["code"], "reason": window_eval["reason"], "gro_footer": GRO_FOOTER}

    notes = str(borrower.get("notes") or "")
    comp_eval = check_compassionate_hold(notes)
    if comp_eval["is_hold"]:
        return {"allowed": False, "stage": "COMPASSIONATE_HOLD", "code": comp_eval["category"], "reason": comp_eval["reason"], "hold_days": comp_eval["hold_days"], "gro_footer": GRO_FOOTER}

    recon_eval = check_reconciliation_hold(notes)
    if recon_eval["is_hold"]:
        return {"allowed": False, "stage": "RECONCILIATION_HOLD", "code": recon_eval["category"], "reason": recon_eval["reason"], "hold_days": recon_eval["hold_days"], "gro_footer": GRO_FOOTER}

    lang = borrower.get("preferred_language", "hi-IN")
    disclosure = MANDATORY_DISCLOSURES.get(lang, MANDATORY_DISCLOSURES["en-IN"])
    return {
        "allowed": True,
        "stage": "COMPLIANCE_PASSED",
        "code": "OUTREACH_PERMITTED",
        "reason": "Borrower is clear for polite vernacular outreach within statutory calling window.",
        "mandatory_disclosure": disclosure,
        "gro_footer": GRO_FOOTER
    }

def calculate_borrower_score(b: Dict[str, Any]) -> float:
    kept_ratio = float(b.get("past_promises_kept_ratio", 0.5))
    hist_pay = float(b.get("historical_pay_rate", 0.5))
    inbound_recency = float(b.get("inbound_recency_days", 15.0))
    dpd = float(b.get("dpd", 30.0))
    broken = float(b.get("broken_promises_count", 0.0))

    recency_norm = max(0.0, 1.0 - (inbound_recency / 30.0))
    dpd_norm = max(0.0, 1.0 - (dpd / 90.0))
    broken_norm = max(0.0, 1.0 - (broken * 0.25))

    score = (
        0.35 * kept_ratio +
        0.25 * hist_pay +
        0.20 * recency_norm +
        0.10 * dpd_norm +
        0.10 * broken_norm
    )
    return round(float(score) * 100.0, 2)

def rank_borrowers(borrower_list: List[Dict[str, Any]], top_slots: int = 360, epsilon: float = 0.10) -> List[Dict[str, Any]]:
    scored = []
    for b in borrower_list:
        item = dict(b)
        item["priority_score"] = calculate_borrower_score(item)
        scored.append(item)

    scored.sort(key=lambda x: x["priority_score"], reverse=True)
    num_explore = max(1, int(top_slots * epsilon))
    num_exploit = top_slots - num_explore

    exploit_batch = scored[:num_exploit]
    remaining = scored[num_exploit:]
    
    rng = random.Random(42)
    explore_batch = rng.sample(remaining, min(num_explore, len(remaining))) if remaining else []

    for item in exploit_batch:
        item["is_exploration"] = False
    for item in explore_batch:
        item["is_exploration"] = True

    combined = exploit_batch + explore_batch
    for rank_idx, item in enumerate(combined, start=1):
        item["rank"] = rank_idx

    return combined

def generate_outreach_script(borrower: Dict[str, Any]) -> Dict[str, Any]:
    lang = borrower.get("preferred_language", "hi-IN")
    name = borrower.get("borrower_name", "Valued Customer")
    amount = float(borrower.get("amount_due", 0.0))
    amt_str = f"₹{amount:,.0f}"

    disclosure = MANDATORY_DISCLOSURES.get(lang, MANDATORY_DISCLOSURES["en-IN"])
    if lang == "kn-IN":
        body = f"ನಮಸ್ಕಾರ {name} ಅವರೇ, ನಿಮ್ಮ ಖಾತೆಯಲ್ಲಿ {amt_str} ಬಾಕಿ ಇದೆ. ನಿಮಗೆ ಅನುಕೂಲಕರವಾದ ಪಾವತಿ ಲಿಂಕ್ ಕಳುಹಿಸಲು ನಾವು ಇಲ್ಲಿದ್ದೇವೆ."
    elif lang == "hi-IN":
        body = f"नमस्ते {name} जी, आपके खाते में {amt_str} की देय राशि लंबित है। आपकी सुविधा के लिए हम डिजिटल भुगतान लिंक भेज रहे हैं।"
    else:
        body = f"Hello {name}, your outstanding dues of {amt_str} are pending. We have generated a secure payment link for your convenience."

    return {
        "language": lang,
        "disclosure": disclosure,
        "body": body,
        "gro_footer": GRO_FOOTER
    }

def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    Main Lambda entrypoint handling both HTTP API proxy events and direct JSON payloads.
    Guaranteed zero external library dependencies.
    """
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, x-api-version, x-client-id"
    }

    # Handle OPTIONS preflight
    http_method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method", "")
    if http_method == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": headers,
            "body": json.dumps({"status": "OK"})
        }

    # Parse payload body
    payload: Dict[str, Any] = {}
    if "body" in event and event["body"] is not None:
        body_data = event["body"]
        if isinstance(body_data, str):
            try:
                payload = json.loads(body_data)
            except Exception:
                payload = {"raw_text": body_data}
        elif isinstance(body_data, dict):
            payload = body_data
    else:
        payload = event

    action = payload.get("action", "").lower()
    event_type = payload.get("type", "")

    # 1. Cashfree Webhook: PAYMENT_LINK_EVENT
    if event_type == "PAYMENT_LINK_EVENT" or "data" in payload or "link_id" in payload:
        data = payload.get("data", {})
        link_data = data.get("link", {}) or data.get("payment_link", {})
        link_id = link_data.get("link_id") or payload.get("link_id", "unknown_link")
        link_status = (link_data.get("link_status") or payload.get("link_status", "PAID")).upper()
        amount_paid = float(link_data.get("link_amount_paid", 0.0) or link_data.get("link_amount", 0.0) or payload.get("link_amount", 0.0))

        response_body = {
            "status": "SUCCESS",
            "event": "CASHFREE_RELAY_PAYMENT_PROCESSED",
            "link_id": link_id,
            "link_status": link_status,
            "amount_paid": amount_paid,
            "queue_action": "DROP_FROM_CALL_QUEUE" if link_status == "PAID" else "REDUCE_BALANCE_PARTIAL",
            "gro_reference": GRO_FOOTER
        }
        return {
            "statusCode": 200,
            "headers": headers,
            "body": json.dumps(response_body)
        }

    # 2. RBI Jan 2027 Compliance Evaluation
    if action == "compliance_check":
        borrower = payload.get("borrower", {})
        comp = evaluate_borrower_call_compliance(borrower)
        return {
            "statusCode": 200,
            "headers": headers,
            "body": json.dumps({"borrower_id": borrower.get("loan_id"), "compliance": comp})
        }

    # 3. Fair Ranker Ranking of batch
    if action == "rank":
        borrowers = payload.get("borrowers", [])
        top_slots = int(payload.get("top_slots", 360))
        ranked = rank_borrowers(borrowers, top_slots=top_slots)
        return {
            "statusCode": 200,
            "headers": headers,
            "body": json.dumps({"count": len(ranked), "ranked_queue": ranked})
        }

    # 4. Generate Polite Regional Script
    if action == "generate_script":
        borrower = payload.get("borrower", {})
        script = generate_outreach_script(borrower)
        return {
            "statusCode": 200,
            "headers": headers,
            "body": json.dumps(script)
        }

    # 5. Default Health & Relay Ping
    return {
        "statusCode": 200,
        "headers": headers,
        "body": json.dumps({
            "service": "samarthdmahajan-collections-agent",
            "status": "HEALTHY",
            "rbi_version": "JAN_2027_COMPLIANT",
            "supported_actions": ["compliance_check", "rank", "generate_script", "PAYMENT_LINK_EVENT"],
            "gro_contact": GRO_FOOTER
        })
    }
