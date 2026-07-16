from app.routers.auth import router as auth_router
from app.routers.businesses import router as businesses_router
from app.routers.dashboard import router as dashboard_router
from app.routers.inventory import router as inventory_router
from app.routers.health import router as health_router
from app.routers.upload import router as upload_router
from app.routers.chat import router as chat_router
from app.routers.forecast import router as forecast_router
from app.routers.decisions import router as decisions_router
from app.routers.money_audit import router as money_audit_router
from app.routers.ops import router as ops_router
from app.routers.organizations import router as organizations_router
from app.routers.subscriptions import router as subscriptions_router
from app.routers.adapters import router as adapters_router
from app.routers.actions import router as actions_router

# Retail Recovery routers
from app.routers.pos_webhooks import router as pos_webhooks_router
from app.routers.orchestrator import router as orchestrator_router
try:
    from app.routers.recovery_match import router as recovery_match_router
except ImportError:
    recovery_match_router = None

# Agent router – may not exist in pure v2.1 KSA Lite
try:
    from app.routers.agent import router as agent_router
except ImportError:
    agent_router = None

# Supplier / Pharmacy routers – Agent OS v1.5
try:
    from app.routers.suppliers import router as suppliers_router
except ImportError:
    suppliers_router = None

try:
    from app.routers.pharmacy import router as pharmacy_router
except ImportError:
    pharmacy_router = None

# WhatsApp webhook
try:
    from app.routers.whatsapp import router as whatsapp_router
except ImportError:
    whatsapp_router = None

__all__ = [
    "auth_router",
    "businesses_router",
    "dashboard_router",
    "inventory_router",
    "health_router",
    "upload_router",
    "chat_router",
    "forecast_router",
    "decisions_router",
    "money_audit_router",
    "ops_router",
    "organizations_router",
    "subscriptions_router",
    "adapters_router",
    "actions_router",
    "agent_router",
    "suppliers_router",
    "pharmacy_router",
    "whatsapp_router",
    "pos_webhooks_router",
    "orchestrator_router",
    "recovery_match_router",
]
