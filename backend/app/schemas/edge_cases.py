from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime, date
from uuid import UUID, uuid4
from typing import List, Optional, Any
from decimal import Decimal
import re


class EdgeCaseBase(BaseModel):
    """Base class for edge case validation."""
    
    @field_validator('*', mode='before')
    @classmethod
    def strip_whitespace(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


class InventoryEdgeCases(EdgeCaseBase):
    """Edge cases for inventory operations."""

    item_id: Optional[UUID] = None
    sku: Optional[str] = None
    name: Optional[str] = None
    current_stock: float = 0
    reorder_level: float = 0
    cost_price: float = 0
    sell_price: float = 0
    
    @model_validator(mode='after')
    def validate_stock_levels(self) -> 'InventoryEdgeCases':
        if self.current_stock < 0:
            raise ValueError('Stock cannot be negative')
        if self.reorder_level < 0:
            raise ValueError('Reorder level cannot be negative')
        if self.cost_price < 0:
            raise ValueError('Cost price cannot be negative')
        if self.sell_price < 0:
            raise ValueError('Sell price cannot be negative')
        if self.cost_price > self.sell_price:
            raise ValueError('Cost price cannot exceed sell price')
        return self
    
    @field_validator('sku')
    @classmethod
    def validate_sku_format(cls, v):
        if v is None:
            return v
        if not re.match(r'^[A-Z0-9\-_]{3,20}$', v.upper()):
            raise ValueError('SKU must be 3-20 alphanumeric characters, hyphens, or underscores')
        return v.upper()
    
    @field_validator('current_stock', 'cost_price', 'sell_price', 'reorder_level')
    @classmethod
    def validate_decimal_precision(cls, v):
        if isinstance(v, (int, float)):
            if v > 999999999:
                raise ValueError('Value exceeds maximum allowed')
            decimal_str = str(v)
            if '.' in decimal_str:
                decimals = len(decimal_str.split('.')[1])
                if decimals > 4:
                    raise ValueError('Maximum 4 decimal places allowed')
        return v


class QuantityUpdate(EdgeCaseBase):
    """Edge cases for quantity updates."""
    
    item_id: UUID
    quantity_change: float
    reason: Optional[str] = None
    reference_id: Optional[str] = None
    
    @field_validator('quantity_change')
    @classmethod
    def validate_quantity_change(cls, v):
        if v == 0:
            raise ValueError('Quantity change cannot be zero')
        if abs(v) > 1000000:
            raise ValueError('Quantity change exceeds maximum allowed')
        return v
    
    @field_validator('reference_id')
    @classmethod
    def validate_reference_id(cls, v):
        if v is not None and len(v) > 100:
            raise ValueError('Reference ID too long (max 100 chars)')
        return v


class DateRangeEdgeCases(BaseModel):
    """Edge cases for date range queries."""
    
    start_date: date
    end_date: date
    
    @model_validator(mode='after')
    def validate_date_range(self) -> 'DateRangeEdgeCases':
        if self.start_date > self.end_date:
            raise ValueError('Start date must be before or equal to end date')
        
        delta = self.end_date - self.start_date
        if delta.days > 730:
            raise ValueError('Date range cannot exceed 2 years')
        
        if self.start_date > date.today():
            raise ValueError('Start date cannot be in the future')
        
        return self


class PaginationEdgeCases(BaseModel):
    """Edge cases for pagination."""
    
    page: int = Field(ge=1, le=10000, default=1)
    limit: int = Field(ge=1, le=1000, default=50)
    
    @model_validator(mode='after')
    def validate_offset_limits(self) -> 'PaginationEdgeCases':
        max_offset = (self.page - 1) * self.limit
        if max_offset > 1000000:
            raise ValueError('Requested offset too large')
        return self


class BulkOperationEdgeCases(BaseModel):
    """Edge cases for bulk operations."""
    
    item_ids: List[UUID] = Field(min_length=1, max_length=1000)
    operation: str
    parameters: Optional[dict] = None
    
    @field_validator('operation')
    @classmethod
    def validate_operation(cls, v):
        allowed_operations = {'restock', 'adjust', 'delete', 'update_category', 'update_prices'}
        if v not in allowed_operations:
            raise ValueError(f'Operation must be one of: {", ".join(allowed_operations)}')
        return v
    
    @model_validator(mode='after')
    def validate_unique_ids(self) -> 'BulkOperationEdgeCases':
        if len(self.item_ids) != len(set(self.item_ids)):
            raise ValueError('Duplicate item IDs in bulk operation')
        return self
    
    @model_validator(mode='after')
    def validate_parameters(self) -> 'BulkOperationEdgeCases':
        if self.operation == 'delete' and self.parameters:
            raise ValueError('Delete operation cannot have parameters')
        return self


class CurrencyEdgeCases(BaseModel):
    """Edge cases for currency/monetary values."""
    
    amount: Decimal = Field(ge=0, le=999999999999)
    currency: str = Field(default='SAR', pattern=r'^[A-Z]{3}$')
    
    @field_validator('currency')
    @classmethod
    def validate_currency(cls, v):
        allowed = {'SAR', 'USD', 'EUR', 'GBP'}
        if v not in allowed:
            raise ValueError(f'Currency must be one of: {", ".join(allowed)}')
        return v


class SearchQueryEdgeCases(BaseModel):
    """Edge cases for search queries."""
    
    query: str = Field(min_length=1, max_length=200)
    filters: Optional[dict] = None
    sort_by: Optional[str] = None
    sort_order: str = Field(default='asc', pattern=r'^(asc|desc)$')
    
    @field_validator('query')
    @classmethod
    def validate_search_query(cls, v):
        v = v.strip()
        if len(v) < 2 and v != '*':
            raise ValueError('Search query must be at least 2 characters')
        if v.count('*') > 3:
            raise ValueError('Too many wildcard characters')
        return v
    
    @field_validator('sort_by')
    @classmethod
    def validate_sort_field(cls, v):
        allowed = {'name', 'sku', 'stock', 'value', 'date', 'price', 'category'}
        if v is not None and v not in allowed:
            raise ValueError(f'Sort field must be one of: {", ".join(allowed)}')
        return v


class FileUploadEdgeCases(BaseModel):
    """Edge cases for file uploads."""
    
    filename: str
    file_size: int = Field(ge=1, le=50_000_000)
    content_type: str
    checksum: Optional[str] = None
    
    @field_validator('filename')
    @classmethod
    def validate_filename(cls, v):
        if not v or len(v) > 255:
            raise ValueError('Filename must be 1-255 characters')
        
        dangerous_chars = ['..', '/', '\\', '\x00', '<', '>', ':', '"', '|', '?', '*']
        for char in dangerous_chars:
            if char in v:
                raise ValueError(f'Filename contains invalid character: {char}')
        
        allowed_extensions = {'.csv', '.xlsx', '.xls', '.json', '.txt'}
        ext = '.' + v.rsplit('.', 1)[-1].lower() if '.' in v else ''
        if ext not in allowed_extensions:
            raise ValueError(f'File extension must be one of: {", ".join(allowed_extensions)}')
        
        return v
    
    @field_validator('content_type')
    @classmethod
    def validate_content_type(cls, v):
        allowed = {
            'text/csv',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/json',
            'text/plain',
        }
        if v not in allowed:
            raise ValueError(f'Content type not allowed: {v}')
        return v
    
    @field_validator('checksum')
    @classmethod
    def validate_checksum(cls, v):
        if v is not None:
            if not re.match(r'^[a-fA-F0-9]{32,128}$', v):
                raise ValueError('Invalid checksum format (expected MD5, SHA256, or SHA512)')
        return v


class WebhookPayloadEdgeCases(BaseModel):
    """Edge cases for webhook payloads."""
    
    event_type: str
    payload: dict
    timestamp: datetime
    retry_count: int = Field(default=0, ge=0, le=10)
    signature: Optional[str] = None
    
    @field_validator('event_type')
    @classmethod
    def validate_event_type(cls, v):
        allowed = {
            'inventory.updated', 'inventory.created', 'inventory.deleted',
            'order.placed', 'order.cancelled', 'order.completed',
            'stock.alerts', 'forecast.updated', 'decision.executed',
        }
        if v not in allowed:
            raise ValueError(f'Invalid event type: {v}')
        return v
    
    @model_validator(mode='after')
    def validate_payload_size(self) -> 'WebhookPayloadEdgeCases':
        import json
        payload_size = len(json.dumps(self.payload))
        if payload_size > 1_000_000:
            raise ValueError('Payload too large (max 1MB)')
        return self
    
    @model_validator(mode='after')
    def validate_retry_policy(self) -> 'WebhookPayloadEdgeCases':
        if self.retry_count > 0 and self.signature is None:
            raise ValueError('Retried webhooks must have a signature')
        return self


class RateLimitEdgeCases(BaseModel):
    """Edge cases for rate limiting."""
    
    user_id: UUID
    endpoint: str
    request_count: int = Field(ge=1)
    window_seconds: int = Field(ge=1, le=86400)
    
    @model_validator(mode='after')
    def validate_rate_limit_values(self) -> 'RateLimitEdgeCases':
        if self.request_count > 10000:
            raise ValueError('Request count exceeds limit')
        return self


class APIKeyEdgeCases(BaseModel):
    """Edge cases for API key validation."""
    
    api_key: str
    organization_id: UUID
    permissions: List[str]
    expires_at: Optional[datetime] = None
    
    @field_validator('api_key')
    @classmethod
    def validate_api_key_format(cls, v):
        if not re.match(r'^sg_live_[a-zA-Z0-9]{32,}$', v):
            if not re.match(r'^sg_test_[a-zA-Z0-9]{32,}$', v):
                raise ValueError('Invalid API key format')
        return v
    
    @model_validator(mode='after')
    def validate_expiry(self) -> 'APIKeyEdgeCases':
        if self.expires_at and self.expires_at < datetime.utcnow():
            raise ValueError('API key has expired')
        return self


class NotificationEdgeCases(BaseModel):
    """Edge cases for notification systems."""
    
    recipient_id: UUID
    channel: str
    content: str
    priority: str = Field(default='normal', pattern=r'^(low|normal|high|urgent)$')
    scheduled_at: Optional[datetime] = None
    
    @field_validator('channel')
    @classmethod
    def validate_channel(cls, v):
        allowed = {'email', 'sms', 'push', 'whatsapp', 'webhook'}
        if v not in allowed:
            raise ValueError(f'Channel must be one of: {", ".join(allowed)}')
        return v
    
    @field_validator('content')
    @classmethod
    def validate_content_length(cls, v):
        if len(v) > 5000:
            raise ValueError('Notification content too long (max 5000 chars)')
        return v
    
    @model_validator(mode='after')
    def validate_scheduling(self) -> 'NotificationEdgeCases':
        if self.scheduled_at:
            if self.scheduled_at < datetime.utcnow():
                raise ValueError('Scheduled time cannot be in the past')
            if self.scheduled_at > datetime.utcnow().replace(year=datetime.utcnow().year + 1):
                raise ValueError('Cannot schedule more than 1 year ahead')
        return self
