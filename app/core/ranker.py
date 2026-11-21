"""
Allowlisted Fair Linear Ranker Engine.
Enforces:
1. Strict ALLOWED_SCORING_FEATURES whitelist (hard exclusion of name, gender,
   religion, caste, pincode, area, language).
2. 10% Epsilon-Greedy exploration for selection bias mitigation.
3. Deterministic 1-sentence Manager Read-Aloud Reason per borrower.
"""
import random
from typing import List, Dict, Any, Tuple
import pandas as pd
import numpy as np

from app.config import ALLOWED_SCORING_FEATURES, EXCLUDED_PROXY_FEATURES
from app.core.compliance import evaluate_borrower_call_compliance
from app.core.signals import extract_signals_from_note

def calculate_borrower_score(borrower: Dict[str, Any]) -> Tuple[float, str, str]:
    """
    Computes priority score using ONLY permissible allowlisted features.
    Returns: (score [0-100], status_badge, manager_reason)
    """
    comp = evaluate_borrower_call_compliance(borrower)
    if not comp["allowed"]:
        if comp["stage"] == "COMPASSIONATE_HOLD":
            return 0.0, "COMPASSIONATE_HOLD", f"ON HOLD: {comp['reason']}"
        elif comp["stage"] == "RECONCILIATION_HOLD":
            return 0.0, "RECONCILIATION_HOLD", f"ON HOLD: {comp['reason']}"

    dpd = float(borrower.get("dpd", 30))
    past_promises_kept = float(borrower.get("past_promises_kept_ratio", 0.5))
    historical_pay_rate = float(borrower.get("historical_pay_rate", 0.5))
    inbound_recency_days = float(borrower.get("inbound_recency_days", 15))
    broken_promises_count = float(borrower.get("broken_promises_count", 0))
    
    note = str(borrower.get("notes", ""))
    nlp_signals = extract_signals_from_note(note)
    intent_score = float(nlp_signals["intent_score"])
    intent_category = nlp_signals["intent"]

    if intent_category in ["MEDICAL_EMERGENCY", "ALREADY_PAID_BRANCH"]:
        return 0.0, intent_category, f"ON HOLD: {nlp_signals['summary']}"

    # 1. DPD factor (early delinquency cure rate highest)
    dpd_factor = max(0.10, 1.0 - (dpd / 90.0))

    # 2. Inbound engagement recency factor
    recency_factor = max(0.10, 1.0 - (inbound_recency_days / 30.0))

    # 3. Broken promises penalty
    broken_penalty = max(0.20, 1.0 - (0.25 * broken_promises_count))

    # 4. Composite Base Score (0.0 to 1.0)
    composite = (
        0.30 * past_promises_kept +
        0.25 * intent_score +
        0.20 * dpd_factor +
        0.15 * recency_factor +
        0.10 * historical_pay_rate
    ) * broken_penalty

    final_score = round(max(1.0, min(99.9, composite * 100.0)), 2)

    action = nlp_signals.get("recommended_action", "FULL_LINK")
    if intent_category == "PROMISE_TO_PAY":
        day_str = f" around {nlp_signals['promise_day']}th" if nlp_signals.get("promise_day") else ""
        reason = f"High intent: Promise to pay{day_str} post-salary. Past promise adherence is {int(past_promises_kept*100)}% with {int(dpd)} DPD. Call & dispatch {action}."
    elif intent_category == "HARDSHIP_PARTIAL_PAYER":
        reason = f"Hardship willingness: Borrower requested flexibility; recommend Hardship Partial Payment link (min 20%) to secure partial recovery."
    elif past_promises_kept > 0.75:
        reason = f"Reliable payer profile: {int(past_promises_kept*100)}% historical promise fulfillment, {int(dpd)} DPD, low broken promises ({int(broken_promises_count)})."
    elif dpd < 15:
        reason = f"Early bucket cure: Only {int(dpd)} days overdue, responsive engagement ({int(inbound_recency_days)}d ago). High chance of instant UPI settlement."
    else:
        reason = f"Standard recovery target: DPD {int(dpd)}, intent score {intent_score:.2f}, repayment track record {int(historical_pay_rate*100)}%."

    return final_score, "ELIGIBLE", reason

def rank_borrowers(
    borrowers: List[Dict[str, Any]],
    top_slots: int = 360,
    epsilon: float = 0.10,
    random_seed: int = 42
) -> List[Dict[str, Any]]:
    scored_records = []
    for b in borrowers:
        record = dict(b)
        score, status_badge, reason = calculate_borrower_score(record)
        record["priority_score"] = score
        record["status_badge"] = status_badge
        record["manager_reason"] = reason
        record["is_exploration"] = False
        scored_records.append(record)

    eligible = [r for r in scored_records if r["status_badge"] == "ELIGIBLE"]
    on_hold = [r for r in scored_records if r["status_badge"] != "ELIGIBLE"]

    eligible.sort(key=lambda x: x["priority_score"], reverse=True)

    n_exploit = int(top_slots * (1.0 - epsilon))
    n_explore = top_slots - n_exploit

    exploit_cohort = eligible[:n_exploit]
    remaining = eligible[n_exploit:]

    rng = random.Random(random_seed)
    if len(remaining) >= n_explore:
        explore_indices = rng.sample(range(len(remaining)), n_explore)
        explore_cohort = []
        rest = []
        for i, item in enumerate(remaining):
            if i in explore_indices:
                item_copy = dict(item)
                item_copy["is_exploration"] = True
                item_copy["manager_reason"] = f"[EXPLORATION 10%]: Selection-bias exploration slot. DPD {int(item_copy.get('dpd', 0))}, testing uncalled cohort."
                explore_cohort.append(item_copy)
            else:
                rest.append(item)
    else:
        explore_cohort = remaining
        rest = []

    final_top = []
    exp_idx = 0
    cur_idx = 0
    total_slots_to_fill = min(top_slots, len(exploit_cohort) + len(explore_cohort))

    for rank_pos in range(1, total_slots_to_fill + 1):
        if rank_pos % 10 == 0 and exp_idx < len(explore_cohort):
            item = explore_cohort[exp_idx]
            exp_idx += 1
        elif cur_idx < len(exploit_cohort):
            item = exploit_cohort[cur_idx]
            cur_idx += 1
        elif exp_idx < len(explore_cohort):
            item = explore_cohort[exp_idx]
            exp_idx += 1
        else:
            break
        item["rank"] = rank_pos
        item["rank_delta"] = 0
        final_top.append(item)

    current_rank = len(final_top) + 1
    for r in rest:
        r["rank"] = current_rank
        r["rank_delta"] = 0
        final_top.append(r)
        current_rank += 1

    for h in on_hold:
        h["rank"] = current_rank
        h["rank_delta"] = 0
        final_top.append(h)
        current_rank += 1

    return final_top
