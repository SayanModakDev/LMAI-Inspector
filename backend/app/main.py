"""
FastAPI application entry point.
Configures CORS, registers routes, and initializes database on startup.
"""

import os
import sys

# Critical: Configure PaddlePaddle C++ memory limits BEFORE any library can import paddle.
# Default FLAGS_initial_cpu_memory_in_mb is 500MB, which instantly exceeds Render 512MB RAM limit.
os.environ["FLAGS_allocator_strategy"] = "naive_best_fit"
os.environ["FLAGS_fraction_of_cpu_memory_to_use"] = "0.05"
os.environ["FLAGS_initial_cpu_memory_in_mb"] = "16"
os.environ["FLAGS_eager_delete_tensor_gb"] = "0.0"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.database.connection import init_db
from app.utils.helpers import ensure_directory
from app.api import scan, inspections, categories, rules


settings = get_settings()

# Windows consoles may default to cp1252; configure application logs before
# startup so legacy Unicode status text cannot abort the FastAPI lifespan.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# StaticFiles validates its directory during app construction, before lifespan
# startup runs, so create these directories before mounting them.
ensure_directory(settings.UPLOAD_DIR)
ensure_directory(settings.REPORT_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    # --- Startup ---
    # Ensure upload and report directories exist
    ensure_directory(settings.UPLOAD_DIR)
    ensure_directory(settings.REPORT_DIR)
    # Create database tables
    init_db()
    # Sync rule matrix from JSON into database
    from app.rules.rule_engine import sync_rules_to_db
    sync_rules_to_db()
    print(f"✅ {settings.APP_NAME} v{settings.APP_VERSION} started")
    yield
    # --- Shutdown ---
    print("🛑 Application shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "AI-Assisted Packaged Commodity Compliance Checking System. "
        "This is an inspection-support tool — NOT automatic legal certification."
    ),
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded images as static files
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
app.mount("/reports", StaticFiles(directory=settings.REPORT_DIR), name="reports")

# Register API routers
app.include_router(scan.router, prefix="/api", tags=["Scan"])
app.include_router(inspections.router, prefix="/api", tags=["Inspections"])
app.include_router(categories.router, prefix="/api", tags=["Categories"])
app.include_router(rules.router, prefix="/api", tags=["Rules"])


@app.get("/", tags=["Health"])
@app.get("/health", tags=["Health"])
def health_check():
    """Root health check endpoint."""
    return {
        "status": "running",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "disclaimer": (
            "This is an AI-assisted screening/inspection-support tool. "
            "Final legal verification must be made by the authorized inspector."
        ),
    }
