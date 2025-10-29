import os
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse
from contextlib import contextmanager

class Database:
    def __init__(self):
        self._init_connection_params()
        self.init_db()

    def _init_connection_params(self):
        """Извлекает параметры подключения из DATABASE_URL"""
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise ValueError("Переменная окружения DATABASE_URL не задана!")
        
        # Парсим URL вида: postgres://user:password@host:port/dbname
        result = urlparse(database_url)
        self.connection_params = {
            'dbname': result.path[1:],  # убираем первый '/'
            'user': result.username,
            'password': result.password,
            'host': result.hostname,
            'port': result.port or 5432,
            'sslmode': 'require'  # Railway требует SSL
        }

    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для безопасного подключения"""
        conn = None
        try:
            conn = psycopg2.connect(**self.connection_params)
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()

    def init_db(self):
        """Создаёт таблицы, если их нет"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Таблица диалогов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    dialog_id INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Индекс для ускорения поиска
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_conversations_user_dialog 
                ON conversations (user_id, dialog_id)
            ''')

            # Таблица сессий
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_sessions (
                    user_id BIGINT PRIMARY KEY,
                    mode TEXT DEFAULT 'free',
                    dialog_id INTEGER DEFAULT 1,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            conn.commit()

    def save_user(self, user_id, username, first_name):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET username = EXCLUDED.username, first_name = EXCLUDED.first_name
            ''', (user_id, username, first_name))
            conn.commit()

    def get_user_session(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT mode, dialog_id FROM user_sessions WHERE user_id = %s', (user_id,))
            result = cursor.fetchone()
            if result:
                return result[0], result[1]
            return 'free', 1

    def set_user_session(self, user_id, mode, dialog_id=1):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_sessions (user_id, mode, dialog_id, updated_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) DO UPDATE
                SET mode = EXCLUDED.mode, dialog_id = EXCLUDED.dialog_id, updated_at = CURRENT_TIMESTAMP
            ''', (user_id, mode, dialog_id))
            conn.commit()

    def save_conversation(self, user_id, role, content, mode, dialog_id=1):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO conversations (user_id, role, content, mode, dialog_id)
                VALUES (%s, %s, %s, %s, %s)
            ''', (user_id, role, content, mode, dialog_id))
            conn.commit()

    def get_conversation_history(self, user_id, dialog_id=1, limit=6):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT role, content, mode FROM conversations
                WHERE user_id = %s AND dialog_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            ''', (user_id, dialog_id, limit))
            history = cursor.fetchall()
            return list(reversed(history))

    def clear_conversation_history(self, user_id, dialog_id=1):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM conversations WHERE user_id = %s AND dialog_id = %s', (user_id, dialog_id))
            conn.commit()

    def get_all_dialogs_summary(self, user_id):
        summaries = {}
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for did in range(1, 6):
                cursor.execute('''
                    SELECT content, mode FROM conversations
                    WHERE user_id = %s AND dialog_id = %s AND role = 'user'
                    ORDER BY created_at DESC LIMIT 1
                ''', (user_id, did))
                res = cursor.fetchone()
                if res:
                    mode_emoji = {
                        'school': '🎒',
                        'university': '🎓',
                        'work': '💼',
                        'free': '💬',
                        'summary': '📚',
                        'explain': '🤔'
                    }.get(res[1], '❓')
                    preview = res[0][:40] + '...' if len(res[0]) > 40 else res[0]
                    summaries[did] = f"{mode_emoji} {preview}"
                else:
                    summaries[did] = None
        return summaries

    def delete_dialog(self, user_id, dialog_id):
        if dialog_id not in range(1, 6):
            return
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM conversations WHERE user_id = %s AND dialog_id = %s', (user_id, dialog_id))
            conn.commit()