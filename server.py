"""
server.py — FastAPI application entry point for Jarvis VPS.
Sets up routes, middleware, static file serving, and WebSockets.
"""

import logging
import os
import sys

# Force UTF-8 output on Windows (fixes cp1252 crashes with unicode chars)
os.environ.setdefault('PYTHONUTF8', '1')
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import CONFIG
from memory import init_db
from voice import load_whisper, cleanup_audio_cache
from auth import decode_token, ACCESS
from actions.downloader import set_ws_callback

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO if not CONFIG.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(stream=open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False, errors='replace')),
        logging.FileHandler(CONFIG.LOG_FILE, encoding='utf-8'),
    ],
)
logger = logging.getLogger("jarvis")

# Silence noisy third-party loggers
logging.getLogger("watchfiles").setLevel(logging.WARNING)
logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("comtypes").setLevel(logging.WARNING)

# ── Rate limiting ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=[CONFIG.RATE_LIMIT])


# ── Lifespan (Startup/Shutdown) ───────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Jarvis VPS v%s...", CONFIG.VERSION)
    CONFIG.validate()
    
    await init_db()
    
    # Load Whisper in a background thread so it doesn't block server startup
    import threading
    threading.Thread(target=load_whisper, daemon=True).start()
    
    # Background scheduler for cleanup tasks
    import schedule
    import time
    schedule.every(5).minutes.do(lambda: cleanup_audio_cache(CONFIG.AUDIO_CACHE_TTL))
    
    def run_scheduler():
        while True:
            schedule.run_pending()
            time.sleep(1)
            
    threading.Thread(target=run_scheduler, daemon=True).start()
    
    yield
    # Shutdown
    logger.info("Shutting down Jarvis VPS...")


# ── App Setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Jarvis VPS",
    version=CONFIG.VERSION,
    lifespan=lifespan,
    docs_url="/docs" if CONFIG.DEBUG else None,
    redoc_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CONFIG.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handler for unhandled errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal Server Error", "code": "SERVER_ERROR"}
    )

# ── Static Files ──────────────────────────────────────────────────────────────
# Serve generated TTS audio files
app.mount("/audio", StaticFiles(directory=CONFIG.AUDIO_CACHE_FOLDER), name="audio")
app.mount("/downloads", StaticFiles(directory=CONFIG.DOWNLOAD_FOLDER), name="downloads")


# ── Routes ────────────────────────────────────────────────────────────────────
from api.routes import command, auth, memory, contacts, downloads, timers, health

app.include_router(command.router)
app.include_router(auth.router)
app.include_router(memory.router)
app.include_router(contacts.router)
app.include_router(downloads.router)
app.include_router(timers.router)
app.include_router(health.router)


# ── WebSockets ────────────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        # session_id -> list of active connections
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        logger.debug("WS connected: session=%s", session_id)

    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        logger.debug("WS disconnected: session=%s", session_id)

    async def send_to_session(self, session_id: str, message: dict):
        connections = self.active_connections.get(session_id, [])
        for conn in connections:
            try:
                await conn.send_json(message)
            except Exception:
                pass

ws_manager = ConnectionManager()

# Hook the downloader WS callback to our manager
set_ws_callback(ws_manager.send_to_session)


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str, token: str = ""):
    """
    WebSocket endpoint for real-time events (downloads, long-running actions).
    Requires JWT token as a query parameter.
    """
    try:
        # Validate token
        decode_token(token, ACCESS)
    except Exception as exc:
        logger.warning("WS auth failed: %s", exc)
        await websocket.close(code=1008) # Policy Violation
        return

    await ws_manager.connect(websocket, session_id)
    try:
        while True:
            # We don't really expect client to send much, but we need to keep loop running
            data = await websocket.receive_text()
            logger.debug("WS received from %s: %s", session_id, data)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, session_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app", 
        host=CONFIG.HOST, 
        port=CONFIG.PORT, 
        reload=CONFIG.DEBUG,
        reload_excludes=["*.log", "logs/*", "data/*", "audio_cache/*", "downloads/*", "*.db", "*.db-journal", "*.db-wal", "*.db-shm"]
    )
