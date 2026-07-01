from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    attendance,
    auth,
    employees,
    leave_types,
    monthly_submissions,
    nfc,
    org_hierarchy,
    reasons,
    reports,
    system_config,
)

app = FastAPI(
    title="GoGoFresh Attendance System",
    description="Zero-Trust PWA Attendance System API",
    version="0.1.0",
    root_path=settings.root_path,
)

# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


# ---------------------------------------------------------------------------
# Secure headers middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(attendance.router)
app.include_router(auth.router)
app.include_router(employees.router)
app.include_router(leave_types.router)
app.include_router(monthly_submissions.router)
app.include_router(nfc.router)
app.include_router(org_hierarchy.ranks_router)
app.include_router(org_hierarchy.scoping_router)
app.include_router(reasons.router)
app.include_router(reports.router)
app.include_router(system_config.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
