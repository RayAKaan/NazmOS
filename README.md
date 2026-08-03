# NazmOS

AI-powered decision layer for physical businesses (supermarkets, cafes, retail shops, hotels).

## Features

### Phase 1 - Core Platform
- 📊 **Dashboard** - Real-time KPIs, alerts, sales trends, and health scores
- 📦 **Inventory Management** - Track stock levels, identify dead stock, and manage reorders
- 🔔 **Smart Alerts** - Get notified about low stock, trends, and opportunities
- 📈 **Analytics** - Sales trends, category breakdown, and top products
- 🔐 **Authentication** - JWT-based secure authentication

### Phase 2 - AI & Automation
- 🤖 **Baseer AI Chat** - Conversational AI for business insights and recommendations
- 📤 **Data Upload** - CSV/Excel upload with automatic ETL pipeline
- 📉 **Demand Forecasting** - Prophet-based sales forecasting with festival alerts
- 🎯 **Decision Engine** - AI-powered actionable recommendations with prioritization
- ⚡ **Real-time Updates** - SSE streaming for instant AI responses
- 🗄️ **Redis Caching** - Fast cached forecasts and chat memory
- 🔄 **Background Tasks** - Celery workers for heavy processing

## Tech Stack

### Backend
- Python 3.13+
- FastAPI
- SQLAlchemy 2.0 (async)
- PostgreSQL 17+
- Alembic (migrations)
- Pydantic v2 / pydantic-settings
- Redis + Celery (optional background tasks; zero-cost mode disables both)
- OpenRouter gateway (model-agnostic; default `google/gemma-2-9b-it:free`)
- Prophet (forecasting)

### Frontend
- Next.js 16 (App Router)
- React 18
- TypeScript
- Tailwind CSS
- Recharts
- Zustand
- React Hook Form + Zod
- Framer Motion (animations)
- React Dropzone (file upload)

## Quick Start

### Prerequisites

- Docker & Docker Compose (optional)
- Node.js 20+ (for local development)
- Python 3.13+ (for local development)
- PostgreSQL 17+ (local or Docker)

### Using Docker (Recommended)

```bash
cd NazmOS
# Zero-cost/SQLite mode
docker-compose -f docker-compose.sqlite.yml up

# Full local stack (Postgres 17 + Redis + backend + frontend)
docker-compose -f docker-compose.local.yml up
```

The application will be available at:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Flower (Celery): http://localhost:5555

### Local Development

#### Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your DATABASE_URL, SECRET_KEY, and optional OpenRouter key.

# Run PostgreSQL 17 (local example)
sudo service postgresql start
# Ensure a `nazmos` user/database exist, or point DATABASE_URL at your instance.

# Apply migrations
python -m alembic upgrade head

# Run Redis (optional; zero-cost mode works without it)
redis-server

# Run Celery worker (optional, for background tasks)
celery -A celery_app worker --loglevel=info

# Run Celery beat (optional, for scheduled tasks)
celery -A celery_app beat --loglevel=info

# Run the server
uvicorn app.main:app --reload
```

#### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Create .env.local file
cp .env.local.example .env.local

# Run the development server
npm run dev
```

## Phase 2 Setup

### Environment Variables

Key backend `.env` values:

```env
# Core
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos
SECRET_KEY=change-me-in-production-minimum-48-chars

# Zero-cost architecture
USE_CELERY=false
USE_REDIS=false
USE_CLIENT_ETL=false

# Redis (optional)
REDIS_URL=redis://localhost:6379/0

# LLM via OpenRouter (mock LLM is used when OPENROUTER_API_KEY is empty)
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
USE_MOCK_LLM=true
LLM_MODEL=google/gemma-2-9b-it:free

# Uploads / object storage
UPLOAD_DIR=./uploads
STORAGE_BACKEND=local  # local | s3 | minio
# STORAGE_BUCKET=...
# STORAGE_ENDPOINT=...
# STORAGE_ACCESS_KEY=...
# STORAGE_SECRET_KEY=...

# Observability
SENTRY_DSN=
SENTRY_ENVIRONMENT=development
PROMETHEUS_ENABLED=true

# PostgreSQL Row-Level Security (production)
# Leave empty in dev to run as table owner; set in prod to enforce RLS.
DATABASE_APP_ROLE=nazmos_app
```

### Feature Flags

Feature flags are now dynamic (database-backed) and support per-business
overrides and plan-level gating. Static env booleans are used as a fallback
before the flag table is seeded.

- `AGENT_ENABLED`, `CHAT_ENABLED`, `BILLING_ENABLED`, etc. — static defaults.
- Run migrations; `seed_default_flags()` populates the `feature_flags` table on
  startup.
- Use `is_feature_enabled()` / `set_business_override()` to control rollout or
  kill-switches without a redeploy.

## Project Structure

```
NazmOS/
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app
│   │   ├── config.py        # Settings
│   │   ├── database/        # Models, connection, seeder
│   │   ├── schemas/         # Pydantic schemas
│   │   ├── routers/         # API routes
│   │   ├── services/        # Business logic
│   │   ├── tasks/           # Celery tasks
│   │   ├── middleware/      # Auth, rate limiting
│   │   └── utils/           # Security, logging, currency
│   ├── celery_app.py       # Celery configuration
│   ├── alembic/            # Database migrations
│   └── tests/               # Unit tests
├── frontend/
│   ├── src/
│   │   ├── app/            # Next.js pages
│   │   │   └── (dashboard)/
│   │   │       ├── dashboard/
│   │   │       ├── inventory/
│   │   │       ├── chat/       # Baseer AI chat
│   │   │       └── upload/      # Data upload
│   │   ├── components/
│   │   │   ├── chat/           # Chat UI components
│   │   │   ├── upload/         # Upload components
│   │   │   └── dashboard/      # Dashboard components
│   │   ├── hooks/          # Custom hooks
│   │   ├── stores/         # Zustand stores
│   │   ├── lib/            # Utilities
│   │   └── types/          # TypeScript types
│   └── __tests__/          # Tests
└── README.md
```

## API Endpoints

### Authentication
- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - Login
- `POST /api/v1/auth/refresh` - Refresh token
- `GET /api/v1/auth/me` - Get current user

### Dashboard
- `GET /api/v1/dashboard/summary` - Get dashboard KPIs
- `GET /api/v1/dashboard/alerts` - Get alerts
- `GET /api/v1/dashboard/sales-trend` - Get sales trend
- `GET /api/v1/dashboard/top-products` - Get top products
- `GET /api/v1/dashboard/dead-stock` - Get dead stock items
- `GET /api/v1/dashboard/hourly-pattern` - Get hourly sales pattern
- `GET /api/v1/dashboard/category-breakdown` - Get category breakdown

### Inventory
- `GET /api/v1/inventory` - Get inventory list
- `GET /api/v1/inventory/:id/detail` - Get item details
- `POST /api/v1/inventory/restock` - Restock item

### Chat (Phase 2)
- `POST /api/v1/chat/` - Send message to Baseer
- `POST /api/v1/chat/stream` - SSE streaming chat
- `GET /api/v1/chat/history` - Get chat history
- `DELETE /api/v1/chat/sessions/:id` - Clear session

### Upload (Phase 2)
- `POST /api/v1/upload/` - Upload CSV/Excel file
- `POST /api/v1/upload/:id/map` - Confirm column mapping
- `GET /api/v1/upload/:id/status` - Get ingestion status
- `GET /api/v1/upload/:id/result` - Get ingestion result

### Forecast (Phase 2)
- `POST /api/v1/forecast/` - Generate forecasts
- `POST /api/v1/forecast/product` - Forecast by product
- `GET /api/v1/forecast/summary` - Get forecast summary
- `GET /api/v1/forecast/cache` - Get cached forecasts

### Decisions (Phase 2)
- `POST /api/v1/decisions/` - Generate decisions
- `GET /api/v1/decisions/history` - Get decision history
- `PATCH /api/v1/decisions/:id` - Update decision status
- `GET /api/v1/decisions/stats` - Get decision statistics

### Health & Observability
- `GET /health` - Root health check
- `GET /api/v1/health` - Detailed health check with dependency probes
- `GET /ready` - Kubernetes readiness probe
- `GET /live` - Kubernetes liveness probe
- `GET /metrics` - Prometheus metrics (when `PROMETHEUS_ENABLED=true`)

All responses include `X-NazmOS-API-Version: 2.1.0-ksa`.

## Development

### Running Tests

```bash
# Backend
cd backend
pytest

# Frontend
cd frontend
npm run test
```

### Building for Production

```bash
# Frontend
cd frontend
npm run build
npm start
```

## License

MIT
