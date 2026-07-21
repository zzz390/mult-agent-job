"""Pytest fixtures (DB, Redis, Client, Auth)."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from job_agent_os.models.base import Base
from job_agent_os.settings import get_settings


def _is_db_available() -> bool:
    """Check if test database is reachable."""
    import socket

    settings = get_settings()
    # Parse host and port from database URL
    try:
        url_part = settings.database_url.split("@")[-1]  # host:port/dbname
        host_port = url_part.split("/")[0]
        host, port = host_port.split(":") if ":" in host_port else (host_port, "5432")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, int(port)))
        sock.close()
        return result == 0
    except Exception:
        return False


# Skip marker for tests requiring database
requires_db = pytest.mark.skipif(
    not _is_db_available(),
    reason="Database not available (start Docker: make docker-up)",
)


# === Database Fixtures ===


@pytest_asyncio.fixture
async def test_engine():
    """Create async engine for testing (uses test database)."""
    if not _is_db_available():
        pytest.skip("Database not available (start Docker: make docker-up)")

    settings = get_settings()
    # Use a separate test database
    test_db_url = settings.database_url.replace("/job_agent_os", "/job_agent_os_test")
    engine = create_async_engine(test_db_url, echo=False, pool_pre_ping=True)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a database session for testing with transaction rollback."""
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


# === Redis Fixture (Mock) ===


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.exists = AsyncMock(return_value=0)
    redis_mock.expire = AsyncMock(return_value=True)
    redis_mock.close = AsyncMock()
    return redis_mock


# === FastAPI TestClient ===


@pytest_asyncio.fixture
async def client(db_session, mock_redis) -> AsyncGenerator[AsyncClient, None]:
    """Create httpx AsyncClient for API testing."""
    from job_agent_os.api.deps import get_db
    from job_agent_os.main import create_app

    app = create_app()

    # Override DB dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with patch("job_agent_os.db.redis.get_redis", return_value=mock_redis):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    app.dependency_overrides.clear()


# === Auth Fixtures ===


@pytest_asyncio.fixture
async def test_user(db_session):
    """Create a test user in the database."""
    from job_agent_os.core.security import hash_password
    from job_agent_os.models.user import User

    user = User(
        id=uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash=hash_password("testpass123"),
        status="active",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user) -> dict[str, str]:
    """Get authentication headers with a valid JWT token."""
    from job_agent_os.core.security import create_access_token

    token = create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def registered_user_token(client) -> dict:
    """Register a user via API and return tokens."""
    response = await client.post(
        "/v1/auth/register",
        json={
            "username": "apiuser",
            "email": "apiuser@example.com",
            "password": "securepass123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    return data["data"]


# === LLM Mock ===


@pytest.fixture
def mock_llm():
    """Mock LLM for unit tests."""
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content='{"result": "mocked"}'))
    llm.with_structured_output = MagicMock(return_value=llm)
    return llm
