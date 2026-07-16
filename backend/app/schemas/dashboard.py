from pydantic import BaseModel
from datetime import datetime, date
from uuid import UUID
from typing import Literal, List


class TodaySummary(BaseModel):
    sales: float
    transactions: int
    profit: float
    avg_basket_size: float


class MonthSummary(BaseModel):
    sales: float
    transactions: int
    profit: float


class ComparisonData(BaseModel):
    sales_change_percent: float
    profit_change_percent: float
    vs_last_month: bool


class DashboardSummaryResponse(BaseModel):
    today: TodaySummary
    this_month: MonthSummary
    comparison: ComparisonData
    health_score: int


class AlertResponse(BaseModel):
    id: UUID
    type: Literal["critical", "warning", "info", "success"]
    icon: str
    title: str
    message: str
    detail: str | None
    action_text: str | None
    action_type: str | None
    item_id: UUID | None
    priority: int
    created_at: datetime


class AlertsResponse(BaseModel):
    alerts: List[AlertResponse]


class SalesTrendItem(BaseModel):
    date: str
    sales: float
    profit: float
    transactions: int


class SalesTrendSummary(BaseModel):
    avg_daily_sales: float
    best_day: str
    worst_day: str
    trend_direction: Literal["up", "down", "stable"]


class SalesTrendResponse(BaseModel):
    data: List[SalesTrendItem]
    summary: SalesTrendSummary


class TopProductItem(BaseModel):
    item_id: UUID
    name: str
    category: str
    total_qty: float
    total_revenue: float
    total_profit: float
    avg_daily_qty: float
    trend: Literal["up", "down", "stable"]
    rank: int


class TopProductsResponse(BaseModel):
    products: List[TopProductItem]


class DeadStockItem(BaseModel):
    item_id: UUID
    name: str
    category: str
    current_stock: float
    stock_value: float
    last_sold_at: str | None
    days_since_last_sale: int | None
    recommendation: Literal["discount", "remove", "bundle"]


class DeadStockResponse(BaseModel):
    items: List[DeadStockItem]
    total_stuck_value: float


class HourlyPatternItem(BaseModel):
    hour: int
    avg_sales: float
    avg_transactions: float
    label: str


class HourlyPatternResponse(BaseModel):
    pattern: List[HourlyPatternItem]
    peak_hours: List[int]
    slow_hours: List[int]


class CategoryBreakdownItem(BaseModel):
    name: str
    total_sales: float
    percentage: float
    item_count: int
    top_item: str | None


class CategoryBreakdownResponse(BaseModel):
    categories: List[CategoryBreakdownItem]
