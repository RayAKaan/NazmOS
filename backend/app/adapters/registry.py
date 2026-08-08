from abc import ABC, abstractmethod
from typing import Optional, Any
import hashlib
import hmac
import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


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

    async def test_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.tally_url}:{self.port}",
                    timeout=5,
                )
                return response.status_code < 500
        except Exception as e:
            logger.error("tally_test_connection_error", error=str(e))
            return False


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

    async def test_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.base_url}/shop.json",
                    headers=self._get_headers(),
                )
                return response.status_code == 200
        except Exception as e:
            logger.error("shopify_test_connection_error", error=str(e))
            return False


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

    async def test_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.site_url}/wp-json/wc/v3/products",
                    auth=(self.consumer_key, self.consumer_secret),
                    params={"per_page": 1},
                )
                return response.status_code == 200
        except Exception as e:
            logger.error("woocommerce_test_connection_error", error=str(e))
            return False


class ZohoAdapter(BasePOSAdapter):
    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self.organization_id = self.credentials.get("organization_id")
        self.client_id = self.credentials.get("client_id")
        self.client_secret = self.credentials.get("client_secret")
        self.refresh_token = self.credentials.get("refresh_token")
        self.accounts_base = self.credentials.get("accounts_base", "https://accounts.zoho.com")
        self.api_base = self.credentials.get("api_base", "https://inventory.zoho.com")

    async def _get_access_token(self) -> Optional[str]:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.accounts_base}/oauth/v2/token",
                params={
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                },
            )
            if response.status_code == 200:
                return response.json().get("access_token")
            logger.warning("zoho_token_refresh_failed", status=response.status_code)
            return None

    async def fetch_sales(self, date_from=None, date_to=None) -> list[dict]:
        return []

    async def fetch_inventory(self) -> list[dict]:
        return []

    async def test_connection(self) -> bool:
        try:
            access_token = await self._get_access_token()
            if not access_token:
                return False
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.api_base}/api/v1/organizations",
                    headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
                )
                return response.status_code == 200
        except Exception as e:
            logger.error("zoho_test_connection_error", error=str(e))
            return False


class CSVWebhookAdapter(BasePOSAdapter):
    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self.endpoint_url = self.credentials.get("endpoint_url") or self.credentials.get("base_url")

    async def fetch_sales(self, date_from=None, date_to=None) -> list[dict]:
        return []

    async def fetch_inventory(self) -> list[dict]:
        return []

    async def test_connection(self) -> bool:
        if not self.endpoint_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(self.endpoint_url, timeout=5)
                return response.status_code < 500
        except Exception as e:
            logger.error("csv_webhook_test_connection_error", error=str(e))
            return False


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

    async def test_connection(self) -> bool:
        if not self.base_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    self.base_url,
                    headers=self.headers,
                    timeout=5,
                )
                return 200 <= response.status_code < 400
        except Exception as e:
            logger.error("custom_api_test_connection_error", error=str(e))
            return False


class FoodicsWebhookAdapter(BasePOSAdapter):
    """Webhook-only adapter for Foodics POS.

    Real-time orders are pushed by Foodics to /api/v1/pos/foodics/webhook.
    This adapter only provides a connection test that validates the configured
    webhook secret can be used for HMAC signature verification.
    """

    async def fetch_sales(self, date_from=None, date_to=None) -> list[dict]:
        return []

    async def fetch_inventory(self) -> list[dict]:
        return []

    async def test_connection(self) -> bool:
        secret = self.credentials.get("webhook_secret") or getattr(settings, "FOODICS_WEBHOOK_SECRET", "")
        if not secret:
            return False
        try:
            expected = hmac.new(secret.encode(), b"nazmos-test", hashlib.sha256).hexdigest()
            return len(expected) == 64
        except Exception as e:
            logger.error("foodics_test_connection_error", error=str(e))
            return False


class SallaAdapter(BasePOSAdapter):
    """Salla E-Commerce adapter.

    Supports both webhook ingestion (order.created) and on-demand API fetch for
    orders and products. Configure either a webhook_secret for real-time push or
    an access_token for API polling.
    """

    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self.access_token = self.credentials.get("access_token")
        self.webhook_secret = self.credentials.get("webhook_secret")
        self.base_url = self.credentials.get("base_url", "https://api.salla.dev/admin/v2")

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    async def fetch_sales(self, date_from=None, date_to=None) -> list[dict]:
        if not self.access_token:
            return []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                params = {"per_page": 100}
                if date_from:
                    params["from"] = str(date_from)
                if date_to:
                    params["to"] = str(date_to)
                response = await client.get(
                    f"{self.base_url}/orders",
                    headers=self._headers(),
                    params=params,
                )
                if response.status_code != 200:
                    logger.warning("salla_fetch_sales_failed", status=response.status_code)
                    return []
                orders = response.json().get("data", [])
                records = []
                for order in orders:
                    for item in order.get("items", []):
                        records.append({
                            "date": order.get("date", {}).get("date") or order.get("created_at"),
                            "item_id": str(item.get("id")),
                            "item_name": item.get("name"),
                            "sku": item.get("sku"),
                            "quantity": float(item.get("quantity", 1)),
                            "unit_price": float(item.get("amount", 0)) / max(1, float(item.get("quantity", 1))),
                            "cost_price": 0,
                            "total": float(item.get("amount", 0)),
                            "profit": 0,
                        })
                return records
        except Exception as e:
            logger.error("salla_fetch_sales_error", error=str(e))
            return []

    async def fetch_inventory(self) -> list[dict]:
        if not self.access_token:
            return []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/products",
                    headers=self._headers(),
                    params={"per_page": 100},
                )
                if response.status_code != 200:
                    logger.warning("salla_fetch_inventory_failed", status=response.status_code)
                    return []
                products = response.json().get("data", [])
                records = []
                for product in products:
                    records.append({
                        "sku": product.get("sku"),
                        "item_name": product.get("name"),
                        "quantity": float(product.get("quantity", 0)),
                        "cost_price": float(product.get("cost_price", 0) or 0),
                        "sell_price": float(product.get("price", 0) or 0),
                    })
                return records
        except Exception as e:
            logger.error("salla_fetch_inventory_error", error=str(e))
            return []

    async def test_connection(self) -> bool:
        if self.access_token:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.get(
                        f"{self.base_url}/store/info",
                        headers=self._headers(),
                    )
                    return response.status_code == 200
            except Exception as e:
                logger.error("salla_api_test_error", error=str(e))
                return False
        if self.webhook_secret:
            try:
                expected = hmac.new(self.webhook_secret.encode(), b"nazmos-test", hashlib.sha256).hexdigest()
                return len(expected) == 64
            except Exception as e:
                logger.error("salla_webhook_test_error", error=str(e))
                return False
        return False


class ZidAdapter(BasePOSAdapter):
    """Zid E-Commerce adapter for Saudi merchants.

    Supports API-polling for orders and products using a Zid merchant API token.
    Webhook support can be added later via the shared webhook infrastructure.
    """

    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self.access_token = self.credentials.get("access_token")
        self.base_url = self.credentials.get("base_url", "https://api.zid.sa/v1")

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

    async def fetch_sales(self, date_from=None, date_to=None) -> list[dict]:
        if not self.access_token:
            return []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                params = {"per_page": 100}
                if date_from:
                    params["from"] = str(date_from)
                if date_to:
                    params["to"] = str(date_to)
                response = await client.get(
                    f"{self.base_url}/orders",
                    headers=self._headers(),
                    params=params,
                )
                if response.status_code != 200:
                    logger.warning("zid_fetch_sales_failed", status=response.status_code)
                    return []
                orders = response.json().get("data", [])
                records = []
                for order in orders:
                    for item in order.get("items", []):
                        records.append({
                            "date": order.get("created_at"),
                            "item_id": str(item.get("id")),
                            "item_name": item.get("name"),
                            "sku": item.get("sku"),
                            "quantity": float(item.get("quantity", 1)),
                            "unit_price": float(item.get("price", 0)),
                            "cost_price": 0,
                            "total": float(item.get("total", 0) or item.get("price", 0)) * float(item.get("quantity", 1)),
                            "profit": 0,
                        })
                return records
        except Exception as e:
            logger.error("zid_fetch_sales_error", error=str(e))
            return []

    async def fetch_inventory(self) -> list[dict]:
        if not self.access_token:
            return []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/products",
                    headers=self._headers(),
                    params={"per_page": 100},
                )
                if response.status_code != 200:
                    logger.warning("zid_fetch_inventory_failed", status=response.status_code)
                    return []
                products = response.json().get("data", [])
                records = []
                for product in products:
                    records.append({
                        "sku": product.get("sku"),
                        "item_name": product.get("name"),
                        "quantity": float(product.get("stock_quantity", 0) or product.get("quantity", 0)),
                        "cost_price": float(product.get("cost_price", 0) or 0),
                        "sell_price": float(product.get("price", 0) or 0),
                    })
                return records
        except Exception as e:
            logger.error("zid_fetch_inventory_error", error=str(e))
            return []

    async def test_connection(self) -> bool:
        if not self.access_token:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.base_url}/store/profile",
                    headers=self._headers(),
                )
                return response.status_code == 200
        except Exception as e:
            logger.error("zid_test_connection_error", error=str(e))
            return False


class QoyodAdapter(BasePOSAdapter):
    """Qoyod Accounting adapter for Saudi SMEs.

    Pulls products and sales invoices into NazmOS using a Qoyod API key. The
    adapter is read-only; NazmOS does not write back to the Qoyod general ledger.
    """

    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self.api_key = self.credentials.get("api_key")
        self.base_url = self.credentials.get("base_url", "https://api.qoyod.com/api/2.0")

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "API-KEY": self.api_key,
        }

    async def fetch_sales(self, date_from=None, date_to=None) -> list[dict]:
        if not self.api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                params = {"per_page": 100}
                if date_from:
                    params["from"] = str(date_from)
                if date_to:
                    params["to"] = str(date_to)
                response = await client.get(
                    f"{self.base_url}/invoices",
                    headers=self._headers(),
                    params=params,
                )
                if response.status_code != 200:
                    logger.warning("qoyod_fetch_sales_failed", status=response.status_code)
                    return []
                invoices = response.json().get("invoices", [])
                records = []
                for invoice in invoices:
                    for line in invoice.get("line_items", invoice.get("products", [])):
                        qty = float(line.get("quantity", 1))
                        unit_price = float(line.get("unit_price", 0) or line.get("price", 0))
                        records.append({
                            "date": invoice.get("date") or invoice.get("created_at"),
                            "item_id": str(line.get("product_id")),
                            "item_name": line.get("description") or line.get("name"),
                            "sku": line.get("sku"),
                            "quantity": qty,
                            "unit_price": unit_price,
                            "cost_price": 0,
                            "total": unit_price * qty,
                            "profit": 0,
                        })
                return records
        except Exception as e:
            logger.error("qoyod_fetch_sales_error", error=str(e))
            return []

    async def fetch_inventory(self) -> list[dict]:
        if not self.api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/products",
                    headers=self._headers(),
                    params={"per_page": 100},
                )
                if response.status_code != 200:
                    logger.warning("qoyod_fetch_inventory_failed", status=response.status_code)
                    return []
                products = response.json().get("products", [])
                records = []
                for product in products:
                    records.append({
                        "sku": product.get("sku"),
                        "item_name": product.get("name") or product.get("description"),
                        "quantity": float(product.get("stock_quantity", 0) or product.get("quantity", 0)),
                        "cost_price": float(product.get("purchase_price", 0) or product.get("cost", 0) or 0),
                        "sell_price": float(product.get("selling_price", 0) or product.get("price", 0) or 0),
                    })
                return records
        except Exception as e:
            logger.error("qoyod_fetch_inventory_error", error=str(e))
            return []

    async def test_connection(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.base_url}/products",
                    headers=self._headers(),
                    params={"per_page": 1},
                )
                return response.status_code == 200
        except Exception as e:
            logger.error("qoyod_test_connection_error", error=str(e))
            return False


ADAPTER_REGISTRY = {
    "tally": TallyAdapter,
    "shopify": ShopifyAdapter,
    "woocommerce": WooCommerceAdapter,
    "zoho": ZohoAdapter,
    "csv_webhook": CSVWebhookAdapter,
    "custom_api": CustomAPIAdapter,
    "foodics": FoodicsWebhookAdapter,
    "salla": SallaAdapter,
    "zid": ZidAdapter,
    "qoyod": QoyodAdapter,
}


# Backward-compatible aliases for tests and code that imported the old names.
SallaWebhookAdapter = SallaAdapter


def get_adapter(adapter_type: str):
    adapter_class = ADAPTER_REGISTRY.get(adapter_type)
    if not adapter_class:
        raise ValueError(f"Unknown adapter type: {adapter_type}")
    return adapter_class
