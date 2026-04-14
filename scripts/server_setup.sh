#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# TPRM AI Assessment Platform — First-Run Server Setup Script
#
# Run this ONCE on a fresh server (Ubuntu 22.04 / 24.04 recommended):
#   chmod +x scripts/server_setup.sh
#   sudo bash scripts/server_setup.sh
#
# What it does:
#   1. Installs Docker + Docker Compose plugin
#   2. Generates a strong SECRET_KEY and writes it to .env
#   3. Prompts for DB password if not already in .env
#   4. Starts the DB container, waits for it to be healthy
#   5. Creates the database schema (via init_db) and seeds users from config/users.json
#   6. Starts the full application stack
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

echo ""
echo "══════════════════════════════════════════════════"
echo "  TPRM AI Assessment Platform — Server Setup"
echo "══════════════════════════════════════════════════"
echo ""

# ── Step 1: Docker ────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "[1/6] Installing Docker..."
    apt-get update -qq
    apt-get install -y ca-certificates curl gnupg lsb-release
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable --now docker
    echo "    Docker installed."
else
    echo "[1/6] Docker already installed — skipping."
fi

# ── Step 2: .env file ─────────────────────────────────
echo ""
echo "[2/6] Configuring .env..."
if [ ! -f "$ENV_FILE" ]; then
    cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
    echo "    Created .env from .env.example"
fi

# Generate a real SECRET_KEY if still placeholder
if grep -qE "^SECRET_KEY=(CHANGE_ME|your_development|$)" "$ENV_FILE" 2>/dev/null; then
    NEW_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || \
              openssl rand -hex 32)
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$NEW_KEY|" "$ENV_FILE"
    echo "    Generated new SECRET_KEY."
fi

# Prompt for DB password if still placeholder
if grep -q "CHANGE_ME_strong_db_password" "$ENV_FILE"; then
    echo ""
    read -rsp "    Enter a strong PostgreSQL password for tprm_user: " DB_PASS
    echo ""
    sed -i "s|CHANGE_ME_strong_db_password|$DB_PASS|" "$ENV_FILE"
    echo "    Database password set."
fi

# ── Step 3: Required directories ─────────────────────
echo ""
echo "[3/6] Creating runtime directories..."
mkdir -p "$PROJECT_DIR/data/artifacts" \
         "$PROJECT_DIR/data/contracts" \
         "$PROJECT_DIR/data/policies" \
         "$PROJECT_DIR/data/questionnaires" \
         "$PROJECT_DIR/assessments" \
         "$PROJECT_DIR/config"
echo "    Done."

# ── Step 4: Start database ───────────────────────────
echo ""
echo "[4/6] Starting database container..."
cd "$PROJECT_DIR"
docker compose -f docker-compose.prod.yml up -d db
echo "    Waiting for PostgreSQL to be healthy..."
for i in $(seq 1 30); do
    if docker compose -f docker-compose.prod.yml exec db \
        pg_isready -U "$(grep POSTGRES_USER .env | cut -d= -f2)" &>/dev/null; then
        echo "    PostgreSQL is ready."
        break
    fi
    sleep 2
    if [ "$i" -eq 30 ]; then
        echo "    ERROR: PostgreSQL did not become ready in time. Check docker logs tprm-db"
        exit 1
    fi
done

# ── Step 5: Init schema + seed users ─────────────────
echo ""
echo "[5/6] Initialising database schema and seeding users..."
# Run schema init via Python (reuses init_db + seed_users_from_json)
docker compose -f docker-compose.prod.yml run --rm \
    -e TPRM_DEBUG=false \
    app python -c "
from webapp.db import init_db, seed_users_from_json, seed_audit_from_json
init_db()
n = seed_users_from_json()
print(f'  Schema ready. Seeded {n} user(s) from config/users.json.')
seed_audit_from_json()
print('  Audit log migrated.')
"
echo "    Done."

# ── Step 6: Start full stack ─────────────────────────
echo ""
echo "[6/6] Starting full application stack..."
docker compose -f docker-compose.prod.yml up -d
echo ""
echo "══════════════════════════════════════════════════"
echo "  Setup complete!"
echo ""
echo "  App is running at http://$(hostname -I | awk '{print $1}'):$(grep TPRM_PORT .env | cut -d= -f2 || echo 8085)"
echo ""
echo "  Default users (from config/users.json):"
docker compose -f docker-compose.prod.yml exec db psql \
    -U "$(grep POSTGRES_USER .env | cut -d= -f2)" \
    -d "$(grep POSTGRES_DB .env | cut -d= -f2)" \
    -c "SELECT email, name, role FROM app_users ORDER BY role DESC;" 2>/dev/null || true
echo ""
echo "  To view logs:   docker compose -f docker-compose.prod.yml logs -f app"
echo "  To stop:        docker compose -f docker-compose.prod.yml down"
echo "══════════════════════════════════════════════════"
