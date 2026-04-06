# BioAgent

## What This Is

Agentic investigator across scientific databases. Connects to AlphaSeq (local Postgres), SAbDab (REST), and ChEMBL (REST). Builds a data map of connected sources, then investigates research questions across them with full traceability.

## Tech Stack

- **Backend:** Python 3.12+, FastAPI, asyncpg, httpx
- **Agent:** Claude via AWS Bedrock (anthropic SDK with bedrock runtime)
- **Database:** PostgreSQL 16 + AlphaSeq dataset
- **Frontend:** React + TypeScript + Vite + Tailwind
- **Containerization:** Docker Compose

## Running

```bash
# Full stack
docker compose up -d

# Dev mode
docker compose up -d db                    # Postgres on :5432
PYTHONPATH=src uvicorn bioagent.api:app --reload --port 8000
cd web && npm run dev                      # React on :3000
```

## Project Structure

```
src/bioagent/
├── models.py       # Pydantic models (frozen=True)
├── data_map.py     # Source registry, entity/relationship map
├── tools/
│   ├── alphaseq.py # AlphaSeq queries (local Postgres)
│   ├── sabdab.py   # SAbDab API client
│   ├── chembl.py   # ChEMBL API client
│   └── statistics.py
├── agent.py        # Orchestration: plan → execute → synthesize
├── trace.py        # Audit trail
└── api.py          # FastAPI: /health, /map, /investigate (SSE), /trace
```

## Conventions

- All Pydantic models use `frozen=True`
- Immutable data flow — never mutate, return new objects
- Error handling at system boundaries only (API clients, user input)
- Parameterized queries for all database access
- Every tool call produces a `reproducible_query` string
- Conventional commits: feat, fix, refactor, test, docs, chore

## Environment Variables

- `DATABASE_URL` — Postgres connection (default: `postgresql://bioagent:bioagent@localhost:5432/bioagent`)
- `AWS_DEFAULT_REGION` — Bedrock region (default: `eu-west-1`)
- AWS credentials via environment (assume role or explicit keys)
