"""
FastAPI Main Application.
Mounts:
- Core collections routers: queue, outreach, actions, curveball, fairness, webhook
- On startup: loads & deduplicates 4,200 borrower records from app/data/book.csv
- Serves Judge Command Center SPA at /
"""
import os
import sys
import pandas as pd
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.queue_engine import queue_engine
from app.data.generate_book import generate_datasets
from app.routes.queue import router as queue_router
from app.routes.outreach import router as outreach_router
from app.routes.actions import router as actions_router
from app.routes.curveball import router as curveball_router
from app.routes.fairness import router as fairness_router
from app.routes.webhook import router as webhook_router

app = FastAPI(
    title="Cashfree × Sarvam AI Collections Agent",
    description="Autonomous Multilingual Collections Recovery Optimizer (PS-2: Who will pay first?)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup Handler: loads or generates book.csv
@app.on_event("startup")
def startup_event():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    book_csv = os.path.join(base_dir, "data", "book.csv")
    if not os.path.exists(book_csv):
        print(f"[STARTUP] {book_csv} not found. Generating synthetic borrower book...")
        generate_datasets()

    df = pd.read_csv(book_csv)
    df_clean = df.drop_duplicates(subset=["loan_id"]).copy()
    
    # Rigorous null and NaN sanitization
    for col in df_clean.columns:
        if df_clean[col].dtype == object or df_clean[col].dtype == 'string':
            df_clean[col] = df_clean[col].fillna("")
        else:
            df_clean[col] = df_clean[col].fillna(0)

    records = df_clean.to_dict(orient="records")
    queue_engine.load_borrowers(records)
    print(f"[STARTUP] Successfully loaded & deduplicated {len(records)} borrowers into queue engine.")

    # Pre-seed initial compliance events (medical/ICU & branch recon holds) into audit trail
    from app.core.compliance import audit_logger
    seeded_count = audit_logger.seed_initial_holds(records)
    print(f"[STARTUP] Pre-seeded {seeded_count} regulatory hold events into audit trail.")

# Register API Routers
app.include_router(queue_router)
app.include_router(outreach_router)
app.include_router(actions_router)
app.include_router(curveball_router)
app.include_router(fairness_router)
app.include_router(webhook_router)

# Mount Static Files & Serve Command Center SPA
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Cashfree × Sarvam Collections Agent API Running</h1>"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
