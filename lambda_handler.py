"""
AWS Lambda Handler for samarthdmahajan-collections-agent (Python 3.12, ap-south-1).
Serves:
1. Cashfree Relay Inbound Webhooks (PAYMENT_LINK_EVENT)
2. Live HTTP API proxy events and raw JSON test events
3. Fair scoring, RBI Jan 2027 compliance gates, and script generation
CRITICAL: Never returns binary images (Cashfree Relay does not support images).
Always returns standard JSON response: {statusCode, headers, body}.
"""
import json
import os
from typing import Dict, Any

from app.compliance import (
    evaluate_borrower_call_compliance,
    check_calling_hours,
    check_compassionate_hold,
    check_reconciliation_hold,
    get_mandatory_recording_disclosure,
    get_gro_footer
)
from app.fair_ranker import calculate_borrower_score, rank_borrowers
from app.nlp_extractor import extract_signals_from_note

def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    Main Lambda entrypoint handling both HTTP API proxy events and direct JSON payloads.
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

    # Determine action
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
            "gro_reference": get_gro_footer()
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
        name = borrower.get("borrower_name", "Valued Customer")
        amount = float(borrower.get("amount_due", 0))
        lang = borrower.get("preferred_language", "hi-IN")
        disclosure = get_mandatory_recording_disclosure(lang)
        gro_footer = get_gro_footer()
        
        body = f"Hello {name}, your loan balance is ₹{amount:,.0f}. Kindly settle via the secure Cashfree UPI link."
        if lang == "hi-IN":
            body = f"नमस्ते {name} जी, आपके बैंक खाते में ₹{amount:,.0f} की देय राशि लंबित है। कृपया इसे कैशफ्री यूपीआई लिंक से भरें।"
        elif lang == "kn-IN":
            body = f"ನಮಸ್ಕಾರ {name} ಅವರೇ, ನಿಮ್ಮ ಸಾಲದ ಖಾತೆಯಲ್ಲಿ ₹{amount:,.0f} ಬಾಕಿ ಇದೆ. ದಯವಿಟ್ಟು ಕ್ಯಾಶ್‌ಫ್ರೀ ಯುಪಿಐ ಬಳಸಿ."
        elif lang == "ta-IN":
            body = f"வணக்கம் {name}, உங்கள் கடன் கணக்கில் ₹{amount:,.0f} நிலுவை உள்ளது. கேஷ்ஃப்ரீ லிங்க் மூலம் செலுத்தலாம்."

        full_script = f"{disclosure}\n\n{body}\n\n[{gro_footer}]"
        return {
            "statusCode": 200,
            "headers": headers,
            "body": json.dumps({
                "language": lang,
                "disclosure": disclosure,
                "body": body,
                "gro_footer": gro_footer,
                "full_script": full_script
            })
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
            "gro_contact": get_gro_footer()
        })
    }
