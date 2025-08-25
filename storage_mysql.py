import aiomysql
import json
from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType
from urllib.parse import urlparse
import os

class MySQLStorage(BaseStorage):
    def __init__(self):
        db_url = os.getenv("DATABASE_URL1")
        if not db_url:
            raise ValueError("DATABASE_URL1 is not set")
        parsed = urlparse(db_url)
        self.user = parsed.username
        self.password = parsed.password
        self.host = parsed.hostname
        self.port = parsed.port or 3306
        self.db = parsed.path.lstrip("/")
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
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS fsm_storage (
                        bot_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        chat_id BIGINT NOT NULL,
                        state VARCHAR(255),
                        data TEXT,
                        PRIMARY KEY (bot_id, user_id, chat_id)
                    )
                """)

    async def close(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()

    # ---------------- State ----------------
    async def set_state(self, key: StorageKey, state: StateType = None):
        state_str = state.state if state else None
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO fsm_storage (bot_id, user_id, chat_id, state, data)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE state=VALUES(state)
                """, (key.bot_id, key.user_id, key.chat_id, state_str, "{}"))

    async def get_state(self, key: StorageKey):
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT state FROM fsm_storage WHERE bot_id=%s AND user_id=%s AND chat_id=%s",
                    (key.bot_id, key.user_id, key.chat_id)
                )
                row = await cur.fetchone()
                return row["state"] if row else None

    # ---------------- Data ----------------
    async def set_data(self, key: StorageKey, data: dict):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Получаем текущее состояние, чтобы не затирать state
                state = await self.get_state(key)
                await cur.execute("""
                    INSERT INTO fsm_storage (bot_id, user_id, chat_id, state, data)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE data=VALUES(data)
                """, (key.bot_id, key.user_id, key.chat_id, state, json.dumps(data)))

    async def get_data(self, key: StorageKey):
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT data FROM fsm_storage WHERE bot_id=%s AND user_id=%s AND chat_id=%s",
                    (key.bot_id, key.user_id, key.chat_id)
                )
                row = await cur.fetchone()
                return json.loads(row["data"]) if row and row["data"] else {}

    # ---------------- Clear ----------------
    async def clear(self, key: StorageKey):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM fsm_storage WHERE bot_id=%s AND user_id=%s AND chat_id=%s",
                    (key.bot_id, key.user_id, key.chat_id)
                )
