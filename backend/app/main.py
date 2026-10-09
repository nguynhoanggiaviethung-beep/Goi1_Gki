from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.scenarios import router as scenarios_router
from backend.app.research_features import router as research_router
from backend.app.company_reports import router as company_reports_router

app = FastAPI(title="Goi1_Gki API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scenarios_router, prefix="/api")
app.include_router(research_router, prefix="/api")
app.include_router(company_reports_router, prefix="/api")

@app.get("/")
def root():
    return {"name": "Goi1_Gki API", "docs": "/docs"}

@app.get("/api/health")
def health():
    return {"status": "ok"}
