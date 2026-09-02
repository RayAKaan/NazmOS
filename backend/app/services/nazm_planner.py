"""
Nazm – Planner Agent – KSA Retail OS
Universal – Pharmacy first, then Food, Auto Parts

No LLM. $0 cost. Pure SQL + Prophet + rules.

Runs every 15 min via cron / Celery beat (optional).
Generates agent_actions → attention feed.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import json

R_RIYADH = timezone(timedelta(hours=3))

class NazmPlanner:
    """The brain – decides what needs human attention"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def scan_business(self, business_id: UUID) -> int:
        """Run all agents for one business – returns actions_created count"""
        created = 0
        created += await self._agent_restock(business_id)
        created += await self._agent_pricing(business_id)
        created += await self._agent_cash(business_id)
        created += await self._agent_expiry(business_id)  # Pharmacy
        # staffing agent – stub
        return created
    
    async def _get_autonomy(self, business_id: UUID, action_type: str) -> int:
        """Get autonomy dial 0-100 – defaults if no policy row"""
        defaults = {
            "restock": 50,
            "pricing_increase": 20,
            "pricing_decrease": 30,
            "cash_alert": 0,
            "staff_schedule": 0,
            "expiry_alert": 50,
        }
        res = await self.db.execute(text(
            "SELECT dial FROM autonomy_policies WHERE business_id = :b AND action_type = :a AND is_active = true"
        ), {"b": str(business_id), "a": action_type})
        row = res.fetchone()
        return row[0] if row else defaults.get(action_type, 0)
    
    async def _create_action(
        self, business_id: UUID, action_type: str,
        title: str, summary: str, payload: dict,
        confidence: float, estimated_value_sar: float = None,
        title_ar: str = None, summary_ar: str = None,
    ) -> bool:
        """Create agent_action respecting autonomy dial"""
        # Dedupe – don't spam same action within 6h
        dup = await self.db.execute(text("""
            SELECT 1 FROM agent_actions 
            WHERE business_id = :b AND action_type = :a 
            AND created_at > NOW() - INTERVAL '6 hours'
            AND status IN ('pending_approval','info_only')
            AND payload->>'item_id' = :item_id
        """), {
            "b": str(business_id), "a": action_type,
            "item_id": str(payload.get("item_id", ""))
        })
        if dup.fetchone() and payload.get("item_id"):
            return False
        
        dial = await self._get_autonomy(business_id, action_type)
        
        # Confidence gate – low confidence never auto-executes
        if confidence < 0.75:
            dial = min(dial, 50)
        
        # Map dial → status
        if dial == 0:
            status = "info_only"
        elif dial >= 95 and confidence >= 0.9:
            status = "auto_executed"
        else:
            status = "pending_approval"
        
        # Calculate urgency score
        urgency = confidence * 100
        if estimated_value_sar:
            urgency += min(float(estimated_value_sar) / 100, 20)
        
        expires_at = datetime.now(R_RIYADH) + timedelta(hours=24)
        if action_type in ("cash_alert", "expiry_alert"):
            expires_at = datetime.now(R_RIYADH) + timedelta(hours=4)
        
        action_id = str(uuid4())
        await self.db.execute(text("""
            INSERT INTO agent_actions
            (id, business_id, action_type, status, confidence, priority,
             title, title_ar, summary, summary_ar, payload,
             estimated_value_sar, autonomy_dial_at_creation,
             was_auto_executed, expires_at, created_at)
            VALUES
            (:id, :b, :atype, :status, :conf, :prio,
             :title, :title_ar, :summary, :summary_ar, :payload::jsonb,
             :val, :dial, :autox, :exp, NOW())
        """), {
            "id": action_id,
            "b": str(business_id),
            "atype": action_type,
            "status": status,
            "conf": confidence,
            "prio": 1 if confidence > 0.9 else 2 if confidence > 0.75 else 3,
            "title": title,
            "title_ar": title_ar or title,
            "summary": summary,
            "summary_ar": summary_ar or summary,
            "payload": json.dumps(payload),
            "val": estimated_value_sar,
            "dial": dial,
            "autox": status == "auto_executed",
            "exp": expires_at,
        })
        if status == "pending_approval":
            try:
                owner_res = await self.db.execute(text("""
                    SELECT COALESCE(NULLIF(b.contact_phone, ''), NULLIF(u.phone, '')) AS phone
                    FROM businesses b
                    LEFT JOIN users u ON u.id = b.owner_id
                    WHERE b.id = :b
                """), {"b": str(business_id)})
                owner_row = owner_res.fetchone()
                to_phone = owner_row.phone if owner_row else None
                if to_phone:
                    from app.services.whatsapp_bridge import send_approval_request
                    from app.config import get_settings
                    from app.services.subscription_service import SubscriptionService
                    settings = get_settings()
                    if getattr(settings, "WHATSAPP_ENABLED", "mock").lower() == "live":
                        can_send_live = await SubscriptionService(self.db).check_feature_access(business_id, "live_whatsapp")
                        if not can_send_live:
                            await self.db.execute(text("""
                                UPDATE agent_actions
                                SET whatsapp_status = 'locked_free_tier'
                                WHERE id = :id
                            """), {"id": action_id})
                            raise PermissionError("live_whatsapp locked for current plan")
                    is_price_action = action_type in ("pricing_increase", "pricing_decrease")
                    resp = await send_approval_request(
                        to_number=to_phone,
                        action_id=action_id,
                        title=title,
                        summary=summary,
                        approve_url=f"/api/v1/agent/actions/{action_id}/approve",
                        reject_url=f"/api/v1/agent/actions/{action_id}/reject",
                        approve_title="✅ Approve Price Shield" if is_price_action else "✅ Approve",
                        reject_title="❌ Reject",
                        action_prefix="approve_price_shield" if is_price_action else "approve",
                    )
                    message_id = None
                    if isinstance(resp, dict):
                        message_id = resp.get("message_id")
                        messages = resp.get("messages") or []
                        if not message_id and messages:
                            message_id = messages[0].get("id")
                    await self.db.execute(text("""
                        UPDATE agent_actions
                        SET whatsapp_message_id = :mid,
                            whatsapp_status = :status
                        WHERE id = :id
                    """), {
                        "id": action_id,
                        "mid": message_id,
                        "status": resp.get("status", "sent") if isinstance(resp, dict) else "sent",
                    })
            except Exception:
                # WhatsApp delivery must never block agent action creation.
                pass

        await self.db.commit()
        return True

    # ── AGENT: RESTOCK ──────────────────────────────────────
    async def _agent_restock(self, business_id: UUID) -> int:
        """Restock agent – Prophet + inventory – $0 LLM

        Demand signal comes from the canonical forecast cache (same numbers the
        forecasting pipeline and agents read). Items without a usable forecast
        are skipped rather than guessed.
        """
        rows = await self.db.execute(text("""
            SELECT 
                i.id, i.name,
                inv.current_stock,
                inv.reorder_level,
                i.sell_price
            FROM items i
            JOIN inventory inv ON inv.item_id = i.id
            WHERE i.business_id = :b AND inv.current_stock >= 0
        """), {"b": str(business_id)})
        items = rows.fetchall()

        from app.services.forecasting.cache import read_forecasts_batch
        from app.services.forecasting.agent_helpers import days_of_supply, forecast_daily_demand
        cached = await read_forecasts_batch(self.db, business_id, [str(r.id) for r in items])

        # Phase 1 (P0-A): make the restock agent PO-aware. Only confirmed inbound
        # that arrives strictly BEFORE the projected stockout may count toward
        # coverage; a far-future / late PO must not suppress a needed reorder.
        from app.services.po_service import get_confirmed_inbound_map, usable_confirmed_inbound, projected_stockout_date
        from app.utils.clock import utcnow
        from decimal import Decimal as _Dec
        inbound_map = await get_confirmed_inbound_map(self.db, business_id=business_id, as_of=utcnow().date())

        created = 0
        for r in items:
            try:
                fc = cached.get(str(r.id))
                daily_demand = forecast_daily_demand(fc) if fc else 0.0
                if daily_demand <= 0:
                    # No usable forecasting signal – refuse to guess a restock.
                    continue
                stock_days = days_of_supply(float(r.current_stock), daily_demand)
                if stock_days == float("inf"):
                    continue

                # Time-aware confirmed inbound for this item (usable-before-stockout only).
                so = projected_stockout_date(
                    as_of=utcnow().date(),
                    current_stock=_Dec(str(float(r.current_stock))),
                    daily_demand=_Dec(str(daily_demand)),
                )
                timing = usable_confirmed_inbound(
                    inbound_map.get(str(r.id)),
                    stockout_date=so,
                )
                usable_inbound = float(timing.usable_qty) if timing else 0.0
                # Effective cover includes useful committed stock.
                effective_stock_days = (float(r.current_stock) + usable_inbound) / daily_demand if daily_demand > 0 else 999

                if effective_stock_days < 3.0 and float(r.current_stock) < float(r.reorder_level or 10) * 1.5:
                    # Calculate reorder qty – 14 days cover, minus useful inbound.
                    reorder_qty = max(int(daily_demand * 14 - usable_inbound), 20)
                    cost_sar = reorder_qty * float(r.sell_price or 0) * 0.7  # estimate cost = 70% of sell
                    
                    confidence = 0.92 if effective_stock_days < 1.5 else 0.85
                    
                    ok = await self._create_action(
                        business_id, "restock",
                        title=f"Restock {r.name}",
                        title_ar=f"إعادة طلب {r.name}",
                        summary=f"Stock runs out in {effective_stock_days:.1f} days (incl. {usable_inbound:.0f} usable confirmed inbound). Order {reorder_qty} units – ~{cost_sar:.0f} SAR. Supplier: TBD",
                        summary_ar=f"المخزون ينتهي خلال {effective_stock_days:.1f} يوم – اطلب {reorder_qty} – ~{cost_sar:.0f} ر.س",
                        payload={
                            "item_id": str(r.id),
                            "item_name": r.name,
                            "current_stock": float(r.current_stock),
                            "days_left": round(effective_stock_days, 1),
                            "recommended_qty": reorder_qty,
                            "estimated_cost_sar": round(cost_sar, 2),
                            "confirmed_inbound_qty": float(timing.total_qty) if timing else 0.0,
                            "usable_inbound_qty": usable_inbound,
                            "late_inbound_qty": float(timing.late_qty) if timing else 0.0,
                        },
                        confidence=confidence,
                        estimated_value_sar=cost_sar,
                    )
                    if ok:
                        created += 1
            except Exception:
                continue
        return created

    # ── AGENT: PRICING – BOM cost drift ────────────────────
    async def _agent_pricing(self, business_id: UUID) -> int:
        """Pricing agent – BOM / recipe cost drift → margin alert
        Pharmacy: drug acquisition cost ↑ → margin squeeze
        Cafe/Food: recipe ingredient cost drift → menu price recommendation
        $0 LLM – pure SQL + arithmetic
        """
        from app.config import get_settings
        settings = get_settings()
        if not getattr(settings, "AGENT_PRICING_ENABLED", False):
            return 0
        
        created = 0
        
        # 1. PHARMACY / RETAIL – simple cost_price vs sell_price margin check
        # Flag items where margin < 20% (pharmacy floor) or < 30% (retail/cafe)
        try:
            rows = await self.db.execute(text("""
                SELECT 
                    i.id, i.name,
                    i.cost_price, i.sell_price,
                    CASE WHEN i.sell_price > 0 
                        THEN ((i.sell_price - i.cost_price) / i.sell_price * 100)
                        ELSE 0 END as margin_pct,
                    COALESCE(SUM(t.quantity), 0) as units_sold_30d
                FROM items i
                LEFT JOIN transactions t ON t.item_id = i.id 
                    AND t.business_id = :b
                    AND t.transaction_at >= NOW() - INTERVAL '30 days'
                    AND t.transaction_type = 'sale'
                WHERE i.business_id = :b AND i.is_active = true
                GROUP BY i.id, i.name, i.cost_price, i.sell_price
                HAVING i.sell_price > 0
            """), {"b": str(business_id)})
            
            for r in rows.fetchall():
                try:
                    cost = float(r.cost_price or 0)
                    sell = float(r.sell_price or 0)
                    if sell <= 0 or cost <= 0:
                        continue
                    margin_pct = float(r.margin_pct or 0)
                    units_sold = float(r.units_sold_30d or 0)
                    
                    # Only flag items that actually sell – no point pricing dead stock
                    if units_sold < 2:
                        continue
                    
                    # Margin floors – pharmacy is tighter than cafe
                    # TODO: read business.type to adjust floor
                    margin_floor = 20.0  # pharmacy / retail default
                    target_margin = 35.0
                    
                    if margin_pct < margin_floor:
                        # Calculate suggested price to restore target margin
                        suggested_price = round(cost / (1 - target_margin/100), 2)
                        # Cap increase at 10% per cycle – trust guardrail
                        max_allowed = sell * 1.10
                        if suggested_price > max_allowed:
                            suggested_price = round(max_allowed, 2)
                        
                        increase_pct = ((suggested_price - sell) / sell * 100) if sell > 0 else 0
                        
                        # Confidence: higher if volume is high and margin breach is large
                        confidence = 0.65
                        if units_sold > 20:
                            confidence += 0.1
                        if margin_pct < margin_floor - 10:
                            confidence += 0.1
                        confidence = min(confidence, 0.88)
                        
                        ok = await self._create_action(
                            business_id, "pricing_increase",
                            title=f"Price increase – {r.name}",
                            title_ar=f"رفع السعر – {r.name}",
                            summary=f"Margin {margin_pct:.1f}% below floor {margin_floor}%. Cost SAR {cost:.2f}, current sell SAR {sell:.2f} → suggested SAR {suggested_price:.2f} (+{increase_pct:.1f}%). Sold {int(units_sold)} units last 30d.",
                            summary_ar=f"الهامش {margin_pct:.1f}% أقل من الحد {margin_floor}%. التكلفة {cost:.2f} ر.س، السعر الحالي {sell:.2f} ر.س → مقترح {suggested_price:.2f} ر.س (+{increase_pct:.1f}%).",
                            payload={
                                "item_id": str(r.id),
                                "item_name": r.name,
                                "current_cost": cost,
                                "current_price": sell,
                                "current_margin_pct": round(margin_pct, 1),
                                "suggested_price": suggested_price,
                                "increase_pct": round(increase_pct, 1),
                                "units_sold_30d": int(units_sold),
                                "reason": "cost_drift_margin_breach"
                            },
                            confidence=confidence,
                            estimated_value_sar=round((suggested_price - sell) * units_sold, 2),
                        )
                        if ok:
                            created += 1
                            if created >= 5:  # throttle – max 5 pricing alerts per scan
                                break
                except Exception:
                    continue
        except Exception:
            pass
        
        # 2. CAFE / FOOD – Recipe BOM costing
        # Check if recipes table has data for this business
        try:
            recipe_rows = await self.db.execute(text("""
                SELECT 
                    r.menu_item_id,
                    i.name as menu_item_name,
                    i.sell_price,
                    r.ingredients_json,
                    r.target_margin_pct
                FROM recipes r
                JOIN items i ON i.id = r.menu_item_id
                WHERE r.business_id = :b AND r.is_active = true
            """), {"b": str(business_id)})
            
            for rr in recipe_rows.fetchall():
                try:
                    import json as _json
                    ingredients = rr.ingredients_json
                    if isinstance(ingredients, str):
                        ingredients = _json.loads(ingredients)
                    
                    # Sum ingredient costs
                    total_cogs = 0.0
                    missing_costs = False
                    for ing in ingredients:
                        ing_item_id = ing.get("item_id")
                        qty = float(ing.get("qty", 0))
                        if not ing_item_id:
                            continue
                        cost_res = await self.db.execute(text(
                            "SELECT cost_price FROM items WHERE id = :id"
                        ), {"id": ing_item_id})
                        cost_row = cost_res.fetchone()
                        if cost_row and cost_row[0]:
                            total_cogs += float(cost_row[0]) * qty
                        else:
                            missing_costs = True
                    
                    if missing_costs or total_cogs <= 0:
                        continue
                    
                    sell_price = float(rr.sell_price or 0)
                    if sell_price <= 0:
                        continue
                    
                    current_margin = (sell_price - total_cogs) / sell_price * 100
                    target_margin = float(rr.target_margin_pct or 40)
                    
                    if current_margin < target_margin - 3:  # 3pt tolerance
                        suggested_price = round(total_cogs / (1 - target_margin/100), 2)
                        # Cap at 8% increase per cycle for menu items – customer sensitivity
                        max_allowed = sell_price * 1.08
                        if suggested_price > max_allowed:
                            suggested_price = round(max_allowed, 2)
                        
                        ok = await self._create_action(
                            business_id, "pricing_increase",
                            title=f"Menu price – {rr.menu_item_name}",
                            title_ar=f"سعر المنيو – {rr.menu_item_name}",
                            summary=f"Recipe COGS SAR {total_cogs:.2f}, sell SAR {sell_price:.2f} → margin {current_margin:.1f}% (target {target_margin}%). Suggested: SAR {suggested_price:.2f}",
                            summary_ar=f"تكلفة الوصفة {total_cogs:.2f} ر.س، البيع {sell_price:.2f} ر.س – الهامش {current_margin:.1f}%",
                            payload={
                                "item_id": str(rr.menu_item_id),
                                "item_name": rr.menu_item_name,
                                "current_cogs": round(total_cogs, 2),
                                "current_price": sell_price,
                                "current_margin_pct": round(current_margin, 1),
                                "suggested_price": suggested_price,
                                "target_margin_pct": target_margin,
                                "reason": "recipe_cost_drift"
                            },
                            confidence=0.78,
                            estimated_value_sar=0,
                        )
                        if ok:
                            created += 1
                except Exception:
                    continue
        except Exception:
            # recipes table may not exist in old DBs – silent
            pass
        
        return created

    # ── AGENT: CASH ───────────────────────────────────────
    async def _agent_cash(self, business_id: UUID) -> int:
        """Cash flow agent – 30-day cash ladder – inform only
        v1.5: simple burn-rate check
        v2.0: AP/AR integration and cash-cycle awareness
        """
        from app.config import get_settings
        settings = get_settings()
        if not getattr(settings, "AGENT_CASH_ENABLED", False):
            return 0
        
        try:
            # Simple cash health: avg daily profit last 30d vs inventory restock needs
            res = await self.db.execute(text("""
                SELECT 
                    COALESCE(SUM(total_amount),0) as revenue_30d,
                    COALESCE(SUM(total_profit),0) as profit_30d,
                    COUNT(*) as tx_count
                FROM daily_summaries
                WHERE business_id = :b
                  AND date >= NOW() - INTERVAL '30 days'
            """), {"b": str(business_id)})
            row = res.fetchone()
            if not row or not row.tx_count:
                return 0
            
            profit_30d = float(row.profit_30d or 0)
            daily_profit = profit_30d / 30 if profit_30d else 0
            
            # Estimate upcoming restock liability – sum of low-stock items at cost
            restock_res = await self.db.execute(text("""
                SELECT COALESCE(SUM((inv.reorder_level * 2 - inv.current_stock) * i.cost_price),0) as restock_liability
                FROM inventory inv
                JOIN items i ON i.id = inv.item_id
                WHERE inv.business_id = :b
                  AND inv.current_stock < inv.reorder_level
                  AND (inv.reorder_level * 2 - inv.current_stock) > 0
            """), {"b": str(business_id)})
            restock_row = restock_res.fetchone()
            restock_liability = float(restock_row[0] or 0) if restock_row else 0
            
            # If restock liability > 14 days of profit → cash alert
            profit_14d = daily_profit * 14
            if restock_liability > 0 and profit_14d > 0 and restock_liability > profit_14d * 1.5:
                await self._create_action(
                    business_id, "cash_alert",
                    title="Cash flow – restock funding gap",
                    title_ar="التدفق النقدي – فجوة تمويل المخزون",
                    summary=f"Upcoming restock needs SAR {restock_liability:.0f}, ~14-day profit is SAR {profit_14d:.0f}. Consider phased ordering or supplier credit terms.",
                    summary_ar=f"احتياج إعادة الطلب {restock_liability:.0f} ر.س، ربح 14 يوم ~{profit_14d:.0f} ر.س – اطلب على دفعات",
                    payload={
                        "restock_liability_sar": round(restock_liability, 2),
                        "profit_14d_sar": round(profit_14d, 2),
                        "gap_sar": round(restock_liability - profit_14d, 2),
                    },
                    confidence=0.82,
                    estimated_value_sar=restock_liability,
                )
                return 1
        except Exception:
            pass
        return 0

    # ── AGENT: EXPIRY – Pharmacy vertical ─────────────────
    async def _agent_expiry(self, business_id: UUID) -> int:
        """Pharmacy FEFO expiry alerts – KSA SFDA compliant"""
        # Check pharmacy_lots for items expiring < 90 days with stock > 0
        try:
            rows = await self.db.execute(text("""
                SELECT 
                    pl.item_id, i.name,
                    pl.expiry_date,
                    pl.quantity,
                    CURRENT_DATE + INTERVAL '90 days' as threshold
                FROM pharmacy_lots pl
                JOIN items i ON i.id = pl.item_id
                WHERE pl.business_id = :b
                  AND pl.quantity > 0
                  AND pl.expiry_date <= CURRENT_DATE + INTERVAL '90 days'
                  AND pl.expiry_date > CURRENT_DATE
                ORDER BY pl.expiry_date ASC
                LIMIT 10
            """), {"b": str(business_id)})
        except Exception:
            # Table may not exist yet in old DBs – silent fail
            return 0
        
        created = 0
        for r in rows.fetchall():
            days_left = (r.expiry_date - datetime.now().date()).days if hasattr(r.expiry_date, 'timetuple') else 60
            try:
                days_left = (r.expiry_date - datetime.now().date()).days
            except:
                days_left = 60
            
            if days_left < 90:
                ok = await self._create_action(
                    business_id, "expiry_alert",
                    title=f"Expiry Alert – {r.name}",
                    title_ar=f"تنبيه انتهاء صلاحية – {r.name}",
                    summary=f"Batch expires in {days_left} days – {float(r.quantity)} units in stock – Discount to clear?",
                    summary_ar=f"تنتهي الصلاحية خلال {days_left} يوم – الكمية {float(r.quantity)} – خصم للتصريف؟",
                    payload={
                        "item_id": str(r.item_id),
                        "item_name": r.name,
                        "expiry_date": str(r.expiry_date),
                        "days_left": days_left,
                        "quantity": float(r.quantity),
                    },
                    confidence=0.95,
                    estimated_value_sar=float(r.quantity) * 10,  # placeholder
                )
                if ok:
                    created += 1
        return created


# Convenience – run for all businesses
async def run_nazm_for_all(db: AsyncSession) -> dict:
    """Cron entrypoint – scans all active businesses"""
    res = await db.execute(text("SELECT id FROM businesses WHERE true LIMIT 100"))
    total_actions = 0
    businesses = 0
    for row in res.fetchall():
        planner = NazmPlanner(db)
        try:
            n = await planner.scan_business(row[0])
            total_actions += n
            businesses += 1
        except Exception:
            continue
    return {"businesses_scanned": businesses, "actions_created": total_actions}
