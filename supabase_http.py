import os
import requests
import logging

logger = logging.getLogger(__name__)

class SupabaseHTTPClient:
    def __init__(self):
        self.url = os.getenv('SUPABASE_URL')
        self.key = os.getenv('SUPABASE_KEY')
        if not self.url or not self.key:
            raise ValueError("Supabase URL and KEY must be set in environment variables")
        
        self.headers = {
            'apikey': self.key,
            'Authorization': f'Bearer {self.key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }
        self.base_url = f"{self.url}/rest/v1"
    
    def _make_request(self, method, endpoint, data=None):
        """Универсальный метод для HTTP запросов"""
        url = f"{self.base_url}/{endpoint}"
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=self.headers, params=data)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=self.headers, json=data)
            elif method.upper() == 'PUT':
                response = requests.put(url, headers=self.headers, json=data)
            elif method.upper() == 'PATCH':
                response = requests.patch(url, headers=self.headers, json=data)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, headers=self.headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json() if response.content else None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP {method} request failed: {e}")
            raise
    
    def save_website_credentials(self, telegram_id: int, login: str, password: str, subscription_type: str = 'free'):
        """Сохраняет логин и пароль в Supabase"""
        try:
            # Сначала проверяем существующую запись
            existing = self._make_request('GET', 'website_users', {
                'telegram_id': f'eq.{telegram_id}',
                'select': 'id'
            })
            
            data = {
                'telegram_id': telegram_id,
                'login': login,
                'password': password,
                'is_active': True,
                'subscription_type': subscription_type
            }
            
            if existing and len(existing) > 0:
                # Обновляем существующую запись
                result = self._make_request('PATCH', f'website_users?telegram_id=eq.{telegram_id}', data)
            else:
                # Создаем новую запись
                result = self._make_request('POST', 'website_users', data)
            
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Error saving credentials to Supabase: {e}")
            raise
    
    def get_website_credentials(self, telegram_id: int):
        """Получает логин и пароль из Supabase"""
        try:
            result = self._make_request('GET', 'website_users', {
                'telegram_id': f'eq.{telegram_id}',
                'select': 'login,password,subscription_type,is_active'
            })
            
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Error getting credentials from Supabase: {e}")
            return None
    
    def user_exists(self, telegram_id: int) -> bool:
        """Проверяет, существует ли пользователь в Supabase"""
        try:
            result = self._make_request('GET', 'website_users', {
                'telegram_id': f'eq.{telegram_id}',
                'select': 'id'
            })
            
            return len(result) > 0 if result else False
            
        except Exception as e:
            logger.error(f"Error checking user in Supabase: {e}")
            return False

# Глобальный клиент Supabase
supabase = SupabaseHTTPClient()