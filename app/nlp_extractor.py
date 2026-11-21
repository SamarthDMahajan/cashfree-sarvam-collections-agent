"""
Multilingual & Code-Mixed NLP Intent & Signal Extractor.
Supports Hinglish, Kannada, Tamil, and English notes and voice transcripts.
Extracts:
1. Intent Category (PROMISE_TO_PAY, ALREADY_PAID_BRANCH, MEDICAL_EMERGENCY,
   HARDSHIP_PARTIAL_PAYER, SILENT_PAYER, DISPUTE_REFUSAL, GENERAL_FOLLOWUP)
2. Intent Score (0.0 to 1.0)
3. Extracted Salary/Promise Day (e.g. 5, 10, tomorrow)
4. Recommended Action (e.g. FULL_LINK, PARTIAL_LINK, COMPASSIONATE_HOLD, RECONCILIATION_HOLD)
"""
import re
from typing import Dict, Any, Optional

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
    
    # Extract date day (e.g. '5th', '10 tarik', '25 ko')
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

