"""Pydantic schemas for the Universal Event Engine (Phase 0).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class EventPayload(BaseModel):
    """Generic payload container; event-type-specific models inherit from this."""
    model_config = ConfigDict(extra="allow")


class SaleCompletedPayload(EventPayload):
    order_id: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    total_amount: float = 0.0
    payment_method: str = "cash"
    branch_id: str | None = None
    customer_id: str | None = None


class InventoryChangedPayload(EventPayload):
    item_id: str | None = None
    sku: str | None = None
    quantity_delta: float = 0.0
    new_quantity: float | None = None
    location: str | None = None
    reason: str | None = None


class PaymentFailedPayload(EventPayload):
    amount: float = 0.0
    payment_method: str | None = None
    reason: str | None = None
    order_id: str | None = None


class SupplierDeliveredPayload(EventPayload):
    supplier_id: str | None = None
    purchase_order_id: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    delivered_at: datetime | None = None


class PriceUpdatedPayload(EventPayload):
    item_id: str | None = None
    sku: str | None = None
    old_price: float | None = None
    new_price: float | None = None


class EmployeeClockInPayload(EventPayload):
    employee_id: str | None = None
    branch_id: str | None = None
    shift_start: datetime | None = None


class CustomerComplaintPayload(EventPayload):
    channel: str | None = None
    text: str | None = None
    customer_id: str | None = None
    order_id: str | None = None


class TemperatureAlertPayload(EventPayload):
    sensor_id: str | None = None
    value: float | None = None
    threshold: float | None = None
    location: str | None = None


class CameraDetectedQueuePayload(EventPayload):
    location: str | None = None
    count: int | None = None
    timestamp: datetime | None = None


class OutcomeFeedbackPayload(EventPayload):
    decision_id: str | None = None
    execution_job_id: str | None = None
    decision_type: str | None = None
    predicted_roi: float | None = None
    actual_roi: float | None = None
    success: bool | None = None


class LearningRefreshedPayload(EventPayload):
    window_days: int = 30
    performance_records: int = 0


# Map of built-in event type names to their Pydantic validation models.
BUILTIN_EVENT_SCHEMAS: dict[str, type[BaseModel]] = {
    "sale.completed": SaleCompletedPayload,
    "inventory.changed": InventoryChangedPayload,
    "payment.failed": PaymentFailedPayload,
    "supplier.delivered": SupplierDeliveredPayload,
    "price.updated": PriceUpdatedPayload,
    "employee.clock_in": EmployeeClockInPayload,
    "customer.complaint": CustomerComplaintPayload,
    "temperature.alert": TemperatureAlertPayload,
    "camera.detected_queue": CameraDetectedQueuePayload,
    "outcome.feedback.recorded": OutcomeFeedbackPayload,
    "learning.refreshed": LearningRefreshedPayload,
}


class EventIngest(BaseModel):
    """Request schema for ingesting a single event."""
    event_type: str = Field(..., min_length=1, max_length=100)
    source: str = Field(..., min_length=1, max_length=50)
    source_id: str | None = Field(default=None, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)
    context_snapshot: dict[str, Any] | None = None
    actor_type: str | None = Field(default=None, max_length=50)
    actor_id: UUID | None = None
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    occurred_at: datetime | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.occurred_at is None:
            self.occurred_at = datetime.now(timezone.utc)


class EventBatchIngest(BaseModel):
    """Request schema for ingesting a batch of events."""
    events: list[EventIngest] = Field(..., min_length=1, max_length=1000)


class EventOut(BaseModel):
    """Response schema for an event record."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    event_type: str
    version: int
    source: str
    source_id: str | None
    payload: dict[str, Any]
    context_snapshot: dict[str, Any] | None
    actor_type: str | None
    actor_id: UUID | None
    correlation_id: UUID | None
    causation_id: UUID | None
    checksum: str
    occurred_at: datetime
    received_at: datetime
    processed: bool
    processed_at: datetime | None
    error: str | None


class EventTypeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    version: int = Field(default=1, ge=1)
    description: str | None = None
    json_schema: dict[str, Any] = Field(
        default_factory=dict,
        alias="schema",
        validation_alias="schema",
        serialization_alias="schema",
    )
    example: dict[str, Any] | None = None


class EventTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    name: str
    version: int
    description: str | None
    json_schema: dict[str, Any] = Field(
        alias="schema",
        validation_alias="schema",
        serialization_alias="schema",
    )
    example: dict[str, Any] | None
    is_system: bool
    created_at: datetime
    updated_at: datetime


class EventSubscriptionCreate(BaseModel):
    consumer_name: str = Field(..., min_length=1, max_length=100)
    event_pattern: str = Field(..., min_length=1, max_length=255)
    queue_or_channel: str = Field(..., min_length=1, max_length=255)
    is_active: bool = True


class EventSubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID | None
    consumer_name: str
    event_pattern: str
    queue_or_channel: str
    is_active: bool
    created_at: datetime
