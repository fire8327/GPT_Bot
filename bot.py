import os
import asyncio
import requests
import secrets
import string
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv
from db import Database
from supabase_http import supabase

load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPEN_ROUTER_API_KEY = os.getenv('OPEN_ROUTER_API_KEY')
WEBSITE_URL = os.getenv('WEBSITE_URL', 'https://ai83274.vercel.app/')

db = Database()
AI_MODEL = "openai/gpt-4o-mini"
MAX_DIALOGS = 5

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("💬 Продолжить диалог")],
        [KeyboardButton("🌐 Доступ к сайту"), KeyboardButton("🔄 Новый диалог")],
        [KeyboardButton("👀 Мои диалоги"), KeyboardButton("❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_system_prompt() -> str:
    return """
ВСЕГДА соблюдай эти правила форматирования:
1. НЕ используй Markdown разметку (**жирный**, *курсив*, ### заголовки)
2. НЕ используй эмодзи в основном тексте ответа
3. Используй только простые символы для структуры: -, •, цифры
4. Разделяй длинные ответы на логические блоки
5. Форматируй так, чтобы текст можно было легко копировать в Word
6. Используй пустые строки между абзацами
7. Если нужны заголовки - пиши их с новой строки без специальных символов

Отвечай на русском языке.

Ты - умный и полезный помощник. Отвечай на вопросы, помогай с учебой, работой, творчеством и любыми другими задачами. Будь дружелюбным и профессиональным.
"""

def generate_credentials():
    """Генерирует логин и пароль для сайта"""
    login_suffix = ''.join(secrets.choice(string.digits) for _ in range(6))
    login = f"user_{login_suffix}"
    
    alphabet = string.ascii_letters + string.digits
    password = ''.join(secrets.choice(alphabet) for _ in range(8))
    
    return login, password

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = user.id
    db.save_user(user_id, user.username, user.first_name)
    db.set_user_session(user_id, "general", 1)
    
    welcome_text = f"""
🤖 Привет, {user.first_name}!

Я твой умный помощник для общения, учебы и работы.

Просто напиши свой вопрос — и я помогу!

Что умею:
• Отвечать на любые вопросы
• Помогать с учебой и работой
• Создавать конспекты и объяснять сложное
• И многое другое!"""
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📋 Как пользоваться:

💬 Продолжить диалог - вернуться к текущему диалогу
🌐 Доступ к сайту - получить логин/пароль для сайта
🔄 Новый диалог - начать новую тему (до 5 параллельных диалогов)
👀 Мои диалоги - просмотреть и управлять диалогами

Просто напиши свой вопрос в любое время!

Команды:
/start — начать заново
/help — эта справка
    """
    await update.message.reply_text(help_text, reply_markup=get_main_keyboard())

async def website_access_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выдает доступ к сайту"""
    user = update.message.from_user
    user_id = user.id
    
    # Проверяем существующие credentials в Supabase
    existing_credentials = supabase.get_website_credentials(user_id)
    
    if existing_credentials:
        login = existing_credentials['login']
        password = existing_credentials['password']
        subscription_type = existing_credentials.get('subscription_type', 'free')
        is_active = existing_credentials.get('is_active', True)
    else:
        # Генерируем новые credentials
        login, password = generate_credentials()
        supabase.save_website_credentials(user_id, login, password, 'free')
        subscription_type = 'free'
        is_active = True
    
    # Форматируем сообщение с code блоками для легкого копирования
    access_text = f"""
🌐 Доступ к сайту

📍 Сайт: {WEBSITE_URL}
Логин: {login}
Пароль: {password}


📊 Статус: {'✅ Активен' if is_active else '❌ Неактивен'}
🎫 Тариф: {subscription_type}

⚠️ Не передавай логин и пароль другим людям.
"""

    await update.message.reply_text(access_text, reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("delete_dialog_"):
        dialog_id = int(data.split("_")[-1])
        db.delete_dialog(user_id, dialog_id)
        await query.edit_message_text(f"🗑 Диалог {dialog_id} удалён.")
        await asyncio.sleep(2)
        await show_all_dialogs(update, context, from_callback=True)
    elif data == "back_to_dialogs":
        await show_all_dialogs(update, context, from_callback=True)

async def show_all_dialogs(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user_id = update.callback_query.from_user.id if from_callback else update.message.from_user.id
    
    summaries = db.get_all_dialogs_summary(user_id)
    active_count = sum(1 for v in summaries.values() if v is not None)
    
    text = "📁 Ваши диалоги (макс. 5):\n\n"
    buttons = []
    
    for did in range(1, MAX_DIALOGS + 1):
        desc = summaries[did] or "Пусто"
        text += f"{did}. {desc}\n"
        if summaries[did]:
            buttons.append(InlineKeyboardButton(f"Удалить {did}", callback_data=f"delete_dialog_{did}"))
    
    if active_count >= MAX_DIALOGS:
        text += "\n⚠️ Достигнут лимит диалогов (5). Удалите ненужные, чтобы создать новые."
    
    if buttons:
        buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_dialogs"))
        reply_markup = InlineKeyboardMarkup([buttons[i:i+3] for i in range(0, len(buttons), 3)])
    else:
        reply_markup = None
    
    if from_callback:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    user = update.message.from_user
    user_id = user.id
    db.save_user(user_id, user.username, user.first_name)
    
    # Обработка специальных кнопок
    if user_message == "🔄 Новый диалог":
        current_mode, current_dialog = db.get_user_session(user_id)
        summaries = db.get_all_dialogs_summary(user_id)
        active_count = sum(1 for v in summaries.values() if v is not None)
        
        if active_count >= MAX_DIALOGS:
            await update.message.reply_text(
                "⚠️ У вас уже 5 активных диалогов. "
                "Сначала удалите ненужные через «👀 Мои диалоги».",
                reply_markup=get_main_keyboard()
            )
            return
        
        new_dialog_id = next((i for i in range(1, MAX_DIALOGS + 1) if summaries[i] is None), 1)
        db.set_user_session(user_id, "general", new_dialog_id)
        db.clear_conversation_history(user_id, new_dialog_id)
        await update.message.reply_text(
            f"🔄 Начат новый диалог №{new_dialog_id}! Пишите ваш запрос.",
            reply_markup=get_main_keyboard()
        )
        return

    elif user_message == "👀 Мои диалоги":
        await show_all_dialogs(update, context)
        return

    elif user_message == "🌐 Доступ к сайту":
        await website_access_command(update, context)
        return

    elif user_message == "❓ Помощь":
        await help_command(update, context)
        return

    elif user_message == "💬 Продолжить диалог":
        current_mode, current_dialog = db.get_user_session(user_id)
        await update.message.reply_text(
            f"💬 Продолжаем диалог №{current_dialog}. Пишите ваш запрос:",
            reply_markup=get_main_keyboard()
        )
        return

    # Обычное сообщение — отправка в AI
    current_mode, current_dialog = db.get_user_session(user_id)
    db.save_conversation(user_id, "user", user_message, "general", current_dialog)
    
    await update.message.chat.send_action(action="typing")
    thinking_msg = await update.message.reply_text("💭 Думаю...")
    
    system_prompt = get_system_prompt()
    history = db.get_conversation_history(user_id, current_dialog, limit=3)
    
    messages = [{"role": "system", "content": system_prompt}]
    for role, content, _ in history:
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    
    try:
        ai_response = await asyncio.get_event_loop().run_in_executor(
            None, lambda: query_openrouter_sync(messages, AI_MODEL)
        )
        await thinking_msg.delete()
        db.save_conversation(user_id, "assistant", ai_response, "general", current_dialog)
        
        if len(ai_response) > 4096:
            for i in range(0, len(ai_response), 4096):
                await update.message.reply_text(ai_response[i:i+4096], reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text(ai_response, reply_markup=get_main_keyboard())
            
    except Exception as e:
        await thinking_msg.delete()
        await update.message.reply_text(f"❌ Ошибка: {str(e)}", reply_markup=get_main_keyboard())

def query_openrouter_sync(messages: list, model: str = AI_MODEL) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPEN_ROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": messages,
        "max_tokens": 15000
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = response.json()
        if 'choices' in result and len(result['choices']) > 0:
            return result['choices'][0]['message']['content']
        else:
            return "Не удалось получить ответ от AI."
    except Exception as e:
        return f"Ошибка: {str(e)}"

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Update {update} caused error {context.error}")

def main():
    db.init_db()
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_error_handler(error_handler)
    
    print(f"Бот запущен с моделью {AI_MODEL}...")
    app.run_polling(poll_interval=3)

if __name__ == '__main__':
    main()