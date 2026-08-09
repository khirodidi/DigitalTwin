# api/main.py — FastAPI application: REST + WebSocket + engine + AI scheduler
import asyncio, json, logging
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from engine.engine        import DigitalTwinEngine
from api.ws_manager       import WebSocketManager
from api.routes           import assets, sensors, zones, events, system, config
from ai.training.trainer  import AITrainer

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

ws_manager  = WebSocketManager()
engine      : DigitalTwinEngine = None
ai_trainer  : AITrainer         = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, ai_trainer
    engine = DigitalTwinEngine(ws_manager=ws_manager)
    await engine.start()
    ai_trainer = AITrainer(engine=engine)
    ai_trainer.start_scheduler()
    yield
    engine.stop()
    ai_trainer.stop_scheduler()

app = FastAPI(title="Digital Twin — Factory Monitoring",
              description="Real-time factory digital twin via WSN + AI",
              version="1.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000","http://frontend:3000"],
    allow_methods=["*"], allow_headers=["*"])

# ── Serve uploaded blueprint images at /static/blueprints/<file> ────────────
import os
from pathlib import Path
STATIC_DIR = Path(os.getenv("STATIC_DIR", "/app/static"))
(STATIC_DIR / "blueprints").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(assets.router,  prefix="/api/assets",  tags=["Assets"])
app.include_router(sensors.router, prefix="/api/sensors", tags=["Sensors"])
app.include_router(zones.router,   prefix="/api/zones",   tags=["Zones"])
app.include_router(events.router,  prefix="/api/events",  tags=["Events"])
app.include_router(system.router,  prefix="/api/system",  tags=["System"])
app.include_router(config.router,  prefix="/api/config",  tags=["Config"])

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        if engine:
            await ws.send_json({"event":"snapshot","payload":engine.get_snapshot()})
        while True:
            data = await ws.receive_text()
            if json.loads(data).get("type") == "ping":
                await ws.send_json({"type":"pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)

@app.get("/health")
async def health():
    return {"status":"ok","timestamp":datetime.utcnow().isoformat(),
            "engine":engine is not None,"ws_clients":ws_manager.count}

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)
