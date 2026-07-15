"""FastAPI + Socket.IO entrypoint for the Migration Agent backend."""
import socketio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from app import config
from app.adapters import mysql, storage
from app.orchestrator.agentic import start_agentic_run
from app.reporting.report import build_report

# ---- Socket.IO (ASGI) so the React socket.io-client works unchanged ----
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")


@sio.event
async def join_run(sid, run_id):
    await sio.enter_room(sid, f"run:{run_id}")


# ---- FastAPI ----
api = FastAPI(title="Migration Agent")
api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class RunRequest(BaseModel):
    schemaName: str
    approved: bool = False


@api.get("/api/health")
async def health():
    return {"ok": True}


@api.get("/api/pipeline/config")
async def get_config():
    return config.config_summary()


@api.get("/api/pipeline/schemas")
async def get_schemas():
    return {"schemas": mysql.list_available_schemas()}


@api.get("/api/pipeline/runs")
async def get_runs():
    return {"runs": storage.get_run_history()}


@api.post("/api/pipeline/agentic-runs")
async def agentic_run(req: RunRequest):
    if not req.schemaName:
        raise HTTPException(400, "schemaName is required")
    run_id, room = await start_agentic_run(req.schemaName, req.approved, sio)
    return {"runId": run_id, "room": room}


# Kept for compatibility with the old deterministic endpoint name.
@api.post("/api/pipeline/runs")
async def run(req: RunRequest):
    if not req.schemaName:
        raise HTTPException(400, "schemaName is required")
    run_id, room = await start_agentic_run(req.schemaName, req.approved, sio)
    return {"runId": run_id, "room": room}


@api.get("/api/pipeline/runs/{run_id}/report")
async def download_report(run_id: str):
    record = storage.get_run(run_id)
    if not record:
        raise HTTPException(404, "run not found")
    pdf = build_report(record)
    filename = f"migration-review-{record.get('schemaName','run')}-{run_id}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# Mount Socket.IO at /socket.io, FastAPI everywhere else.
app = socketio.ASGIApp(sio, other_asgi_app=api, socketio_path="/socket.io")