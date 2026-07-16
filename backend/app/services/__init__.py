from app.services.auth_service import (
    register_user,
    login_user,
    refresh_access_token,
    get_user_by_id,
    get_demo_business,
)
from app.services.analytics_service import (
    get_dashboard_summary,
    get_sales_trend,
    get_top_products,
    get_dead_stock,
    get_hourly_pattern,
    get_category_breakdown,
    get_inventory_list,
    get_item_detail,
    calculate_health_score,
)
from app.services.inventory_service import restock_item
# Forecast – use ProphetService directly
# from app.services.prophet_service import ProphetService

__all__ = [
    "register_user",
    "login_user",
    "refresh_access_token",
    "get_user_by_id",
    "get_demo_business",
    "get_dashboard_summary",
    "get_sales_trend",
    "get_top_products",
    "get_dead_stock",
    "get_hourly_pattern",
    "get_category_breakdown",
    "get_inventory_list",
    "get_item_detail",
    "calculate_health_score",
    "restock_item",
]
