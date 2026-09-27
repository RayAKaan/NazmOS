import asyncio, asyncpg, sys

async def main():
    try:
        c = await asyncpg.connect(
            "postgresql://nazmos:nazmos_dev@localhost:5432/nazmos_test",
            timeout=8,
        )
        v = await c.fetchval("SHOW server_version")
        role = await c.fetchval("SELECT current_user")
        db = await c.fetchval("SELECT current_database()")
        await c.close()
        print(f"TCP+asyncpg AUTH OK: user={role} db={db} pg={v}")
        sys.exit(0)
    except Exception as e:
        print(f"TCP+asyncpg AUTH FAIL: {type(e).__name__}: {str(e)[:120]}")
        sys.exit(1)

asyncio.run(main())
