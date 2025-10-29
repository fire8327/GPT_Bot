import sqlite3
from datetime import datetime

class Database:
    def __init__(self, db_path='bot_database.db'):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)
    
    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица диалогов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                content TEXT,
                mode TEXT,
                dialog_id INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Добавим dialog_id, если таблица старая
        cursor.execute("PRAGMA table_info(conversations)")
        columns = [col[1] for col in cursor.fetchall()]
        if "dialog_id" not in columns:
            cursor.execute("ALTER TABLE conversations ADD COLUMN dialog_id INTEGER DEFAULT 1")
        
        # Таблица сессий (режим + текущий диалог)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                user_id INTEGER PRIMARY KEY,
                mode TEXT DEFAULT 'free',
                dialog_id INTEGER DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_user(self, user_id, username, first_name):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, username, first_name) 
            VALUES (?, ?, ?)
        ''', (user_id, username, first_name))
        conn.commit()
        conn.close()
    
    def get_user_session(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT mode, dialog_id FROM user_sessions WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        if result:
            return result[0], result[1]
        return 'free', 1
    
    def set_user_session(self, user_id, mode, dialog_id=1):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO user_sessions (user_id, mode, dialog_id, updated_at) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, mode, dialog_id))
        conn.commit()
        conn.close()
    
    def save_conversation(self, user_id, role, content, mode, dialog_id=1):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO conversations (user_id, role, content, mode, dialog_id) 
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, role, content, mode, dialog_id))
        conn.commit()
        conn.close()
    
    def get_conversation_history(self, user_id, dialog_id=1, limit=6):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT role, content, mode FROM conversations 
            WHERE user_id = ? AND dialog_id = ?
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (user_id, dialog_id, limit))
        history = cursor.fetchall()
        conn.close()
        return list(reversed(history))
    
    def clear_conversation_history(self, user_id, dialog_id=1):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM conversations WHERE user_id = ? AND dialog_id = ?', (user_id, dialog_id))
        conn.commit()
        conn.close()
    
    def get_all_dialogs_summary(self, user_id):
        """Возвращает словарь: dialog_id -> краткое описание последнего запроса"""
        conn = self.get_connection()
        cursor = conn.cursor()
        summaries = {}
        for did in range(1, 6):  # диалоги 1–5
            cursor.execute('''
                SELECT content, mode, created_at FROM conversations 
                WHERE user_id = ? AND dialog_id = ? AND role = 'user'
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
                summaries[did] = None  # диалог пуст
        conn.close()
        return summaries

    def count_active_dialogs(self, user_id):
        """Считает, сколько диалогов содержат хотя бы одно сообщение"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(DISTINCT dialog_id) FROM conversations 
            WHERE user_id = ? AND dialog_id BETWEEN 1 AND 5
        ''')
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def delete_dialog(self, user_id, dialog_id):
        """Удаляет все сообщения в указанном диалоге"""
        if dialog_id not in range(1, 6):
            return
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM conversations WHERE user_id = ? AND dialog_id = ?', (user_id, dialog_id))
        conn.commit()
        conn.close()