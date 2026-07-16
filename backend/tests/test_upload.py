import pytest
from httpx import AsyncClient
from io import BytesIO
import csv


@pytest.fixture
def auth_headers(client: AsyncClient):
    async def _get_headers():
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "upload_test@example.com",
                "password": "testpass123",
                "full_name": "Upload Test User"
            }
        )
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "upload_test@example.com",
                "password": "testpass123"
            }
        )
        token = login_response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    
    import asyncio
    return asyncio.run(_get_headers())


def create_csv_file(rows: list[dict]) -> BytesIO:
    buffer = BytesIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    buffer.seek(0)
    return buffer


@pytest.mark.asyncio
async def test_upload_requires_auth(client: AsyncClient):
    csv_file = create_csv_file([
        {"product_name": "Test Product", "quantity": "10", "price": "100"}
    ])
    response = await client.post(
        "/api/v1/upload/",
        files={"file": ("test.csv", csv_file, "text/csv")},
        data={"business_id": "test-id"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upload_csv_file(client: AsyncClient, auth_headers):
    csv_content = """product_name,sku,category,quantity,unit_price,supplier
Organic Milk,MLK001,Dairy,50,60,Fresh Farms
Greek Yogurt,YGT001,Dairy,30,80,Dairy Plus
Wheat Bread,BRD001,Bakery,20,35,Baker's Delight"""

    csv_file = BytesIO(csv_content.encode())
    
    response = await client.post(
        "/api/v1/upload/",
        files={"file": ("inventory.csv", csv_file, "text/csv")},
        data={"business_id": "00000000-0000-0000-0000-000000000001"},
        headers=auth_headers
    )
    
    assert response.status_code in [200, 201]
    data = response.json()
    assert "upload_id" in data or "file_id" in data


@pytest.mark.asyncio
async def test_upload_invalid_file_type(client: AsyncClient, auth_headers):
    text_file = BytesIO(b"This is not a CSV file")
    
    response = await client.post(
        "/api/v1/upload/",
        files={"file": ("test.txt", text_file, "text/plain")},
        data={"business_id": "00000000-0000-0000-0000-000000000001"},
        headers=auth_headers
    )
    
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_large_file_rejected(client: AsyncClient, auth_headers):
    large_content = "a" * (16 * 1024 * 1024)
    large_file = BytesIO(large_content.encode())
    
    response = await client.post(
        "/api/v1/upload/",
        files={"file": ("large.csv", large_file, "text/csv")},
        data={"business_id": "00000000-0000-0000-0000-000000000001"},
        headers=auth_headers
    )
    
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_get_upload_status(client: AsyncClient, auth_headers):
    csv_content = """product_name,sku,category,quantity,unit_price
Test Product,TST001,Test,10,100"""
    csv_file = BytesIO(csv_content.encode())
    
    upload_response = await client.post(
        "/api/v1/upload/",
        files={"file": ("test.csv", csv_file, "text/csv")},
        data={"business_id": "00000000-0000-0000-0000-000000000001"},
        headers=auth_headers
    )
    
    if upload_response.status_code in [200, 201]:
        upload_id = upload_response.json().get("upload_id") or upload_response.json().get("file_id")
        
        status_response = await client.get(
            f"/api/v1/upload/{upload_id}/status",
            headers=auth_headers
        )
        
        assert status_response.status_code == 200
        assert "status" in status_response.json()
