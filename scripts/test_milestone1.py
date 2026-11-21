"""
Milestone 1 Verification Script.
Tests:
1. 4,200 dataset deduplication and data cleaning.
2. Fair Ranker calculation, epsilon-greedy exploration, read-aloud reason.
3. Fairness Audit (Disparate Impact Ratio >= 0.80 and proxy correlations).
4. RBI Jan 2027 compliance gate (hours, holds, tone guard).
5. Dynamic queue re-ranking and rank deltas upon simulated events.
"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd

from app.fair_ranker import rank_borrowers, audit_fairness_and_proxies
from app.compliance import (
    check_calling_hours,
    check_compassionate_hold,
    check_reconciliation_hold,
    guard_tone_and_ethics,
    evaluate_borrower_call_compliance
)
from app.queue_engine import QueueEngine

IST = ZoneInfo("Asia/Kolkata")

def run_tests():
    print("=" * 60)
    print("RUNNING MILESTONE 1 AUTOMATED CHECKS")
    print("=" * 60)

    # 1. Load 4,200 book and deduplicate
    df = pd.read_csv("data/borrower_book_4200.csv")
    print(f"[TEST 1] Raw dataset rows: {len(df)}")
    df_clean = df.drop_duplicates(subset=["loan_id"]).copy()
    print(f"         Deduplicated rows: {len(df_clean)} (Cleaned {len(df) - len(df_clean)} duplicates)")
    assert len(df_clean) > 4000, "Should have >4000 unique borrowers"

    # 2. Fair Ranker
    records = df_clean.to_dict(orient="records")
    ranked = rank_borrowers(records, top_slots=360, epsilon=0.10)
    assert len(ranked) == len(records), "All records must be preserved in queue"
    
    top_360 = ranked[:360]
    explore_slots = [r for r in top_360 if r.get("is_exploration")]
    print(f"[TEST 2] Fair Ranker evaluated. Top 360 slots filled.")
    print(f"         Epsilon-greedy exploration slots: {len(explore_slots)} / 360 ({len(explore_slots)/360*100:.1f}%)")
    print(f"         Sample #1 Read-Aloud Reason: {top_360[0]['manager_reason']}")
    assert len(explore_slots) >= 30, "Should allocate ~36 exploratory slots (10%)"

    # 3. Fairness & Proxy Audit
    df_ranked = pd.DataFrame(ranked)
    audit = audit_fairness_and_proxies(df_ranked, top_n=360)
    print("\n[TEST 3] Fairness & Proxy Audit Results:")
    print(f"         Gender DIR: {audit['disparate_impact']['gender']['disparate_impact_ratio']} (Compliant >= 0.80: {audit['disparate_impact']['gender']['compliant_dir_ge_0_80']})")
    print(f"         Language DIR: {audit['disparate_impact']['language']['disparate_impact_ratio']} (Compliant >= 0.80: {audit['disparate_impact']['language']['compliant_dir_ge_0_80']})")
    print(f"         Proxy Correlations: {audit['proxy_correlations']}")
    print(f"         PASSED ALL FAIRNESS AUDITS: {audit['pass_all_fairness_checks']}")
    assert audit['pass_all_fairness_checks'], "Fairness audit must pass 4/5ths rule and zero proxy correlation"

    # 4. RBI Jan 2027 Compliance Gate
    print("\n[TEST 4] RBI Jan 2027 Compliance Gate Checks:")
    # Check 7:15 PM IST (19:15) without opt-in -> MUST BLOCK
    t_evening = datetime(2026, 11, 21, 19, 15, tzinfo=IST)
    res_evening_blocked = check_calling_hours(t_evening, borrower_opted_in=False)
    print(f"         7:15 PM without opt-in: Allowed={res_evening_blocked['allowed']} (Code: {res_evening_blocked['code']})")
    assert not res_evening_blocked['allowed'], "Must block calls at 7:15 PM IST without opt-in"

    # Check 7:15 PM IST with explicit opt-in -> ALLOWED
    res_evening_optin = check_calling_hours(t_evening, borrower_opted_in=True)
    print(f"         7:15 PM WITH opt-in: Allowed={res_evening_optin['allowed']} (Code: {res_evening_optin['code']})")
    assert res_evening_optin['allowed'], "Must allow calls at 7:15 PM IST with explicit opt-in"

    # Check compassionate hold (hospitalization)
    comp_hold = check_compassionate_hold("Borrower is admitted in hospital following surgery")
    print(f"         Hospitalization Hold: is_hold={comp_hold['is_hold']}, Category={comp_hold['category']}")
    assert comp_hold['is_hold'] and comp_hold['category'] == "MEDICAL_EMERGENCY"

    # Check already paid at branch hold
    recon_hold = check_reconciliation_hold("Branch mein de diya cash receipt hai")
    print(f"         Branch Paid Hold: is_hold={recon_hold['is_hold']}, Category={recon_hold['category']}")
    assert recon_hold['is_hold'] and recon_hold['category'] == "ALREADY_PAID_RECONCILIATION"

    # Check tone guard on prohibited words
    tone_bad = guard_tone_and_ethics("Pay immediately or police will arrest you and humiliate your family")
    tone_good = guard_tone_and_ethics("Good afternoon, this is an automated courtesy reminder regarding your overdue payment.")
    print(f"         Tone Guard (Threat text): Passed={tone_bad['passed']}")
    print(f"         Tone Guard (Courteous text): Passed={tone_good['passed']}")
    assert not tone_bad['passed'] and tone_good['passed'], "Tone guard must catch prohibited words"

    # 5. Dynamic Queue Re-Forming & Rank Deltas
    print("\n[TEST 5] Dynamic Queue Engine Re-ranking & Rank Deltas:")
    engine = QueueEngine()
    engine.load_borrowers(records[:100])
    initial_top5 = [b["loan_id"] for b in engine.get_top_queue(5)]
    print(f"         Initial Top 5 Loan IDs: {initial_top5}")

    # Simulate payment for #1 loan
    first_lid = initial_top5[0]
    engine.handle_payment_event(first_lid, amount_paid=50000, is_full=True)
    new_top5 = engine.get_top_queue(5)
    print(f"         After Full Payment of {first_lid}:")
    print(f"         Former #1 status: {engine.borrowers[first_lid]['status']}")
    print(f"         New Top Borrower: {new_top5[0]['loan_id']} (Rank Delta: {new_top5[0]['rank_delta']})")
    assert engine.borrowers[first_lid]["status"] == "PAID", "Loan status must be PAID"
    assert new_top5[0]["rank_delta"] >= 0, "Lower borrower should have moved up"

    print("\n" + "=" * 60)
    print("ALL MILESTONE 1 ASSERTIONS PASSED WITH ZERO ERRORS!")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
