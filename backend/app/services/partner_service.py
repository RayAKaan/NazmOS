"""Accountant / Monshaat advisor partner program service.

V1 tracks partner applications, referral codes, and conversion status. Payouts
are recorded but not wired automatically.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.money import sar


_PARTNER_TYPE_LABELS = {
    "accountant": "Accountant / محاسب",
    "advisor": "Monshaat Advisor / مستشار",
    "consultant": "Business Consultant / مستشار أعمال",
    "auditor": "Compliance Auditor / مدقق",
    "fintech": "Bank / Fintech Partner / شريك مالي",
}


def _generate_code() -> str:
    return "NAZM-" + secrets.token_hex(4).upper()


async def register_partner(
    db: AsyncSession,
    owner_user_id: UUID | str | None,
    partner_type: str,
    name: str,
    email: str,
    phone: str | None = None,
    city: str | None = None,
    cr_number: str | None = None,
    monshaat_certified: bool = False,
    commission_pct: float = 10.0,
    bank_iban: str | None = None,
) -> dict:
    if partner_type not in _PARTNER_TYPE_LABELS:
        raise ValueError(f"Unsupported partner type: {partner_type}")

    # Idempotent re-application: if email exists and is pending, update.
    existing = await db.execute(text(
        "SELECT id, status FROM partners WHERE email = :email"
    ), {"email": email})
    row = existing.fetchone()
    if row and row.status != "suspended":
        await db.execute(text("""
            UPDATE partners
            SET partner_type = :ptype,
                name = :name,
                phone = :phone,
                city = :city,
                cr_number = :cr,
                monshaat_certified = :mc,
                commission_pct = :comm,
                bank_iban = :iban,
                updated_at = NOW()
            WHERE id = :id
        """), {
            "id": str(row.id),
            "ptype": partner_type,
            "name": name,
            "phone": phone,
            "city": city,
            "cr": cr_number,
            "mc": monshaat_certified,
            "comm": sar(commission_pct),
            "iban": bank_iban,
        })
        await db.commit()
        updated = await db.execute(text("SELECT * FROM partners WHERE id = :id"), {"id": str(row.id)})
        return dict(updated.fetchone()._mapping)

    code = _generate_code()
    # Ensure uniqueness (collision unlikely but possible).
    while True:
        dup = await db.execute(text("SELECT 1 FROM partners WHERE referral_code = :c"), {"c": code})
        if not dup.fetchone():
            break
        code = _generate_code()

    res = await db.execute(text("""
        INSERT INTO partners
            (id, owner_user_id, partner_type, status, name, email, phone, city,
             cr_number, monshaat_certified, referral_code, commission_pct,
             bank_iban, created_at, updated_at)
        VALUES
            (gen_random_uuid(), :uid, :ptype, 'pending', :name, :email, :phone, :city,
             :cr, :mc, :code, :comm, :iban, NOW(), NOW())
        RETURNING *
    """), {
        "uid": str(owner_user_id) if owner_user_id else None,
        "ptype": partner_type,
        "name": name,
        "email": email,
        "phone": phone,
        "city": city,
        "cr": cr_number,
        "mc": monshaat_certified,
        "code": code,
        "comm": sar(commission_pct),
        "iban": bank_iban,
    })
    await db.commit()
    return dict(res.fetchone()._mapping)


async def get_partner_by_user(db: AsyncSession, user_id: UUID | str) -> dict | None:
    res = await db.execute(text(
        "SELECT * FROM partners WHERE owner_user_id = :uid ORDER BY created_at DESC LIMIT 1"
    ), {"uid": str(user_id)})
    row = res.fetchone()
    return dict(row._mapping) if row else None


async def get_partner_dashboard(db: AsyncSession, partner_id: UUID | str) -> dict[str, Any]:
    res = await db.execute(text("SELECT * FROM partners WHERE id = :id"), {"id": str(partner_id)})
    partner = res.fetchone()
    if not partner:
        raise ValueError("Partner not found")

    refs = await db.execute(text("""
        SELECT id, merchant_name, status, estimated_arr_sar, created_at, converted_at, payout_sar
        FROM partner_referrals
        WHERE partner_id = :pid
        ORDER BY created_at DESC
    """), {"pid": str(partner_id)})

    referral_rows = [dict(r._mapping) for r in refs.fetchall()]
    converted = [r for r in referral_rows if r["status"] == "converted"]
    return {
        "partner": dict(partner._mapping),
        "label": _PARTNER_TYPE_LABELS.get(partner.partner_type, partner.partner_type),
        "referrals": referral_rows,
        "summary": {
            "total": len(referral_rows),
            "converted": len(converted),
            "estimated_arr_sar": sum(float(r["estimated_arr_sar"] or 0) for r in converted),
            "payout_due_sar": float(partner.payout_due_sar or 0),
        },
    }


async def record_referral(
    db: AsyncSession,
    partner_id: UUID | str,
    merchant_name: str,
    merchant_email: str | None = None,
    merchant_phone: str | None = None,
    estimated_arr_sar: float | None = None,
    business_id: UUID | str | None = None,
    notes: str | None = None,
) -> dict:
    res = await db.execute(text("SELECT id, status FROM partners WHERE id = :id"), {"id": str(partner_id)})
    partner = res.fetchone()
    if not partner:
        raise ValueError("Partner not found")
    if partner.status != "active":
        raise ValueError("Partner is not active")

    res = await db.execute(text("""
        INSERT INTO partner_referrals
            (id, partner_id, business_id, merchant_name, merchant_email, merchant_phone,
             estimated_arr_sar, status, notes, created_at, updated_at)
        VALUES
            (gen_random_uuid(), :pid, :bid, :name, :email, :phone, :arr, 'lead', :notes, NOW(), NOW())
        RETURNING *
    """), {
        "pid": str(partner_id),
        "bid": str(business_id) if business_id else None,
        "name": merchant_name,
        "email": merchant_email,
        "phone": merchant_phone,
        "arr": sar(estimated_arr_sar) if estimated_arr_sar is not None else None,
        "notes": notes,
    })
    await db.execute(text("""
        UPDATE partners
        SET total_referrals = total_referrals + 1,
            updated_at = NOW()
        WHERE id = :id
    """), {"id": str(partner_id)})
    await db.commit()
    return dict(res.fetchone()._mapping)


async def update_referral_status(
    db: AsyncSession,
    partner_id: UUID | str,
    referral_id: UUID | str,
    status: str,
    payout_sar: float | None = None,
) -> dict:
    if status not in {"lead", "converted", "churned"}:
        raise ValueError("Invalid status")

    res = await db.execute(text("""
        SELECT * FROM partner_referrals
        WHERE id = :rid AND partner_id = :pid
    """), {"rid": str(referral_id), "pid": str(partner_id)})
    ref = res.fetchone()
    if not ref:
        raise ValueError("Referral not found")

    converted_at = None
    churned_at = None
    if status == "converted" and ref.status != "converted":
        converted_at = datetime.now(timezone.utc)
    if status == "churned" and ref.status != "churned":
        churned_at = datetime.now(timezone.utc)

    payout = sar(payout_sar) if payout_sar is not None else ref.payout_sar
    await db.execute(text("""
        UPDATE partner_referrals
        SET status = :status,
            converted_at = COALESCE(:converted_at, converted_at),
            churned_at = COALESCE(:churned_at, churned_at),
            payout_sar = :payout,
            updated_at = NOW()
        WHERE id = :rid
    """), {
        "rid": str(referral_id),
        "status": status,
        "converted_at": converted_at,
        "churned_at": churned_at,
        "payout": payout,
    })

    # Sync partner totals when status changes to converted.
    if status == "converted" and ref.status != "converted":
        arr = float(ref.estimated_arr_sar or 0)
        await db.execute(text("""
            UPDATE partners
            SET total_converted = total_converted + 1,
                total_revenue_sar = total_revenue_sar + :arr,
                payout_due_sar = payout_due_sar + :payout,
                updated_at = NOW()
            WHERE id = :pid
        """), {"pid": str(partner_id), "arr": sar(arr), "payout": sar(payout or 0)})

    await db.commit()
    updated = await db.execute(text("SELECT * FROM partner_referrals WHERE id = :id"), {"id": str(referral_id)})
    return dict(updated.fetchone()._mapping)


async def list_active_partners(db: AsyncSession, city: str | None = None, limit: int = 100) -> list[dict]:
    query = "SELECT * FROM partners WHERE status = 'active'"
    params: dict[str, Any] = {}
    if city:
        query += " AND city = :city"
        params["city"] = city
    query += " ORDER BY total_converted DESC, created_at DESC LIMIT :limit"
    params["limit"] = limit
    res = await db.execute(text(query), params)
    return [dict(r._mapping) for r in res.fetchall()]


async def approve_partner(db: AsyncSession, partner_id: UUID | str, reviewed_by: UUID | str) -> dict:
    await db.execute(text("""
        UPDATE partners
        SET status = 'active',
            reviewed_at = NOW(),
            reviewed_by = :uid,
            updated_at = NOW()
        WHERE id = :id
    """), {"id": str(partner_id), "uid": str(reviewed_by)})
    await db.commit()
    res = await db.execute(text("SELECT * FROM partners WHERE id = :id"), {"id": str(partner_id)})
    return dict(res.fetchone()._mapping)
