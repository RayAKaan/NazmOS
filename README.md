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
- Python 3.11+
- FastAPI
- SQLAlchemy 2.0 (async)
- PostgreSQL 15+
- Alembic (migrations)
- Pydantic v2
- Redis + Celery (background tasks)
- OpenAI GPT-4 (LLM)
- Prophet (forecasting)

### Frontend
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- Recharts
- Zustand
- React Hook Form + Zod
- Framer Motion (animations)
- React Dropzone (file upload)

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Node.js 20+ (for local development)
- Python 3.11+ (for local development)

### Using Docker (Recommended)

```bash
cd NazmOS
docker-compose up
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
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env and add your OpenAI API key and Redis URL

# Run Redis (required for Phase 2)
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

## Demo Account

- Email: demo@nazmos.ai
- Password: demo123456

Or click "Try Demo Without Login" on the login page.

## Phase 2 Setup

### Environment Variables

Add these to your backend `.env` file:

```env
# Redis
REDIS_URL=redis://localhost:6379/0

# OpenAI (optional - mock LLM used if not set)
OPENAI_API_KEY=sk-your-api-key
OPENAI_MODEL=gpt-4
USE_MOCK_LLM=false

# Uploads
UPLOAD_DIR=./uploads
MAX_FILE_SIZE_MB=15

# Forecasting
FORECAST_DAYS_DEFAULT=30
FORECAST_DAYS_MAX=365
```

### Feature Flags

- `USE_MOCK_LLM=true` - Use mock LLM responses for offline demo
- Set `OPENAI_API_KEY` for real AI responses

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

### Health
- `GET /api/v1/health` - Health check

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
