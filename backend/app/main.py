
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import Base, engine
from app import models
from app.api.doctors import router as doctors_router


app = FastAPI(
    title="Voice AI Doctor Appointment Assistant",
    description="Backend API for the AI-powered doctor appointment assistant.",
    version="1.0.0",
)

app.include_router(doctors_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "message": "Voice AI Doctor Appointment Assistant API",
        "status": "running",
    }


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "backend",
    }

@app.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)