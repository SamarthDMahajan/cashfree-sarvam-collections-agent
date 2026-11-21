"""
Realistic Messy 4,200-Borrower Dataset & Curveball Unseen Test Generator.
Generates:
1. `data/borrower_book_4200.csv` (messy duplicates, phones, dates, code-mixed notes)
2. `data/curveball_unseen_sample.csv` (unseen sample with ground truth `actually_paid` label for lift evaluation)
"""
import os
import random
import re
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

def generate_datasets():
    os.makedirs("data", exist_ok=True)
    random.seed(42)
    np.random.seed(42)

    # Names and demographics for proxy testing
    female_first_names = [
        "Priya", "Ananya", "Kavya", "Sunita", "Deepa", "Lakshmi", "Ritu", "Neha",
        "Pooja", "Aarti", "Shreya", "Fatima", "Amina", "Simran", "Preeti", "Kavitha",
        "Meenakshi", "Divya", "Swati", "Chitra", "Rekha", "Geeta", "Shalini", "Zoya"
    ]
    male_first_names = [
        "Rahul", "Amit", "Rohan", "Vikram", "Suresh", "Ramesh", "Aditya", "Sanjay",
        "Mohammad", "Imran", "Harpreet", "Gurpreet", "Manish", "Karthik", "Venkatesh",
        "Arun", "Rajesh", "Vijay", "Anand", "Naveen", "Deepak", "Ajay", "Prashant", "Ali"
    ]
    last_names = [
        "Sharma", "Verma", "Patel", "Gupta", "Singh", "Kumar", "Iyer", "Nair",
        "Reddy", "Gowda", "Khan", "Ahmed", "Kaur", "Jain", "Deshmukh", "Chavan",
        "Mukherjee", "Das", "Bose", "Mehta", "Yadav", "Pandey", "Mishra", "Joshi"
    ]
    religions = ["Hindu", "Muslim", "Sikh", "Christian", "Jain"]
    religion_weights = [0.78, 0.14, 0.03, 0.03, 0.02]
    castes = ["General", "OBC", "SC", "ST"]
    caste_weights = [0.35, 0.40, 0.17, 0.08]

    cities = [
        ("Bengaluru", "560001", "kn-IN"),
        ("Mysuru", "570001", "kn-IN"),
        ("Hubballi", "580020", "kn-IN"),
        ("Chennai", "600001", "ta-IN"),
        ("Coimbatore", "641001", "ta-IN"),
        ("Madurai", "625001", "ta-IN"),
        ("Delhi", "110001", "hi-IN"),
        ("Lucknow", "226001", "hi-IN"),
        ("Jaipur", "302001", "hi-IN"),
        ("Mumbai", "400001", "en-IN"),
        ("Pune", "411001", "en-IN"),
        ("Hyderabad", "500001", "en-IN")
    ]

    # Archetype notes with realistic code-mixed expressions
    notes_catalog = [
        # 1. Salary promises
        ("salary 5th ko aayega tab pay kar dunga", 0.90, "hi-IN"),
        ("salry 7th ko credit hogi pakka transfer kar dunga", 0.88, "hi-IN"),
        ("10 tarik ko salary aate hi link pe bhar dunga", 0.92, "hi-IN"),
        ("salary delay ho gayi hai kal shaam tak kar dunga", 0.75, "hi-IN"),
        ("sambala 5th baratte aaga full pay madtini", 0.91, "kn-IN"),
        ("salary 7th barutte nodi kanditha pay madtini", 0.89, "kn-IN"),
        ("salary 5th varum sir appo kandippa pay panren", 0.90, "ta-IN"),
        ("enaku salary 10th varum appo pay pannidren", 0.88, "ta-IN"),
        ("Will pay by 5th as soon as my salary is credited", 0.85, "en-IN"),
        ("Salary expected on 8th, will clear full EMI then", 0.87, "en-IN"),

        # 2. Hardship Partial Payer
        ("abhi paise kam hai aadha abhi de sakta hu baki next month", 0.70, "hi-IN"),
        ("job change hua hai thoda financial issue hai partial payment link bhejo", 0.74, "hi-IN"),
        ("swalpa duddu ide half pay madtini link kalsi", 0.72, "kn-IN"),
        ("konjam kashtam sir half amount pay panren link anupunga", 0.73, "ta-IN"),
        ("Facing temporary liquidity shortage, please send partial settlement link", 0.71, "en-IN"),

        # 3. Already Paid at Branch / Counter (Reconciliation Hold)
        ("branch mein de diya cash receipt hai mere paas", 0.05, "hi-IN"),
        ("already branch counter pe jama kar diya tha check karo", 0.05, "hi-IN"),
        ("branch nalli duddu kottidini receipt ide", 0.05, "kn-IN"),
        ("branch la already cash pay panniyachu check pannunga", 0.05, "ta-IN"),
        ("Already deposited at bank branch 2 days ago, check counter ledger", 0.05, "en-IN"),

        # 4. Medical / Life Compassionate Hold
        ("hospital me admit hu accident ho gaya tha 10 din baad baat karo", 0.0, "hi-IN"),
        ("father ICU me hai critical condition hai please abhi call mat karo", 0.0, "hi-IN"),
        ("gharme shaadi chal rahi hai agle hafte call karna", 0.05, "hi-IN"),
        ("hospital nalli iddini surgery aagide please thoda time bidi", 0.0, "kn-IN"),
        ("hospital la admit aagi irukken surgery mudinjathum pesuren", 0.0, "ta-IN"),
        ("Family medical emergency, admitted in hospital, please hold calls", 0.0, "en-IN"),

        # 5. Chronic Promiser / Delayed
        ("kal pakka pay kar dunga guarantee", 0.40, "hi-IN"),
        ("two days me clear karta hu", 0.45, "hi-IN"),
        ("naale kanditha kodtini", 0.42, "kn-IN"),
        ("naalaiki kandippa pay panren", 0.43, "ta-IN"),
        ("Promised to pay tomorrow", 0.40, "en-IN"),

        # 6. Dispute / Refusal
        ("nahi dunga galat charges lagaye hai", 0.10, "hi-IN"),
        ("fraud call hai dispute raise kiya hai maine", 0.12, "hi-IN"),
        ("kodolla tumba extra interest haktidira", 0.10, "kn-IN"),
        ("pay panna mudiyathu wrongful charges", 0.10, "ta-IN"),
        ("Disputing penal interest charges, will not pay until rectified", 0.10, "en-IN"),

        # 7. Silent / Empty note
        ("", 0.50, "en-IN"),
        ("", 0.55, "hi-IN"),
        ("Follow up required", 0.52, "en-IN")
    ]

    def create_row(idx: int, is_test_set: bool = False) -> dict:
        is_female = random.random() < 0.50
        first_name = random.choice(female_first_names) if is_female else random.choice(male_first_names)
        last_name = random.choice(last_names)
        full_name = f"{first_name} {last_name}"
        gender = "Female" if is_female else "Male"
        religion = random.choices(religions, weights=religion_weights)[0]
        caste = random.choices(castes, weights=caste_weights)[0]

        city_info = random.choice(cities)
        city_name, pincode_base, lang_pref = city_info
        pincode = f"{int(pincode_base) + random.randint(0, 80):06d}"

        # Messy phone formatting
        raw_digits = f"9{random.randint(100000000, 999999999)}"
        phone_style = random.choice(["plain", "prefix91", "spaces", "dashes", "plus91"])
        if phone_style == "plain":
            phone = raw_digits
        elif phone_style == "prefix91":
            phone = f"91{raw_digits}"
        elif phone_style == "plus91":
            phone = f"+91 {raw_digits[:5]} {raw_digits[5:]}"
        elif phone_style == "spaces":
            phone = f"{raw_digits[:5]} {raw_digits[5:]}"
        else:
            phone = f"{raw_digits[:5]}-{raw_digits[5:]}"

        # Messy date formatting
        due_dt = datetime.now() - timedelta(days=random.randint(1, 110))
        date_style = random.choice(["iso", "slash", "dash", "word"])
        if date_style == "iso":
            due_date = due_dt.strftime("%Y-%m-%d")
        elif date_style == "slash":
            due_date = due_dt.strftime("%d/%m/%Y")
        elif date_style == "dash":
            due_date = due_dt.strftime("%d-%m-%Y")
        else:
            due_date = due_dt.strftime("%b %d, %Y")

        dpd = random.randint(1, 105)
        # Financial metrics
        amount_due = float(random.choice([
            random.randint(500, 3000),      # Small microfinance
            random.randint(3000, 15000),    # Consumer durable
            random.randint(15000, 60000),   # Personal loan EMI
            random.randint(60000, 140000)   # Business / Auto loan
        ]))

        # Select note archetype matching language preference if possible
        matched_notes = [n for n in notes_catalog if n[2] == lang_pref or n[2] == "en-IN"]
        note_tuple = random.choice(matched_notes if matched_notes else notes_catalog)
        note_text, true_intent_prob, _ = note_tuple

        past_promises_kept = round(random.uniform(0.1, 0.95), 2)
        historical_pay_rate = round(random.uniform(0.1, 0.95), 2)
        inbound_recency_days = random.randint(0, 45)
        broken_promises_count = random.choices([0, 1, 2, 3, 4], weights=[0.50, 0.25, 0.15, 0.07, 0.03])[0]
        opted_in = random.random() < 0.08  # 8% explicit opt-in for evening calls

        # Determine ground-truth `actually_paid` based on true behavioral logic
        # (NOT on gender, religion, caste, pincode, or language!)
        pay_logit = (
            2.5 * past_promises_kept +
            2.0 * true_intent_prob +
            1.5 * historical_pay_rate +
            (1.5 if dpd < 25 else (0.5 if dpd < 60 else -1.0)) -
            0.8 * broken_promises_count -
            (3.0 if "hospital" in note_text or "branch" in note_text else 0.0) -
            (2.5 if "nahi dunga" in note_text else 0.0)
        )
        # Sigmoid
        pay_prob = 1.0 / (1.0 + np.exp(-pay_logit))
        actually_paid = 1 if (random.random() < pay_prob) else 0

        prefix = "TEST" if is_test_set else "LN"
        loan_id = f"{prefix}-{20260000 + idx}"

        return {
            "loan_id": loan_id,
            "borrower_name": full_name,
            "phone": phone,
            "gender": gender,
            "religion": religion,
            "caste": caste,
            "city": city_name,
            "pincode": pincode,
            "preferred_language": lang_pref,
            "due_date": due_date,
            "dpd": dpd,
            "amount_due": amount_due,
            "past_promises_kept_ratio": past_promises_kept,
            "historical_pay_rate": historical_pay_rate,
            "inbound_recency_days": inbound_recency_days,
            "broken_promises_count": broken_promises_count,
            "notes": note_text,
            "borrower_opted_in": opted_in,
            "actually_paid": actually_paid
        }

    # Generate 4,200 rows with duplicates & messiness
    print("[1/2] Generating 4,200-borrower main book...")
    rows_4200 = []
    for i in range(1, 4171):
        rows_4200.append(create_row(i, is_test_set=False))
    
    # Introduce 30 realistic duplicate loans (e.g. repeated records from batch export)
    for i in range(30):
        orig = rows_4200[random.randint(0, len(rows_4200) - 1)].copy()
        # Messy phone variation or slight note amendment
        orig["notes"] = f"{orig['notes']} (duplicate export)"
        rows_4200.append(orig)

    df_4200 = pd.DataFrame(rows_4200)
    # Shuffle
    df_4200 = df_4200.sample(frac=1.0, random_state=42).reset_index(drop=True)
    df_4200.to_csv("data/borrower_book_4200.csv", index=False)
    print(f" -> Saved 'data/borrower_book_4200.csv' ({len(df_4200)} rows, including {df_4200['loan_id'].duplicated().sum()} duplicates).")

    # Generate 600-row held-out Curveball Unseen Test CSV
    print("[2/2] Generating 600-row held-out Curveball Unseen Test CSV...")
    rows_test = []
    for i in range(1, 601):
        rows_test.append(create_row(i, is_test_set=True))
    df_test = pd.DataFrame(rows_test)
    df_test.to_csv("data/curveball_unseen_sample.csv", index=False)
    print(f" -> Saved 'data/curveball_unseen_sample.csv' ({len(df_test)} rows with ground-truth 'actually_paid' labels).")

if __name__ == "__main__":
    generate_datasets()
