"""
Cashfree Sandbox PG Links Client & Webhook Parser.
Supports:
1. Creating Full Payment Links (POST /pg/links)
2. Creating Hardship Partial Payment Links (link_partial_payments=True)
3. Fetching Live Link Status (GET /pg/links/{link_id})
4. Webhook payload parsing for PAYMENT_LINK_EVENT
"""
import time
import re
from typing import Dict, Any, Optional
import httpx

from app.config import (
    CASHFREE_CLIENT_ID,
    CASHFREE_CLIENT_SECRET,
    CASHFREE_BASE_URL,
    CASHFREE_API_VERSION,
    LAMBDA_WEBHOOK_URL
)

class CashfreeClient:
    def __init__(self):
        self.base_url = CASHFREE_BASE_URL
        self.headers = {
            "x-client-id": CASHFREE_CLIENT_ID,
            "x-client-secret": CASHFREE_CLIENT_SECRET,
            "x-api-version": CASHFREE_API_VERSION,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def _clean_phone(self, phone: str) -> str:
        digits = re.sub(r"\D", "", str(phone))
        if len(digits) >= 10:
            return digits[-10:]
        return "9999999999"

    def create_payment_link(
        self,
        loan_id: str,
        amount: float,
        customer_phone: str,
        customer_name: str,
        customer_email: str = "borrower@collections.example.com",
        is_partial: bool = False,
        min_partial_amount: Optional[float] = None,
        purpose: str = "Loan EMI Collections Repayment"
    ) -> Dict[str, Any]:
        clean_phone = self._clean_phone(customer_phone)
        link_id = f"link_{loan_id.replace('-', '_')}_{int(time.time())}"
        
        amt = round(float(amount), 2)
        if amt <= 0:
            amt = 100.00

        payload: Dict[str, Any] = {
            "link_id": link_id,
            "link_amount": amt,
            "link_currency": "INR",
            "link_purpose": purpose,
            "customer_details": {
                "customer_phone": clean_phone,
                "customer_name": customer_name or "Valued Borrower",
                "customer_email": customer_email or "borrower@collections.example.com"
            },
            "link_notify": {
                "send_sms": False,
                "send_email": False
            },
            "link_meta": {
                "notify_url": LAMBDA_WEBHOOK_URL
            }
        }

        if is_partial:
            payload["link_partial_payments"] = True
            min_amt = round(float(min_partial_amount or (amt * 0.20)), 2)
            payload["link_minimum_partial_amount"] = max(1.00, min_amt)
        else:
            payload["link_partial_payments"] = False

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(f"{self.base_url}/pg/links", json=payload, headers=self.headers)
                if res.status_code in [200, 201]:
                    data = res.json()
                    return {
                        "success": True,
                        "link_id": data.get("link_id", link_id),
                        "link_url": data.get("link_url", ""),
                        "link_status": data.get("link_status", "ACTIVE"),
                        "link_amount": data.get("link_amount", amt),
                        "is_partial": is_partial,
                        "min_partial_amount": payload.get("link_minimum_partial_amount"),
                        "raw": data
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Cashfree HTTP {res.status_code}: {res.text}",
                        "link_id": link_id,
                        "link_url": f"https://payments-test.cashfree.com/links/{link_id}",
                        "link_status": "MOCK_ACTIVE",
                        "is_partial": is_partial,
                        "min_partial_amount": payload.get("link_minimum_partial_amount")
                    }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "link_id": link_id,
                "link_url": f"https://payments-test.cashfree.com/links/{link_id}",
                "link_status": "MOCK_ACTIVE",
                "is_partial": is_partial,
                "min_partial_amount": payload.get("link_minimum_partial_amount")
            }

    def get_payment_link_status(self, link_id: str) -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(f"{self.base_url}/pg/links/{link_id}", headers=self.headers)
                if res.status_code == 200:
                    data = res.json()
                    return {
                        "success": True,
                        "link_id": link_id,
                        "link_status": data.get("link_status", "ACTIVE"),
                        "link_amount": data.get("link_amount", 0.0),
                        "link_amount_paid": data.get("link_amount_paid", 0.0),
                        "raw": data
                    }
                else:
                    return {
                        "success": False,
                        "error": f"HTTP {res.status_code}: {res.text}",
                        "link_id": link_id,
                        "link_status": "UNKNOWN"
                    }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "link_id": link_id,
                "link_status": "UNKNOWN"
            }

    def parse_webhook_payload(self, body: Dict[str, Any]) -> Dict[str, Any]:
        data = body.get("data", {})
        link_data = data.get("link", {}) or data.get("payment_link", {})
        link_id = link_data.get("link_id") or body.get("link_id", "")
        link_status = (link_data.get("link_status") or body.get("link_status", "")).upper()
        amount_paid = float(link_data.get("link_amount_paid", 0.0) or link_data.get("link_amount", 0.0) or body.get("link_amount", 0.0))
        return {
            "link_id": link_id,
            "link_status": link_status,
            "amount_paid": amount_paid,
            "is_paid": (link_status == "PAID"),
            "is_partial": (link_status == "PARTIALLY_PAID"),
            "is_expired": (link_status == "EXPIRED")
        }

cashfree_client = CashfreeClient()

