"""Shared test fixtures."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Force test settings before importing the app.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-0123456789-abcdef")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-0123456789-abcdef")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "TestPassword123!")
# The suite logs in repeatedly within one process; the in-process limiter is
# not shared across deployments, so disable it here rather than raising limits.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from app.core.database import get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)
    session = maker()
    try:
        yield session
    finally:
        await session.close()


@pytest_asyncio.fixture
async def app(test_engine, db_session):
    application = create_app()
    application.dependency_overrides[get_db] = lambda: db_session
    yield application
    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_user(db_session):
    from app.core.security import hash_password
    from app.models import Role, User
    from app.models.role import ROLE_PERMISSIONS

    admin_perms = ",".join(ROLE_PERMISSIONS["admin"])
    role = Role(name="admin", is_system=True, permissions=admin_perms)
    db_session.add(role)
    await db_session.flush()

    user = User(
        id=uuid.uuid4(),
        username="admin",
        email="admin@example.com",
        password_hash=hash_password("TestPassword123!"),
        is_active=True,
        roles=[role],
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def admin_token(client, admin_user) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "TestPassword123!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest_asyncio.fixture
async def auth_client(client, admin_token) -> AsyncClient:
    client.headers["Authorization"] = f"Bearer {admin_token}"
    return client
