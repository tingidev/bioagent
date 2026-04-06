"""FastAPI application — /health, /map, /investigate (SSE), /trace endpoints."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from bioagent.agent import investigate
from bioagent.data_map import build_data_map
from bioagent.models import HealthResponse, InvestigationRequest
from bioagent.tools import alphaseq, chembl, sabdab
from bioagent.trace import get_investigation

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioagent:bioagent@localhost:5432/bioagent")

_pool: asyncpg.Pool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage database pool lifecycle."""
    global _pool
    try:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    except Exception:
        _pool = None
    yield
    if _pool:
        await _pool.close()


app = FastAPI(
    title="BioAgent",
    description="Agentic investigator across scientific databases",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health():
    """System health check — reports connectivity to all data sources."""
    alphaseq_ok = await alphaseq.check_connectivity(_pool) if _pool else False
    sabdab_ok = await sabdab.check_connectivity()
    chembl_ok = await chembl.check_connectivity()
    count = await alphaseq.get_record_count(_pool) if _pool else None

    return HealthResponse(
        status="ok" if any([alphaseq_ok, sabdab_ok, chembl_ok]) else "degraded",
        sources={
            "alphaseq": alphaseq_ok,
            "sabdab": sabdab_ok,
            "chembl": chembl_ok,
        },
        alphaseq_count=count,
    )


@app.get("/map")
async def data_map():
    """Return the full data map: sources, entities, relationships."""
    dm = build_data_map()
    return {
        "sources": [s.model_dump() for s in dm.sources],
        "relationships": [r.model_dump() for r in dm.relationships],
        "built_at": dm.built_at.isoformat(),
    }


@app.post("/investigate")
async def start_investigation(request: InvestigationRequest):
    """Start an investigation — streams trace events via SSE."""
    async def event_stream() -> AsyncGenerator[dict, None]:
        async for event in investigate(request.question, _pool, api_key=request.api_key):
            yield {
                "event": event.event_type,
                "data": event.model_dump_json(),
            }

    return EventSourceResponse(event_stream())


@app.get("/trace/{investigation_id}")
async def get_trace(investigation_id: UUID):
    """Retrieve the full trace for a completed investigation."""
    inv = get_investigation(investigation_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return {
        "id": str(inv.id),
        "question": inv.question,
        "started_at": inv.started_at.isoformat(),
        "completed_at": inv.completed_at.isoformat() if inv.completed_at else None,
        "steps": [
            {
                "step_number": s.step_number,
                "phase": s.phase.value,
                "description": s.description,
                "reasoning": s.reasoning,
                "timestamp": s.timestamp.isoformat(),
                "tool_call": {
                    "tool_name": s.tool_call.tool_name,
                    "input_params": s.tool_call.input_params,
                    "output_summary": s.tool_call.output_summary,
                    "duration_ms": s.tool_call.duration_ms,
                    "reproducible_query": s.tool_call.reproducible_query,
                } if s.tool_call else None,
            }
            for s in inv.steps
        ],
        "report": inv.report,
    }
