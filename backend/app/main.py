import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

from .database import engine
from . import models
from .routers import auth, users, stores, casts, customers, tickets, ai, excel_import
from .init_db import init_db

init_db()

app = FastAPI(
    title="RYOH API",
    description="ナイトレジャー業務統合管理システム",
    version="1.0.0",
)

allow_all = os.getenv("CORS_ALLOW_ALL", "false").lower() == "true"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all else ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"],
    allow_credentials=not allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(stores.router)
app.include_router(casts.router)
app.include_router(customers.router)
app.include_router(tickets.router)
app.include_router(ai.router)
app.include_router(excel_import.router)


uploads_dir = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")


@app.get("/")
def root():
    return {"message": "RYOH API", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "ok"}
