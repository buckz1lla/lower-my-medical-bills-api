from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=True)

from app.api import eob_routes, analytics_routes, payments_routes, admin_routes, email_routes, appeal_routes

# Initialize FastAPI app
app = FastAPI(
    title="Lower My Medical Bills API",
    description="API for analyzing medical bills and identifying savings opportunities",
    version="0.1.0"
)

# CORS middleware - allow frontend connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root endpoint
@app.get("/")
def read_root():
    return {"message": "Lower My Medical Bills API", "version": "0.1.0"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

# Include routers
app.include_router(eob_routes.router, prefix="/api/eob", tags=["EOB Analysis"])
app.include_router(analytics_routes.router, prefix="/api", tags=["Analytics"])
app.include_router(payments_routes.router, prefix="/api", tags=["Payments"])
app.include_router(admin_routes.router, prefix="/api", tags=["Owner Auth"])
app.include_router(email_routes.router, prefix="/api", tags=["Email"])
app.include_router(appeal_routes.router, prefix="/api", tags=["Appeal Tracker"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
