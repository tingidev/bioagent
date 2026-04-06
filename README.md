# BioAgent

Agentic investigator that reasons across scientific databases to answer research questions about antibodies, drug targets, and bioactivity.

**Live at [bioagent.eu](https://bioagent.eu)**

## What It Does

BioAgent connects to three real scientific data sources and investigates them autonomously:

| Source | Type | Scale |
|--------|------|-------|
| **MIT AlphaSeq** | Local (Postgres) | 104,972 antibody binding measurements |
| **SAbDab** | REST API | 18,744 antibody crystal structures |
| **ChEMBL 35** | REST API | 21.1M bioactivity measurements |

Given a research question, four specialised agents work in sequence — each with a focused role, structured handoffs, and full traceability.

## How It Works

BioAgent uses the **RPES methodology** (Research, Plan, Execute, Synthesise), implemented as four independent agents with handoffs between each phase:

| Phase | Agent | Tools | Purpose |
|-------|-------|-------|---------|
| **Research** | Research Agent | Yes | Explore the data landscape — record counts, targets, connectivity |
| **Plan** | Plan Agent | No | Design investigation strategy with hypothesis and query sequence |
| **Execute** | Execute Agent | Yes | Run queries, cross-reference across databases, statistical analysis |
| **Synthesise** | Synthesis Agent | No | Produce structured report with citations and reproducible queries |

Phase transitions are architectural, not keyword-detected. Each agent receives the previous phase's output as structured context.

### Cross-Database Reasoning

The three databases share no common identifiers. Cross-referencing works through shared biology: AlphaSeq binding targets map to SAbDab antigen searches and ChEMBL target queries. The agent bridges sources through domain knowledge, not ID joins.

### Analytical Tools

The execute agent has access to statistical analysis: correlation, outlier detection, group comparison with effect size, ranking, cross-tabulation, and descriptive statistics. Every analytical claim is backed by a specific result.

### Audit Trail

Every tool call is logged with the exact query (SQL or API request), input parameters, output summary, and execution time. Findings are reproducible — any step can be re-run independently.

## Quick Start

```bash
# Set your Anthropic API key
export ANTHROPIC_API_KEY=sk-ant-...

# Start everything
docker compose up -d

# Load AlphaSeq data (first time only)
docker compose run --rm ingest

# Open the UI
open http://localhost:3000
```

## Development

```bash
# Database
docker compose up -d db

# Backend
export ANTHROPIC_API_KEY=sk-ant-...
pip install -e ".[dev]"
PYTHONPATH=src uvicorn bioagent.api:app --reload --port 8000

# Frontend
cd web && npm install && npm run dev
```

> **LLM Provider:** Uses Claude Sonnet 4 via the Anthropic API (recommended). Set `ANTHROPIC_API_KEY`, or provide AWS credentials for Bedrock as a fallback.

## Tech Stack

- **Backend:** Python, FastAPI, asyncpg, httpx
- **Agent:** Claude Sonnet 4 via Anthropic API
- **Database:** PostgreSQL 16
- **Frontend:** React, TypeScript, Vite, Tailwind CSS
- **Deployment:** Docker Compose

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────────────────┐
│   React UI  │────▶│  FastAPI SSE  │────▶│  RPES Agent Orchestrator     │
│  Live Trace │◀────│  /investigate │◀────│                              │
└─────────────┘     └──────────────┘     │  Research ─▶ Plan ─▶ Execute │
                                         │      ▼                  │    │
                                         │  Synthesise ◀───────────┘    │
                                         └──────────────┬───────────────┘
                                                        │
                    ┌───────────────┬────────────────────┼────────────┐
                    ▼               ▼                    ▼            ▼
              ┌──────────┐   ┌──────────┐         ┌──────────┐ ┌──────────┐
              │ AlphaSeq │   │  SAbDab  │         │  ChEMBL  │ │Statistics│
              │ Postgres │   │ REST API │         │ REST API │ │  Local   │
              └──────────┘   └──────────┘         └──────────┘ └──────────┘
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | System status and data source connectivity |
| `/map` | GET | Full data map: sources, entities, relationships |
| `/investigate` | POST | Start investigation (SSE stream of trace events) |
| `/trace/{id}` | GET | Full audit trail for a completed investigation |
