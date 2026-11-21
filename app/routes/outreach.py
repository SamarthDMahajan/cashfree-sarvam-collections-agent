"""
Outreach Routes.
POST /api/outreach/{id}/speak
POST /api/outreach/{id}/voice-reply
POST /api/outreach/{id}/payment-link
"""
import os
from datetime import datetime
from typing import Optional
import httpx
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel

from app.config import IST
from app.core.queue_engine import queue_engine
from app.core.signals import generate_outreach_script, extract_signals_from_note
from app.core.voice import synthesize_speech, transcribe_audio
from app.core.cashfree import cashfree_client
from app.core.compliance import evaluate_borrower_call_compliance, audit_logger

router = APIRouter(prefix="/api/outreach", tags=["Outreach"])

class PaymentLinkPayload(BaseModel):
    is_partial: bool = False
    min_partial_amount: Optional[float] = None

class RelayCallPayload(BaseModel):
    demo_phone: Optional[str] = None
    is_partial: bool = False

@router.post("/{id}/speak")
def outreach_speak(id: str, is_partial: bool = Form(False)):
    """
    Generates polite regional script (disclosure + body + GRO footer)
    and synthesizes playable base64 WAV audio via Sarvam Bulbul.
    """
    if id not in queue_engine.borrowers:
        raise HTTPException(status_code=404, detail="Borrower loan ID not found")

    b = queue_engine.borrowers[id]
    script_data = generate_outreach_script(b, is_partial=is_partial)

    # Synthesize speech
    text_to_speak = f"{script_data['disclosure']} {script_data['body']}"
    tts_res = synthesize_speech(
        text=text_to_speak,
        language_code=script_data["language"],
        speaker=script_data["speaker"]
    )

    # Record in audit trail
    comp = evaluate_borrower_call_compliance(b)
    audit_logger.record_call_event(
        loan_id=id,
        phone=str(b.get("phone", "")),
        language=script_data["language"],
        channel="VOICE_OUTREACH",
        status="SPOKEN_VIA_BULBUL",
        compliance_check=comp,
        disclosure_text=script_data["disclosure"]
    )

    return {
        "loan_id": id,
        "script": script_data,
        "audio_base64": tts_res.get("audio_base64", ""),
        "audio_data_uri": tts_res.get("audio_data_uri", ""),
        "speaker": script_data["speaker"],
        "compliance": comp
    }

@router.post("/{id}/voice-reply")
async def outreach_voice_reply(
    id: str,
    file: Optional[UploadFile] = File(None),
    transcript_text: Optional[str] = Form(None)
):
    """
    Transcribes live inbound audio via Saaras STT (`mode="codemix"`),
    extracts structured intent, updates notes, and dynamically re-ranks the queue.
    """
    if id not in queue_engine.borrowers:
        raise HTTPException(status_code=404, detail="Borrower loan ID not found")

    b = queue_engine.borrowers[id]
    lang = b.get("preferred_language", "hi-IN")

    if file:
        audio_bytes = await file.read()
        stt_res = transcribe_audio(audio_bytes, filename=file.filename or "reply.wav", language_code=lang)
        transcript = stt_res.get("transcript", "")
    else:
        transcript = transcript_text or ""

    signals = extract_signals_from_note(transcript)
    if transcript:
        queue_engine.handle_audio_update(id, transcript)

    return {
        "loan_id": id,
        "transcript": transcript,
        "signals": signals,
        "new_rank": queue_engine.borrowers[id].get("rank"),
        "queue_reformed": True
    }

@router.post("/{id}/payment-link")
def outreach_payment_link(id: str, payload: PaymentLinkPayload):
    """
    Issues a live Cashfree Sandbox payment link (Full or Hardship Partial)
    with webhook notification URL set to LAMBDA_WEBHOOK_URL.
    """
    if id not in queue_engine.borrowers:
        raise HTTPException(status_code=404, detail="Borrower loan ID not found")

    b = queue_engine.borrowers[id]
    amount = float(b.get("amount_due", 100))
    phone = str(b.get("phone", "9999999999"))
    name = str(b.get("borrower_name", "Borrower"))

    result = cashfree_client.create_payment_link(
        loan_id=id,
        amount=amount,
        customer_phone=phone,
        customer_name=name,
        is_partial=payload.is_partial,
        min_partial_amount=payload.min_partial_amount or (amount * 0.20)
    )

    if result.get("success"):
        b["last_link_id"] = result["link_id"]
        b["last_link_url"] = result["link_url"]
        b["last_link_type"] = "PARTIAL" if payload.is_partial else "FULL"
        b["last_link_status"] = result["link_status"]

    return result

@router.post("/{id}/relay-call")
async def outreach_relay_call(id: str, payload: Optional[RelayCallPayload] = None):
    """
    Places a live vernacular outbound call via Cashfree Relay to borrower or judge's demo phone.
    Enforces:
    1. RBI Jan 2027 8AM-7PM IST Calling Window Gate & Compassionate Hold check
    2. Mandated vernacular disclosure & GRO footer
    3. Logs call disclosure in 6-month compliance audit trail (Tab 4)
    4. Posts payload to RELAY_WEBHOOK_URL
    """
    if id not in queue_engine.borrowers:
        raise HTTPException(status_code=404, detail="Borrower loan ID not found")

    b = queue_engine.borrowers[id]
    comp = evaluate_borrower_call_compliance(b)
    
    target_phone = (payload.demo_phone.strip() if (payload and payload.demo_phone and payload.demo_phone.strip()) else str(b.get("phone", "9999999999")))
    is_partial = payload.is_partial if payload else False
    lang = b.get("preferred_language", "hi-IN")
    amount = float(b.get("amount_due", 100))

    # Compliance Gate Check: 8AM-7PM & Compassionate Holds
    if not comp["allowed"]:
        audit_logger.record_call_event(
            loan_id=id,
            phone=target_phone,
            language=lang,
            channel="CASHFREE_RELAY_CALL",
            status="BLOCKED_BY_COMPLIANCE",
            compliance_check=comp,
            disclosure_text=""
        )
        return {
            "success": False,
            "status": "BLOCKED",
            "loan_id": id,
            "reason": comp["reason"],
            "compliance": comp
        }

    script_data = generate_outreach_script(b, is_partial=is_partial)

    # Generate live Cashfree payment link
    link_res = cashfree_client.create_payment_link(
        loan_id=id,
        amount=amount,
        customer_phone=target_phone,
        customer_name=str(b.get("borrower_name", "Borrower")),
        is_partial=is_partial,
        min_partial_amount=max(500, amount * 0.20)
    )
    payment_link_url = link_res.get("payment_link_url") or link_res.get("link_url", "https://sandbox.cashfree.com")

    # Record in audit trail (Tab 4)
    audit_logger.record_call_event(
        loan_id=id,
        phone=target_phone,
        language=script_data["language"],
        channel="CASHFREE_RELAY_CALL",
        status="RELAY_CALL_INITIATED",
        compliance_check=comp,
        disclosure_text=script_data["disclosure"],
        metadata={
            "target_phone": target_phone,
            "payment_link_url": payment_link_url,
            "amount_due": amount
        }
    )

    relay_webhook_url = os.getenv("RELAY_WEBHOOK_URL") or os.getenv("LAMBDA_WEBHOOK_URL", "")
    
    relay_payload = {
        "event": "CASHFREE_RELAY_OUTBOUND_CALL",
        "loan_id": id,
        "borrower_name": b.get("borrower_name"),
        "phone": target_phone,
        "amount_due": amount,
        "language": script_data["language"],
        "reason": b.get("manager_reason", "Routine follow-up"),
        "script": script_data,
        "payment_link_url": payment_link_url,
        "timestamp_ist": datetime.now(IST).isoformat()
    }

    relay_status = "DISPATCHED"
    if relay_webhook_url and relay_webhook_url.startswith("http"):
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.post(relay_webhook_url, json=relay_payload)
                relay_status = f"HTTP_{resp.status_code}"
        except Exception as e:
            relay_status = f"RELAY_SIMULATED ({str(e)[:40]})"
    else:
        relay_status = "RELAY_URL_NOT_CONFIGURED (LOCAL_SIMULATION)"

    return {
        "success": True,
        "status": "CALL_INITIATED",
        "loan_id": id,
        "borrower_name": b.get("borrower_name"),
        "target_phone": target_phone,
        "language": script_data["language"],
        "speaker": script_data["speaker"],
        "script": script_data,
        "payment_link_url": payment_link_url,
        "compliance": comp,
        "relay_dispatch": {
            "status": relay_status,
            "url": relay_webhook_url
        }
    }

