# BioAgent

## What This Is

Agentic investigator across scientific databases. Connects to AlphaSeq (local Postgres), SAbDab (REST), and ChEMBL (REST). Builds a data map of connected sources, then investigates research questions across them with full traceability.

## Tech Stack

- **Backend:** Python 3.12+, FastAPI, asyncpg, httpx
- **Agent:** Claude Sonnet 4 via direct Anthropic API (primary) or Bedrock (fallback)
- **Database:** PostgreSQL 16 + AlphaSeq dataset
- **Frontend:** React + TypeScript + Vite + Tailwind
- **Containerization:** Docker Compose
- **Hosting:** Hetzner CX22, Caddy reverse proxy, bioagent.eu

## Running Locally

```bash
# 1. Database
docker compose up -d db

# 2. API — pick one:
# Direct API:
export ANTHROPIC_API_KEY=...
PYTHONPATH=src uvicorn bioagent.api:app --reload --port 8000

# Or Bedrock:
assume Aizon-LLM---aizonllmsandbox/AizonLLMSandboxReaders
PYTHONPATH=src uvicorn bioagent.api:app --reload --port 8000

# 3. Frontend (separate terminal)
cd web && npm run dev
```

AlphaSeq data is already ingested (104,972 rows). No re-ingestion needed unless DB is reset.

## GitHub

- **Repo:** `tingidev/bioagent` (private)
- **SSH alias:** `github-personal` (personal account, not work `joerivwijn`)
- **Remote:** `git@github-personal:tingidev/bioagent.git`
- **Push:** `git push origin main`
- **Note:** `gh` CLI is authenticated as work account — use git directly, not `gh`

## Production Deployment

**Live at https://bioagent.eu**

### Server

- **SSH:** `ssh -i ~/.ssh/datavoorelkaar root@46.224.211.74`
- **Path:** `/opt/bioagent`
- **Secrets:** `/opt/bioagent/deploy/.env` (ANTHROPIC_API_KEY, POSTGRES_PASSWORD)

### Deploy

```bash
# Quick deploy
git push origin main
ssh -i ~/.ssh/datavoorelkaar root@46.224.211.74 \
  "cd /opt/bioagent && git pull origin main && cd deploy && docker compose up -d --build"

# If Caddyfile changed, also restart Caddy:
ssh -i ~/.ssh/datavoorelkaar root@46.224.211.74 \
  "cd /opt/datavoorelkaar/deploy/website && docker compose restart caddy"
```

Or use: `./deploy/deploy.sh`

### Caddy

BioAgent routes live in `/opt/datavoorelkaar/deploy/website/Caddyfile` (shared with datavoorelkaar).
- Uses `172.17.0.1:3001` (docker bridge IP, not `host.docker.internal` — IPv6 issues)
- `flush_interval -1` for SSE streaming
- Reload: `docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile`
- If reload doesn't apply, restart: `docker compose restart caddy`

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
├── api.py          # FastAPI: /health, /map, /investigate (SSE), /trace
└── ingest.py       # AlphaSeq streaming ingestion
deploy/
├── docker-compose.yml  # Production compose (db + api + web + ingest)
├── .env.example        # Template for secrets
├── Caddyfile.snippet   # Add to Hetzner Caddyfile
└── deploy.sh           # One-command deploy from local
web/
├── src/
│   ├── api.ts          # Auto-detects /api in prod, localhost:8000 in dev
│   ├── App.tsx         # Tab nav: How It Works | Investigate
│   └── components/     # HowItWorksPanel, InvestigationPanel, etc.
├── nginx.conf          # SPA routing + API proxy (buffering disabled for SSE)
└── Dockerfile          # node build → nginx serve
```

## Conventions

- All Pydantic models use `frozen=True`
- Immutable data flow — never mutate, return new objects
- Error handling at system boundaries only (API clients, user input)
- Parameterized queries for all database access
- Every tool call produces a `reproducible_query` string
- Conventional commits: feat, fix, refactor, test, docs, chore

## Environment Variables

- `ANTHROPIC_API_KEY` — Direct Anthropic API (preferred)
- `DATABASE_URL` — Postgres connection (default: `postgresql://bioagent:bioagent@localhost:5432/bioagent`)
- `AWS_DEFAULT_REGION` — Bedrock region (fallback, default: `us-east-1`)
- AWS credentials via environment for Bedrock fallback

## Gotchas

- `pyproject.toml` needs `[tool.hatch.build.targets.wheel] packages = ["src/bioagent"]` for src layout
- Ingest streams CSV row-by-row — loading full CSV into memory OOMs on 4GB servers
- nginx needs `proxy_buffering off` and Caddy needs `flush_interval -1` for SSE
- Caddy `host.docker.internal` resolves to IPv6 on Linux — use `172.17.0.1` instead
- `web/.npmrc` overrides global registry (Aizon CodeArtifact tokens in global `~/.npmrc`)
- SAbDab may return 503 — their server, not ours. Agent handles gracefully.
