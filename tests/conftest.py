import asyncio
import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Force SQLite in-memory / file for testing
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_inventory.db"
os.environ["SYNC_DATABASE_URL"] = "sqlite:///./test_inventory.db"
os.environ["ENVIRONMENT"] = "testing"
os.environ["MLFLOW_DISABLE_AGENT_HINT"] = "1"

from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token
from backend.app.main import app
from backend.app.models.user import User
import uuid

test_engine = create_async_engine(
    "sqlite+aiosqlite:///./test_inventory.db",
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()
    if os.path.exists("./test_inventory.db"):
        try:
            os.remove("./test_inventory.db")
        except OSError:
            pass


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with TestingSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def async_client():
    async def override_get_db():
        async with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(db_session: AsyncSession):
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        email=f"admin_{user_id[:8]}@example.com",
        hashed_password="hash",
        full_name="Admin User",
        role="admin",
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    token = create_access_token(subject=user.id, role="admin")
    return {"Authorization": f"Bearer {token}"}


