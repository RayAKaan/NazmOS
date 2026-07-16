from sqlalchemy import select
from uuid import UUID
from datetime import datetime, timezone

from app.config import get_settings
from app.database.connection import get_sync_session
from app.database.models import POSConnection, POSSyncLog, Item, Inventory, Transaction
from app.services.credential_vault import POSCredentialManager
from app.adapters.registry import get_adapter

settings = get_settings()


def run_sync_pos_connection(connection_id: str):
    with get_sync_session() as db:
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

                for record in sales_data:
                    existing = db.execute(
                        select(Transaction).where(
                            Transaction.business_id == connection.business_id,
                            Transaction.transaction_at >= record.get("date", datetime.min)
                        )
                    )

                    if not existing.scalar_one_or_none():
                        transaction = Transaction(
                            business_id=connection.business_id,
                            item_id=record.get("item_id"),
                            quantity=record.get("quantity", 1),
                            unit_price=record.get("unit_price", 0),
                            cost_price=record.get("cost_price", 0),
                            total_amount=record.get("total", 0),
                            profit=record.get("profit", 0),
                            transaction_type="sale",
                            transaction_at=record.get("date", datetime.now(timezone.utc)),
                        )
                        db.add(transaction)

                sync_log.records_created += records_fetched

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
                        celery_app.send_task("pos_sync_tasks.sync_pos_connection", args=[str(conn.id)])
                    else:
                        run_sync_pos_connection(str(conn.id))


if settings.USE_CELERY:
    from celery import Task
    from app.celery_app import celery_app as celery

    @celery.task(bind=True, name="pos_sync_tasks.sync_pos_connection")
    def sync_pos_connection(self, connection_id: str):
        return run_sync_pos_connection(connection_id)

    @celery.task(name="pos_sync_tasks.schedule_syncs")
    def schedule_syncs():
        return run_schedule_syncs()
