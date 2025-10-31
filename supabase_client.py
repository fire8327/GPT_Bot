import os
from supabase import create_client, Client
import logging

logger = logging.getLogger(__name__)

class SupabaseClient:
    def __init__(self):
        self.url = os.getenv('SUPABASE_URL')
        self.key = os.getenv('SUPABASE_KEY')
        if not self.url or not self.key:
            raise ValueError("Supabase URL and KEY must be set in environment variables")
        
        try:
            self.client: Client = create_client(self.url, self.key)
            logger.info("Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Supabase client: {e}")
            raise
    
    def save_website_credentials(self, telegram_id: int, login: str, password: str, subscription_type: str = 'free'):
        """Сохраняет логин и пароль в Supabase"""
        try:
            data = {
                'telegram_id': telegram_id,
                'login': login,
                'password': password,
                'is_active': True,
                'subscription_type': subscription_type
            }
            
            # Проверяем существующую запись
            existing = self.client.table('website_users')\
                .select('id')\
                .eq('telegram_id', telegram_id)\
                .execute()
            
            if existing.data:
                # Обновляем существующую запись
                result = self.client.table('website_users')\
                    .update({
                        'login': login,
                        'password': password,
                        'subscription_type': subscription_type,
                        'is_active': True
                    })\
                    .eq('telegram_id', telegram_id)\
                    .execute()
            else:
                # Создаем новую запись
                result = self.client.table('website_users')\
                    .insert(data)\
                    .execute()
            
            return result.data[0] if result.data else None
            
        except Exception as e:
            logger.error(f"Error saving credentials to Supabase: {e}")
            raise
    
    def get_website_credentials(self, telegram_id: int):
        """Получает логин и пароль из Supabase"""
        try:
            result = self.client.table('website_users')\
                .select('login, password, subscription_type, is_active')\
                .eq('telegram_id', telegram_id)\
                .execute()
            
            return result.data[0] if result.data else None
            
        except Exception as e:
            logger.error(f"Error getting credentials from Supabase: {e}")
            return None
    
    def user_exists(self, telegram_id: int) -> bool:
        """Проверяет, существует ли пользователь в Supabase"""
        try:
            result = self.client.table('website_users')\
                .select('id')\
                .eq('telegram_id', telegram_id)\
                .execute()
            
            return len(result.data) > 0
            
        except Exception as e:
            logger.error(f"Error checking user in Supabase: {e}")
            return False

# Глобальный клиент Supabase
supabase = SupabaseClient()