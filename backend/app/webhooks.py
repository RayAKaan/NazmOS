from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)

app = FastAPI(title="NazmOS Webhooks", version="1.0.0")


class WebhookPayload(BaseModel):
    adapter_type: str
    business_id: str
    payload: dict
    signature: Optional[str] = None


@app.post("/pos/tally")
async def tally_webhook(request: Request):
    body = await request.json()
    logger.info("tally_webhook_received", payload=body)
    return {"status": "received"}


@app.post("/pos/shopify")
async def shopify_webhook(request: Request):
    body = await request.json()
    logger.info("shopify_webhook_received", payload=body)
    return {"status": "received"}


@app.post("/pos/woocommerce")
async def woocommerce_webhook(request: Request):
    body = await request.json()
    logger.info("woocommerce_webhook_received", payload=body)
    return {"status": "received"}


@app.post("/pos/zoho")
async def zoho_webhook(request: Request):
    body = await request.json()
    logger.info("zoho_webhook_received", payload=body)
    return {"status": "received"}


@app.post("/pos/csv")
async def csv_webhook(request: Request):
    body = await request.json()
    logger.info("csv_webhook_received", payload=body)
    return {"status": "received"}


@app.post("/pos/custom")
async def custom_webhook(request: Request):
    body = await request.json()
    logger.info("custom_webhook_received", payload=body)
    return {"status": "received"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
