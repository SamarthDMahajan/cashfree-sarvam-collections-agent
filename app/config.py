import os
from datetime import time
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv(override=True)

# Timezone
IST = ZoneInfo("Asia/Kolkata")

# Cashfree Sandbox Config
CASHFREE_CLIENT_ID = os.getenv("CASHFREE_CLIENT_ID", "").strip()
CASHFREE_CLIENT_SECRET = os.getenv("CASHFREE_CLIENT_SECRET", "").strip()
CASHFREE_BASE_URL = os.getenv("CASHFREE_BASE_URL", "https://sandbox.cashfree.com").rstrip("/")
CASHFREE_API_VERSION = os.getenv("CASHFREE_API_VERSION", "2026-01-01").strip()

# Sarvam AI Config
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "").strip()
SARVAM_BASE_URL = "https://api.sarvam.ai"

# Lambda / Webhook Config
LAMBDA_WEBHOOK_URL = os.getenv("LAMBDA_WEBHOOK_URL", "https://ggfyc5ptui4jk3ogez6vzo66r40wqloo.lambda-url.ap-south-1.on.aws/samarthdmahajan-collections-agent/").strip()
PORT = int(os.getenv("PORT", 8000))

# RBI Jan 2027 Regulatory Compliance Constants
RBI_CALLING_WINDOW_START = time(8, 0, 0)   # 08:00 AM IST
RBI_CALLING_WINDOW_END = time(19, 0, 0)    # 07:00 PM IST (19:00 IST)

# Statutory Principal Grievance Redressal Officer (GRO) Contact Footer
RBI_GRO_CONTACT = {
    "officer_name": "Mr. Alok Verma",
    "designation": "Principal Grievance Redressal Officer (GRO)",
    "email": "gro@sarvam-cashfree-bank.in",
    "toll_free": "1800-258-4455",
    "rbi_cms_portal": "https://cms.rbi.org.in",
    "rbi_cms_helpline": "14448",
    "disclosure_text": "GRO: Alok Verma (gro@sarvam-cashfree-bank.in | Toll-free: 1800-258-4455). Escalate to RBI CMS at cms.rbi.org.in or dial 14448."
}

# Mandatory Recording Disclosures by Language
MANDATORY_DISCLOSURES = {
    "en-IN": "Notice: This call is recorded for quality, service assurance, and regulatory compliance under the RBI Fair Practices Code.",
    "hi-IN": "सूचना: यह कॉल भारतीय रिजर्व बैंक के निष्पक्ष व्यवहार संहिता के तहत गुणवत्ता और नियामक अनुपालन के लिए रिकॉर्ड की जा रही है।",
    "kn-IN": "ಸೂಚನೆ: ಈ ಕರೆಯನ್ನು ಗುಣಮಟ್ಟ ಮತ್ತು ಆರ್‌ಬಿಐ ನಿಯಮಾವಳಿಗಳ ಅನುಸರಣೆಗಾಗಿ ರೆಕಾರ್ಡ್ ಮಾಡಲಾಗುತ್ತಿದೆ.",
    "ta-IN": "அறிவிப்பு: தரக்கட்டுப்பாடு மற்றும் ஆர்பிஐ ஒழுங்குமுறை விதிகளுக்கு இணங்க இந்த அழைப்பு பதிவு செய்யப்படுகிறது."
}

# Strict Feature Allowlist for Fair Ranking
ALLOWED_SCORING_FEATURES = [
    "dpd",
    "amount_due",
    "past_promises_kept_ratio",
    "intent_score",
    "inbound_recency_days",
    "broken_promises_count",
    "historical_pay_rate"
]

# Strict Exclusion List (Guarded against proxy leakage)
EXCLUDED_PROXY_FEATURES = [
    "name",
    "borrower_name",
    "gender",
    "religion",
    "caste",
    "pincode",
    "area",
    "language",
    "preferred_language",
    "city",
    "phone"
]

# Compassionate & Reconciliation Hold Moratorium Periods
COMPASSIONATE_HOLD_DAYS = 14
RECONCILIATION_HOLD_DAYS = 3
WEDDING_HOLD_DAYS = 7
