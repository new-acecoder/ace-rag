from __future__ import annotations

from pathlib import Path

import asyncpg

from app.core.config import Settings


async def run_migrations(settings: Settings) -> None:
    connection: asyncpg.Connection | None = None
    try:
        connection = await asyncpg.connect(settings.postgres_uri)
        await connection.execute("SELECT pg_advisory_lock(821671)")
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        migration_path = Path(__file__).with_name("migrations") / "001_ingestion_jobs.sql"
        applied = await connection.fetchval(
            "SELECT 1 FROM schema_migrations WHERE version = $1",
            migration_path.name,
        )
        if not applied:
            async with connection.transaction():
                await connection.execute(migration_path.read_text(encoding="utf-8"))
                await connection.execute(
                    "INSERT INTO schema_migrations(version) VALUES ($1)",
                    migration_path.name,
                )
    finally:
        if connection is not None:
            await connection.execute("SELECT pg_advisory_unlock(821671)")
            await connection.close()
