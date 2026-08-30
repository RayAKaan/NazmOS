from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from typing import Literal, List, Optional


class InventoryItem(BaseModel):
    item_id: UUID
    name: str
    sku: str | None
    category: str | None
    current_stock: float
    unit: str
    daily_avg_sale: float
    days_until_stockout: float | None
    cost_price: float
    sell_price: float
    stock_value: float
    status: Literal["critical", "low", "healthy", "overstock", "dead"]
    last_restocked: datetime | None
    reorder_level: float
    trend_7d: Literal["up", "down", "stable"]


class PaginationInfo(BaseModel):
    page: int
    limit: int
    total: int
    total_pages: int


class InventorySummary(BaseModel):
    total_items: int
    total_stock_value: float
    critical_count: int
    low_count: int
    healthy_count: int
    overstock_count: int
    dead_count: int


class InventoryResponse(BaseModel):
    items: List[InventoryItem]
    pagination: PaginationInfo
    summary: InventorySummary
    intelligence_recommendations: List[dict] | None = None


class SalesHistoryItem(BaseModel):
    date: str
    quantity: float


class ForecastItem(BaseModel):
    date: str
    predicted_qty: float


class ReorderRecommendation(BaseModel):
    should_reorder: bool
    recommended_qty: float
    recommended_by_date: str | None
    reason: str | None
    reorder_evidence: dict | None = None


class ItemDetailResponse(BaseModel):
    item: InventoryItem
    sales_history_30d: List[SalesHistoryItem]
    forecast_7d: List[ForecastItem]
    reorder_recommendation: ReorderRecommendation
    intelligence_recommendations: List[dict] | None = None


class RestockRequest(BaseModel):
    item_id: UUID
    quantity: float
    business_id: UUID


class RestockResponse(BaseModel):
    success: bool
    updated_inventory: InventoryItem
    message: str
