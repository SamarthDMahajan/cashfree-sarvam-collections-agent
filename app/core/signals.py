"""
Multilingual Signals & Intent Extraction Engine.
Wraps `sarvam-105b-conversations` with high-velocity code-mixed regex parsing.
Extracts:
1. Intent Category (PROMISE_TO_PAY, ALREADY_PAID_BRANCH, MEDICAL_EMERGENCY,
   HARDSHIP_PARTIAL_PAYER, SILENT_PAYER, DISPUTE_REFUSAL, GENERAL_FOLLOWUP)
2. Intent Score (0.0 to 1.0)
3. Extracted Salary/Promise Day (e.g. 5, 10, tomorrow)
4. Recommended Action (FULL_LINK, PARTIAL_LINK, COMPASSIONATE_HOLD, RECONCILIATION_HOLD)
5. Empathetic Regional Script Generation with statutory disclosures
"""
import re
import json
import httpx
from typing import Dict, Any, Optional

from app.config import (
    SARVAM_API_KEY,
    SARVAM_BASE_URL,
    MANDATORY_DISCLOSURES,
    RBI_GRO_CONTACT
)
from app.core.compliance import guard_tone_and_ethics

LANGUAGE_SPEAKERS = {
    "hi-IN": "priya_hi_recovery",
    "kn-IN": "chaitra_kn_conversation",
    "ta-IN": "vijay_ta_narration",
    "en-IN": "shubh_enhi_banking"
}

def extract_signals_from_note(note: str) -> Dict[str, Any]:
    text = (note or "").strip().lower()
    if not text:
        return {
            "intent": "SILENT_PAYER",
            "intent_score": 0.50,
            "promise_day": None,
            "recommended_action": "FULL_LINK",
            "summary": "No note available; scoring primarily on repayment history and DPD."
        }

    # 1. Reconciliation Hold ('already paid at branch')
    if any(k in text for k in [
        "branch mein", "branch me", "branch nalli", "branch la", "counter pe",
        "already paid", "jama kar", "jama kiya", "receipt hai", "de diya", "kottidini", "kuduthen"
    ]):
        return {
            "intent": "ALREADY_PAID_BRANCH",
            "intent_score": 0.05,
            "promise_day": None,
            "recommended_action": "RECONCILIATION_HOLD",
            "summary": "Borrower claims payment completed at branch/counter. Reconciliation hold triggered."
        }

    # 2. Medical / Hardship Compassionate Hold
    if any(k in text for k in [
        "hospital", "admit", "icu", "surgery", "accident", "bimari", "ilaj",
        "dawa", "death", "passed away", "cremation", "funeral", "shaadi", "wedding"
    ]):
        return {
            "intent": "MEDICAL_EMERGENCY",
            "intent_score": 0.0,
            "promise_day": None,
            "recommended_action": "COMPASSIONATE_HOLD",
            "summary": "Medical emergency/life distress detected. Compassionate hold applied."
        }

    # 3. Hardship / Partial Payment Requested
    if any(k in text for k in [
        "thoda", "kam paise", "aadha", "half", "partial", "installment", "kist",
        "paise kam hai", "swalpa", "konjam", "salary cut", "job loss", "tight"
    ]):
        return {
            "intent": "HARDSHIP_PARTIAL_PAYER",
            "intent_score": 0.72,
            "promise_day": None,
            "recommended_action": "PARTIAL_LINK",
            "summary": "Borrower expresses liquidity strain but willingness to pay partial amount. Recommended Hardship Partial Link."
        }

    # 4. Promise to Pay with Date / Salary Mention
    salary_promise = any(k in text for k in [
        "salary", "sambala", "salry", "pay", "dedunga", "de dunga", "kardunga",
        "kar dunga", "bhar dunga", "madtini", "panren", "tomorrow", "kal", "naale", "parso"
    ])
    
    day_match = re.search(r'(\b\d{1,2})(?:st|nd|rd|th)?\s*(?:ko|tarik|tareekh|th|date|\b)', text)
    extracted_day = int(day_match.group(1)) if day_match and 1 <= int(day_match.group(1)) <= 31 else None

    if salary_promise:
        intent_score = 0.88 if extracted_day else 0.78
        return {
            "intent": "PROMISE_TO_PAY",
            "intent_score": intent_score,
            "promise_day": extracted_day,
            "recommended_action": "FULL_LINK",
            "summary": f"Clear commitment to pay{' around date ' + str(extracted_day) if extracted_day else ''} post-salary."
        }

    # 5. Dispute / Refusal
    if any(k in text for k in ["nahi dunga", "fraud call", "galat amount", "dispute", "court", "complaint"]):
        return {
            "intent": "DISPUTE_REFUSAL",
            "intent_score": 0.15,
            "promise_day": None,
            "recommended_action": "MANAGER_ESCALATION",
            "summary": "Borrower disputes charges or refuses payment. Supervisor intervention needed."
        }

    return {
        "intent": "GENERAL_FOLLOWUP",
        "intent_score": 0.55,
        "promise_day": None,
        "recommended_action": "FULL_LINK",
        "summary": "Standard customer follow-up required."
    }

def extract_signals_with_sarvam_llm(transcript_or_note: str) -> Dict[str, Any]:
    """Optional deep LLM extraction via Sarvam-105b-conversations for complex spoken turns."""
    if not SARVAM_API_KEY:
        return extract_signals_from_note(transcript_or_note)

    prompt = f"""You are a banking collections signal extraction model.
Analyze this code-mixed borrower response:
"{transcript_or_note}"

Return valid JSON with keys:
"intent": one of ["PROMISE_TO_PAY", "ALREADY_PAID_BRANCH", "MEDICAL_EMERGENCY", "HARDSHIP_PARTIAL_PAYER", "SILENT_PAYER", "DISPUTE_REFUSAL", "GENERAL_FOLLOWUP"],
"intent_score": float between 0.0 and 1.0,
"promise_day": integer day of month or null,
"recommended_action": one of ["FULL_LINK", "PARTIAL_LINK", "COMPASSIONATE_HOLD", "RECONCILIATION_HOLD", "MANAGER_ESCALATION"],
"summary": brief 1-sentence explanation.
JSON only:"""

    try:
        headers = {
            "api-subscription-key": SARVAM_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "model": "sarvam-105b-conversations",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        with httpx.Client(timeout=8.0) as client:
            res = client.post(f"{SARVAM_BASE_URL}/v1/chat/completions", json=payload, headers=headers)
            if res.status_code == 200:
                raw_content = res.json()["choices"][0]["message"]["content"]
                # Parse JSON block
                clean_json = re.search(r'\{.*\}', raw_content, re.DOTALL)
                if clean_json:
                    return json.loads(clean_json.group(0))
    except Exception:
        pass

    # Fast fallback
    return extract_signals_from_note(transcript_or_note)

def generate_outreach_script(
    borrower: Dict[str, Any],
    is_partial: bool = False
) -> Dict[str, Any]:
    """Generates empathetic regional outreach script with mandatory disclosure and statutory GRO footer."""
    name = borrower.get("borrower_name", "Valued Customer")
    amount = float(borrower.get("amount_due", 0))
    lang = borrower.get("preferred_language", "hi-IN")
    disclosure = MANDATORY_DISCLOSURES.get(lang, MANDATORY_DISCLOSURES["en-IN"])
    gro_footer = RBI_GRO_CONTACT["disclosure_text"]

    if lang == "hi-IN":
        if is_partial:
            body = f"नमस्ते {name} जी, आपके ऋण खाते में ₹{amount:,.0f} का बकाया है। आपकी सुविधा के लिए हम आंशिक भुगतान (Partial Payment) का विकल्प दे रहे हैं। क्या हम आपको तत्काल यूपीआई भुगतान लिंक भेजें?"
            translation = f"Hello {name}, ₹{amount:,.0f} is pending on your loan account. For your convenience, we offer a partial payment option. Shall we send the payment link?"
        else:
            body = f"नमस्ते {name} जी, आपके ऋण खाते में ₹{amount:,.0f} की देय राशि लंबित है। कृपया इसे समय पर चुकाने के लिए सुरक्षित कैशफ्री यूपीआई लिंक का उपयोग करें।"
            translation = f"Hello {name}, an overdue amount of ₹{amount:,.0f} is pending on your loan account. Kindly use the secure Cashfree UPI link to clear it."
    elif lang == "kn-IN":
        if is_partial:
            body = f"ನಮಸ್ಕಾರ {name} ಅವರೇ, ನಿಮ್ಮ ಸಾಲದ ಖಾತೆಯಲ್ಲಿ ₹{amount:,.0f} ಬಾಕಿ ಇದೆ. ನಿಮ್ಮ ಅನುಕೂಲಕ್ಕಾಗಿ ಭಾಗಶಃ ಪಾವತಿ (Partial Payment) ಅವಕಾಶ ನೀಡುತ್ತಿದ್ದೇವೆ. ಲಿಂಕ್ ಕಳುಹಿಸಬೇಕೆ?"
            translation = f"Hello {name}, ₹{amount:,.0f} is due on your loan. For your convenience we offer a partial payment option. Shall we send the link?"
        else:
            body = f"ನಮಸ್ಕಾರ {name} ಅವರೇ, ನಿಮ್ಮ ಸಾಲದ ಖಾತೆಯಲ್ಲಿ ₹{amount:,.0f} ಬಾಕಿ ಪಾವತಿ ಇದೆ. ದಯವಿಟ್ಟು ಸುಲಭವಾಗಿ ಪಾವತಿಸಲು ಕ್ಯಾಶ್‌ಫ್ರೀ ಯುಪಿಐ ಲಿಂಕ್ ಬಳಸಿ."
            translation = f"Hello {name}, ₹{amount:,.0f} is pending on your loan account. Please use the Cashfree UPI link to settle easily."
    elif lang == "ta-IN":
        if is_partial:
            body = f"வணக்கம் {name}, உங்கள் கடன் கணக்கில் ₹{amount:,.0f} நிலுவையில் உள்ளது. உங்கள் வசதிக்காக பகுதி கட்டணம் (Partial Payment) செலுத்தும் வசதியை வழங்குகிறோம். லிங்க் அனுப்பவா?"
            translation = f"Hello {name}, ₹{amount:,.0f} is pending on your loan. We offer a partial payment option for your convenience. Shall we send the link?"
        else:
            body = f"வணக்கம் {name}, உங்கள் கடன் கணக்கில் ₹{amount:,.0f} நிலுவை தொகை உள்ளது. பாதுகாப்பான கேஷ்ஃப்ரீ யூபிஐ லிங்க் மூலம் எளிதாக செலுத்தலாம்."
            translation = f"Hello {name}, an overdue amount of ₹{amount:,.0f} is due. You can pay securely via the Cashfree UPI link."
    else: # en-IN
        if is_partial:
            body = f"Hello {name}, an outstanding balance of ₹{amount:,.0f} is pending on your loan account. To support you, we are pleased to offer a flexible partial payment option today. May we send you the payment link?"
            translation = body
        else:
            body = f"Hello {name}, a gentle reminder that ₹{amount:,.0f} is currently overdue on your loan account. You can securely settle it instantly using our Cashfree UPI payment link."
            translation = body

    full_script = f"{disclosure}\n\n{body}\n\n[RBI Grievance Redressal: {gro_footer}]"
    tone_check = guard_tone_and_ethics(full_script)

    return {
        "language": lang,
        "speaker": LANGUAGE_SPEAKERS.get(lang, "priya_hi_recovery"),
        "disclosure": disclosure,
        "body": body,
        "translation_en": translation,
        "gro_footer": gro_footer,
        "full_script": full_script,
        "tone_passed": tone_check["passed"]
    }
