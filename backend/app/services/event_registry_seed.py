"""Seed the built-in event type registry on startup."""
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import EventType
from app.schemas.events import BUILTIN_EVENT_SCHEMAS


BUILTIN_EVENT_TYPES = [
    ("sale.completed", "Sale Completed", "A sale or order was completed."),
    ("inventory.changed", "Inventory Changed", "Stock level changed through sale, delivery, adjustment, or waste."),
    ("payment.failed", "Payment Failed", "A payment attempt failed."),
    ("supplier.delivered", "Supplier Delivered", "A supplier delivery was recorded."),
    ("price.updated", "Price Updated", "An item price was updated."),
    ("employee.clock_in", "Employee Clock In", "An employee started a shift."),
    ("customer.complaint", "Customer Complaint", "A customer complaint was received."),
    ("temperature.alert", "Temperature Alert", "A temperature threshold was breached."),
    ("camera.detected_queue", "Camera Detected Queue", "A camera detected a queue."),
    ("pos.order.received", "POS Order Received", "A raw order was received from a POS webhook."),
    ("agent.proposal", "Agent Proposal", "A specialized agent proposed an action."),
    ("execution.completed", "Execution Completed", "An approved action was executed successfully."),
    ("execution.failed", "Execution Failed", "An approved action failed during execution."),
    ("outcome.feedback.recorded", "Outcome Feedback Recorded", "A predicted-vs-actual outcome feedback record was stored."),
    ("learning.refreshed", "Learning Refreshed", "Model performance aggregates were refreshed by the Learning Engine."),
]


async def seed_builtin_event_types(session: AsyncSession) -> None:
    """Insert built-in event types if the registry is empty."""
    result = await session.execute(select(EventType).limit(1))
    if result.scalar_one_or_none() is not None:
        return

    for name, title, description in BUILTIN_EVENT_TYPES:
        schema_model = BUILTIN_EVENT_SCHEMAS.get(name)
        schema = schema_model.model_json_schema() if schema_model else {}
        session.add(
            EventType(
                id=uuid4(),
                name=name,
                version=1,
                description=description,
                schema=schema,
                is_system=True,
            )
        )
    await session.commit()
