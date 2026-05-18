import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Assuming standard pg url from .env
DATABASE_URL = "postgresql+asyncpg://linqdev:linqdev123@localhost:5432/doctor_onboarding"

async def async_main():
    engine = create_async_engine(DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        print("Executing update on users...")
        res1 = await conn.execute(text("UPDATE users SET role = 'operation' WHERE role = 'operational'"))
        print(f"Updated {res1.rowcount} users.")
        
        print("Executing update on doctor_status_history...")
        res2 = await conn.execute(text("UPDATE doctor_status_history SET changed_by = 'operation' WHERE changed_by = 'operational'"))
        print(f"Updated {res2.rowcount} doctor_status_history records.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(async_main())
