from app.utils.clock import utcnow
from datetime import datetime, timedelta, date
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import select, func, and_, or_, text, bindparam
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import Item, Inventory, Transaction, DailySummary, Category
from app.schemas.dashboard import (
    DashboardSummaryResponse, TodaySummary, MonthSummary, ComparisonData,
    SalesTrendResponse, SalesTrendItem, SalesTrendSummary,
    TopProductsResponse, TopProductItem,
    DeadStockResponse, DeadStockItem,
    HourlyPatternResponse, HourlyPatternItem,
    CategoryBreakdownResponse, CategoryBreakdownItem,
)
from app.schemas.inventory import InventoryItem, InventoryResponse, PaginationInfo, InventorySummary, ItemDetailResponse, SalesHistoryItem, ForecastItem, ReorderRecommendation
from app.schemas.dashboard import AlertsResponse, AlertResponse
from app.services.intelligence_api_client import IntelligenceAPIClient
from typing import List, Optional, Tuple


async def get_dashboard_summary(db: AsyncSession, business_id: UUID) -> DashboardSummaryResponse:
    from app.database.connection import enforce_tenant_filter
    enforce_tenant_filter(business_id)

    today = utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    
    month_start = today.replace(day=1)
    
    today_result = await db.execute(
        select(
            func.coalesce(func.sum(Transaction.total_amount), 0).label("sales"),
            func.coalesce(func.sum(Transaction.profit), 0).label("profit"),
            func.count(Transaction.id).label("transactions"),
        ).where(
            and_(
                Transaction.business_id == business_id,
                Transaction.transaction_at >= today_start,
                Transaction.transaction_at <= today_end,
            )
        )
    )
    today_data = today_result.one()
    
    yesterday = today - timedelta(days=1)
    yesterday_start = datetime.combine(yesterday, datetime.min.time())
    yesterday_end = datetime.combine(yesterday, datetime.max.time())
    
    yesterday_result = await db.execute(
        select(
            func.coalesce(func.sum(Transaction.total_amount), 0).label("sales"),
        ).where(
            and_(
                Transaction.business_id == business_id,
                Transaction.transaction_at >= yesterday_start,
                Transaction.transaction_at <= yesterday_end,
            )
        )
    )
    yesterday_data = yesterday_result.one()
    
    month_result = await db.execute(
        select(
            func.coalesce(func.sum(Transaction.total_amount), 0).label("sales"),
            func.coalesce(func.sum(Transaction.profit), 0).label("profit"),
            func.count(Transaction.id).label("transactions"),
        ).where(
            and_(
                Transaction.business_id == business_id,
                Transaction.transaction_at >= month_start,
            )
        )
    )
    month_data = month_result.one()
    
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    
    last_month_result = await db.execute(
        select(
            func.coalesce(func.sum(Transaction.total_amount), 0).label("sales"),
            func.coalesce(func.sum(Transaction.profit), 0).label("profit"),
        ).where(
            and_(
                Transaction.business_id == business_id,
                Transaction.transaction_at >= last_month_start,
                Transaction.transaction_at <= datetime.combine(last_month_end, datetime.max.time()),
            )
        )
    )
    last_month_data = last_month_result.one()
    
    today_sales = float(today_data.sales) if today_data.sales else 0
    yesterday_sales = float(yesterday_data.sales) if yesterday_data.sales else 0
    sales_change = ((today_sales - yesterday_sales) / yesterday_sales * 100) if yesterday_sales > 0 else 0
    
    month_sales = float(month_data.sales) if month_data.sales else 0
    last_month_sales = float(last_month_data.sales) if last_month_data.sales else 0
    month_change = ((month_sales - last_month_sales) / last_month_sales * 100) if last_month_sales > 0 else 0
    
    month_profit = float(month_data.profit) if month_data.profit else 0
    last_month_profit = float(last_month_data.profit) if last_month_data.profit else 0
    profit_change = ((month_profit - last_month_profit) / last_month_profit * 100) if last_month_profit > 0 else 0
    
    avg_basket = today_sales / today_data.transactions if today_data.transactions > 0 else 0
    
    health_score = await calculate_health_score(db, business_id)
    
    return DashboardSummaryResponse(
        today=TodaySummary(
            sales=round(today_sales, 2),
            transactions=today_data.transactions,
            profit=round(float(today_data.profit), 2) if today_data.profit else 0,
            avg_basket_size=round(avg_basket, 2),
        ),
        this_month=MonthSummary(
            sales=round(month_sales, 2),
            transactions=month_data.transactions,
            profit=round(month_profit, 2),
        ),
        comparison=ComparisonData(
            sales_change_percent=round(sales_change, 1),
            profit_change_percent=round(profit_change, 1),
            vs_last_month=month_sales >= last_month_sales,
        ),
        health_score=health_score,
    )


async def calculate_health_score(db: AsyncSession, business_id: UUID) -> int:
    inventory_result = await db.execute(
        select(Inventory).where(Inventory.business_id == business_id)
    )
    inventories = inventory_result.scalars().all()
    
    if not inventories:
        return 50
    
    item_ids = [inv.item_id for inv in inventories]
    items_result = await db.execute(
        select(Item).where(Item.id.in_(item_ids))
    )
    items = {item.id: item for item in items_result.scalars().all()}
    
    # Single grouped aggregation replaces one query per item (N+1 fix).
    qty_result = await db.execute(
        select(
            Transaction.item_id,
            func.coalesce(func.sum(Transaction.quantity), 0).label("total_qty"),
        )
        .where(
            and_(
                Transaction.business_id == business_id,
                Transaction.transaction_at >= utcnow() - timedelta(days=30),
            )
        )
        .group_by(Transaction.item_id)
    )
    qty_map = {row.item_id: float(row.total_qty) for row in qty_result}
    
    critical_count = 0
    low_count = 0
    total_count = len(inventories)
    
    for inv in inventories:
        item = items.get(inv.item_id)
        if not item:
            continue
        
        daily_avg = qty_map.get(inv.item_id, 0) / 30
        
        if daily_avg <= 0:
            status = "dead"
        elif float(inv.current_stock) / daily_avg < 2:
            status = "critical"
        elif float(inv.current_stock) / daily_avg < 5:
            status = "low"
        else:
            status = "healthy"
        
        if status == "critical":
            critical_count += 1
        elif status == "low":
            low_count += 1
    
    inventory_score = ((total_count - critical_count - low_count) / total_count) * 40
    
    dead_stock_value = await calculate_dead_stock_value(db, business_id)
    total_value_result = await db.execute(
        select(func.sum(Inventory.current_stock * Item.sell_price))
        .join(Item, Inventory.item_id == Item.id)
        .where(Inventory.business_id == business_id)
    )
    total_value = total_result = total_value_result.scalar() or Decimal("0")
    
    stock_health_score = 30 if dead_stock_value == 0 else max(0, 30 - (float(dead_stock_value) / float(total_value) * 30)) if total_value > 0 else 15
    
    trend_score = 20
    
    data_score = 10
    
    return min(100, int(inventory_score + stock_health_score + trend_score + data_score))


async def get_item_daily_avg(db: AsyncSession, business_id: UUID, item_id: UUID, days: int = 30) -> float:
    start_date = utcnow() - timedelta(days=days)
    
    result = await db.execute(
        select(func.coalesce(func.sum(Transaction.quantity), 0))
        .where(
            and_(
                Transaction.business_id == business_id,
                Transaction.item_id == item_id,
                Transaction.transaction_at >= start_date,
            )
        )
    )
    total_qty = result.scalar() or 0
    return float(total_qty) / days


async def calculate_dead_stock_value(db: AsyncSession, business_id: UUID) -> Decimal:
    """Total dead-stock SAR for the business (canonical scan, WS5).

    Canonical rule (shared with ``get_dead_stock_summary`` and the dashboard
    ``get_dead_stock``): an item is dead when it has fewer than one unit of
    sales in the last 30 days and still holds stock; stuck value is
    ``current_stock * cost_price``.  Items with NO sales at all count as dead
    (LEFT JOIN from inventory, not an inner sweep of transactions).
    """
    thirty_days_ago = utcnow() - timedelta(days=30)

    recent_sales = (
        select(
            Transaction.item_id.label("item_id"),
            func.sum(Transaction.quantity).label("qty_30d"),
        )
        .where(
            Transaction.business_id == business_id,
            Transaction.transaction_at >= thirty_days_ago,
        )
        .group_by(Transaction.item_id)
        .subquery()
    )

    result = await db.execute(
        select(func.sum(Inventory.current_stock * Item.cost_price))
        .join(Item, Item.id == Inventory.item_id)
        .outerjoin(recent_sales, recent_sales.c.item_id == Inventory.item_id)
        .where(
            and_(
                Inventory.business_id == business_id,
                Inventory.current_stock > 0,
                func.coalesce(recent_sales.c.qty_30d, 0) < 1,
            )
        )
    )

    return result.scalar() or Decimal("0")


async def get_sales_trend(db: AsyncSession, business_id: UUID, period: int = 30) -> SalesTrendResponse:
    from app.database.connection import enforce_tenant_filter
    enforce_tenant_filter(business_id)

    end_date = utcnow().date()
    start_date = end_date - timedelta(days=period)
    
    result = await db.execute(
        select(DailySummary)
        .where(
            and_(
                DailySummary.business_id == business_id,
                DailySummary.date >= datetime.combine(start_date, datetime.min.time()),
                DailySummary.date <= datetime.combine(end_date, datetime.max.time()),
            )
        )
        .order_by(DailySummary.date)
    )
    summaries = result.scalars().all()
    
    data = []
    for summary in summaries:
        data.append(SalesTrendItem(
            date=summary.date.strftime("%Y-%m-%d"),
            sales=float(summary.total_sales),
            profit=float(summary.total_profit),
            transactions=int(summary.total_transactions),
        ))
    
    if not data:
        return SalesTrendResponse(
            data=[],
            summary=SalesTrendSummary(
                avg_daily_sales=0,
                best_day="N/A",
                worst_day="N/A",
                trend_direction="stable",
            )
        )
    
    avg_daily = sum(d.sales for d in data) / len(data)
    best_day = max(data, key=lambda x: x.sales)
    worst_day = min(data, key=lambda x: x.sales)
    
    if len(data) >= 7:
        recent_avg = sum(d.sales for d in data[-7:]) / 7
        older_avg = sum(d.sales for d in data[-14:-7]) / 7 if len(data) >= 14 else recent_avg
        if recent_avg > older_avg * 1.05:
            trend = "up"
        elif recent_avg < older_avg * 0.95:
            trend = "down"
        else:
            trend = "stable"
    else:
        trend = "stable"
    
    return SalesTrendResponse(
        data=data,
        summary=SalesTrendSummary(
            avg_daily_sales=round(avg_daily, 2),
            best_day=best_day.date,
            worst_day=worst_day.date,
            trend_direction=trend,
        )
    )


async def get_top_products(db: AsyncSession, business_id: UUID, period: int = 7, limit: int = 10) -> TopProductsResponse:
    from app.database.connection import enforce_tenant_filter
    enforce_tenant_filter(business_id)

    end_date = utcnow()
    start_date = end_date - timedelta(days=period)
    
    result = await db.execute(
        select(
            Item.id,
            Item.name,
            func.coalesce(func.sum(Transaction.quantity), 0).label("total_qty"),
            func.coalesce(func.sum(Transaction.total_amount), 0).label("total_revenue"),
            func.coalesce(func.sum(Transaction.profit), 0).label("total_profit"),
        )
        .join(Transaction, Transaction.item_id == Item.id)
        .where(
            and_(
                Transaction.business_id == business_id,
                Transaction.transaction_at >= start_date,
            )
        )
        .group_by(Item.id, Item.name)
        .order_by(func.sum(Transaction.quantity).desc())
        .limit(limit)
    )
    
    rows = result.all()
    if not rows:
        return TopProductsResponse(products=[])

    item_ids = [row.id for row in rows]

    # Batch-load items + categories for all top products in one query.
    items_result = await db.execute(
        select(Item, Category)
        .outerjoin(Category, Category.id == Item.category_id)
        .where(Item.id.in_(item_ids))
    )
    item_map = {
        item.id: (item, cat.name if cat else "Uncategorized")
        for item, cat in items_result.all()
    }

    # Batch-load previous-period quantities for all top products in one query.
    prev_period_start = start_date - timedelta(days=period)
    prev_result = await db.execute(
        select(
            Transaction.item_id,
            func.coalesce(func.sum(Transaction.quantity), 0).label("prev_qty"),
        )
        .where(
            and_(
                Transaction.business_id == business_id,
                Transaction.item_id.in_(item_ids),
                Transaction.transaction_at >= prev_period_start,
                Transaction.transaction_at < start_date,
            )
        )
        .group_by(Transaction.item_id)
    )
    prev_qty_map = {row.item_id: float(row.prev_qty) for row in prev_result.all()}

    products = []
    for idx, row in enumerate(rows):
        _, category_name = item_map.get(row.id, (None, "Uncategorized"))

        daily_avg = float(row.total_qty) / period

        prev_qty = prev_qty_map.get(row.id, 0)

        if prev_qty > 0:
            change = (float(row.total_qty) - prev_qty) / prev_qty
            if change > 0.1:
                trend = "up"
            elif change < -0.1:
                trend = "down"
            else:
                trend = "stable"
        else:
            trend = "stable"

        products.append(TopProductItem(
            item_id=row.id,
            name=row.name,
            category=category_name,
            total_qty=float(row.total_qty),
            total_revenue=float(row.total_revenue),
            total_profit=float(row.total_profit),
            avg_daily_qty=round(daily_avg, 2),
            trend=trend,
            rank=idx + 1,
        ))

    return TopProductsResponse(products=products)


async def get_dead_stock(db: AsyncSession, business_id: UUID) -> DeadStockResponse:
    thirty_days_ago = utcnow() - timedelta(days=30)
    
    result = await db.execute(
        select(
            Item.id,
            Item.name,
            Inventory.current_stock.label("current_stock"),
            Item.cost_price.label("cost_price"),
            Category.name.label("category_name"),
            func.max(Transaction.transaction_at).label("last_sold"),
            func.coalesce(func.sum(Transaction.quantity), 0).label("total_qty"),
        )
        .join(Transaction, Transaction.item_id == Item.id, isouter=True)
        .join(Inventory, Inventory.item_id == Item.id)
        .outerjoin(Category, Category.id == Item.category_id)
        .where(
            and_(
                Item.business_id == business_id,
                Inventory.current_stock > 0,
            )
        )
        .group_by(
            Item.id,
            Item.name,
            Inventory.current_stock,
            Item.cost_price,
            Category.name,
        )
    )
    
    items = []
    total_stuck = Decimal("0")
    
    for row in result.all():
        total_qty = float(row.total_qty) if row.total_qty else 0
        
        if total_qty < 1:
            days_since = 30
            last_sold = thirty_days_ago - timedelta(days=30)
        else:
            days_since = 0
            last_sold = row.last_sold
        
        days_since_last_sale = (utcnow().date() - last_sold.date()).days if last_sold else days_since
        
        if days_since_last_sale >= 30:
            stock_value = row.current_stock * (row.cost_price or Decimal("0"))
            total_stuck += stock_value
            category_name = row.category_name if row.category_name else "Uncategorized"
            
            if days_since_last_sale > 60:
                recommendation = "remove"
            elif days_since_last_sale > 45:
                recommendation = "discount"
            else:
                recommendation = "bundle"
            
            items.append(DeadStockItem(
                item_id=row.id,
                name=row.name,
                category=category_name,
                current_stock=float(row.current_stock),
                stock_value=float(stock_value),
                last_sold_at=last_sold.strftime("%Y-%m-%d") if last_sold else None,
                days_since_last_sale=days_since_last_sale,
                recommendation=recommendation,
            ))
    
    return DeadStockResponse(
        items=items,
        total_stuck_value=float(total_stuck),
    )


async def get_hourly_pattern(db: AsyncSession, business_id: UUID, period: int = 30) -> HourlyPatternResponse:
    end_date = utcnow()
    start_date = end_date - timedelta(days=period)
    
    result = await db.execute(
        select(
            func.extract('hour', Transaction.transaction_at).label("hour"),
            func.coalesce(func.sum(Transaction.total_amount), 0).label("total_sales"),
            func.count(Transaction.id).label("total_transactions"),
        )
        .where(
            and_(
                Transaction.business_id == business_id,
                Transaction.transaction_at >= start_date,
            )
        )
        .group_by(func.extract('hour', Transaction.transaction_at))
        .order_by("hour")
    )
    
    hourly_data = {int(row.hour): {"sales": float(row.total_sales), "transactions": int(row.total_transactions)} for row in result.all()}
    
    pattern = []
    peak_hours = []
    slow_hours = []
    
    for hour in range(6, 24):
        hour_data = hourly_data.get(hour, {"sales": 0, "transactions": 0})
        avg_transactions = hour_data["transactions"] / period if period > 0 else 0
        
        # KSA retail routine & prayer time blackout recognition
        if hour in [8, 9, 10]:
            label = "Morning Business Rush (الفترة الصباحية)"
        elif hour == 12:
            label = "Dhuhr Prayer Break (صلاة الظهر)"
        elif hour in [13, 14]:
            label = "Siesta / Afternoon Lull (فترة القيلولة)"
        elif hour == 15:
            label = "Asr Prayer Break (صلاة العصر)"
        elif hour in [16, 17]:
            label = "Afternoon Re-opening (فترة العصر)"
        elif hour == 18:
            label = "Maghrib Prayer Transition (صلاة المغرب)"
        elif hour == 19:
            label = "Isha Prayer Transition (صلاة العشاء)"
        elif hour in [20, 21, 22, 23]:
            label = "Saudi Evening Peak Shopping (ذروة المساء)"
        else:
            label = f"{hour}:00 KSA"
        
        pattern.append(HourlyPatternItem(
            hour=hour,
            avg_sales=round(hour_data["sales"] / period if period > 0 else 0, 2),
            avg_transactions=round(avg_transactions, 1),
            label=label,
        ))
        
        if avg_transactions > 20:
            peak_hours.append(hour)
        elif avg_transactions < 5:
            slow_hours.append(hour)
    
    return HourlyPatternResponse(
        pattern=pattern,
        peak_hours=peak_hours,
        slow_hours=slow_hours,
    )


async def get_category_breakdown(db: AsyncSession, business_id: UUID, period: int = 30) -> CategoryBreakdownResponse:
    from app.database.connection import enforce_tenant_filter
    enforce_tenant_filter(business_id)

    end_date = utcnow()
    start_date = end_date - timedelta(days=period)
    
    result = await db.execute(
        select(
            Category.id,
            Category.name,
            func.coalesce(func.sum(Transaction.total_amount), 0).label("total_sales"),
            func.count(func.distinct(Item.id)).label("item_count"),
        )
        .join(Category, Category.id == Item.category_id)
        .join(Transaction, Transaction.item_id == Item.id)
        .where(
            and_(
                Item.business_id == business_id,
                Transaction.transaction_at >= start_date,
            )
        )
        .group_by(Category.id, Category.name)
        .order_by(func.sum(Transaction.total_amount).desc())
    )
    
    rows = result.all()
    total_sales = sum(float(row.total_sales) for row in rows)

    category_ids = [row.id for row in rows]
    best_per_category: dict = {}
    if category_ids:
        # Batch-load the top item per category in a single query (ordered by
        # quantity desc, so the first hit per category wins).
        top_items_result = await db.execute(
            select(
                Item.category_id,
                Item.name,
                func.coalesce(func.sum(Transaction.quantity), 0).label("qty"),
            )
            .join(Transaction, Transaction.item_id == Item.id)
            .where(
                and_(
                    Item.business_id == business_id,
                    Item.category_id.in_(category_ids),
                    Transaction.transaction_at >= start_date,
                )
            )
            .group_by(Item.category_id, Item.name)
            .order_by(func.sum(Transaction.quantity).desc())
        )
        for cat_id, item_name, _ in top_items_result.all():
            if cat_id not in best_per_category:
                best_per_category[cat_id] = item_name

    categories = []
    for row in rows:
        top_item = best_per_category.get(row.id)

        percentage = (float(row.total_sales) / total_sales * 100) if total_sales > 0 else 0

        categories.append(CategoryBreakdownItem(
            name=row.name,
            total_sales=float(row.total_sales),
            percentage=round(percentage, 1),
            item_count=int(row.item_count),
            top_item=top_item,
        ))

    return CategoryBreakdownResponse(categories=categories)


async def get_inventory_list(
    db: AsyncSession,
    business_id: UUID,
    status: str = "all",
    category: str = "all",
    search: str = "",
    sort: str = "days_left",
    order: str = "asc",
    page: int = 1,
    limit: int = 20,
) -> InventoryResponse:
    from app.database.connection import enforce_tenant_filter
    enforce_tenant_filter(business_id)

    query = (
        select(Item, Inventory, Category.name.label("category_name"))
        .join(Inventory, Inventory.item_id == Item.id)
        .outerjoin(Category, Category.id == Item.category_id)
        .where(Item.business_id == business_id, Item.is_active == True)
    )
    
    if status != "all":
        pass
    
    if category != "all":
        query = query.where(Category.name == category)
    
    if search:
        query = query.where(Item.name.ilike(f"%{search}%"))
    
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    if sort == "days_left":
        sort_col = Inventory.current_stock
    elif sort == "name":
        sort_col = Item.name
    elif sort == "stock":
        sort_col = Inventory.current_stock
    else:
        sort_col = Inventory.current_stock
    
    if order == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())
    
    query = query.offset((page - 1) * limit).limit(limit)
    
    result = await db.execute(query)
    rows = result.all()
    
    thirty_days_ago = utcnow() - timedelta(days=30)
    fourteen_days_ago = utcnow() - timedelta(days=14)
    seven_days_ago = utcnow() - timedelta(days=7)
    
    # Batch aggregate transactions for all page items to eliminate N+1 query hell
    item_ids = [row[0].id for row in rows]
    sales_map = {}
    if item_ids:
        batch_sales_query = text("""
            SELECT item_id,
                   COALESCE(SUM(CASE WHEN transaction_at >= :thirty_days THEN quantity ELSE 0 END), 0) as sales_30d,
                   COALESCE(SUM(CASE WHEN transaction_at >= :seven_days THEN quantity ELSE 0 END), 0) as sales_7d,
                   COALESCE(SUM(CASE WHEN transaction_at >= :fourteen_days AND transaction_at < :seven_days THEN quantity ELSE 0 END), 0) as sales_7d_prev
            FROM transactions
            WHERE business_id = :bid AND item_id IN :item_ids AND transaction_at >= :thirty_days
            GROUP BY item_id
        """).bindparams(bindparam("item_ids", expanding=True))
        batch_res = await db.execute(batch_sales_query, {
            "bid": str(business_id),
            "item_ids": item_ids,
            "thirty_days": thirty_days_ago,
            "fourteen_days": fourteen_days_ago,
            "seven_days": seven_days_ago
        })
        for r in batch_res.fetchall():
            sales_map[str(r.item_id)] = {
                "sales_30d": float(r.sales_30d or 0),
                "sales_7d": float(r.sales_7d or 0),
                "sales_7d_prev": float(r.sales_7d_prev or 0)
            }
    
    items = []
    summary = {
        "total_items": 0,
        "total_stock_value": Decimal("0"),
        "critical_count": 0,
        "low_count": 0,
        "healthy_count": 0,
        "overstock_count": 0,
        "dead_count": 0,
    }
    
    for row in rows:
        item, inventory, category_name = row
        item_sales = sales_map.get(str(item.id), {"sales_30d": 0.0, "sales_7d": 0.0, "sales_7d_prev": 0.0})
        sales_30d = item_sales["sales_30d"]
        daily_avg = sales_30d / 30.0
        sales_7d = item_sales["sales_7d"]
        sales_7d_prev = item_sales["sales_7d_prev"]
        
        if sales_7d_prev > 0:
            change = (sales_7d - sales_7d_prev) / sales_7d_prev
            if change > 0.1:
                trend = "up"
            elif change < -0.1:
                trend = "down"
            else:
                trend = "stable"
        else:
            trend = "stable"
        
        days_until_stockout = float(inventory.current_stock) / daily_avg if daily_avg > 0 else None
        
        if daily_avg < 0.1:
            computed_status = "dead"
        elif days_until_stockout is not None and days_until_stockout < 2:
            computed_status = "critical"
        elif days_until_stockout is not None and days_until_stockout < 5:
            computed_status = "low"
        elif days_until_stockout is not None and days_until_stockout > 20:
            computed_status = "overstock"
        else:
            computed_status = "healthy"

        if status != "all" and computed_status != status:
            continue
        
        stock_value = inventory.current_stock * item.sell_price
        
        summary["total_items"] += 1
        summary["total_stock_value"] += stock_value
        
        if computed_status == "critical":
            summary["critical_count"] += 1
        elif computed_status == "low":
            summary["low_count"] += 1
        elif computed_status == "healthy":
            summary["healthy_count"] += 1
        elif computed_status == "overstock":
            summary["overstock_count"] += 1
        elif computed_status == "dead":
            summary["dead_count"] += 1
        
        items.append(InventoryItem(
            item_id=item.id,
            name=item.name,
            sku=item.sku,
            category=category_name,
            current_stock=float(inventory.current_stock),
            unit=item.unit,
            daily_avg_sale=round(daily_avg, 2),
            days_until_stockout=round(days_until_stockout, 1) if days_until_stockout else None,
            cost_price=float(item.cost_price),
            sell_price=float(item.sell_price),
            stock_value=float(stock_value),
            status=computed_status,
            last_restocked=inventory.last_restocked,
            reorder_level=float(inventory.reorder_level),
            trend_7d=trend,
        ))
    
    response = InventoryResponse(
        items=items,
        pagination=PaginationInfo(
            page=page,
            limit=limit,
            total=total,
            total_pages=(total + limit - 1) // limit,
        ),
        summary=InventorySummary(
            total_items=summary["total_items"],
            total_stock_value=float(summary["total_stock_value"]),
            critical_count=summary["critical_count"],
            low_count=summary["low_count"],
            healthy_count=summary["healthy_count"],
            overstock_count=summary["overstock_count"],
            dead_count=summary["dead_count"],
        ),
    )

    # Phase 7: enrich inventory response with intelligence-driven recommendations.
    try:
        client = IntelligenceAPIClient(db, business_id)
        analysis = await client.analyze(query="Inventory optimization recommendations")
        decision = analysis.get("decision")
        recommendations: list[dict] = []
        if decision:
            ranked = decision.ranked_action
            if ranked:
                recommendations.append({
                    "action_type": ranked.get("action_type"),
                    "title": ranked.get("title"),
                    "description": ranked.get("description"),
                    "confidence": float(decision.confidence) if decision.confidence else None,
                    "expected_value_sar": ranked.get("expected_value_sar") or ranked.get("expected_roi"),
                    "expected_roi": ranked.get("expected_roi"),
                    "reasons": ranked.get("reasons", []),
                })
            for candidate in (decision.candidate_actions or [])[:2]:
                if candidate != ranked:
                    recommendations.append({
                        "action_type": candidate.get("action_type"),
                        "title": candidate.get("title"),
                        "description": candidate.get("description"),
                        "confidence": candidate.get("confidence"),
                        "expected_value_sar": candidate.get("expected_value_sar") or candidate.get("expected_roi"),
                        "expected_roi": candidate.get("expected_roi"),
                        "reasons": candidate.get("reasons", []),
                    })
        response.intelligence_recommendations = recommendations
    except Exception:
        # Intelligence enrichment is best-effort; never break inventory listing.
        response.intelligence_recommendations = None

    return response


async def get_item_detail(db: AsyncSession, business_id: UUID, item_id: UUID) -> ItemDetailResponse:
    result = await db.execute(
        select(Item, Inventory, Category.name.label("category_name"))
        .join(Inventory, Inventory.item_id == Item.id)
        .outerjoin(Category, Category.id == Item.category_id)
        .where(Item.business_id == business_id, Item.id == item_id)
    )
    row = result.first()
    
    if not row:
        return None
    
    item, inventory, category_name = row
    
    thirty_days_ago = utcnow() - timedelta(days=30)
    seven_days_ago = utcnow() - timedelta(days=7)
    fourteen_days_ago = utcnow() - timedelta(days=14)
    
    sales_30d_result = await db.execute(
        select(
            func.date(Transaction.transaction_at).label("date"),
            func.coalesce(func.sum(Transaction.quantity), 0).label("qty")
        )
        .where(
            and_(
                Transaction.business_id == business_id,
                Transaction.item_id == item.id,
                Transaction.transaction_at >= thirty_days_ago,
            )
        )
        .group_by(func.date(Transaction.transaction_at))
        .order_by(func.date(Transaction.transaction_at))
    )
    
    sales_history = [
        SalesHistoryItem(date=str(row.date), quantity=float(row.qty))
        for row in sales_30d_result.all()
    ]
    
    # Use live Prophet service with KSA Ramadan/Eid holiday calibration instead of static 0.95 multiplier
    from app.services.prophet_service import ProphetService
    prophet = ProphetService(db)
    try:
        live_forecast = await prophet.predict_item_demand(business_id, item_id, horizon_days=7)
        forecast_7d = [
            ForecastItem(date=f["date"], predicted_qty=round(float(f["predicted_qty"]), 2))
            for f in live_forecast.get("forecast", [])
        ]
    except Exception as e:
        # Fallback if historical data is under 14 days minimum threshold for Prophet
        forecast_7d = []
        avg_daily_sales = sum(h.quantity for h in sales_history) / max(1, len(sales_history))
        for i in range(1, 8):
            forecast_date = utcnow().date() + timedelta(days=i)
            # Apply Saudi Friday weekend uplift
            day_mult = 1.35 if forecast_date.weekday() in [3, 4] else 1.0
            forecast_7d.append(ForecastItem(
                date=forecast_date.strftime("%Y-%m-%d"),
                predicted_qty=round(avg_daily_sales * day_mult, 2)
            ))
    
    daily_avg_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.quantity), 0))
        .where(
            and_(
                Transaction.business_id == business_id,
                Transaction.item_id == item.id,
                Transaction.transaction_at >= thirty_days_ago,
            )
        )
    )
    sales_30d = float(daily_avg_result.scalar() or 0)
    daily_avg = sales_30d / 30
    
    days_until_stockout = float(inventory.current_stock) / daily_avg if daily_avg > 0 else None

    # Phase 1 (P0-A): PO-aware reorder decision. Only confirmed inbound that
    # arrives strictly BEFORE the projected stockout (%usable%) covers the gap;
    # a far-future / late PO must not suppress a needed reorder.
    from app.services.po_service import get_confirmed_inbound_map, usable_confirmed_inbound, projected_stockout_date
    from decimal import Decimal as _Dec
    inbound_map = await get_confirmed_inbound_map(db, business_id=business_id, as_of=utcnow().date())
    _so = projected_stockout_date(
        as_of=utcnow().date(),
        current_stock=_Dec(str(float(inventory.current_stock))),
        daily_demand=_Dec(str(daily_avg)) if daily_avg > 0 else _Dec("1"),
    )
    _timing = usable_confirmed_inbound(inbound_map.get(str(item.id)), stockout_date=_so)
    usable_inbound = float(_timing.usable_qty) if _timing else 0.0
    total_inbound = float(_timing.total_qty) if _timing else 0.0
    late_inbound = float(_timing.late_qty) if _timing else 0.0
    effective_days = (float(inventory.current_stock) + usable_inbound) / daily_avg if daily_avg > 0 else None

    if daily_avg < 0.1 or (effective_days and effective_days < 3):
        should_reorder = True
        recommended_qty = float(inventory.max_stock)
        reason = "Stock critically low or dead stock"
    elif effective_days and effective_days < 7:
        should_reorder = True
        recommended_qty = float(inventory.max_stock) - float(inventory.current_stock) - usable_inbound
        reason = f"Stock will run out in {round(effective_days, 1)} days"
    else:
        should_reorder = False
        recommended_qty = 0
        reason = None

    days_until_stockout_display = round(effective_days, 1) if effective_days else None
    reorder_evidence = {
        "confirmed_inbound_qty": total_inbound,
        "usable_inbound_qty": usable_inbound,
        "late_inbound_qty": late_inbound,
        "projected_stockout_date": _so.isoformat() if _so else None,
    }
    
    if daily_avg < 0.1:
        computed_status = "dead"
    elif days_until_stockout_display is not None and days_until_stockout_display < 2:
        computed_status = "critical"
    elif days_until_stockout_display is not None and days_until_stockout_display < 5:
        computed_status = "low"
    elif days_until_stockout_display is not None and days_until_stockout_display > 20:
        computed_status = "overstock"
    else:
        computed_status = "healthy"
    
    trend_7d_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.quantity), 0))
        .where(
            and_(
                Transaction.business_id == business_id,
                Transaction.item_id == item.id,
                Transaction.transaction_at >= seven_days_ago,
            )
        )
    )
    trend_7d_prev_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.quantity), 0))
        .where(
            and_(
                Transaction.business_id == business_id,
                Transaction.item_id == item.id,
                Transaction.transaction_at >= fourteen_days_ago,
                Transaction.transaction_at < seven_days_ago,
            )
        )
    )
    sales_7d = float(trend_7d_result.scalar() or 0)
    sales_7d_prev = float(trend_7d_prev_result.scalar() or 0)
    
    if sales_7d_prev > 0:
        change = (sales_7d - sales_7d_prev) / sales_7d_prev
        trend = "up" if change > 0.1 else "down" if change < -0.1 else "stable"
    else:
        trend = "stable"
    
    response = ItemDetailResponse(
        item=InventoryItem(
            item_id=item.id,
            name=item.name,
            sku=item.sku,
            category=category_name,
            current_stock=float(inventory.current_stock),
            unit=item.unit,
            daily_avg_sale=round(daily_avg, 2),
            days_until_stockout=days_until_stockout_display,
            cost_price=float(item.cost_price),
            sell_price=float(item.sell_price),
            stock_value=float(inventory.current_stock * item.sell_price),
            status=computed_status,
            last_restocked=inventory.last_restocked,
            reorder_level=float(inventory.reorder_level),
            trend_7d=trend,
        ),
        sales_history_30d=sales_history,
        forecast_7d=forecast_7d,
        reorder_recommendation=ReorderRecommendation(
            should_reorder=should_reorder,
            recommended_qty=round(recommended_qty, 2),
            recommended_by_date=(utcnow() + timedelta(days=3)).strftime("%Y-%m-%d") if should_reorder else None,
            reason=reason,
            reorder_evidence=reorder_evidence,
        ),
    )

    # Phase 7: enrich item detail with demand prediction and reasoning.
    try:
        client = IntelligenceAPIClient(db, business_id)
        prediction = await client.predict(target="demand", horizon_days=7, item_id=str(item_id))
        reasoning = await client.reason(question=f"What should I do about {item.name}?")
        recommendations: list[dict] = [
            {
                "type": "demand_forecast",
                "horizon_days": prediction.get("horizon_days"),
                "predicted_qty": prediction.get("predicted_value"),
                "confidence": prediction.get("confidence"),
            },
        ]
        if reasoning.get("decision"):
            ranked = reasoning["decision"].ranked_action
            if ranked:
                recommendations.append({
                    "type": "recommended_action",
                    "action_type": ranked.get("action_type"),
                    "title": ranked.get("title"),
                    "confidence": float(reasoning["decision"].confidence) if reasoning["decision"].confidence else None,
                    "reasons": ranked.get("reasons", []),
                })
        response.intelligence_recommendations = recommendations
    except Exception:
        response.intelligence_recommendations = None

    return response


async def get_dashboard_alerts(db: AsyncSession, business_id: UUID) -> AlertsResponse:
    from app.database.connection import enforce_tenant_filter
    enforce_tenant_filter(business_id)

    alerts = []
    
    inventory_result = await db.execute(
        select(Item, Inventory, Category.name.label("category_name"))
        .join(Inventory, Inventory.item_id == Item.id)
        .outerjoin(Category, Category.id == Item.category_id)
        .where(Item.business_id == business_id, Item.is_active == True)
    )
    inventory_rows = inventory_result.all()

    thirty_days_ago = utcnow() - timedelta(days=30)
    item_ids = [row[0].id for row in inventory_rows]
    sales_map = {}
    if item_ids:
        sales_query = text("""
            SELECT item_id, COALESCE(SUM(quantity), 0) AS sales_30d
            FROM transactions
            WHERE business_id = :business_id
              AND item_id IN :item_ids
              AND transaction_at >= :thirty_days_ago
            GROUP BY item_id
        """).bindparams(bindparam("item_ids", expanding=True))
        sales_res = await db.execute(sales_query, {
            "business_id": str(business_id),
            "item_ids": item_ids,
            "thirty_days_ago": thirty_days_ago,
        })
        sales_map = {str(r.item_id): float(r.sales_30d or 0) for r in sales_res.fetchall()}
    
    for row in inventory_rows:
        item, inventory, category_name = row
        sales_30d = sales_map.get(str(item.id), 0.0)
        daily_avg = sales_30d / 30
        
        days_until_stockout = float(inventory.current_stock) / daily_avg if daily_avg > 0 else float('inf')
        
        if days_until_stockout < 2 and daily_avg > 0:
            alerts.append(AlertResponse(
                id=item.id,
                type="critical",
                icon="alert-triangle",
                title=f"{item.name} - Critical Stock",
                message=f"Only {round(float(inventory.current_stock), 0)} {item.unit} left",
                detail=f"Avg daily sales: {round(daily_avg, 1)} {item.unit}/day",
                action_text=f"Reorder {max(50, int(daily_avg * 14))} units NOW",
                action_type="reorder",
                item_id=item.id,
                priority=1,
                created_at=utcnow(),
            ))
        elif days_until_stockout < 5 and daily_avg > 0:
            alerts.append(AlertResponse(
                id=item.id,
                type="warning",
                icon="alert-circle",
                title=f"{item.name} - Low Stock",
                message=f"{round(days_until_stockout, 1)} days until stockout",
                detail=f"Current: {round(float(inventory.current_stock), 0)} {item.unit} | Daily avg: {round(daily_avg, 1)}",
                action_text="Restock Soon",
                action_type="restock",
                item_id=item.id,
                priority=2,
                created_at=utcnow(),
            ))
        
        if daily_avg < 0.1 and float(inventory.current_stock) > 0:
            alerts.append(AlertResponse(
                id=item.id,
                type="warning",
                icon="package-x",
                title=f"{item.name} - Dead Stock",
                message="No sales in 30 days",
                detail=f"Capital stuck: ﷼ {round(float(inventory.current_stock) * float(item.cost_price), 2)}",
                action_text="Consider discount or removal",
                action_type="dead_stock",
                item_id=item.id,
                priority=3,
                created_at=utcnow(),
            ))
    
    today = utcnow().date()
    day_of_week = today.weekday()
    
    if day_of_week == 4:
        alerts.append(AlertResponse(
                id=uuid4(),
                type="info",
            icon="calendar",
            title="Friday stocking reminder",
            message="Prepare for weekend rush",
            detail="Saturday/Sunday sales typically 35-45% higher",
            action_text="Check inventory levels",
            action_type="stock_check",
            item_id=None,
            priority=5,
            created_at=utcnow(),
        ))
    elif day_of_week == 6:
        alerts.append(AlertResponse(
            id=uuid.uuid4(),
            type="success",
            icon="trending-up",
            title="Weekend boost detected",
            message="Sales trending above average",
            detail="Keep shelves stocked for the rush",
            action_text=None,
            action_type=None,
            item_id=None,
            priority=5,
            created_at=utcnow(),
        ))
    
    alerts.sort(key=lambda x: x.priority)
    
    return AlertsResponse(alerts=alerts[:10])
