"""FastAPI main application entry point."""

import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.api import routes, websocket

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Autonomous Resume Agent API",
    description="Agentic AI system for tailored resume generation",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create required directories
os.makedirs(settings.output_dir, exist_ok=True)
os.makedirs(settings.upload_dir, exist_ok=True)

# Include routers
app.include_router(routes.router)
app.include_router(websocket.router)

# Mount static files (optional, if we want to serve the frontend from FastAPI)
# app.mount("/", StaticFiles(directory="../frontend/dist", html=True), name="static")

@app.get("/health")
def health_check():
    """Basic health check endpoint."""
    return {"status": "ok", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    # Test localhost binding constraint
    logger.info("Starting server on %s:%d", settings.host, settings.port)
    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=True)
