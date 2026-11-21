"""
Dynamic Queue Engine & Hold Lane Manager.
Manages:
1. In-memory state, dynamic re-ranking upon payment, lapse, audio STT, and holds.
2. Computation of rank deltas (↑ / ↓) against snapshots.
3. Separation of active queue (Top 360) vs Hold Lanes (Compassionate / Recon).
"""
from typing import List, Dict, Any, Optional
from app.core.ranker import rank_borrowers

class QueueEngine:
    def __init__(self):
        self.borrowers: Dict[str, Dict[str, Any]] = {}
        self.ranked_queue: List[Dict[str, Any]] = []
        self.previous_ranks: Dict[str, int] = {}
        self.last_event: Optional[Dict[str, Any]] = None

    def load_borrowers(self, borrower_list: List[Dict[str, Any]]) -> None:
        self.borrowers = {str(b["loan_id"]): dict(b) for b in borrower_list}
        self.re_rank(event_description="Initial queue load")

    def re_rank(self, event_description: str = "") -> List[Dict[str, Any]]:
        borrower_data = list(self.borrowers.values())
        new_ranked = rank_borrowers(borrower_data, top_slots=360)

        new_ranks: Dict[str, int] = {}
        for item in new_ranked:
            lid = str(item["loan_id"])
            current_rank = item["rank"]
            new_ranks[lid] = current_rank
            
            # Rank Delta: Previous Rank - Current Rank
            # (e.g. Previous 15, Now 10 -> +5 = Moved UP)
            if lid in self.previous_ranks:
                item["rank_delta"] = self.previous_ranks[lid] - current_rank
            else:
                item["rank_delta"] = 0

        self.previous_ranks = new_ranks
        self.ranked_queue = new_ranked
        self.last_event = {
            "description": event_description,
            "timestamp": new_ranked[0].get("timestamp_ist", "") if new_ranked else ""
        }
        return self.ranked_queue

    def handle_payment_event(self, loan_id: str, amount_paid: float, is_full: bool = True) -> Dict[str, Any]:
        lid = str(loan_id)
        if lid not in self.borrowers:
            return {"success": False, "error": f"Loan {loan_id} not found"}

        b = self.borrowers[lid]
        prev_amt = float(b.get("amount_due", 0.0))
        new_amt = max(0.0, prev_amt - float(amount_paid))
        b["amount_due"] = new_amt

        if is_full or new_amt <= 0.0:
            b["status"] = "PAID"
            b["status_badge"] = "PAID"
            b["notes"] = f"Payment verified via Cashfree (₹{amount_paid:,.2f} received). Account closed."
        else:
            b["status"] = "PARTIALLY_PAID"
            b["status_badge"] = "PARTIAL_PAID"
            b["past_promises_kept_ratio"] = min(1.0, float(b.get("past_promises_kept_ratio", 0.5)) + 0.20)
            b["notes"] = f"Hardship partial payment of ₹{amount_paid:,.2f} verified. Balance due: ₹{new_amt:,.2f}."

        self.re_rank(event_description=f"Payment received for {lid}: ₹{amount_paid:,.2f} ({'Full' if is_full else 'Partial'})")
        return {"success": True, "loan_id": lid, "remaining_amount": new_amt, "status": b["status"]}

    def handle_promise_lapse(self, loan_id: str) -> Dict[str, Any]:
        lid = str(loan_id)
        if lid not in self.borrowers:
            return {"success": False, "error": f"Loan {loan_id} not found"}

        b = self.borrowers[lid]
        b["broken_promises_count"] = int(b.get("broken_promises_count", 0)) + 1
        b["past_promises_kept_ratio"] = max(0.10, float(b.get("past_promises_kept_ratio", 0.5)) - 0.25)
        b["notes"] = f"Lapsed promise on payment date. Broken promises count increased to {b['broken_promises_count']}."

        self.re_rank(event_description=f"Promise lapsed for loan {lid}")
        return {"success": True, "loan_id": lid, "broken_promises": b["broken_promises_count"]}

    def handle_reconciliation_claim(self, loan_id: str) -> Dict[str, Any]:
        lid = str(loan_id)
        if lid not in self.borrowers:
            return {"success": False, "error": f"Loan {loan_id} not found"}

        b = self.borrowers[lid]
        b["notes"] = "Borrower claims: 'branch mein de diya cash receipt hai'. Outbound halted pending ops verification."
        self.re_rank(event_description=f"Branch reconciliation hold triggered for {lid}")
        return {"success": True, "loan_id": lid, "status": "RECONCILIATION_HOLD"}

    def handle_audio_update(self, loan_id: str, transcript: str) -> Dict[str, Any]:
        lid = str(loan_id)
        if lid not in self.borrowers:
            return {"success": False, "error": f"Loan {loan_id} not found"}

        b = self.borrowers[lid]
        b["notes"] = transcript
        b["inbound_recency_days"] = 0
        self.re_rank(event_description=f"Live inbound audio processed for {lid}")
        return {"success": True, "loan_id": lid, "new_rank": self.borrowers[lid].get("rank")}

    def get_top_queue(self, limit: int = 360) -> List[Dict[str, Any]]:
        return self.ranked_queue[:limit]

    def get_hold_lanes(self) -> Dict[str, List[Dict[str, Any]]]:
        compassionate = [b for b in self.ranked_queue if "COMPASSIONATE_HOLD" in str(b.get("status_badge", ""))]
        reconciliation = [b for b in self.ranked_queue if "RECONCILIATION_HOLD" in str(b.get("status_badge", ""))]
        resolved_paid = [b for b in self.ranked_queue if b.get("status") == "PAID"]
        return {
            "compassionate_holds": compassionate,
            "reconciliation_holds": reconciliation,
            "resolved_paid": resolved_paid
        }

    def get_summary_metrics(self) -> Dict[str, Any]:
        total_accounts = len(self.ranked_queue)
        top_360 = self.ranked_queue[:360]
        
        total_book_value = sum(float(b.get("amount_due", 0)) for b in self.ranked_queue)
        top_360_value = sum(float(b.get("amount_due", 0)) for b in top_360)
        
        paid_count = sum(1 for b in self.ranked_queue if b.get("status") == "PAID")
        hold_count = sum(1 for b in self.ranked_queue if "HOLD" in str(b.get("status_badge", "")))
        explore_count = sum(1 for b in top_360 if b.get("is_exploration", False))

        return {
            "total_borrowers": total_accounts,
            "top_call_slots": len(top_360),
            "total_book_value": round(total_book_value, 2),
            "top_360_target_value": round(top_360_value, 2),
            "paid_accounts": paid_count,
            "on_hold_accounts": hold_count,
            "exploration_slots_allocated": explore_count,
            "last_event": self.last_event
        }

queue_engine = QueueEngine()
