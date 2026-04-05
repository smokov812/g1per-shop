from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from bot.db.base import Base
from bot.db import models  # noqa: F401


ORDER_ADDITIONAL_COLUMNS = {
    "payment_provider": "ALTER TABLE orders ADD COLUMN payment_provider VARCHAR(32)",
    "external_payment_id": "ALTER TABLE orders ADD COLUMN external_payment_id VARCHAR(128)",
    "payment_url": "ALTER TABLE orders ADD COLUMN payment_url VARCHAR(500)",
    "payment_status": "ALTER TABLE orders ADD COLUMN payment_status VARCHAR(64)",
    "payment_currency": "ALTER TABLE orders ADD COLUMN payment_currency VARCHAR(32)",
    "payment_network": "ALTER TABLE orders ADD COLUMN payment_network VARCHAR(64)",
    "payment_amount": "ALTER TABLE orders ADD COLUMN payment_amount NUMERIC(18, 8)",
    "payment_txid": "ALTER TABLE orders ADD COLUMN payment_txid VARCHAR(255)",
    "paid_at": "ALTER TABLE orders ADD COLUMN paid_at DATETIME",
}

PAYMENT_EVENT_ADDITIONAL_COLUMNS = {
    "payment_id": "ALTER TABLE payment_events ADD COLUMN payment_id INTEGER",
    "source": "ALTER TABLE payment_events ADD COLUMN source VARCHAR(32) DEFAULT 'unknown'",
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


async def _apply_sqlite_migrations(connection) -> None:
    existing_order_columns = await _list_columns(connection, "orders")
    for column_name, ddl in ORDER_ADDITIONAL_COLUMNS.items():
        if column_name not in existing_order_columns:
            await connection.exec_driver_sql(ddl)

    existing_payment_event_columns = await _list_columns(connection, "payment_events")
    for column_name, ddl in PAYMENT_EVENT_ADDITIONAL_COLUMNS.items():
        if column_name not in existing_payment_event_columns:
            await connection.exec_driver_sql(ddl)


async def _list_columns(connection, table_name: str) -> set[str]:
    result = await connection.exec_driver_sql(f"PRAGMA table_info({table_name})")
    return {row[1] for row in result.fetchall()}
