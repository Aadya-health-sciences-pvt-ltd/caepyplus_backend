import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = "postgresql+asyncpg://linqdev:linqdev123@localhost:5432/doctor_onboarding"

async def async_main():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        res = await conn.execute(text("UPDATE alembic_version SET version_num='001'"))
        print(f"Updated {res.rowcount} rows in alembic_version")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(async_main())
