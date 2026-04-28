"""FastAPI application entry point."""

from fastapi import FastAPI

from app.modules.auth.routes import router as auth_router
from app.modules.diagnosis.routes import router as diagnosis_router 
from app.modules.curriculum.routes import router as curriculum_router
from app.modules.tasks.routes import router as tasks_router
from app.modules.responses.routes import router as responses_router

app = FastAPI(
    title="LingosAI - English Tutor API",
    version='0.1.0'
)

@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Liveness probe - confirms server is up."""
    return {"status": "ok"}

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(diagnosis_router, prefix="/diagnosis", tags=["diagnosis"])
app.include_router(curriculum_router)
app.include_router(tasks_router)
app.include_router(responses_router)
