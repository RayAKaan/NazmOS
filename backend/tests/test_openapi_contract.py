"""Contract test: ensure the OpenAPI schema does not drift unexpectedly.

Run with ``UPDATE_GOLDEN=1 pytest tests/test_openapi_contract.py`` to refresh
the committed golden file after intentional API changes. Install the exact
dependency pins from ``backend/requirements.txt`` (fastapi is pinned) so the
regenerated schema matches what CI produces.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

GOLDEN_PATH = Path(__file__).parent.parent / "docs" / "openapi.json"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _load_golden() -> dict:
    if not GOLDEN_PATH.exists():
        return {}
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _save_golden(data: dict) -> None:
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _strip_non_semantic(schema: object) -> None:
    """Drop ``additionalProperties: true`` in place.

    Pydantic version differences (2.9.2 vs 2.13) toggle whether an explicit
    ``additionalProperties: true`` is emitted for dict-valued fields. JSON
    Schema defaults to ``additionalProperties: true`` anyway, so the key is
    semantically inert and must not gate the contract test on the installing
    pydantic version. Real schema drift is still caught by exact comparison.
    """
    if isinstance(schema, dict):
        if schema.get("additionalProperties") is True:
            del schema["additionalProperties"]
        for value in schema.values():
            _strip_non_semantic(value)
    elif isinstance(schema, list):
        for item in schema:
            _strip_non_semantic(item)


def test_openapi_schema_matches_golden(client: TestClient):
    response = client.get("/openapi.json")
    assert response.status_code == 200, "OpenAPI schema endpoint should return 200"
    current = response.json()

    if os.getenv("UPDATE_GOLDEN"):
        _save_golden(current)
        pytest.skip("Golden OpenAPI file updated")

    golden = _load_golden()
    assert golden, "Golden OpenAPI file is missing. Run UPDATE_GOLDEN=1 pytest ... to create it."

    _strip_non_semantic(current)
    _strip_non_semantic(golden)

    # Compare only the stable parts: paths and component schemas. Metadata/version
    # changes are intentional and should not break clients.
    assert current.get("paths") == golden.get("paths"), "OpenAPI paths have changed"
    assert current.get("components", {}).get("schemas") == golden.get("components", {}).get("schemas"), (
        "OpenAPI component schemas have changed"
    )
