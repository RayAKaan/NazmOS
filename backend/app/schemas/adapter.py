from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional


class POSConnectionCreate(BaseModel):
    adapter_type: str = Field(..., pattern=r'^(tally|shopify|woocommerce|zoho|csv_webhook|custom_api)$')
    connection_name: str = Field(..., min_length=1, max_length=100)
    endpoint_url: Optional[str] = None
    sync_interval_minutes: int = Field(default=15, ge=5, le=1440)
    sync_sales: bool = True
    sync_inventory: bool = True
    push_orders: bool = False


class POSCredentialsTally(BaseModel):
    company_name: str
    tally_url: str = Field(..., description="Tally server URL (e.g., http://localhost:9000)")
    port: int = Field(default=9000, ge=1, le=65535)


class POSCredentialsShopify(BaseModel):
    shop_name: str
    access_token: str
    api_version: str = Field(default="2024-01")


class POSCredentialsWooCommerce(BaseModel):
    site_url: str
    consumer_key: str
    consumer_secret: str


class POSCredentialsZoho(BaseModel):
    organization_id: str
    client_id: str
    client_secret: str
    refresh_token: str


class POSCredentialsGeneric(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    headers: Optional[dict] = None


class POSConnectionCredentials(BaseModel):
    tally: Optional[POSCredentialsTally] = None
    shopify: Optional[POSCredentialsShopify] = None
    woocommerce: Optional[POSCredentialsWooCommerce] = None
    zoho: Optional[POSCredentialsZoho] = None
    custom_api: Optional[POSCredentialsGeneric] = None


class POSConnectionResponse(BaseModel):
    id: UUID
    business_id: UUID
    adapter_type: str
    connection_name: str
    endpoint_url: Optional[str]
    sync_status: str
    sync_interval_minutes: int
    sync_sales: bool
    sync_inventory: bool
    push_orders: bool
    last_sync_at: Optional[datetime]
    last_sync_duration_seconds: Optional[int]
    last_sync_records_processed: Optional[int]
    last_sync_error: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class POSConnectionUpdate(BaseModel):
    connection_name: Optional[str] = Field(None, min_length=1, max_length=100)
    sync_interval_minutes: Optional[int] = Field(None, ge=5, le=1440)
    sync_sales: Optional[bool] = None
    sync_inventory: Optional[bool] = None
    push_orders: Optional[bool] = None


class POSSyncStatusResponse(BaseModel):
    connection_id: UUID
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    records_fetched: int
    records_created: int
    records_updated: int
    records_skipped: int
    records_failed: int
    errors: list[dict]


class POSSyncTriggerResponse(BaseModel):
    task_id: str
    status: str
    message: str


class POSFieldMapping(BaseModel):
    source_field: str
    target_field: str


class POSFieldMappingConfig(BaseModel):
    sales: Optional[list[POSFieldMapping]] = None
    inventory: Optional[list[POSFieldMapping]] = None


class POSFieldMappingUpdate(BaseModel):
    mapping: POSFieldMappingConfig
