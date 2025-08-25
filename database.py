# database.py
import os
from urllib.parse import urlparse
import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta

class Database:
    def __init__(self):
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("DATABASE_URL is not set")

        # Разбираем URL через urlparse (поддерживает разные форматы)
        parsed = urlparse(db_url)
        user = parsed.username
        password = parsed.password
        host = parsed.hostname
        port = parsed.port or 3306
        database = parsed.path.lstrip("/")

        self.conn = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port,
            autocommit=False
        )
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username VARCHAR(255),
            full_name VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB;
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            user_id BIGINT PRIMARY KEY,
            text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
        """)
        cursor.execute("""
                    CREATE TABLE IF NOT EXISTS chats (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user1_id BIGINT NOT NULL,
                        user2_id BIGINT NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user1_id) REFERENCES users(user_id),
                        FOREIGN KEY (user2_id) REFERENCES users(user_id)
                    )
                """)
        self.conn.commit()
        cursor.close()

    # --- users ---
    def add_user(self, user_id: int, username: str, full_name: str):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, full_name)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE username = VALUES(username), full_name = VALUES(full_name)
        """, (user_id, username, full_name))
        self.conn.commit()
        cursor.close()

    def get_all_users(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        rows = cursor.fetchall()
        cursor.close()
        return [r[0] for r in rows]

    # --- posts ---
    def add_post(self, user_id: int, text: str):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO posts (user_id, text)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE text = VALUES(text), created_at = CURRENT_TIMESTAMP
        """, (user_id, text))
        self.conn.commit()
        cursor.close()

    def delete_post(self, user_id: int):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM posts WHERE user_id = %s", (user_id,))
        deleted = cursor.rowcount
        self.conn.commit()
        cursor.close()
        return deleted

    def get_post(self, user_id: int):
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id, text, created_at FROM posts WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        cursor.close()
        return row

    def get_active_posts(self, max_age_seconds: int = 5 * 3600):
        """
        Возвращает посты, младше max_age_seconds
        """
        cutoff = datetime.utcnow() - timedelta(seconds=max_age_seconds)
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id, text, created_at FROM posts WHERE created_at >= %s", (cutoff,))
        rows = cursor.fetchall()
        cursor.close()
        return rows

    def delete_old_posts(self, older_than_seconds: int = 5 * 3600):
        cutoff = datetime.utcnow() - timedelta(seconds=older_than_seconds)
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM posts WHERE created_at < %s", (cutoff,))
        deleted = cursor.rowcount
        self.conn.commit()
        cursor.close()
        return deleted

    def count_posts_since(self, seconds: int):
        cutoff = datetime.utcnow() - timedelta(seconds=seconds)
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM posts WHERE created_at >= %s", (cutoff,))
        cnt = cursor.fetchone()[0]
        cursor.close()
        return cnt

    def get_posts_raw(self):
        """Возвращает все посты (dictionary) — полезно для админов"""
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id, text, created_at FROM posts")
        rows = cursor.fetchall()
        cursor.close()
        return rows

        # ---------- CHATS ----------

    def create_chat(self, user1_id: int, user2_id: int):
        cursor = self.conn.cursor()
        cursor.execute("""
               INSERT INTO chats (user1_id, user2_id, is_active)
               VALUES (%s, %s, TRUE)
           """, (user1_id, user2_id))
        self.conn.commit()
        chat_id = cursor.lastrowid
        cursor.close()
        return chat_id

    def end_chat(self, user_id: int):
        """Закрыть чат по участнику"""
        cursor = self.conn.cursor()
        cursor.execute("""
               UPDATE chats
               SET is_active = FALSE
               WHERE (user1_id = %s OR user2_id = %s) AND is_active = TRUE
           """, (user_id, user_id))
        self.conn.commit()
        cursor.close()

    def get_active_chat_partner(self, user_id: int):
        """Вернуть айди собеседника, если пользователь в активном чате"""
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute("""
               SELECT user1_id, user2_id
               FROM chats
               WHERE (user1_id = %s OR user2_id = %s) AND is_active = TRUE
               LIMIT 1
           """, (user_id, user_id))
        chat = cursor.fetchone()
        cursor.close()
        if chat:
            return chat["user2_id"] if chat["user1_id"] == user_id else chat["user1_id"]
        return None

    def count_active_chats(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chats WHERE is_active = TRUE")
        count = cursor.fetchone()[0]
        cursor.close()
        return count

    def close(self):
        try:
            self.conn.close()
        except:
            pass
