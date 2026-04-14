from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.v1 import questionnaires, artifacts, assessments, policies, hitl

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API v1 routers
app.include_router(questionnaires.router, prefix="/api/v1", tags=["Questionnaires"])
app.include_router(artifacts.router, prefix="/api/v1", tags=["Artifacts"])
app.include_router(assessments.router, prefix="/api/v1", tags=["Assessments"])
app.include_router(policies.router, prefix="/api/v1", tags=["Policies"])
app.include_router(hitl.router, prefix="/api/v1", tags=["HITL Feedback"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.APP_VERSION}
