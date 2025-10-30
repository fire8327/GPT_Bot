import os
import asyncio
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv
from db import Database

load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPEN_ROUTER_API_KEY = os.getenv('OPEN_ROUTER_API_KEY')

db = Database()
AI_MODEL = "openai/gpt-4o-mini"
MAX_DIALOGS = 5

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("🎒 Школьный режим"), KeyboardButton("🎓 Универ/Колледж")],
        [KeyboardButton("💼 Рабочий режим"), KeyboardButton("💬 Свободный диалог")],
        [KeyboardButton("📚 Конспект"), KeyboardButton("🤔 Объяснить понятно")],
        [KeyboardButton("🔄 Новый диалог"), KeyboardButton("👀 Показать все диалоги")],
        [KeyboardButton("❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_system_prompt(mode: str) -> str:
    base_prompt = """
ВСЕГДА соблюдай эти правила форматирования:
1. НЕ используй Markdown разметку (**жирный**, *курсив*, ### заголовки)
2. НЕ используй эмодзи в основном тексте ответа
3. Используй только простые символы для структуры: -, •, цифры
4. Разделяй длинные ответы на логические блоки
5. Форматируй так, чтобы текст можно было легко копировать в Word
6. Используй пустые строки между абзацами
7. Если нужны заголовки - пиши их с новой строки без специальных символов

Отвечай на русском языке.
"""
    
    prompts = {
        "school": base_prompt + """
Ты - добрый и терпеливый репетитор для школьника.
Объясняй всё просто, пошагово, с примерами из жизни.

НЕ ИСПОЛЬЗУЙ и НЕ УПОМИНАЙ:
- тригонометрию, синусы/косинусы
- логарифмы, экспоненты
- дифференцирование, интегралы, производные

Если тема требует этих понятий - скажи, что это пока не входит в школьную программу.
Давай полные решения уравнений, а не только ответы.
""",
        
        "university": base_prompt + """
Ты - эксперт, помогающий студенту университета или колледжа.
Давай глубокие, структурированные объяснения.
Можешь использовать профессиональную терминологию, но поясняй её.
Помогай с анализом, академическим письмом, подготовкой к экзаменам.
Форматируй ответы как готовые академические тексты.
""",
        
        "work": base_prompt + """
Ты - профессиональный деловой ассистент.
Будь кратким, конкретным и практичным.
Помогай с письмами, анализом, планированием, презентациями.
Избегай жаргона, если он не уместен.
Форматируй ответы как готовые бизнес-документы.
""",
        
        "free": base_prompt + """
Ты - умный и дружелюбный собеседник.
Общайся естественно, отвечай на любые вопросы, помогай с творчеством.
""",
        
        "summary": base_prompt + """
Ты - мастер создания конспектов.
Преврати присланный текст в структурированный конспект:
- ключевые тезисы
- основные выводы  
- важные детали
Сделай информацию легко усваиваемой.
""",
        
        "explain": base_prompt + """
Ты - эксперт по объяснению сложного простыми словами.
Используй аналогии, примеры, пошаговые объяснения.
Проверяй, понятно ли объяснение.
"""
    }
    return prompts.get(mode, base_prompt)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = user.id
    db.save_user(user_id, user.username, user.first_name)
    db.set_user_session(user_id, "free", 1)
    
    welcome_text = f"""
🤖 Привет, {user.first_name}!

Я помогу с учёбой, работой или просто поболтаю.

Выбери режим и пиши свой запрос — всё готово!"""
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📋 **Как пользоваться:**

1. Выбери режим кнопкой:
   - 🎒 Школьный — без тригонометрии и логарифмов
   - 🎓 Универ/Колледж — для студентов
   - 💼 Работа — деловые задачи
   - 💬 Свободный — просто общаться
   - 📚 Конспект — сократить текст
   - 🤔 Объяснить — разжевать сложное

2. Напиши свой вопрос или текст.

3. Хочешь начать заново? Жми «🔄 Новый диалог».

4. У тебя до **5 параллельных диалогов**. 
   Жми «👀 Показать все диалоги», чтобы управлять ими.

Команды:
/start — начать заново
/help — эта справка
    """
    await update.message.reply_text(help_text, reply_markup=get_main_keyboard())

# Обработчик inline-кнопок для удаления диалогов
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("delete_dialog_"):
        dialog_id = int(data.split("_")[-1])
        db.delete_dialog(user_id, dialog_id)
        await query.edit_message_text(f"🗑 Диалог {dialog_id} удалён.")
        # Вернём пользователя к просмотру диалогов через 2 сек
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
        if summaries[did]:  # только если диалог не пустой
            buttons.append(InlineKeyboardButton(f"Удалить {did}", callback_data=f"delete_dialog_{did}"))
    
    if active_count >= MAX_DIALOGS:
        text += "\n⚠️ Достигнут лимит диалогов (5). Удалите ненужные, чтобы создать новые."
    
    # Добавим кнопку "Назад"
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
                "Сначала удалите ненужные через «👀 Показать все диалоги».",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Найдём первый свободный dialog_id
        new_dialog_id = next((i for i in range(1, MAX_DIALOGS + 1) if summaries[i] is None), 1)
        db.set_user_session(user_id, current_mode, new_dialog_id)
        db.clear_conversation_history(user_id, new_dialog_id)
        await update.message.reply_text(
            f"🔄 Начат новый диалог №{new_dialog_id}! Режим: {current_mode}. Пишите ваш запрос.",
            reply_markup=get_main_keyboard()
        )
        return

    elif user_message == "👀 Показать все диалоги":
        await show_all_dialogs(update, context)
        return

    elif user_message == "❓ Помощь":
        await help_command(update, context)
        return

    # Обработка выбора режима
    mode_map = {
        "🎒 Школьный режим": "school",
        "🎓 Универ/Колледж": "university",
        "💼 Рабочий режим": "work",
        "💬 Свободный диалог": "free",
        "📚 Конспект": "summary",
        "🤔 Объяснить понятно": "explain"
    }
    
    if user_message in mode_map:
        current_mode, current_dialog = db.get_user_session(user_id)
        new_mode = mode_map[user_message]
        db.set_user_session(user_id, new_mode, current_dialog)
        mode_names = {
            "school": "🎒 Школьный",
            "university": "🎓 Универ/Колледж",
            "work": "💼 Рабочий",
            "free": "💬 Свободный",
            "summary": "📚 Конспект",
            "explain": "🤔 Объяснить"
        }
        await update.message.reply_text(
            f"✅ Режим изменён на {mode_names[new_mode]}! Пишите ваш запрос.",
            reply_markup=get_main_keyboard()
        )
        return

    # Обычное сообщение — отправка в AI
    current_mode, current_dialog = db.get_user_session(user_id)
    db.save_conversation(user_id, "user", user_message, current_mode, current_dialog)
    
    await update.message.chat.send_action(action="typing")
    thinking_msg = await update.message.reply_text("💭 Думаю...")
    
    system_prompt = get_system_prompt(current_mode)
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
        db.save_conversation(user_id, "assistant", ai_response, current_mode, current_dialog)
        
        # Отправка длинных ответов частями
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