"""FastAPI + Socket.IO entrypoint for the Migration Agent backend."""
import socketio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List, Optional

from app import config
from app.adapters import mysql, redshift, storage
from app.orchestrator.agentic import start_agentic_run, start_review_run, continue_review_run
from app.reporting.report import build_report
from app.pipelines import PIPELINES, DEFAULT_PIPELINE, get_pipeline, list_pipelines

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")


@sio.event
async def join_run(sid, run_id):
    await sio.enter_room(sid, f"run:{run_id}")


api = FastAPI(title="Migration Agent")
api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _source_adapter(pipeline: str):
    return mysql if pipeline == "mysql_snowflake" else redshift


class RunRequest(BaseModel):
    schemaName: str
    pipeline: str = DEFAULT_PIPELINE
    approved: bool = False


class EditedTable(BaseModel):
    name: str
    ddl: str


class ContinueRequest(BaseModel):
    approved: bool = False
    editedTables: Optional[List[EditedTable]] = None


@api.get("/api/health")
async def health():
    return {"ok": True}


@api.get("/api/pipeline/config")
async def get_config():
    return config.config_summary()


@api.get("/api/pipeline/pipelines")
async def get_pipelines():
    return {"pipelines": list_pipelines(), "default": DEFAULT_PIPELINE}


@api.get("/api/pipeline/schemas")
async def get_schemas(pipeline: str = DEFAULT_PIPELINE):
    if pipeline not in PIPELINES:
        raise HTTPException(400, f"Unknown pipeline '{pipeline}'")
    p = get_pipeline(pipeline)
    adapter = _source_adapter(pipeline)
    return {"schemas": adapter.list_available_schemas(p["sampleSchemaDir"])}


@api.get("/api/pipeline/runs")
async def get_runs():
    return {"runs": storage.get_run_history()}


@api.post("/api/pipeline/agentic-runs")
async def agentic_run(req: RunRequest):
    if not req.schemaName:
        raise HTTPException(400, "schemaName is required")
    if req.pipeline not in PIPELINES:
        raise HTTPException(400, f"Unknown pipeline '{req.pipeline}'")
    run_id, room = await start_agentic_run(req.schemaName, req.pipeline, req.approved, sio)
    return {"runId": run_id, "room": room}


@api.post("/api/pipeline/review-runs")
async def review_run(req: RunRequest):
    if not req.schemaName:
        raise HTTPException(400, "schemaName is required")
    if req.pipeline not in PIPELINES:
        raise HTTPException(400, f"Unknown pipeline '{req.pipeline}'")
    run_id, room = await start_review_run(req.schemaName, req.pipeline, sio)
    return {"runId": run_id, "room": room}


@api.post("/api/pipeline/review-runs/{run_id}/continue")
async def review_run_continue(run_id: str, req: ContinueRequest):
    edited = [t.dict() for t in req.editedTables] if req.editedTables else None
    result = await continue_review_run(run_id, req.approved, edited, sio)
    return result


@api.post("/api/pipeline/runs")
async def run(req: RunRequest):
    if not req.schemaName:
        raise HTTPException(400, "schemaName is required")
    if req.pipeline not in PIPELINES:
        raise HTTPException(400, f"Unknown pipeline '{req.pipeline}'")
    run_id, room = await start_agentic_run(req.schemaName, req.pipeline, req.approved, sio)
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


app = socketio.ASGIApp(sio, other_asgi_app=api, socketio_path="/socket.io")
