"""Unit tests for partner program service."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

from app.services.partner_service import register_partner, get_partner_dashboard, record_referral, update_referral_status


def _mock_db(rows=None):
    db = MagicMock()

    async def _execute(stmt, params=None):
        res = MagicMock()
        if rows is not None:
            res.fetchone = MagicMock(return_value=rows)
        else:
            res.fetchone = MagicMock(return_value=None)
        res.fetchall = MagicMock(return_value=[])
        return res

    db.execute = AsyncMock(side_effect=_execute)
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_register_partner_new():
    db = _mock_db()
    inserted = MagicMock()
    inserted.id = uuid4()
    inserted._mapping = {"id": inserted.id, "referral_code": "NAZM-1234ABCD"}
    db.execute.side_effect = [
        MagicMock(fetchone=MagicMock(return_value=None)),  # existing by email
        MagicMock(fetchone=MagicMock(return_value=None)),  # duplicate code check
        MagicMock(fetchone=MagicMock(return_value=inserted)),  # insert returning
        MagicMock(fetchone=MagicMock(return_value=inserted)),  # final select
    ]
    partner = await register_partner(db, uuid4(), "accountant", "Ahmed Books", "ahmed@example.com")
    assert partner["id"] == inserted.id


@pytest.mark.asyncio
async def test_register_partner_invalid_type():
    db = _mock_db()
    with pytest.raises(ValueError):
        await register_partner(db, uuid4(), "invalid", "X", "x@x.com")


@pytest.mark.asyncio
async def test_get_partner_dashboard_not_found():
    db = _mock_db(rows=None)
    with pytest.raises(ValueError):
        await get_partner_dashboard(db, uuid4())


@pytest.mark.asyncio
async def test_record_referral_inactive_partner():
    db = _mock_db()
    partner_row = MagicMock()
    partner_row.status = "pending"
    db.execute.return_value = MagicMock(fetchone=MagicMock(return_value=partner_row))
    with pytest.raises(ValueError):
        await record_referral(db, uuid4(), "Store", estimated_arr_sar=1000)


@pytest.mark.asyncio
async def test_update_referral_status_invalid():
    db = _mock_db()
    with pytest.raises(ValueError):
        await update_referral_status(db, uuid4(), uuid4(), "unknown")
