from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings # Assuming you load your .env here

# Create the async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False, # Set to True for debugging SQL queries locally
    future=True,
    pool_size=20,
    max_overflow=10
)

# Create a session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Dependency to yield DB sessions for FastAPI endpoints
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()