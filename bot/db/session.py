from __future__ import annotations

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from bot.db.base import Base
from bot.db import models  # noqa: F401


ADDITIONAL_COLUMNS = {
    "orders": {
        "payment_provider": "VARCHAR(32)",
        "external_payment_id": "VARCHAR(128)",
        "payment_url": "VARCHAR(500)",
        "payment_status": "VARCHAR(64)",
        "payment_currency": "VARCHAR(32)",
        "payment_network": "VARCHAR(64)",
        "payment_amount": "NUMERIC(18, 8)",
        "payment_txid": "VARCHAR(255)",
        "paid_at": "TIMESTAMP NULL",
        "delivery_sent_at": "TIMESTAMP NULL",
        "preorder_delivery_sent_at": "TIMESTAMP NULL",
    },
    "product_delivery_files": {
        "sync_key": "VARCHAR(255)",
    },
    "products": {
        "delivery_content": "TEXT",
        "post_payment_message": "TEXT",
    },
    "order_items": {
        "stock_status": "VARCHAR(32)",
        "delivery_content": "TEXT",
        "post_payment_message": "TEXT",
    },
    "payment_events": {
        "payment_id": "INTEGER",
        "source": "VARCHAR(32) DEFAULT 'unknown'",
    },
}


def create_session_maker(database_url: str) -> tuple[AsyncEngine, async_sessionmaker]:
    is_sqlite = database_url.startswith("sqlite+") or database_url.startswith("sqlite://")
    engine_kwargs = {"echo": False}

    if is_sqlite:
        engine_kwargs["connect_args"] = {"timeout": 30}
    else:
        engine_kwargs["pool_pre_ping"] = True
        engine_kwargs["pool_recycle"] = 1800

    engine = create_async_engine(database_url, **engine_kwargs)

    if is_sqlite:
        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_maker


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        if engine.dialect.name == "sqlite":
            await _apply_sqlite_migrations(connection)
        elif engine.dialect.name == "postgresql":
            await _apply_postgres_migrations(connection)


async def _apply_sqlite_migrations(connection) -> None:
    for table_name, columns in ADDITIONAL_COLUMNS.items():
        existing_columns = await _list_sqlite_columns(connection, table_name)
        for column_name, definition in columns.items():
            if column_name not in existing_columns:
                await connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


async def _apply_postgres_migrations(connection) -> None:
    for table_name, columns in ADDITIONAL_COLUMNS.items():
        for column_name, definition in columns.items():
            await connection.execute(
                text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {definition}")
            )


async def _list_sqlite_columns(connection, table_name: str) -> set[str]:
    result = await connection.exec_driver_sql(f"PRAGMA table_info({table_name})")
    return {row[1] for row in result.fetchall()}




