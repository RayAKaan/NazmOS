from abc import ABC, abstractmethod
from typing import Optional, Any
import httpx
import structlog

logger = structlog.get_logger(__name__)


class BasePOSAdapter(ABC):
    def __init__(self, credentials: dict):
        self.credentials = credentials.get("credentials", {})
        self.adapter_type = credentials.get("adapter_type", "unknown")
    
    @abstractmethod
    async def fetch_sales(self, date_from=None, date_to=None) -> list[dict]:
        pass
    
    @abstractmethod
    async def fetch_inventory(self) -> list[dict]:
        pass
    
    async def push_order(self, order_data: dict) -> dict:
        raise NotImplementedError("Push orders not supported by this adapter")
    
    async def test_connection(self) -> bool:
        raise NotImplementedError("Connection test not implemented")
    
    def _normalize_sales_record(self, record: dict) -> dict:
        return {
            "date": record.get("date"),
            "item_id": record.get("item_id"),
            "item_name": record.get("item_name"),
            "sku": record.get("sku"),
            "quantity": float(record.get("quantity", 1)),
            "unit_price": float(record.get("unit_price", 0)),
            "cost_price": float(record.get("cost_price", 0)),
            "total": float(record.get("total", 0)),
            "profit": float(record.get("profit", 0)),
        }
    
    def _normalize_inventory_record(self, record: dict) -> dict:
        return {
            "sku": record.get("sku") or record.get("item_code"),
            "item_name": record.get("item_name") or record.get("name"),
            "quantity": float(record.get("quantity", 0)),
            "cost_price": float(record.get("cost_price", 0)),
            "sell_price": float(record.get("sell_price", 0)),
        }


class TallyAdapter(BasePOSAdapter):
    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self.tally_url = self.credentials.get("tally_url", "http://localhost:9000")
        self.company_name = self.credentials.get("company_name")
        self.port = self.credentials.get("port", 9000)
    
    async def fetch_sales(self, date_from=None, date_to=None) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.tally_url}:{self.port}",
                    json={
                        "type": "sales_report",
                        "company": self.company_name,
                        "from_date": str(date_from) if date_from else None,
                        "to_date": str(date_to) if date_to else None,
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return [self._normalize_sales_record(r) for r in data.get("sales", [])]
                else:
                    logger.warning("tally_fetch_failed", status=response.status_code)
                    return []
                    
        except Exception as e:
            logger.error("tally_connection_error", error=str(e))
            return []
    
    async def fetch_inventory(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.tally_url}:{self.port}",
                    json={
                        "type": "stock_summary",
                        "company": self.company_name,
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return [self._normalize_inventory_record(r) for r in data.get("inventory", [])]
                else:
                    return []
                    
        except Exception as e:
            logger.error("tally_inventory_error", error=str(e))
            return []


class ShopifyAdapter(BasePOSAdapter):
    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self.shop_name = self.credentials.get("shop_name")
        self.access_token = self.credentials.get("access_token")
        self.api_version = self.credentials.get("api_version", "2024-01")
        self.base_url = f"https://{self.shop_name}.myshopify.com/admin/api/{self.api_version}"
    
    def _get_headers(self) -> dict:
        return {
            "X-Shopify-Access-Token": self.access_token,
            "Content-Type": "application/json",
        }
    
    async def fetch_sales(self, date_from=None, date_to=None) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                params = {"status": "any"}
                if date_from:
                    params["created_at_min"] = date_from.isoformat()
                if date_to:
                    params["created_at_max"] = date_to.isoformat()
                
                response = await client.get(
                    f"{self.base_url}/orders.json",
                    headers=self._get_headers(),
                    params=params,
                )
                
                if response.status_code == 200:
                    orders = response.json().get("orders", [])
                    records = []
                    for order in orders:
                        for item in order.get("line_items", []):
                            records.append({
                                "date": order.get("created_at"),
                                "item_id": str(item.get("product_id")),
                                "item_name": item.get("title"),
                                "sku": item.get("sku"),
                                "quantity": float(item.get("quantity", 1)),
                                "unit_price": float(item.get("price", 0)),
                                "cost_price": 0,
                                "total": float(order.get("total_price", 0)),
                                "profit": 0,
                            })
                    return records
                return []
        except Exception as e:
            logger.error("shopify_sales_error", error=str(e))
            return []
    
    async def fetch_inventory(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/products.json",
                    headers=self._get_headers(),
                )
                
                if response.status_code == 200:
                    products = response.json().get("products", [])
                    records = []
                    for product in products:
                        for variant in product.get("variants", []):
                            records.append({
                                "sku": variant.get("sku"),
                                "item_name": f"{product.get('title')} - {variant.get('title')}",
                                "quantity": float(variant.get("inventory_quantity", 0)),
                                "cost_price": float(variant.get("cost_per_item", 0)),
                                "sell_price": float(variant.get("price", 0)),
                            })
                    return records
                return []
        except Exception as e:
            logger.error("shopify_inventory_error", error=str(e))
            return []


class WooCommerceAdapter(BasePOSAdapter):
    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self.site_url = self.credentials.get("site_url")
        self.consumer_key = self.credentials.get("consumer_key")
        self.consumer_secret = self.credentials.get("consumer_secret")
    
    async def fetch_sales(self, date_from=None, date_to=None) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                params = {"per_page": 100}
                if date_from:
                    params["after"] = date_from.isoformat()
                
                response = await client.get(
                    f"{self.site_url}/wp-json/wc/v3/orders",
                    auth=(self.consumer_key, self.consumer_secret),
                    params=params,
                )
                
                if response.status_code == 200:
                    orders = response.json()
                    records = []
                    for order in orders:
                        for item in order.get("line_items", []):
                            records.append({
                                "date": order.get("date_created"),
                                "item_id": str(item.get("product_id")),
                                "item_name": item.get("name"),
                                "quantity": float(item.get("quantity", 1)),
                                "unit_price": float(item.get("price", 0)),
                                "cost_price": 0,
                                "total": float(item.get("total", 0)),
                                "profit": 0,
                            })
                    return records
                return []
        except Exception as e:
            logger.error("woocommerce_error", error=str(e))
            return []
    
    async def fetch_inventory(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.site_url}/wp-json/wc/v3/products",
                    auth=(self.consumer_key, self.consumer_secret),
                    params={"per_page": 100},
                )
                
                if response.status_code == 200:
                    products = response.json()
                    return [{
                        "sku": p.get("sku"),
                        "item_name": p.get("name"),
                        "quantity": float(p.get("stock_quantity", 0)),
                        "cost_price": 0,
                        "sell_price": float(p.get("price", 0)),
                    } for p in products]
                return []
        except Exception as e:
            logger.error("woocommerce_inventory_error", error=str(e))
            return []


class ZohoAdapter(BasePOSAdapter):
    async def fetch_sales(self, date_from=None, date_to=None) -> list[dict]:
        return []
    
    async def fetch_inventory(self) -> list[dict]:
        return []


class CSVWebhookAdapter(BasePOSAdapter):
    async def fetch_sales(self, date_from=None, date_to=None) -> list[dict]:
        return []
    
    async def fetch_inventory(self) -> list[dict]:
        return []


class CustomAPIAdapter(BasePOSAdapter):
    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self.base_url = self.credentials.get("base_url")
        self.api_key = self.credentials.get("api_key")
        self.headers = self.credentials.get("headers", {})
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"
    
    async def fetch_sales(self, date_from=None, date_to=None) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/sales",
                    headers=self.headers,
                    params={"from": date_from, "to": date_to},
                )
                
                if response.status_code == 200:
                    return response.json()
                return []
        except Exception as e:
            logger.error("custom_api_error", error=str(e))
            return []
    
    async def fetch_inventory(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/inventory",
                    headers=self.headers,
                )
                
                if response.status_code == 200:
                    return response.json()
                return []
        except Exception as e:
            logger.error("custom_api_inventory_error", error=str(e))
            return []


ADAPTER_REGISTRY = {
    "tally": TallyAdapter,
    "shopify": ShopifyAdapter,
    "woocommerce": WooCommerceAdapter,
    "zoho": ZohoAdapter,
    "csv_webhook": CSVWebhookAdapter,
    "custom_api": CustomAPIAdapter,
}


def get_adapter(adapter_type: str):
    adapter_class = ADAPTER_REGISTRY.get(adapter_type)
    if not adapter_class:
        raise ValueError(f"Unknown adapter type: {adapter_type}")
    return adapter_class
