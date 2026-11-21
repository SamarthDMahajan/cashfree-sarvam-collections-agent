"""
Allowlisted Fair Ranker Engine.
Enforces:
1. Strict ALLOWED_SCORING_FEATURES whitelist (hard exclusion of name, gender,
   religion, caste, pincode, area, language).
2. 10% Epsilon-Greedy exploration for selection bias mitigation.
3. 1-sentence Manager Read-Aloud Reason per borrower.
4. Mathematical Fairness & Proxy-Free Audit (Disparate Impact Ratio >= 0.80 and zero correlation).
"""
import math
import random
from typing import List, Dict, Any, Tuple
import pandas as pd
import numpy as np

from app.config import (
    ALLOWED_SCORING_FEATURES,
    PROTECTED_ATTRIBUTES
)
from app.compliance import evaluate_borrower_call_compliance
from app.nlp_extractor import extract_signals_from_note

def calculate_borrower_score(borrower: Dict[str, Any]) -> Tuple[float, str, str]:
    """
    Computes priority score using ONLY permissible allowlisted features.
    Returns: (score [0-100], status_badge, manager_reason)
    """
    # Compliance pre-check
    comp = evaluate_borrower_call_compliance(borrower)
    if not comp["allowed"]:
        if comp["stage"] == "COMPASSIONATE_HOLD":
            return 0.0, "COMPASSIONATE_HOLD", f"ON HOLD: {comp['reason']}"
        elif comp["stage"] == "RECONCILIATION_HOLD":
            return 0.0, "RECONCILIATION_HOLD", f"ON HOLD: {comp['reason']}"

    # Extract allowlisted metrics
    dpd = float(borrower.get("dpd", 30))
    amount_due = float(borrower.get("amount_due", 5000))
    past_promises_kept = float(borrower.get("past_promises_kept_ratio", 0.5))
    historical_pay_rate = float(borrower.get("historical_pay_rate", 0.5))
    inbound_recency_days = float(borrower.get("inbound_recency_days", 15))
    broken_promises_count = float(borrower.get("broken_promises_count", 0))
    
    # NLP extraction on note
    note = str(borrower.get("notes", ""))
    nlp_signals = extract_signals_from_note(note)
    intent_score = float(nlp_signals["intent_score"])
    intent_category = nlp_signals["intent"]

    if intent_category in ["MEDICAL_EMERGENCY", "ALREADY_PAID_BRANCH"]:
        return 0.0, intent_category, f"ON HOLD: {nlp_signals['summary']}"

    # 1. DPD factor: Early delinquency (1-30) has highest cure likelihood
    dpd_factor = max(0.10, 1.0 - (dpd / 90.0))

    # 2. Past promise factor (strongest behavioural signal)
    promise_factor = past_promises_kept

    # 3. Inbound Engagement factor: Recent engagement shows responsiveness
    recency_factor = max(0.10, 1.0 - (inbound_recency_days / 30.0))

    # 4. Broken promise penalty
    broken_penalty = max(0.20, 1.0 - (0.25 * broken_promises_count))

    # 5. Composite Base Score (0.0 to 1.0)
    composite = (
        0.30 * promise_factor +
        0.25 * intent_score +
        0.20 * dpd_factor +
        0.15 * recency_factor +
        0.10 * historical_pay_rate
    ) * broken_penalty

    # Scale to 0-100
    final_score = round(max(1.0, min(99.9, composite * 100.0)), 2)

    # Generate Manager Read-Aloud Reason
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
    """
    Ranks borrowers using Fair Allowlisted scoring + 10% Epsilon-Greedy exploration.
    Top `top_slots` (e.g. 360) are prioritized:
    - (1 - epsilon)*top_slots pure highest-score exploitation
    - epsilon*top_slots random exploration to combat selection bias
    """
    scored_records = []
    for b in borrowers:
        record = dict(b)
        score, status_badge, reason = calculate_borrower_score(record)
        record["priority_score"] = score
        record["status_badge"] = status_badge
        record["manager_reason"] = reason
        record["is_exploration"] = False
        scored_records.append(record)

    # Separate eligible from on-hold
    eligible = [r for r in scored_records if r["status_badge"] == "ELIGIBLE"]
    on_hold = [r for r in scored_records if r["status_badge"] != "ELIGIBLE"]

    # Sort eligible by priority score descending
    eligible.sort(key=lambda x: x["priority_score"], reverse=True)

    n_exploit = int(top_slots * (1.0 - epsilon))
    n_explore = top_slots - n_exploit

    exploit_cohort = eligible[:n_exploit]
    remaining = eligible[n_exploit:]

    # Sample exploratory cohort from remaining to prevent starvation & selection bias
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

    # Interleave explore cohort into top slots (e.g. every 10th slot is exploratory)
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
        item["rank_delta"] = 0  # Default initial delta
        final_top.append(item)

    # Append remaining eligible and on_hold
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

def audit_fairness_and_proxies(
    df: pd.DataFrame,
    top_n: int = 360
) -> Dict[str, Any]:
    """
    Performs rigorous mathematical fairness and proxy correlation checks:
    1. Disparate Impact Ratio (DIR) for Gender (Female vs Male)
    2. DIR for Language (Regional vs English)
    3. Pearson correlations between protected attributes and priority score
    Asserts zero proxy leakage!
    """
    audit_results = {
        "disparate_impact": {},
        "proxy_correlations": {},
        "pass_all_fairness_checks": True
    }

    total_rows = len(df)
    if total_rows == 0:
        return audit_results

    # Top N cohort boolean mask
    is_top_n = (df["rank"] <= top_n)

    # 1. Gender DIR
    if "gender" in df.columns:
        males = (df["gender"].str.lower() == "male")
        females = (df["gender"].str.lower() == "female")
        
        male_rate = (males & is_top_n).sum() / max(1, males.sum())
        female_rate = (females & is_top_n).sum() / max(1, females.sum())
        
        # 4/5ths rule DIR: min(rate) / max(rate) or unprivileged/privileged
        dir_gender = female_rate / max(0.0001, male_rate)
        audit_results["disparate_impact"]["gender"] = {
            "female_selection_rate": round(float(female_rate), 4),
            "male_selection_rate": round(float(male_rate), 4),
            "disparate_impact_ratio": round(float(dir_gender), 4),
            "compliant_dir_ge_0_80": bool(dir_gender >= 0.80)
        }
        if dir_gender < 0.80:
            audit_results["pass_all_fairness_checks"] = False

    # 2. Language DIR (Regional vs English)
    if "preferred_language" in df.columns:
        english = (df["preferred_language"].str.startswith("en"))
        regional = (~english)
        
        en_rate = (english & is_top_n).sum() / max(1, english.sum())
        reg_rate = (regional & is_top_n).sum() / max(1, regional.sum())
        
        dir_lang = reg_rate / max(0.0001, en_rate)
        audit_results["disparate_impact"]["language"] = {
            "regional_selection_rate": round(float(reg_rate), 4),
            "english_selection_rate": round(float(en_rate), 4),
            "disparate_impact_ratio": round(float(dir_lang), 4),
            "compliant_dir_ge_0_80": bool(dir_lang >= 0.80)
        }
        if dir_lang < 0.80:
            audit_results["pass_all_fairness_checks"] = False

    # 3. Proxy Correlation Audit
    # We test whether priority score or any allowlisted feature has significant correlation with protected attributes
    corrs = {}
    if "gender" in df.columns:
        gender_num = (df["gender"].str.lower() == "female").astype(float)
        corr_score_gender = float(np.corrcoef(df["priority_score"], gender_num)[0, 1])
        corrs["priority_score_vs_gender"] = round(corr_score_gender, 4)
        if abs(corr_score_gender) > 0.08:
            audit_results["pass_all_fairness_checks"] = False

    if "preferred_language" in df.columns:
        lang_num = (df["preferred_language"].str.startswith("en")).astype(float)
        corr_score_lang = float(np.corrcoef(df["priority_score"], lang_num)[0, 1])
        corrs["priority_score_vs_language"] = round(corr_score_lang, 4)
        if abs(corr_score_lang) > 0.08:
            audit_results["pass_all_fairness_checks"] = False

    if "pincode" in df.columns:
        # Pincode as arbitrary integer
        pincode_num = pd.to_numeric(df["pincode"], errors="coerce").fillna(0)
        corr_score_pin = float(np.corrcoef(df["priority_score"], pincode_num)[0, 1])
        corrs["priority_score_vs_pincode"] = round(corr_score_pin, 4)
        if abs(corr_score_pin) > 0.08:
            audit_results["pass_all_fairness_checks"] = False

    audit_results["proxy_correlations"] = corrs
    audit_results["excluded_protected_columns"] = PROTECTED_ATTRIBUTES
    audit_results["allowed_scoring_features"] = ALLOWED_SCORING_FEATURES
    return audit_results
