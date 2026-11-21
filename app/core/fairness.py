"""
Fairness & Proxy-Free Audit Module.
Calculates:
1. Disparate Impact Ratio (DIR >= 0.80 4/5ths rule verification)
2. Pearson correlation against all excluded demographic/geographic proxies
"""
from typing import Dict, Any
import pandas as pd
import numpy as np

from app.config import ALLOWED_SCORING_FEATURES, EXCLUDED_PROXY_FEATURES

def audit_fairness_and_proxies(
    df: pd.DataFrame,
    top_n: int = 360
) -> Dict[str, Any]:
    audit_results = {
        "disparate_impact": {},
        "proxy_correlations": {},
        "pass_all_fairness_checks": True
    }

    total_rows = len(df)
    if total_rows == 0:
        return audit_results

    is_top_n = (df["rank"] <= top_n)

    # 1. Gender Disparate Impact Ratio
    if "gender" in df.columns:
        males = (df["gender"].str.lower() == "male")
        females = (df["gender"].str.lower() == "female")
        
        male_rate = (males & is_top_n).sum() / max(1, males.sum())
        female_rate = (females & is_top_n).sum() / max(1, females.sum())
        
        dir_gender = female_rate / max(0.0001, male_rate)
        audit_results["disparate_impact"]["gender"] = {
            "female_selection_rate": round(float(female_rate), 4),
            "male_selection_rate": round(float(male_rate), 4),
            "disparate_impact_ratio": round(float(dir_gender), 4),
            "compliant_dir_ge_0_80": bool(dir_gender >= 0.80)
        }
        if dir_gender < 0.80:
            audit_results["pass_all_fairness_checks"] = False

    # 2. Language Disparate Impact Ratio (Regional vs English)
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

    # 3. Pearson Correlation Proof vs Excluded Proxies
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
        pincode_num = pd.to_numeric(df["pincode"], errors="coerce").fillna(0)
        corr_score_pin = float(np.corrcoef(df["priority_score"], pincode_num)[0, 1])
        corrs["priority_score_vs_pincode"] = round(corr_score_pin, 4)
        if abs(corr_score_pin) > 0.08:
            audit_results["pass_all_fairness_checks"] = False

    audit_results["proxy_correlations"] = corrs
    audit_results["excluded_proxy_features"] = EXCLUDED_PROXY_FEATURES
    audit_results["allowed_scoring_features"] = ALLOWED_SCORING_FEATURES
    return audit_results
