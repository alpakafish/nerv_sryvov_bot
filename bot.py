import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from database import (
    init_db, register_user, save_stress_message,
    get_today_stresses, get_month_stresses, get_total_stresses,
    get_month_statistics, get_next_today_number
)

from config import BOT_TOKEN
from datetime import datetime
import calendar
import pytz
from config import TIMEZONE

import requests
from bs4 import BeautifulSoup
import random

# --- Конфигурация для парсинга новостей ---
NEWS_URL = "https://naked-science.ru/?yandex_feed=news"
NEWS_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Создаем бота и диспетчер
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Определяем состояния для FSM
class StressState(StatesGroup):
    waiting_for_reason = State()  # Ждем текст причины срыва


# --- Класс для хранения колоды заголовков для каждого пользователя ---
class UserNewsSession:
    def __init__(self, all_titles=None, remaining_titles=None):
        if all_titles is None:
            self.all_titles = []
            self.remaining_titles = []
        else:
            self.all_titles = all_titles
            self.remaining_titles = remaining_titles if remaining_titles is not None else all_titles.copy()

        if self.remaining_titles:
            random.shuffle(self.remaining_titles)

    def to_dict(self):
        return {
            'all_titles': self.all_titles,
            'remaining_titles': self.remaining_titles
        }

    def refresh_pool(self, new_titles):
        self.all_titles = list(dict.fromkeys(new_titles))
        self.remaining_titles = self.all_titles.copy()
        random.shuffle(self.remaining_titles)
        print(f"Пул обновлен. Всего заголовков: {len(self.all_titles)}")

    def has_titles(self):
        return len(self.remaining_titles) > 0

    def get_random_title(self):
        if self.has_titles():
            return self.remaining_titles.pop()
        return None


# Создаем клавиатуру меню
def get_main_keyboard():
    buttons = [
        [KeyboardButton(text="😫 Причина нервного срыва")],
        [KeyboardButton(text="📆 Срывы за сегодня")],
        [KeyboardButton(text="📅 Срывы за месяц")],
        [KeyboardButton(text="📊 Всего срывов")],
        [KeyboardButton(text="📈 Статистика месяца")],
        [KeyboardButton(text="🎲 Случайный срыв")]
    ]
    keyboard = ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard


# --- Функция парсинга заголовков с повторными попытками ---
def fetch_titles_from_page(retries=2) -> list:
    """Загружает страницу и извлекает все заголовки из тегов <h1> с повторными попытками"""
    for attempt in range(retries + 1):
        try:
            response = requests.get(NEWS_URL, headers=NEWS_HEADERS, timeout=15)
            response.raise_for_status()
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            h1_tags = soup.find_all('h1')
            titles = [h1.get_text(strip=True) for h1 in h1_tags if h1.get_text(strip=True)]
            unique_titles = list(dict.fromkeys(titles))
            print(f"Успешно получено {len(unique_titles)} уникальных заголовков")
            return unique_titles
        except Exception as e:
            print(f"Попытка {attempt + 1} из {retries + 1} не удалась: {e}")
            if attempt == retries:
                return []
            asyncio.sleep(2)  # Ждем перед повторной попыткой
    return []


# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Регистрируем пользователя
    user = message.from_user
    await register_user(
        user.id,
        user.username,
        user.first_name,
        user.last_name
    )

    await message.answer(
        f"Привет, {user.first_name}! 👋\n\n"
        f"Я бот для отслеживания нервных срывов.\n"
        f"Выбери действие в меню:",
        reply_markup=get_main_keyboard()
    )


# Обработчик кнопки "Причина нервного срыва"
@dp.message(lambda message: message.text == "😫 Причина нервного срыва")
async def add_stress(message: types.Message, state: FSMContext):
    # Получаем следующий номер за сегодня
    next_number = await get_next_today_number(message.from_user.id)
    await state.set_state(StressState.waiting_for_reason)
    await message.answer(
        f"📝 Напиши, что вывело тебя из себя.\n"
        f"Это будет твой срыв #{next_number} за сегодня.",
        reply_markup=types.ReplyKeyboardRemove()  # Убираем меню на время ввода
    )


# Обработчик текста причины срыва
@dp.message(StressState.waiting_for_reason)
async def process_stress_reason(message: types.Message, state: FSMContext):
    if not message.text or len(message.text.strip()) == 0:
        await message.answer("Пожалуйста, напиши текст причины.")
        return

    reason_text = message.text.strip()
    user_id = message.from_user.id

    # Сохраняем в базу данных
    await save_stress_message(user_id, reason_text)

    # Получаем номер сообщения
    number = await get_next_today_number(user_id)

    await state.clear()  # Очищаем состояние
    await message.answer(
        f"✅ Срыв #{number - 1} за сегодня сохранен!\n\n"
        f"Твой текст: {reason_text}\n\n"
        f"Вернуться в меню: /start",
        reply_markup=get_main_keyboard()
    )


# Обработчик кнопки "Срывы за сегодня"
@dp.message(lambda message: message.text == "📆 Срывы за сегодня")
async def show_today_stresses(message: types.Message):
    stresses = await get_today_stresses(message.from_user.id)

    if not stresses:
        await message.answer(
            "🎉 Вау, спокойный день! Сегодня без срывов.",
            reply_markup=get_main_keyboard()
        )
        return

    # Формируем ответ
    response = "📆 Твои срывы за сегодня:\n\n"
    for i, stress in enumerate(stresses, 1):
        created_at = stress['created_at']
        if isinstance(created_at, datetime):
            time_str = created_at.strftime("%H:%M")
        else:
            # Более безопасное преобразование
            time_str = str(created_at)[:16] if created_at else "время неизвестно"
        response += f"{i}. {stress['message_text']} ({time_str})\n"

    await message.answer(response, reply_markup=get_main_keyboard())


# Обработчик кнопки "Срывы за месяц"
@dp.message(lambda message: message.text == "📅 Срывы за месяц")
async def show_month_stresses(message: types.Message):
    stresses = await get_month_stresses(message.from_user.id)

    if not stresses:
        tz = pytz.timezone(TIMEZONE)
        now = datetime.now(tz)
        month_name = now.strftime("%B")
        # Переводим название месяца на русский
        months_ru = {
            "January": "Январь", "February": "Февраль", "March": "Март", "April": "Апрель",
            "May": "Май", "June": "Июнь", "July": "Июль", "August": "Август",
            "September": "Сентябрь", "October": "Октябрь", "November": "Ноябрь", "December": "Декабрь"
        }
        month_name_ru = months_ru.get(month_name, month_name)
        await message.answer(
            f"📅 За {month_name_ru} у тебя не было срывов. Отлично!",
            reply_markup=get_main_keyboard()
        )
        return

    # Формируем ответ (показываем последние 20, чтобы не перегружать)
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    months_ru = {
        "January": "Январь", "February": "Февраль", "March": "Март", "April": "Апрель",
        "May": "Май", "June": "Июнь", "July": "Июль", "August": "Август",
        "September": "Сентябрь", "October": "Октябрь", "November": "Ноябрь", "December": "Декабрь"
    }
    month_name_ru = months_ru.get(now.strftime("%B"), now.strftime("%B"))

    response = f"📅 Твои срывы за {month_name_ru} {now.year}:\n\n"
    for i, stress in enumerate(stresses[-20:], 1):
        created_at = stress['created_at']
        if isinstance(created_at, datetime):
            date_str = created_at.strftime("%d.%m %H:%M")
        else:
            date_str = str(created_at)[:16] if created_at else "дата неизвестна"
        response += f"{i}. {stress['message_text']} ({date_str})\n"

    if len(stresses) > 20:
        response += f"\nВсего срывов за месяц: {len(stresses)}"

    await message.answer(response, reply_markup=get_main_keyboard())


# Обработчик кнопки "Всего срывов"
@dp.message(lambda message: message.text == "📊 Всего срывов")
async def show_total_stresses(message: types.Message):
    total = await get_total_stresses(message.from_user.id)

    if total == 0:
        await message.answer(
            "🌟 Ты еще ни разу не сообщал о срывах. Продолжай в том же духе!",
            reply_markup=get_main_keyboard()
        )
    elif total == 1:
        await message.answer(
            f"📊 За все время у тебя был {total} срыв.",
            reply_markup=get_main_keyboard()
        )
    elif 2 <= total <= 4:
        await message.answer(
            f"📊 За все время у тебя было {total} срыва.",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(
            f"📊 За все время у тебя было {total} срывов.",
            reply_markup=get_main_keyboard()
        )


# Обработчик кнопки "Статистика месяца"
@dp.message(lambda message: message.text == "📈 Статистика месяца")
async def show_month_stats(message: types.Message):
    stats = await get_month_statistics(message.from_user.id)

    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    year = now.year
    month = now.month

    # Получаем количество дней в месяце
    days_in_month = calendar.monthrange(year, month)[1]

    # Русские названия месяцев
    months_ru = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
    }
    month_name_ru = months_ru[month]

    # Формируем статистику в простом текстовом формате
    response = f"📈 Статистика за {month_name_ru} {year}:\n\n"

    # Собираем строки с днями, где есть срывы
    days_with_stresses = []
    for day in range(1, days_in_month + 1):
        count = stats.get(day, 0)
        if count > 0:
            # Визуализация (максимум 10 эмодзи)
            angry_face = "🤬"
            bars = angry_face * min(count, 10)
            days_with_stresses.append(f"• {day:2d}.{month:02d} — {count} {bars}")

    if days_with_stresses:
        response += "\n".join(days_with_stresses)
    else:
        response += "✨ В этом месяце не было ни одного срыва! ✨"

    # Добавляем итог
    total_month = sum(stats.values())
    if total_month > 0:
        response += f"\n\n📊 Всего за месяц: {total_month}"

    await message.answer(response, reply_markup=get_main_keyboard())


# Обработчик непонятных сообщений
@dp.message()
async def handle_unknown(message: types.Message):
    # Временная отладка
    print(f"DEBUG: Получен неизвестный текст: '{message.text}'")
    await message.answer(
        "Пожалуйста, используй кнопки меню. Если меню пропало, нажми /start",
        reply_markup=get_main_keyboard()
    )


# Обработчик кнопки "Случайный срыв" (ИСПРАВЛЕННЫЙ)
@dp.message(lambda message: message.text == "🎲 Случайный срыв")
async def random_news_stress(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = await state.get_data()

    # Правильное восстановление сессии
    session_data = user_data.get('news_session')
    if session_data and isinstance(session_data, dict):
        session = UserNewsSession(
            all_titles=session_data.get('all_titles', []),
            remaining_titles=session_data.get('remaining_titles', [])
        )
    else:
        session = UserNewsSession()

    if not session.has_titles():
        await message.answer("🔄 Загружаю свежие научные новости с Naked Science...")
        fresh_titles = await asyncio.to_thread(fetch_titles_from_page)  # Запускаем в отдельном потоке

        if not fresh_titles:
            await message.answer(
                "⚠️ Не удалось загрузить свежие научные новости.\n"
                "Попробуй позже или нажми кнопку снова.",
                reply_markup=get_main_keyboard()
            )
            return

        session.refresh_pool(fresh_titles)

    if session.has_titles():
        random_title = session.get_random_title()
        # Сохраняем обновленную сессию
        await state.update_data(news_session=session.to_dict())

        response = (
            f"🧠 *Случайный научный нервный срыв от Скелетора:*\n\n"
            f"{random_title}\n\n"
            f"🎲 Нажми снова, чтобы получить другую причину.\n"
            f"_Осталось новостей: {len(session.remaining_titles)}_"
        )
        await message.answer(response, parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        await message.answer(
            "⚡️ *Причины на сегодня закончились!*\n\n"
            "Скелетор вернется позже с другими причинами для нервного срыва.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )


# Функция для запуска Flask сервера
def run_flask():
    from flask import Flask
    import os

    flask_app = Flask(__name__)

    @flask_app.route('/')
    def hello():
        return "Bot is running!"

    @flask_app.route('/health')
    def health():
        return "OK"

    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)


# Запуск бота
async def main():
    # Инициализируем базу данных
    await init_db()
    print("✅ Бот запущен и готов к работе!")
    print(f"📁 База данных: PostgreSQL на Render")
    print(f"🕐 Временная зона сервера: {TIMEZONE}")

    # Запускаем бота
    await dp.start_polling(bot)


if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке только если не на локальной разработке
    import sys

    if '--no-flask' not in sys.argv:
        import threading

        threading.Thread(target=run_flask, daemon=True).start()

    asyncio.run(main())