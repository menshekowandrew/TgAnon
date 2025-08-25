import aiomysql
import json
from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType
import os
from urllib.parse import urlparse

class MySQLStorage(BaseStorage):
    def __init__(self):
        db_url = os.getenv("DATABASE_URL1")
        if not db_url:
            raise ValueError("DATABASE_URL is not set")
        parsed = urlparse(db_url)
        user = parsed.username
        password = parsed.password
        host = parsed.hostname
        port = parsed.port or 3306
        db = parsed.path.lstrip("/")
        self.host = host
        self.user = user
        self.password = password
        self.db = db
        self.port = port
        self.pool = None

    async def connect(self):
        self.pool = await aiomysql.create_pool(
            host=self.host,
            user=self.user,
            password=self.password,
            db=self.db,
            port=self.port,
            autocommit=True
        )

    async def close(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()

    async def set_state(self, key: StorageKey, state: StateType = None):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO fsm_storage (user_id, chat_id, state, data)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE state=VALUES(state)
                    """,
                    (key.user_id, key.chat_id, state, "{}")
                )

    async def get_state(self, key: StorageKey):
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT state FROM fsm_storage WHERE user_id=%s AND chat_id=%s",
                    (key.user_id, key.chat_id)
                )
                row = await cur.fetchone()
                return row["state"] if row else None

    async def set_data(self, key: StorageKey, data: dict):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE fsm_storage
                    SET data=%s
                    WHERE user_id=%s AND chat_id=%s
                    """,
                    (json.dumps(data), key.user_id, key.chat_id)
                )

    async def get_data(self, key: StorageKey):
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT data FROM fsm_storage WHERE user_id=%s AND chat_id=%s",
                    (key.user_id, key.chat_id)
                )
                row = await cur.fetchone()
                return json.loads(row["data"]) if row and row["data"] else {}

    async def clear_state(self, key: StorageKey):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM fsm_storage WHERE user_id=%s AND chat_id=%s",
                    (key.user_id, key.chat_id))