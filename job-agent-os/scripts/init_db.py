"""Initialize database: create pgvector extension + all tables.

Usage:
    python scripts/init_db.py
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from job_agent_os.models import Base  # noqa: F401 - import all models
from job_agent_os.settings import get_settings


async def init_database() -> None:
    """Initialize database with pgvector extension and all tables."""
    settings = get_settings()
    print(f"Connecting to database: {settings.database_url.split('@')[-1]}")

    engine = create_async_engine(settings.database_url, echo=False)

    try:
        async with engine.begin() as conn:
            # 1. Create pgvector extension
            print("Creating pgvector extension...")
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            print("  ✓ pgvector extension ready")

            # 2. Create all tables
            print("Creating tables...")
            await conn.run_sync(Base.metadata.create_all)
            print(f"  ✓ {len(Base.metadata.tables)} tables created")

            # 3. List created tables
            result = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
            )
            tables = [row[0] for row in result.fetchall()]
            print(f"\nTables in database ({len(tables)}):")
            for table in tables:
                print(f"  - {table}")

        print("\n✅ Database initialization complete!")

    except Exception as e:
        print(f"\n❌ Database initialization failed: {e}")
        raise
    finally:
        await engine.dispose()


async def create_test_database() -> None:
    """Create test database if it doesn't exist."""
    settings = get_settings()
    # Connect to default postgres database to create test db
    base_url = settings.database_url.rsplit("/", 1)[0] + "/postgres"
    engine = create_async_engine(base_url, echo=False, isolation_level="AUTOCOMMIT")

    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = 'job_agent_os_test'")
            )
            if not result.fetchone():
                await conn.execute(text("CREATE DATABASE job_agent_os_test"))
                print("✓ Test database 'job_agent_os_test' created")
            else:
                print("✓ Test database 'job_agent_os_test' already exists")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Initialize Job Agent OS database")
    parser.add_argument(
        "--test-db",
        action="store_true",
        help="Also create test database",
    )
    args = parser.parse_args()

    if args.test_db:
        asyncio.run(create_test_database())

    asyncio.run(init_database())
