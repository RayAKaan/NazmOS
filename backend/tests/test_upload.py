from io import BytesIO
import pytest
from httpx import AsyncClient


INVENTORY_CSV = """Product,Current Stock,Cost Price,Shelf Price,Barcode,SKU,Category,Brand,Pack Size,Storage Type,Expiry Date,Batch Number,Reorder Level
Test Coffee,50,15,25,1234567890123,TCF-001,Beverages,Test Brand,250g,ambient,2026-12-31,BATCH-001,10
Test Dates,30,25,40,1234567890124,TDT-001,Dates,Test Brand,1kg,ambient,2026-12-31,BATCH-002,5
"""


@pytest.mark.asyncio
async def test_upload_requires_auth(client: AsyncClient):
    csv_file = BytesIO(b"product_name,quantity,price\nTest,10,100")
    response = await client.post(
        "/api/v1/upload/",
        files={"file": ("test.csv", csv_file, "text/csv")},
        data={"business_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upload_csv_file(authenticated_client: dict):
    ac = authenticated_client
    csv_file = BytesIO(INVENTORY_CSV.encode())
    response = await ac["client"].post(
        "/api/v1/upload/",
        files={"file": ("inventory.csv", csv_file, "text/csv")},
        data={"business_id": ac["business_id"]},
        headers=ac["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert "upload_id" in data
    assert "row_count" in data
    assert "detected_columns" in data


@pytest.mark.asyncio
async def test_upload_invalid_file_type(authenticated_client: dict):
    ac = authenticated_client
    text_file = BytesIO(b"This is not a CSV file")
    response = await ac["client"].post(
        "/api/v1/upload/",
        files={"file": ("test.txt", text_file, "text/plain")},
        data={"business_id": ac["business_id"]},
        headers=ac["headers"],
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_large_file_rejected(authenticated_client: dict):
    ac = authenticated_client
    large_content = "a" * (16 * 1024 * 1024)
    large_file = BytesIO(large_content.encode())
    response = await ac["client"].post(
        "/api/v1/upload/",
        files={"file": ("large.csv", large_file, "text/csv")},
        data={"business_id": ac["business_id"]},
        headers=ac["headers"],
    )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_get_upload_status(authenticated_client: dict):
    ac = authenticated_client
    csv_file = BytesIO(INVENTORY_CSV.encode())
    upload_response = await ac["client"].post(
        "/api/v1/upload/",
        files={"file": ("inventory.csv", csv_file, "text/csv")},
        data={"business_id": ac["business_id"]},
        headers=ac["headers"],
    )
    assert upload_response.status_code == 200
    upload_id = upload_response.json()["upload_id"]

    status_response = await ac["client"].get(
        f"/api/v1/upload/{upload_id}/status",
        headers=ac["headers"],
    )
    assert status_response.status_code == 200
    data = status_response.json()
    assert "status" in data
    assert "upload_id" in data
