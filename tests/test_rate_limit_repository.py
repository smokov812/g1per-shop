from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from bot.db.repositories import RateLimitRepository
from bot.db.session import create_session_maker, init_db


class RateLimitRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "rate_limit_test.db"
        self.engine, self.session_maker = create_session_maker(f"sqlite+aiosqlite:///{db_path.as_posix()}")
        await init_db(self.engine)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self.temp_dir.cleanup()

    async def test_consume_blocks_repeated_hits_inside_window(self) -> None:
        async with self.session_maker() as session:
            repo = RateLimitRepository(session)
            first = await repo.consume(user_id=1, scope="message", window_seconds=0.2)
        self.assertTrue(first.allowed)

        async with self.session_maker() as session:
            repo = RateLimitRepository(session)
            second = await repo.consume(user_id=1, scope="message", window_seconds=0.2)
        self.assertFalse(second.allowed)
        self.assertGreater(second.retry_after, 0)

        await asyncio.sleep(0.25)

        async with self.session_maker() as session:
            repo = RateLimitRepository(session)
            third = await repo.consume(user_id=1, scope="message", window_seconds=0.2)
        self.assertTrue(third.allowed)


if __name__ == "__main__":
    unittest.main()
