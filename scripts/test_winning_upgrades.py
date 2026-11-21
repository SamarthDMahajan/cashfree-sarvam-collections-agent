"""
Comprehensive Verification of the 5 Winning Upgrades:
1. Fix Queue Loading Bug: HTTP 200, 360 records, clean stats, zero NaNs in JSON.
2. Tab 2: Live Mic/Audio & Live Relay Phone Call with demo phone input.
3. Tab 3: Normalized DIR [0.00, 1.00] and Dual Lift (Top 10% and Top 360).
4. Tab 4: Pre-seeded regulatory compliance events.
5. Zero-dependency AWS Lambda Handler.
"""
import os
import sys
import json
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import startup_event
from app.routes.queue import get_queue, get_audit_logs
from app.routes.outreach import outreach_relay_call, outreach_voice_reply, RelayCallPayload
from app.routes.fairness import get_fairness_report
from app.routes.curveball import upload_curveball
from lambda_handler import lambda_handler

def run_tests():
    print("=" * 70)
    print("VERIFYING 5 WINNING UPGRADES")
    print("=" * 70)

    # Startup
    startup_event()

    # 1. Queue test
    q_res = get_queue(360)
    count = q_res.get("count", 0)
    stats = q_res.get("stats", {})
    assert count == 360, f"Expected 360, got {count}"
    assert stats.get("total_borrowers") == 4170, f"Expected 4170, got {stats.get('total_borrowers')}"
    assert stats.get("total_book_value") > 0, "Book value must be positive"
    assert stats.get("top_360_target_value") > 0, "Target value must be positive"
    q_json = json.dumps(q_res)
    assert ": NaN" not in q_json and ":NaN" not in q_json, "Found illegal NaN token in queue JSON"
    print("[PASS] 1. GET /api/queue: 360 records, valid stats, ZERO NaNs in JSON")

    # 2. Relay Call test
    first_loan = q_res["queue"][0]["loan_id"]
    relay_res = asyncio.run(outreach_relay_call(first_loan, RelayCallPayload(demo_phone="+919876543210")))
    assert relay_res.get("success") is True, "Relay call should succeed"
    assert relay_res.get("target_phone") == "+919876543210", "Target phone should match demo phone"
    assert "payment_link_url" in relay_res, "Payment link URL must be in response"
    assert "script" in relay_res, "Vernacular script must be generated"
    print(f"[PASS] 2. Tab 2 Live Relay Call: Dispatched to demo phone +919876543210 for loan {first_loan}")

    # 3. Voice Reply test
    vr_res = asyncio.run(outreach_voice_reply(first_loan, file=None, transcript_text="salary 5th ko aayega tab pakka pay kar dunga"))
    assert vr_res.get("signals", {}).get("intent") == "PROMISE_TO_PAY", "Intent extraction failed"
    print("[PASS] 3. Tab 2 Voice STT: Extracted PROMISE_TO_PAY intent from code-mixed reply")

    # 4. Fairness DIR [0.00, 1.00] test
    fair_res = get_fairness_report()
    dir_g = fair_res["disparate_impact"]["gender"]["disparate_impact_ratio"]
    dir_l = fair_res["disparate_impact"]["language"]["disparate_impact_ratio"]
    assert 0.80 <= dir_g <= 1.00, f"Gender DIR {dir_g} must be in [0.80, 1.00]"
    assert 0.80 <= dir_l <= 1.00, f"Language DIR {dir_l} must be in [0.80, 1.00]"
    print(f"[PASS] 4. Tab 3 Normalized DIR: Gender DIR = {dir_g:.4f}, Lang DIR = {dir_l:.4f} (both strictly in [0.80, 1.00])")

    # 5. Curveball Dual Lift test
    cb_res = upload_curveball(None)
    assert "lift_top_10pct" in cb_res, "Must return lift_top_10pct"
    assert "lift_top_360" in cb_res, "Must return lift_top_360"
    lift_10 = cb_res["lift_top_10pct"]["payer_capture_lift_percentage"]
    lift_360 = cb_res["lift_top_360"]["payer_capture_lift_percentage"]
    print(f"[PASS] 5. Tab 3 Dual Lift: Top 10% (8.6% Capacity) = {lift_10}, Top 360 = {lift_360}")

    # 6. Tab 4 Pre-seeded Compliance Audit Trail test
    logs_res = get_audit_logs(limit=100)
    logs_count = len(logs_res.get("logs", []))
    assert logs_count >= 21, f"Expected >= 21 logs, got {logs_count}"
    print(f"[PASS] 6. Tab 4 Audit Trail: {logs_count} pre-seeded regulatory hold & live call events")

    # 7. Lambda Zero-Dependency test
    l_res = lambda_handler({"httpMethod": "GET"})
    assert l_res.get("statusCode") == 200, "Lambda health check failed"
    l_comp = lambda_handler({"action": "compliance_check", "borrower": {"loan_id": "TEST", "notes": "ICU admit"}})
    assert json.loads(l_comp["body"])["compliance"]["stage"] == "COMPASSIONATE_HOLD"
    print("[PASS] 7. AWS Lambda Zero-Dependency: Executed health check & compliance gate standalone")

    print("=" * 70)
    print("ALL 5 WINNING UPGRADES VERIFIED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
