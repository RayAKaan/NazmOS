from sqlalchemy import select
from uuid import UUID
from datetime import datetime, time, timezone

from app.config import get_settings
from app.database.connection import get_sync_session
from app.database.models import POSConnection, POSSyncLog, Item, Inventory, Transaction
from app.services.credential_vault import POSCredentialManager
from app.adapters.registry import get_adapter

settings = get_settings()


def run_sync_pos_connection(connection_id: str, business_id: str | None = None):
    with get_sync_session(tenant_id=business_id) as db:
        connection = db.get(POSConnection, UUID(connection_id))

        if not connection:
            return {"error": "Connection not found"}

        sync_log = POSSyncLog(
            connection_id=connection.id,
            started_at=datetime.now(timezone.utc),
            status="running",
        )
        db.add(sync_log)

        connection.sync_status = "syncing"
        db.commit()

        try:
            vault = POSCredentialManager()
            credentials = vault.decrypt_credentials(connection.credentials_encrypted)

            adapter_class = get_adapter(connection.adapter_type)
            adapter = adapter_class(credentials)

            if connection.sync_sales:
                import asyncio
                sales_data = asyncio.run(adapter.fetch_sales())
                records_fetched = len(sales_data)
                imported = 0
                skipped = 0

                for record in sales_data:
                    transaction_at = record.get("date") or datetime.now(timezone.utc)
                    if isinstance(transaction_at, str):
                        try:
                            transaction_at = datetime.fromisoformat(transaction_at)
                        except ValueError:
                            transaction_at = datetime.now(timezone.utc)

                    quantity = float(record.get("quantity", 1))
                    total_amount = float(record.get("total", 0))

                    # Exact-fact dedup only. The old ``transaction_at >=`` cut-off
                    # silently dropped any backdated order and any new sale that
                    # landed before the earliest already-fetched transaction of
                    # the day. A re-sync of identical POS rows is suppressed by
                    # matching the same item/date/quantity/amount facts instead.
                    day_start = datetime.combine(transaction_at.date(), time.min)
                    day_end = datetime.combine(transaction_at.date(), time.max)
                    existing = db.execute(
                        select(Transaction.id).where(
                            Transaction.business_id == connection.business_id,
                            Transaction.item_id == record.get("item_id"),
                            Transaction.transaction_at >= day_start,
                            Transaction.transaction_at <= day_end,
                            Transaction.quantity == quantity,
                            Transaction.total_amount == total_amount,
                            Transaction.transaction_type == "sale",
                        ).limit(1)
                    )
                    if existing.scalar_one_or_none():
                        skipped += 1
                        continue

                    db.add(
                        Transaction(
                            business_id=connection.business_id,
                            item_id=record.get("item_id"),
                            quantity=quantity,
                            unit_price=float(record.get("unit_price", 0)),
                            cost_price=float(record.get("cost_price", 0)),
                            total_amount=total_amount,
                            profit=float(record.get("profit", 0)),
                            transaction_type="sale",
                            transaction_at=transaction_at,
                        )
                    )
                    imported += 1

                sync_log.records_created += imported

            if connection.sync_inventory:
                import asyncio
                inventory_data = asyncio.run(adapter.fetch_inventory())

                for record in inventory_data:
                    item = db.execute(
                        select(Item).where(
                            Item.business_id == connection.business_id,
                            Item.sku == record.get("sku")
                        )
                    )
                    item = item.scalar_one_or_none()

                    if item:
                        inv = db.execute(
                            select(Inventory).where(
                                Inventory.business_id == connection.business_id,
                                Inventory.item_id == item.id
                            )
                        )
                        inv = inv.scalar_one_or_none()

                        if inv:
                            inv.current_stock = record.get("quantity", inv.current_stock)
                            inv.updated_at = datetime.now(timezone.utc)

            sync_log.completed_at = datetime.now(timezone.utc)
            sync_log.status = "success"
            sync_log.records_fetched = sync_log.records_created + sync_log.records_updated

            connection.sync_status = "synced"
            connection.last_sync_at = datetime.now(timezone.utc)
            connection.last_sync_records_processed = sync_log.records_fetched
            connection.consecutive_failures = 0

            db.commit()

            return {
                "success": True,
                "records_processed": sync_log.records_fetched,
            }

        except Exception as e:
            sync_log.completed_at = datetime.now(timezone.utc)
            sync_log.status = "failed"
            sync_log.errors = [{"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}]

            connection.sync_status = "error"
            connection.last_sync_error = str(e)
            connection.consecutive_failures += 1

            db.commit()

            return {
                "success": False,
                "error": str(e),
            }


def run_schedule_syncs():
    # Supervisor scope: enumerating every active POS connection is cross-tenant
    # scheduler work.  Each sync is then dispatched with an explicit
    # business_id so ``run_sync_pos_connection`` runs RLS-scoped.
    with get_sync_session() as db:
        result = db.execute(
            select(POSConnection).where(
                POSConnection.is_active == True,
                POSConnection.sync_status == "synced",
            )
        )
        connections = result.scalars().all()

        for conn in connections:
            if conn.last_sync_at:
                elapsed = (datetime.now(timezone.utc) - conn.last_sync_at).total_seconds() / 60
                if elapsed >= conn.sync_interval_minutes:
                    if settings.USE_CELERY:
                        from app.celery_app import celery_app
                        celery_app.send_task(
                            "pos_sync_tasks.sync_pos_connection",
                            args=[str(conn.id), str(conn.business_id)],
                        )
                    else:
                        run_sync_pos_connection(str(conn.id), str(conn.business_id))


if settings.USE_CELERY:
    from celery import Task
    from app.celery_app import celery_app as celery

    @celery.task(bind=True, name="pos_sync_tasks.sync_pos_connection")
    def sync_pos_connection(self, connection_id: str, business_id: str | None = None):
        return run_sync_pos_connection(connection_id, business_id)

    @celery.task(name="pos_sync_tasks.schedule_syncs")
    def schedule_syncs():
        return run_schedule_syncs()
