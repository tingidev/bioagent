#!/bin/bash
# Deploy BioAgent to Hetzner server
# Run from local machine: ./deploy/deploy.sh

set -e

SERVER="root@46.224.211.74"
SSH_KEY="~/.ssh/datavoorelkaar"
REMOTE_PATH="/opt/bioagent"

echo "=== BioAgent Deploy ==="

# Check for uncommitted changes
if ! git diff --quiet HEAD; then
    echo "ERROR: Uncommitted changes detected. Commit or stash them first."
    exit 1
fi

COMMIT=$(git rev-parse --short HEAD)
echo "Deploying commit: $COMMIT"
echo ""

ssh -i $SSH_KEY $SERVER << 'EOF'
    set -e

    # First-time setup: clone if not present
    if [ ! -d /opt/bioagent ]; then
        echo "=== First-time setup: cloning repo ==="
        git clone https://github.com/tingidev/bioagent.git /opt/bioagent
    fi

    cd /opt/bioagent
    echo "=== Pulling latest code ==="
    git fetch origin main
    git reset --hard origin/main

    echo "=== Deploying ==="
    cd deploy

    # Check .env exists
    if [ ! -f .env ]; then
        echo "ERROR: deploy/.env not found. Create it with:"
        echo "  ANTHROPIC_API_KEY=sk-ant-..."
        echo "  POSTGRES_PASSWORD=<random>"
        exit 1
    fi

    docker compose down
    docker compose up -d --build

    echo "=== Waiting for services ==="
    sleep 15

    echo "=== Container status ==="
    docker compose ps

    echo "=== Health check ==="
    curl -sf http://localhost:8001/health && echo "" || echo "API health check failed!"

    echo "=== Ingesting data (if needed) ==="
    # Only run ingest if DB is empty
    COUNT=$(docker compose exec -T db psql -U bioagent -t -c "SELECT count(*) FROM antibody_bindings;" 2>/dev/null | tr -d ' ' || echo "0")
    if [ "$COUNT" = "0" ] || [ -z "$COUNT" ]; then
        echo "Database empty — running ingest..."
        docker compose run --rm ingest
    else
        echo "Database has $COUNT records — skipping ingest."
    fi
EOF

echo ""
echo "=== Deploy complete ==="
echo "Deployed: $COMMIT"
echo "Site: https://bioagent.eu"
echo "API: https://bioagent.eu/api/health"
echo ""
echo "Monitor logs: ssh -i $SSH_KEY $SERVER 'cd /opt/bioagent/deploy && docker compose logs -f'"
