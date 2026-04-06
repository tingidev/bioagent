# BioAgent

Agentic investigator that reasons across scientific databases to answer research questions about antibodies, drug targets, and bioactivity.

## What It Does

BioAgent connects to three real scientific data sources and navigates them autonomously:

| Source | Type | Scale |
|--------|------|-------|
| **MIT AlphaSeq** | Local (Postgres) | 104,972 antibody binding measurements |
| **SAbDab** | REST API | 18,744 antibody crystal structures |
| **ChEMBL 35** | REST API | 21.1M bioactivity measurements |

The agent builds a **data map** of connected sources, takes a research question, plans an investigation strategy, executes queries across databases, and produces a structured report — with every step traced and every finding reproducible.

## How It Works

1. **Data Map** — The agent knows what each source contains, what entities exist, and how they relate. This map is visible in the UI and constrains the agent's reasoning.
2. **Investigation Loop** — Research → Plan → Execute → Synthesize. Each phase is visible in real time.
3. **Audit Trail** — Every API call, every SQL query, every reasoning step is logged. Every finding includes the exact query that produced it.

## Quick Start

```bash
# Start everything
docker compose up -d

# Load AlphaSeq data
docker compose run --rm ingest

# Open the UI
open http://localhost:3000
```

## Development

```bash
# Database
docker compose up -d db

# Backend
pip install -e ".[dev]"
PYTHONPATH=src uvicorn bioagent.api:app --reload --port 8000

# Frontend
cd web && npm install && npm run dev
```

## Tech Stack

- **Backend:** Python, FastAPI, asyncpg, httpx
- **Agent:** Claude via AWS Bedrock
- **Database:** PostgreSQL 16
- **Frontend:** React, TypeScript, Vite, Tailwind CSS
- **Deployment:** Docker Compose

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   React UI  │────▶│  FastAPI SSE  │────▶│  Agent Loop  │
│  Live Trace │◀────│  /investigate │◀────│  Claude LLM  │
└─────────────┘     └──────────────┘     └──────┬───────┘
                                                │
                    ┌───────────────┬────────────┼────────────┐
                    ▼               ▼            ▼            ▼
              ┌──────────┐   ┌──────────┐  ┌──────────┐ ┌──────────┐
              │ AlphaSeq │   │  SAbDab  │  │  ChEMBL  │ │Statistics│
              │ Postgres │   │ REST API │  │ REST API │ │  Local   │
              └──────────┘   └──────────┘  └──────────┘ └──────────┘
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | System status + data source connectivity |
| `/map` | GET | Full data map: sources, entities, relationships |
| `/investigate` | POST | Start investigation (SSE stream of trace events) |
| `/trace/{id}` | GET | Full audit trail for a completed investigation |
