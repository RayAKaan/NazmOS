import pytest
from httpx import AsyncClient

from app.services.storage import LocalStorageBackend, get_storage_backend


@pytest.mark.asyncio
async def test_local_storage_round_trip(client: AsyncClient):
    backend = LocalStorageBackend(base_dir="/tmp/nazmos_test_storage")
    key = await backend.store("test.csv", b"hello,world", "text/csv")
    assert await backend.exists(key)
    assert await backend.retrieve(key) == b"hello,world"
    await backend.delete(key)
    assert not await backend.exists(key)


def test_default_backend_is_local():
    backend = get_storage_backend()
    assert isinstance(backend, LocalStorageBackend)
