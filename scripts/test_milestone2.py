"""
Milestone 2 Verification Script (Synchronous & Direct).
Tests:
1. App startup and queue engine load (4,170 deduplicated records).
2. /api/queue and /api/metrics endpoints.
3. Sarvam outreach script generation with recording disclosure & GRO footer.
4. Curveball evaluation (Recovery Lift @ Top 360 + DIR Matrix).
5. 7:15 PM Compliance Toggle for RBI Jan 2027 calling hours.
"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import (
    startup_event,
    get_metrics,
    get_queue,
    generate_voice_script,
    evaluate_curveball,
    toggle_test_hours,
    TestHoursRequest
)

def run_milestone2_tests():
    print("=" * 60)
    print("RUNNING MILESTONE 2 AUTOMATED CHECKS")
    print("=" * 60)

    # 1. Startup
    startup_event()
    m = get_metrics()
    print(f"[TEST 1] get_metrics() OK -> Total: {m['total_borrowers']}, Top 360 Target: ₹{m['top_360_target_value']:,.2f}")
    assert m['total_borrowers'] >= 4000, "Should have loaded >4000 borrowers"

    # 2. Queue
    q_data = get_queue(limit=360)
    items = q_data.get("queue", [])
    print(f"[TEST 2] get_queue() OK -> Fetched {len(items)} slots.")
    assert len(items) == 360, "Should fetch top 360 slots"
    assert "rank" in items[0] and "priority_score" in items[0] and "manager_reason" in items[0]
    print(f"         Slot #1: {items[0]['loan_id']} | Score: {items[0]['priority_score']} | Reason: {items[0]['manager_reason']}")

    # 3. Voice Script with Compliance
    sample_lid = items[0]["loan_id"]
    s = generate_voice_script(loan_id=sample_lid, is_partial=False)
    print(f"[TEST 3] generate_voice_script() OK -> Lang: {s['language']}, Tone Passed: {s['tone_passed']}")
    print(f"         Disclosure: {s['disclosure']}")
    print(f"         GRO Contact Footer: {s['gro_footer']}")
    assert "recorded" in s["disclosure"].lower() or "रिकॉर्ड" in s["disclosure"] or "ರೆಕಾರ್ಡ್" in s["disclosure"] or "பதிவு" in s["disclosure"], "Disclosure must mention recording"
    assert "gro" in s["gro_footer"].lower() and "14448" in s["gro_footer"], "GRO footer must mention 14448"

    # 4. Curveball & Mathematical Proof
    cb = evaluate_curveball(file=None)
    lift = cb["performance_lift"]
    audit = cb["fairness_audit"]
    print(f"[TEST 4] evaluate_curveball() OK -> Unseen rows: {cb['total_unseen_rows']}")
    print(f"         Payer Capture Lift: {lift['payer_capture_lift_percentage']} (Ranked: {lift['ranked_order_payers_captured']} vs Default: {lift['default_order_payers_captured']})")
    print(f"         Recovery Amount Lift: {lift['recovery_lift_percentage']}")
    print(f"         Fairness Audit DIR (Gender): {audit['disparate_impact']['gender']['disparate_impact_ratio']}")
    assert "+" in lift['payer_capture_lift_percentage'], "Must demonstrate positive capture lift"
    assert audit['disparate_impact']['gender']['compliant_dir_ge_0_80'], "Must satisfy DIR >= 0.80"

    # 5. 7:15 PM Compliance Toggle
    toggle_test_hours(TestHoursRequest(is_evening_override=True))
    q_evening = get_queue(limit=10)
    evening_items = q_evening.get("queue", [])
    blocked_count = sum(1 for it in evening_items if not it["rbi_compliance"]["allowed"])
    print(f"[TEST 5] 7:15 PM Toggle OK -> {blocked_count} / {len(evening_items)} sample items blocked outside window.")
    assert blocked_count > 0, "Non-opted-in borrowers must be blocked at 7:15 PM IST"
    # Revert toggle
    toggle_test_hours(TestHoursRequest(is_evening_override=False))

    print("\n" + "=" * 60)
    print("ALL MILESTONE 2 ASSERTIONS PASSED WITH ZERO ERRORS!")
    print("=" * 60)

if __name__ == "__main__":
    run_milestone2_tests()
