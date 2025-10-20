import sqlite3
import time
from typing import List, Dict, Any, Optional


class Database:
    def __init__(self):
        self.conn = sqlite3.connect('anon_chat.db', check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        # Таблица пользователей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Таблица постов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')

        # Таблица активных чатов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            user1_id INTEGER,
            user2_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user1_id, user2_id),
            FOREIGN KEY (user1_id) REFERENCES users (user_id),
            FOREIGN KEY (user2_id) REFERENCES users (user_id)
        )
        ''')

        cursor.execute('''
                CREATE TABLE IF NOT EXISTS message_mirror (
    sender_id INTEGER,
    receiver_id INTEGER,
    sender_message_id INTEGER,
    receiver_message_id INTEGER,
    PRIMARY KEY (sender_id, sender_message_id)
);


                ''')
        self.conn.commit()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                expires_at INTEGER,
                permanent INTEGER DEFAULT 0
            )
            """)
        self.conn.commit()

    def add_user(self, user_id: int, username: str, full_name: str):
        cursor = self.conn.cursor()
        cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, full_name)
        VALUES (?, ?, ?)
        ''', (user_id, username, full_name))
        self.conn.commit()

    def add_post(self, user_id: int, text: str):
        cursor = self.conn.cursor()
        # Удаляем старый пост пользователя если есть
        cursor.execute('DELETE FROM posts WHERE user_id = ?', (user_id,))
        cursor.execute('''
        INSERT INTO posts (user_id, text)
        VALUES (?, ?)
        ''', (user_id, text))
        self.conn.commit()

    def get_post(self, user_id: int) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id, text, created_at FROM posts WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if row:
            return {'user_id': row[0], 'text': row[1], 'created_at': row[2]}
        return None

    def get_posts_raw(self) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id, text, created_at FROM posts')
        return [{'user_id': row[0], 'text': row[1], 'created_at': row[2]} for row in cursor.fetchall()]

    def get_active_posts(self, max_age_seconds: int = 18000) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute('''
        SELECT user_id, text, created_at 
        FROM posts 
        WHERE datetime(created_at) > datetime('now', ?)
        ''', (f'-{max_age_seconds} seconds',))
        return [{'user_id': row[0], 'text': row[1], 'created_at': row[2]} for row in cursor.fetchall()]

    def delete_post(self, user_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM posts WHERE user_id = ?', (user_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def delete_old_posts(self, older_than_seconds: int = 18000) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
        DELETE FROM posts 
        WHERE datetime(created_at) <= datetime('now', ?)
        ''', (f'-{older_than_seconds} seconds',))
        self.conn.commit()
        return cursor.rowcount

    def create_chat(self, user1_id: int, user2_id: int):
        cursor = self.conn.cursor()
        cursor.execute('''
        INSERT INTO chats (user1_id, user2_id)
        VALUES (?, ?)
        ''', (user1_id, user2_id))
        self.conn.commit()

    def get_active_chat_partner(self, user_id: int) -> Optional[int]:
        cursor = self.conn.cursor()
        cursor.execute('''
        SELECT user1_id, user2_id FROM chats 
        WHERE user1_id = ? OR user2_id = ?
        ''', (user_id, user_id))
        row = cursor.fetchone()
        if row:
            return row[1] if row[0] == user_id else row[0]
        return None

    def end_chat(self, user_id: int):
        cursor = self.conn.cursor()
        cursor.execute('''
        DELETE FROM chats 
        WHERE user1_id = ? OR user2_id = ?
        ''', (user_id, user_id))
        self.conn.commit()

    def count_active_chats(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM chats')
        return cursor.fetchone()[0]

    def get_all_users(self) -> List[int]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id FROM users')
        return [row[0] for row in cursor.fetchall()]

    def count_posts_since(self, seconds: int) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
        SELECT COUNT(*) FROM posts 
        WHERE datetime(created_at) > datetime('now', ?)
        ''', (f'-{seconds} seconds',))
        return cursor.fetchone()[0]

    def clear_message_mirror_between(user1_id, user2_id):
        conn = sqlite3.connect("database.db")
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM message_mirror 
            WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)
        """, (user1_id, user2_id, user2_id, user1_id))
        conn.commit()
        conn.close()
    def save_message_mirror(self, sender_id, receiver_id, sender_message_id, receiver_message_id):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO message_mirror
            (sender_id, receiver_id, sender_message_id, receiver_message_id)
            VALUES (?, ?, ?, ?)
            """,
            (sender_id, receiver_id, sender_message_id, receiver_message_id)
        )
        self.conn.commit()

    def get_mirrored_message_id(self, receiver_id, sender_message_id):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT receiver_message_id
            FROM message_mirror
            WHERE receiver_id = ? AND sender_message_id = ?
            """,
            (receiver_id, sender_message_id)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def set_subscription(self, user_id: int, months: int = 0, permanent: bool = False):
        import time

        now = int(time.time())
        if permanent:
            expires_at = now + 100 * 365 * 24 * 3600  # фактически "навсегда"
        else:
            expires_at = now + months * 30 * 24 * 3600
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO subscriptions (user_id, expires_at, permanent)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET expires_at=?, permanent=?;
        """, (user_id, expires_at, int(permanent), expires_at, int(permanent)))
        self.conn.commit()

    def has_active_subscription(self, user_id: int):
        import time
        now = int(time.time())
        cursor = self.conn.cursor()
        res = cursor.execute("""
            SELECT expires_at, permanent FROM subscriptions WHERE user_id=?
        """, (user_id,)).fetchone()
        if not res:
            return False
        expires_at, permanent = res
        if permanent:
            return True
        return expires_at > now