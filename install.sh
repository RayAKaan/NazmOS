#!/bin/bash
# NazmOS KSA – One-click installer
# For Ubuntu / Debian / WSL
set -e

echo "=============================="
echo "  NazmOS KSA v2.1 – Installer"
echo "  SAR 25,000 License"
echo "=============================="
echo ""

if ! command -v docker &> /dev/null; then
  echo "[!] Docker not found. Installing Docker..."
  curl -fsSL https://get.docker.com | sh
fi

if ! docker compose version &> /dev/null; then
  echo "[!] docker compose not found. Please install Docker Compose v2"
  exit 1
fi

# Generate secure secrets
if [ ! -f .env ]; then
  echo "[+] Creating .env (production secrets)"
  SECRET=$(openssl rand -base64 48 | tr -d '\n')
  DB_PASS=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 24)
  REDIS_PASS=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 24)
  VAULT_KEY=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)
  echo "[?] Public URL for the app (what users/browsers will hit, e.g. https://app.nazmak.com):"
  read -r -p "    PUBLIC_API_URL [http://localhost:3000]: " PUBLIC_API_URL
  PUBLIC_API_URL=${PUBLIC_API_URL:-http://localhost:3000}
  echo "[?] Sentry DSN (required in production; grab one at https://sentry.io):"
  read -r -p "    SENTRY_DSN: " SENTRY_DSN
  if [ -z "$SENTRY_DSN" ]; then
    echo "[-] SENTRY_DSN is required in production. Aborting."
    exit 1
  fi
  cat > .env <<EOF
# NazmOS KSA – Production
SECRET_KEY=$SECRET
DB_PASSWORD=$DB_PASS
REDIS_PASSWORD=$REDIS_PASS
ENVIRONMENT=production
CREDENTIAL_MASTER_KEY=$VAULT_KEY
DATABASE_APP_ROLE=nazmos_app
SENTRY_DSN=$SENTRY_DSN
PUBLIC_API_URL=$PUBLIC_API_URL
CORS_ORIGINS=$PUBLIC_API_URL
EOF
  echo "  Secrets generated"
fi

# Backend .env – mirrors compose env
if [ ! -f backend/.env ]; then
  echo "[+] Creating backend/.env"
  # Source from root .env
  set -a; source .env; set +a
  cat > backend/.env <<EOF
ENVIRONMENT=production
SECRET_KEY=$SECRET_KEY
DATABASE_URL=postgresql+asyncpg://nazmos:${DB_PASSWORD}@postgres:5432/nazmos
CORS_ORIGINS=$CORS_ORIGINS
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
SENTRY_DSN=$SENTRY_DSN
DATABASE_APP_ROLE=$DATABASE_APP_ROLE
CREDENTIAL_MASTER_KEY=$CREDENTIAL_MASTER_KEY
CHAT_ENABLED=false
BILLING_ENABLED=false
USE_MOCK_LLM=true
DEFAULT_CURRENCY=SAR
DEFAULT_TIMEZONE=Asia/Riyadh
EOF
fi

if [ ! -f frontend/.env.local ]; then
  echo "[+] Creating frontend/.env.local"
  cat > frontend/.env.local << 'EOF'
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_CHAT_ENABLED=false
NEXT_PUBLIC_APP_NAME=NazmOS KSA
NEXT_PUBLIC_CURRENCY=SAR
NEXT_PUBLIC_LOCALE=ar-SA
EOF
fi

echo ""
echo "[+] Starting NazmOS KSA (production)..."
docker compose -f docker-compose.prod.yml up -d --build

echo ""
echo "Waiting 15s for services..."
sleep 15

echo ""
echo "[+] Installing nightly backup systemd service..."
NAZMOS_DIR="$(pwd)"
sed "s|/opt/nazmos|$NAZMOS_DIR|g" deployment/nazmos-backup.service > /etc/systemd/system/nazmos-backup.service
cp deployment/nazmos-backup.timer /etc/systemd/system/nazmos-backup.timer
systemctl daemon-reload
systemctl enable --now nazmos-backup.timer

echo ""
echo "=========================================="
echo "  NazmOS KSA is running!"
echo "=========================================="
echo "  Frontend: http://localhost:3000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "  First time? Go to http://localhost:3000/register"
echo "  Create your admin account, then upload your POS CSV"
echo ""
echo "  Support WhatsApp: +966 5X XXX XXXX"
echo "=========================================="
