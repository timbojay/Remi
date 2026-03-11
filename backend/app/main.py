from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import init_db, close_db
from app.routers import chat, status, knowledge, biography
from app.services.maintenance import start_maintenance_loop, stop_maintenance_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await start_maintenance_loop()
    yield
    stop_maintenance_loop()
    await close_db()


app = FastAPI(title="Remi", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(status.router)
app.include_router(knowledge.router)
app.include_router(biography.router)
